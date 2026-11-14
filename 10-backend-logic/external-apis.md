---
description: "HTTP clients, timeouts, retries, and error mapping."
---

# Consuming external APIs

Calling another system from Odoo fails in ways local code never does: the connection hangs, the server answers 502, the token expired an hour ago, the rate limit kicks in. This chapter is the client layer that survives those, built on `requests`, which Odoo already ships.

## One client class per remote system

Keep HTTP details out of business models. A small client owns the session, base URL, authentication, timeouts and error translation:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TIMEOUT = (3.05, 20)  # connect, read


class CatalogueError(Exception):
    def __init__(self, message, status=None, retryable=False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class CatalogueClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        retry = Retry(
            total=3, backoff_factor=0.5,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset({"GET", "PUT", "DELETE"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def request(self, method, path, **kwargs):
        try:
            resp = self.session.request(
                method, f"{self.base_url}{path}", timeout=TIMEOUT, **kwargs
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise CatalogueError(str(exc), retryable=True) from exc
        if resp.status_code >= 500 or resp.status_code == 429:
            raise CatalogueError(resp.text[:200], resp.status_code, retryable=True)
        if resp.status_code >= 400:
            raise CatalogueError(resp.text[:200], resp.status_code)
        return resp.json() if resp.content else None
```

## Timeouts are mandatory

`requests` has no default timeout. A call without `timeout=` can block a worker indefinitely, and Odoo's own worker limits then kill the whole process mid-request. Always pass a tuple: a short connect timeout (a few seconds) and a read timeout sized to the slowest legitimate response. The timeout applies to each socket operation, not to the whole call, so a server that trickles bytes can still exceed it. Keep payloads small and paginate to bound total time.

## Retries: what is safe

Retry only what is idempotent. `GET`, `PUT` and `DELETE` are by definition; `POST` is not, unless the remote supports an idempotency key. Send one and `POST` becomes retryable:

```python
headers = {"Idempotency-Key": f"library.loan-{loan.id}-{loan.write_date:%Y%m%d%H%M%S}"}
```

Two levels of retry coexist. The `urllib3` `Retry` above handles brief network hiccups inside one call, with exponential backoff (`backoff_factor * 2 ** n` seconds). The queue handles long outages across cron runs (see Queues and background work). Do not stack long sleeps in the first level: a `time.sleep` inside a web request holds a worker.

## Classify errors

Decide per status code, once, in the client:

| Outcome | Action |
| --- | --- |
| Network error, timeout, 429, 5xx | retryable, back off |
| 401 | refresh the token once, retry, then fail |
| 400, 404, 409, 422 | permanent: record the message, no retry |
| 2xx with an unexpected body | treat as failure, log a body prefix |

Callers branch on `exc.retryable` and never inspect status codes themselves.

## Credentials and configuration

Keep base URL and token in `ir.config_parameter` or a configuration record with restricted access, never in source or in a view everyone can read. Read them with `sudo()` inside a factory method and never log them. When a log line must show a request, log method, path and status, not headers or body.

```python
def _get_client(self):
    icp = self.env["ir.config_parameter"].sudo()
    return CatalogueClient(
        icp.get_param("library_sync.base_url"),
        icp.get_param("library_sync.token"),
    )
```

## Outside the transaction

An HTTP call is not part of the database transaction. If the remote call succeeds and your transaction rolls back, the remote keeps the change. If you write locally and the remote call fails, the local record says something false. Two rules follow:

1. Write locally first, enqueue the remote call, and perform it after commit (in a cron, or through `self.env.cr.postcommit.add(func)`).
2. Store the remote id and sync state on the local record as soon as the call returns, in the same commit.

## Pagination and volume

Never fetch "all". Follow the remote's cursor or page parameter, process each page, and commit between pages. Keep the cursor in a record (a `last_synced` timestamp or a page token) so a crashed run resumes instead of restarting.

## Pitfalls

* Missing `timeout`. The most common cause of workers stuck for minutes.
* `verify=False` to silence a certificate error. Fix the chain or supply a CA bundle.
* Retrying a non-idempotent `POST` and creating duplicates on the remote.
* Logging whole response bodies. Truncate.
* Catching `Exception` around the client call and turning programming errors into "network errors". Catch the `requests` exceptions you expect.
* Calling the API from a compute method. Computes run on reads, exports and onchanges, many times over.
* Tests that reach the real network. Patch `requests.Session.request` or inject a client double.

## Versions

{% hint style="info" %}
The installed `urllib3` varies by distribution. `allowed_methods` replaced `method_whitelist` in urllib3 1.26, so check the version on your build. `cr.postcommit` is available in 16, 17 and 18.
{% endhint %}

## Try it

Measure the remote from the server before wiring it in:

```
curl -sS -o /dev/null -w 'connect=%{time_connect}s total=%{time_total}s code=%{http_code}\n' https://api.example.test/health
```
