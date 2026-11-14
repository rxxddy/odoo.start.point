---
description: Requests, status codes, headers, and JSON as the common language.
---

# HTTP and JSON

Every integration you will build around Odoo, and the web client itself, speaks HTTP carrying JSON. Browser to server, Odoo to a payment provider, a script to the external API, a webhook arriving from another system: it is all requests, responses, headers, and cookies. If you can read a raw exchange and say what each line means, most integration bugs shrink to a diff between what you expected and what is on the wire. This chapter covers the protocol, JSON as a format, sessions and cookies, CORS, the JSON-RPC shape Odoo uses, REST design for your own endpoints, and `curl` as the debugging tool.

The examples were run against a small local server written with Node.js (a throwaway scratch script, not part of Odoo). The Odoo-specific facts are limited to routes and envelopes that are stable across the versions covered by this book.

## A request and a response

HTTP is text over a connection. A client sends a request; a server sends one response.

```text
POST /books HTTP/1.1
Host: localhost:8765
Content-Type: application/json
Accept: application/json
Content-Length: 18

{"title":"Ulysses"}
```

```text
HTTP/1.1 201 Created
Content-Type: application/json
Location: /books/3
Content-Length: 27

{"id":3,"title":"Ulysses"}
```

Anatomy:

- **Request line**: method, target (path plus query string), protocol version.
- **Headers**: `Name: value` lines. One blank line ends the headers.
- **Body**: optional bytes, described by `Content-Type` and `Content-Length`.
- **Status line** (response): protocol, status code, reason phrase. Clients act on the code, not the phrase.

HTTP is stateless: each request stands alone, and anything that looks like a session (a logged-in user) is carried by something the client sends each time, normally a cookie or an `Authorization` header.

### URLs

```text
https://shop.example.com:8069/library/books?year=1965&tag=sf#reviews
 scheme      host        port   path           query string   fragment
```

The fragment (`#reviews`) never reaches the server. The query string is `key=value` pairs separated by `&`, and values must be percent-encoded: a space is `%20` (or `+` in form encoding), `&` is `%26`. In JavaScript, `encodeURIComponent("a&b")` gives `a%26b`, and `new URL(...).searchParams` handles building and parsing. In Python, use `urllib.parse.urlencode` and never string concatenation.

## Methods

| Method | Meaning | Body | Safe | Idempotent |
|--------|---------|------|------|------------|
| `GET` | Read a resource | no | yes | yes |
| `HEAD` | Like GET, headers only | no | yes | yes |
| `POST` | Create, or run an action | yes | no | no |
| `PUT` | Replace a resource at a known URL | yes | no | yes |
| `PATCH` | Partial update | yes | no | not guaranteed |
| `DELETE` | Remove | rarely | no | yes |
| `OPTIONS` | Ask what is allowed (CORS preflight) | no | yes | yes |

Safe means it should not change server state; idempotent means repeating the request has the same effect as sending it once. These words matter in practice: browsers, proxies, and retry logic may repeat idempotent requests automatically, and a `GET` that deletes data will be triggered by a link prefetcher or a crawler. Never perform a state change on `GET`. Odoo's own `type="http"` routes accept both methods unless restricted with `methods=["POST"]` in the route declaration.

A network timeout on a `POST` leaves you not knowing if it happened. Safe retrying of non-idempotent calls requires an idempotency key (see REST design below).

## Status codes

The first digit gives the class.

