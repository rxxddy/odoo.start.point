---
description: XML-RPC and JSON-RPC from outside Odoo, with API keys.
---

# Remote scripts over RPC

When you cannot or should not log in to the server, a script can drive Odoo over its external API. The calls go through the normal ORM with the permissions of one user, so record rules apply, which is both the limit and the safety.

## API keys

Create a key under Preferences, Account Security, New API Key (user menu, in developer mode if the option is hidden). Use it in place of the password. Treat it as a password: keep it in an environment variable or a secrets file outside the repository, never in the script.

```bash
export ODOO_URL=https://odoo.example.test
export ODOO_DB=mydb
export ODOO_LOGIN=api.user@example.test
export ODOO_KEY=...   # from your secret store
```

Use a dedicated user with only the groups the script needs. An automation running as an administrator can do anything the administrator can.

## XML-RPC

```python
import os
import xmlrpc.client

url, db = os.environ["ODOO_URL"], os.environ["ODOO_DB"]
common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, os.environ["ODOO_LOGIN"], os.environ["ODOO_KEY"], {})
if not uid:
    raise SystemExit("authentication failed")

models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

def call(model, method, *args, **kwargs):
    return models.execute_kw(db, uid, os.environ["ODOO_KEY"], model, method, list(args), kwargs)

print(common.version()["server_version"])
ids = call("library.book", "search", [("isbn", "=", False)], limit=100)
rows = call("library.book", "read", ids, fields=["name", "isbn"])
```

Shortcuts: `search_read` returns dicts directly, `search_count` counts, `create` takes a dict or a list of dicts, `write` takes `ids, values`, `unlink` takes ids.

```python
new_id = call("library.book", "create", {"name": "Test book"})
call("library.book", "write", [new_id], {"isbn": "9780000000000"})
```

## JSON-RPC

The `/jsonrpc` endpoint exposes the same services:

```python
import json, os, urllib.request

def rpc(service, method, *args):
    payload = {"jsonrpc": "2.0", "method": "call", "id": 1,
               "params": {"service": service, "method": method, "args": args}}
    req = urllib.request.Request(os.environ["ODOO_URL"] + "/jsonrpc",
                                 json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req))
    if "error" in out:
        raise RuntimeError(out["error"]["data"]["message"])
    return out["result"]

uid = rpc("common", "authenticate", db, login, key, {})
count = rpc("object", "execute_kw", db, uid, key, "library.book", "search_count", [[]])
```

{% hint style="info" %}
Odoo 18 contains no `/json/2` route (searched `odoo` and `addons/base` of the 18.0 source). Releases after 18 may add a REST-style endpoint; check the documentation of the version you target before building something long-lived on XML-RPC or `/jsonrpc`.
{% endhint %}

## Context, companies and languages

Pass context as a keyword argument:

```python
call("library.book", "search_read", [], fields=["name"],
     context={"lang": "fr_FR", "allowed_company_ids": [1, 2]})
```

## Reading and writing in batches

Each call is an HTTP round trip. Read in pages, write in chunks, and never loop one call per record for thousands of records:

```python
offset = 0
while True:
    rows = call("library.book", "search_read", [], fields=["name"], limit=500, offset=offset, order="id")
    if not rows:
        break
    offset += len(rows)
```

Paginating with `offset` over a table that changes underneath you can skip or repeat rows. Prefer paging by id (`[("id", ">", last_id)]`, `order="id"`) for long jobs.

## Errors

A failure raises `xmlrpc.client.Fault`; `fault.faultString` holds the server traceback. Access errors, validation errors and constraint violations all arrive this way. Log the model, ids and values before each write, so a failure at record 4,000 is diagnosable.

## Pitfalls

- **Secrets in the repository.** Use the environment.
- **Methods that return recordsets.** Only plain data crosses RPC. A method returning a recordset fails to serialize; return ids or `True`.
- **Private methods.** Methods starting with an underscore cannot be called over RPC.
- **`None` in XML-RPC.** XML-RPC cannot marshal `None` by default; use `ServerProxy(url, allow_none=True)` or send `False`.
- **Dry run.** RPC has no transaction to roll back; each call commits. Test against a copy, and add a `--apply` switch that skips writes by default.
- **Timeouts.** Long server-side methods hit worker time limits. Chunk the work.

## Try it

```bash
python -c "import xmlrpc.client,os;print(xmlrpc.client.ServerProxy(os.environ['ODOO_URL']+'/xmlrpc/2/common').version())"
```