| Code | Name | Use |
|------|------|-----|
| 200 | OK | Success with a body |
| 201 | Created | A resource was created; send `Location` |
| 204 | No Content | Success, nothing to return (DELETE, OPTIONS) |
| 301 / 302 | Moved permanently / found | Redirect to `Location`. Browsers turn a POST into GET on 302 |
| 303 | See Other | Redirect after POST to a GET page |
| 304 | Not Modified | Cached copy is valid (`ETag`, `If-None-Match`) |
| 400 | Bad Request | Malformed request or JSON |
| 401 | Unauthorized | Not authenticated (missing or bad credentials) |
| 403 | Forbidden | Authenticated but not allowed |
| 404 | Not Found | No such resource (also used to hide existence) |
| 405 | Method Not Allowed | Wrong method for this URL |
| 409 | Conflict | State conflict, such as a duplicate or stale update |
| 415 | Unsupported Media Type | Wrong `Content-Type` |
| 422 | Unprocessable Content | Well-formed but fails validation |
| 429 | Too Many Requests | Rate limited; honour `Retry-After` |
| 500 | Internal Server Error | Unhandled server bug |
| 502 / 503 / 504 | Bad gateway / unavailable / gateway timeout | Proxy or upstream trouble |

A useful rule: 4xx means "you must change the request", 5xx means "the server failed; the same request might work later". Retry logic retries 5xx and 429 with backoff, and never 4xx.

Odoo specifics you will hit:

- A `type="json"` route (the RPC style) answers with HTTP 200 even when the call failed; the failure is reported inside the JSON body under an `error` key. A client that only looks at the HTTP status will treat errors as success. Verify the shape on your version, but the convention has been stable for years.
- A `type="http"` route returns real status codes. An access error from the framework becomes 403, a missing record routed through `request.not_found()` becomes 404, an unhandled exception becomes 500.
- A request for a protected page without a session is redirected (302) to `/web/login`, so scripts that follow redirects can end up "successfully" downloading the login page. Check the final URL and `Content-Type`.

## Headers

Headers carry metadata about the message. The ones you will actually look at:

| Header | Direction | Purpose |
|--------|-----------|---------|
| `Host` | request | Which site on this server; Odoo's `dbfilter` can use it to pick a database |
| `Content-Type` | both | Format of the body: `application/json`, `application/x-www-form-urlencoded`, `multipart/form-data`, `text/html; charset=utf-8` |
| `Accept` | request | What formats the client wants |
| `Authorization` | request | Credentials: `Bearer <token>` or `Basic <base64(user:pass)>` |
| `Cookie` / `Set-Cookie` | request / response | Session state |
| `Location` | response | Redirect target or the URL of a created resource |
| `Cache-Control`, `ETag`, `Last-Modified` | response | Caching |
| `User-Agent` | request | Client identification |
| `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` | request via proxy | Real client IP, scheme, host as seen by the proxy |
| `Retry-After` | response | When to retry (429, 503) |

Header names are case-insensitive. Values are not always.

The forwarded headers matter on every real Odoo deployment, because Odoo sits behind a reverse proxy that terminates TLS. If the proxy does not send them and Odoo is not configured to trust them (`proxy_mode` in the configuration file), Odoo generates `http://` links, loses client IPs, and cookies marked `Secure` misbehave. Misconfigured proxy headers are the most common cause of "login works on the server but redirects to the wrong URL".

### Content types for bodies

- `application/json`: the body is JSON. This is what you send to JSON endpoints.
- `application/x-www-form-urlencoded`: `a=1&b=two%20words`. Traditional HTML form posts.
- `multipart/form-data`: forms with file uploads; each part has its own headers.
- A response may be `text/html`, `application/pdf`, `image/png`, `text/csv`, or a download with `Content-Disposition: attachment; filename="loans.csv"`.

If a JSON endpoint receives `application/x-www-form-urlencoded`, it typically returns 400 or 415, or sees an empty body. Always send the header that matches the body.

## Cookies, sessions, and CSRF

A cookie is a small value the server stores in the browser with `Set-Cookie`; the browser sends it back on every later request to that site.

```text
Set-Cookie: session_id=abc123; HttpOnly; Path=/; SameSite=Lax; Secure; Max-Age=604800
```

Attributes:

- **HttpOnly**: JavaScript cannot read it. Protects the session ID from theft by injected scripts.
- **Secure**: sent only over HTTPS.
- **SameSite**: `Lax` (default in modern browsers) withholds the cookie on cross-site sub-requests such as images and POSTs from another site, `Strict` withholds it more broadly, `None` allows cross-site (and requires `Secure`).
- **Path** and **Domain**: where the cookie applies.
- **Max-Age** / **Expires**: lifetime; without it the cookie dies when the browser closes.

How Odoo uses them: after login, the server creates a session, stores it server-side (files in the data directory by default, or a configured store), and sets a cookie holding the session ID. The cookie name is `session_id`. Every request sends it; the server looks up the session to find the user, database, and context. Authentication via cookie is what lets a script reuse a login:

```bash
# 1. Authenticate (JSON-RPC style); -c saves the session cookie
curl -s -c cookies.txt -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"call","params":{"db":"<db>","login":"<login>","password":"<password>"}}' \
  http://localhost:8069/web/session/authenticate

# 2. Reuse it; -b sends the saved cookies
curl -s -b cookies.txt http://localhost:8069/web/session/get_session_info \
  -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"call","params":{}}'
```

(`<db>`, `<login>`, `<password>` are placeholders, as everywhere in this book. Never put real credentials into scripts you commit.)

The session cookie lets a request act as the user. That is both the feature and the attack surface:

- **CSRF** (cross-site request forgery): a malicious page makes the victim's browser send a request to your server, and the browser attaches the cookie automatically. Defences: `SameSite` cookies, and a secret token that a legitimate page embeds and a foreign page cannot read. Odoo `type="http"` routes that change data with POST check a `csrf_token` form field by default, which templates provide with `request.csrf_token()`. Turning that check off (`csrf=False` on the route) is legitimate for webhooks that authenticate by other means (a signature), and never for browser-facing forms.
- **Session fixation and theft**: keep cookies `HttpOnly` and `Secure`, serve everything over HTTPS.

Cookies versus tokens: browsers use cookies naturally; server-to-server integrations prefer an explicit credential in the `Authorization` header, an API key or a bearer token, which does not require a login dance and is not subject to CSRF. Odoo supports API keys for external API use (generated by the user in their account security settings), usable in place of the password in RPC calls.

## CORS

Browsers enforce the same-origin policy: a script on `https://a.example` cannot read responses from `https://b.example` unless `b` opts in. An origin is scheme + host + port. **CORS** (cross-origin resource sharing) is that opt-in, done with response headers. The browser, not the server, enforces it, so `curl` is never blocked, which is why "works in curl, fails in the browser" is the classic symptom.

A cross-origin request is either simple or needs a preflight. If the request uses a method other than GET/HEAD/POST, or a custom header, or a `Content-Type` such as `application/json`, the browser first sends an `OPTIONS` request:

```text
OPTIONS /books HTTP/1.1
Origin: https://portal.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

and expects:

```text
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://portal.example
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type
Access-Control-Max-Age: 600
```

Only if the preflight passes does it send the real request, whose response must also carry `Access-Control-Allow-Origin`. Rules worth remembering:

- `Access-Control-Allow-Origin: *` allows any origin but cannot be combined with credentials. For requests that send cookies (`fetch(..., { credentials: "include" })`), the server must name the exact origin and send `Access-Control-Allow-Credentials: true`.
- Browsers hide response headers from scripts unless listed in `Access-Control-Expose-Headers`.
- A CORS error does not mean the server rejected the call. The request often reached the server and ran; only the response was withheld from the script. For a POST that creates a record, you may have created it and not seen the result.

Odoo's route decorator has a `cors` parameter (`@http.route("/library/api/books", type="json", auth="public", cors="*")`) that adds the headers. Use a specific origin rather than `*` for anything that is not public data.

Same-origin is the easy case: a portal page served by Odoo calling Odoo's own routes needs no CORS at all. You only configure CORS when a different site's JavaScript calls Odoo.

## JSON

JSON is the data format of the web: objects, arrays, strings, numbers, `true`, `false`, `null`.

```json
{
  "id": 3,
  "title": "Dune",
  "year": 1965,
  "price": 12.5,
  "available": true,
  "tags": ["sf", "classic"],
  "author": { "id": 7, "name": "F. Herbert" },
  "series": null
}
```

Strict rules, a stricter grammar than JavaScript object literals:

- Keys are double-quoted strings. Strings use double quotes; `'single'` is invalid.
- No comments, no trailing commas, no `undefined`, no `NaN`/`Infinity`, no functions.
- Numbers are decimal; no leading zeros and no hex. There is no integer type, only a number; very large integers lose precision in JavaScript (above 2^53), a concern for 64-bit identifiers. Send them as strings if you control the format.
- There is no date type. Dates travel as strings. Use ISO 8601 (`2025-03-01T10:00:00Z`) in your own APIs, always with an explicit time zone or `Z`. Odoo's own `Datetime` fields serialise to `"2025-03-01 10:00:00"` in UTC, with a space and no zone marker, and `Date` fields as `"2025-03-01"`; convert deliberately.
- There is no binary type. Binary data is base64 text, with a 33% size cost. Odoo `Binary` fields come over RPC as base64 strings.

Parsing and writing:

```js
const text = '{"a":[1,2,{"b":null}]}';
const data = JSON.parse(text);              // throws SyntaxError on bad JSON
console.log(data.a[2].b);                   // null
console.log(JSON.stringify(data, null, 2)); // pretty print with 2 spaces
console.log(JSON.stringify({ d: new Date(0), u: undefined, n: null }));
// {"d":"1970-01-01T00:00:00.000Z","n":null}   undefined keys are dropped, dates become strings
```

```python
import json

payload = json.loads('{"a": [1, 2, {"b": null}]}')   # null -> None
print(payload["a"][2]["b"] is None)                 # True
print(json.dumps({"ok": True, "n": None}, indent=2, sort_keys=True))
print(json.dumps({"price": 12.5, "d": "é"}, ensure_ascii=False))
```

Mappings between Python and JSON: `True`/`False` to `true`/`false`, `None` to `null`, `dict` to object, `list` and `tuple` to array. Python's `json` does not serialise `datetime`, `Decimal`, or recordsets by default: convert them first, or pass `default=str` consciously. Odoo's `json` route type serialises standard cases for you; for your own `type="http"` responses, convert dates with `fields.Date.to_string` and friends before `json.dumps`.

Practical checks on JSON on the command line:

```bash
curl -s http://localhost:8765/books | python -m json.tool    # pretty printing
curl -s http://localhost:8765/books | jq '.items[].title'    # if jq is installed
```

### JSON-RPC and Odoo

JSON-RPC 2.0 is a tiny protocol on top of JSON over HTTP: the client sends a method name and params with an id; the server returns the same id with either a `result` or an `error`.

```json
{ "jsonrpc": "2.0", "method": "call", "params": { "a": 1 }, "id": 7 }
```

```json
{ "jsonrpc": "2.0", "id": 7, "result": { "echo": { "a": 1 } } }
```

```json
{ "jsonrpc": "2.0", "id": 7, "error": { "code": 200, "message": "Odoo Server Error", "data": { "name": "odoo.exceptions.UserError", "message": "Cannot loan a book twice." } } }
```

In Odoo, `type="json"` routes use this envelope with method `"call"`: whatever `params` carry becomes the keyword arguments of the controller method, and the return value becomes `result`. The web client calls model methods through `/web/dataset/call_kw` with `params` of the form `{ "model": "library.book", "method": "search_read", "args": [[["year", "<", 2000]]], "kwargs": { "fields": ["name"] } }`. For external scripts, Odoo exposes the `/jsonrpc` endpoint and its `execute_kw`:

```bash
curl -s http://localhost:8069/jsonrpc -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0", "method": "call", "id": 1,
  "params": {
    "service": "object", "method": "execute_kw",
    "args": ["<db>", <uid>, "<password_or_api_key>", "library.book", "search_read",
             [[["year", "<", 2000]]], {"fields": ["name", "year"], "limit": 5}]
  }
}'
```

`<uid>` is the numeric user id returned by a prior call to `{"service": "common", "method": "login", "args": ["<db>", "<login>", "<password>"]}`. The positional `args` after the credentials are the model, the method, the positional arguments of the ORM method, and a dictionary of keyword arguments. This is the same mechanism as the XML-RPC interface under `/xmlrpc/2/`, which accepts the same arguments in XML. The external API chapter later in the book builds complete clients; the shape is what matters here: **model, method, args, kwargs**.

The first two lines worth memorising when debugging an RPC call in the browser's network tab: the response status is 200 even for a failure, and the failure is in `error.data.message` (the text the user sees) and `error.data.debug` (the traceback, present in developer deployments).

{% hint style="info" %}
Versions: the `/jsonrpc` and `/xmlrpc/2/` endpoints, `call_kw`, and the envelope above are available across the versions covered here. Newer releases add other external API styles; consult the target version's documentation before choosing one for a new integration.
{% endhint %}

## Designing HTTP APIs (REST style)

When you add routes to Odoo for another system to call, you design a small API. The conventions of REST-style design keep it predictable:

- **Resources are nouns, methods are verbs.** `GET /library/api/v1/books`, `GET /library/api/v1/books/3`, `POST /library/api/v1/books`, `PATCH /library/api/v1/books/3`, `DELETE /library/api/v1/books/3`. Not `/getBook` or `/deleteBook`.
- **Version the path** (`/v1/`) so a breaking change does not break existing clients.
- **Filtering, sorting, paging in the query string**: `?year_lt=2000&sort=-year&limit=20&offset=40`. Return the total, or a cursor, so clients can page. Always put a default and a maximum on `limit`.
- **Consistent response shapes.** List: `{ "items": [...], "total": 120 }`. Error: `{ "error": { "code": "validation_failed", "message": "title is required", "fields": { "title": "required" } } }`. Pick one error shape and keep it.
- **Correct status codes.** 201 plus `Location` on creation, 204 on delete, 400/422 on bad input, 401 versus 403 as defined above, 404 for unknown ids, 409 for conflicts.
- **Authentication in a header**, not in the URL (URLs end up in logs). API key or bearer token for server-to-server use.
- **Idempotency for POSTs that must not repeat.** Accept an `Idempotency-Key` header, store the key with the result, and on a repeat return the stored result. This is how a client can safely retry after a timeout.
- **Dates in ISO 8601 with a zone**, money as strings or integer minor units with a currency code, never floats.
- **Do not expose database ids if you have a better identifier** and do not leak internal field names you may rename.
- **Rate limits and payload limits** exist because someone will send a million rows. Check `Content-Length`, cap list sizes.
- **Return only what the caller is allowed to see.** Routes with `auth="public"` and `sudo()` inside are a data leak waiting to happen; use record rules and fetch with the caller's user, as the security part explains.

Exposing everything an ORM model has is rarely a good API: shape the response explicitly.

```python
# fragment of a controller; models, security and routing are covered in later parts
@http.route("/library/api/v1/books", type="http", auth="user", methods=["GET"])
def list_books(self, limit=20, offset=0, **kw):
    ...
```

The `auth` values and API-key handling are covered in the controller chapter; with `auth="user"` the caller needs a valid session, which an external client obtains by logging in first.

## curl: the debugging tool

`curl` shows what the wire carries. These commands were run against the scratch server.

```bash
# GET with response headers
curl -i http://localhost:8765/books

# Only the status code
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8765/books

# POST JSON
curl -i -X POST http://localhost:8765/books \
  -H 'Content-Type: application/json' \
  -d '{"title":"Ulysses"}'

# Validation failure: 422
curl -s -w ' -> %{http_code}\n' -X POST http://localhost:8765/books \
  -H 'Content-Type: application/json' -d '{}'

# Show the request and response in full, including TLS details
curl -v http://localhost:8765/books

# Preflight, as a browser would send it
curl -i -X OPTIONS http://localhost:8765/books \
  -H 'Origin: https://portal.example' \
  -H 'Access-Control-Request-Method: POST'

# Save and reuse cookies
curl -c jar.txt -X POST http://localhost:8765/login
curl -b jar.txt http://localhost:8765/books

# Send a body from a file
curl -X POST http://localhost:8765/books -H 'Content-Type: application/json' -d @book.json

# Follow redirects and show the final URL
curl -sL -o /dev/null -w '%{url_effective} %{http_code}\n' http://localhost:8069/my
```

Useful flags: `-i` include response headers, `-s` silent, `-v` verbose, `-X` method, `-H` header, `-d` data (implies POST), `-b`/`-c` cookies in/out, `-o` output file, `-w` write-out format, `-L` follow redirects, `-k` skip TLS verification (never in scripts that matter), `-u user:pass` Basic auth.

Shell quoting breaks JSON on Windows `cmd` and PowerShell; use Git Bash, put the JSON in a file and use `-d @file`, or use PowerShell's `Invoke-RestMethod`. The browser's developer tools (Network tab, "Copy as cURL") give you a working command for any request the browser made, which is the fastest way to reproduce what the Odoo web client sends.

A minimal Python client with `requests`, for scripts:

```python
import requests

BASE = "http://localhost:8765"
s = requests.Session()
s.post(f"{BASE}/login").raise_for_status()           # cookie kept in the session
r = s.post(f"{BASE}/books", json={"title": "Ulysses"}, timeout=10)
if r.status_code == 422:
    print("validation:", r.json())
else:
    r.raise_for_status()
    print(r.status_code, r.headers["Location"], r.json())
```

Always pass `timeout`; the library default is to wait forever, and a stuck remote call stalls an Odoo worker until it is killed.

## Debugging checklist

1. Reproduce with `curl -v` or the browser's Network tab. Look at the status, the `Content-Type` you sent and received, and the body.
2. Status 200 from a JSON route: read the `error` key.
3. Redirect to a login page: your session or credentials are missing; check the cookie.
4. 403 versus 401: 401 means "who are you", 403 means "you may not". For Odoo, 403 on a controller often is a CSRF failure or an access rule.
5. Works in `curl`, fails in the browser: CORS or cookies (`SameSite`, `Secure`, third-party restrictions).
6. Works locally, wrong URLs in production: proxy headers and `proxy_mode`.
7. Empty body received: wrong `Content-Type`, or the body was sent on a method that drops it.
8. Timeouts: look at the server side first; a 504 from the proxy means the proxy gave up while Odoo kept working.

## Pitfalls

- **Trusting the status of JSON-RPC calls.** HTTP 200 with an `error` key is a failure.
- **State change on GET.** Prefetchers, crawlers, and email scanners will trigger it.
- **Missing `Content-Type: application/json`** on a JSON body; the server reads nothing.
- **Following a redirect to the login page** and treating the HTML as data.
- **Credentials in URLs and logs.** Query strings are logged by proxies. Use headers.
- **`csrf=False` on browser-facing routes.** Only for endpoints authenticated by a signature or token.
- **CORS as a security control.** It restricts browsers only. Anyone with `curl` ignores it; authenticate and authorise on the server regardless.
- **`Access-Control-Allow-Origin: *` with cookies.** Browsers reject it. Name the origin.
- **Floats for money and large integer ids in JSON.** Precision loss. Use strings or integer minor units.
- **Naive datetimes.** A date string without a zone is ambiguous. State UTC or an offset, and know what Odoo stores.
- **No timeouts on outbound calls.** A slow upstream ties up a worker.
- **Retrying non-idempotent requests blindly** and creating duplicates. Add idempotency keys.
- **Unbounded list endpoints.** No `limit` means one client can take the server down.
- **Returning tracebacks to clients.** Log them; return a short error.

## Try it

**1. Read a response.** Without running anything, say what each part of this response means and what a client should do next.

```text
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json

{"error":{"code":"rate_limited","message":"slow down"}}
```

<details>
<summary>Solution</summary>

Status 429: the client sent too many requests. `Retry-After: 30` says to wait 30 seconds before trying again. The body is JSON with an error object whose `code` is machine-readable and whose `message` is for humans. The client should pause for 30 seconds (adding some random jitter), then retry the same request; a 4xx other than 429 would not be retried.
</details>

**2. curl a JSON-RPC call.** Write the `curl` command that calls a `type="json"` route at `/library/api/ping` with params `{"name": "Ann"}` on a local server, and say how to tell if it failed.

<details>
<summary>Solution</summary>

```bash
curl -s http://localhost:8069/library/api/ping \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{"name":"Ann"},"id":1}'
```

The HTTP status will be 200 either way. Failure is the presence of an `error` key in the response JSON, whose `data.message` holds the text. Success has a `result` key.
</details>

**3. Choose status codes.** For each case pick the best status code: (a) a client posts `{"title": ""}` to create a book and `title` is required; (b) a client asks for `/books/9999` which does not exist; (c) a logged-in portal user requests another member's loan; (d) a client sends invalid JSON; (e) a client creates a loan successfully.

<details>
<summary>Solution</summary>

(a) 422 (or 400 if you do not distinguish validation from malformed input). (b) 404. (c) 403, or 404 if you prefer not to reveal that the loan exists. (d) 400. (e) 201 with a `Location` header pointing at the new loan.
</details>

**4. Explain a CORS failure.** A page at `https://portal.example` calls `fetch("https://erp.example/library/api/ping", { method: "POST", headers: {"Content-Type": "application/json"}, credentials: "include" })`. The browser console says the request was blocked, but the Odoo log shows a request arrived. What happened, and which headers must the response carry?

<details>
<summary>Solution</summary>

The request is cross-origin, uses `application/json`, so the browser sends a preflight `OPTIONS` first, then the real request. A request arrived, but the browser withheld the response from the script because the CORS headers were missing or insufficient. With `credentials: "include"` the server must send `Access-Control-Allow-Origin: https://portal.example` (not `*`) and `Access-Control-Allow-Credentials: true`; the preflight response must also send `Access-Control-Allow-Methods` including `POST` and `Access-Control-Allow-Headers` including `Content-Type`.
</details>

**5. Build and call.** Run a scratch HTTP server of your own in Node with a `GET /books` route that returns a JSON list and a `POST /books` route that returns 422 when `title` is missing. Call both with `curl` and confirm the status codes.

<details>
<summary>Solution</summary>

```js
// server.mjs: run with `node server.mjs`
import http from "node:http";
const books = [{ id: 1, title: "Dune" }];
const send = (res, code, body, headers = {}) => {
  res.writeHead(code, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(body));
};
http.createServer(async (req, res) => {
  if (req.url === "/books" && req.method === "GET") return send(res, 200, { items: books });
  if (req.url === "/books" && req.method === "POST") {
    let raw = "";
    for await (const chunk of req) raw += chunk;
    let data;
    try { data = JSON.parse(raw); } catch { return send(res, 400, { error: "invalid JSON" }); }
    if (!data.title) return send(res, 422, { error: "title required" });
    const book = { id: books.length + 1, title: data.title };
    books.push(book);
    return send(res, 201, book, { Location: `/books/${book.id}` });
  }
  send(res, 404, { error: "not found" });
}).listen(8765);
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8765/books                                   # 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8765/books -H 'Content-Type: application/json' -d '{}'   # 422
curl -i -X POST localhost:8765/books -H 'Content-Type: application/json' -d '{"title":"Emma"}'  # 201 + Location
```
</details>
