---
description: From HTTP request to database commit.
---

# Request lifecycle

Every interaction with Odoo that is not a cron job or a shell session is an HTTP request. Understanding what happens between the socket and the `COMMIT` tells you where transactions begin and end, why an exception rolls back everything, and where to put code that must run once per request or once per transaction.

## The path of a request

1. **WSGI entry.** A worker (or thread) receives the request. The framework's `odoo.http.Application` (a WSGI application on top of Werkzeug) handles it.
2. **Session and database.** The session cookie is loaded; the database is selected from the session, the `db` parameter, or the `--db-filter` matching the host name.
3. **Routing.** The request is matched to a controller method registered with `@http.route`. Routes from all installed modules are collected at registry load, so an uninstalled module has no routes.
4. **Dispatch.** Depending on `type=` (`'http'` or `'json'` in 16 and 17; 18 renames the JSON type to `'jsonrpc'` while keeping `'json'` as an alias, so verify in your branch), a dispatcher parses the body and prepares arguments.
5. **Authentication.** `auth='user'`, `'public'`, `'none'`. The result is a user id and an environment.
6. **Cursor and environment.** For database-bound routes, the framework opens a cursor and creates `request.env`. One cursor per request.
7. **Handler runs.** Your controller code executes ORM calls inside that single transaction.
8. **Commit or rollback.** On normal return the cursor commits; on an exception it rolls back. Both happen after your handler returns, not at each ORM call.
9. **Response.** Rendered, headers set, session saved.

A controller in its simplest form:

```python
from odoo import http
from odoo.http import request


class LibraryController(http.Controller):

    @http.route('/library/books', type='http', auth='user')
    def books(self, **kw):
        books = request.env['library.book'].search([], limit=20)
        return request.render('library.book_list', {'books': books})
```

## The ORM RPC path

The web client does not call controllers for most things. It calls two generic JSON routes that expose model methods:

- `/web/dataset/call_kw` (and `/web/dataset/call_kw/<model>/<method>`) calls `model.method(*args, **kwargs)` on the server.
- `/web/dataset/call_button` is the older sibling for buttons.

Both end up in `odoo.service.model.execute_kw`, which opens a cursor, builds an environment for the user, calls the public method, and commits. The external XML-RPC and JSON-RPC endpoints (`/xmlrpc/2/object`, `/jsonrpc`) use the same machinery. This is why every public model method (not starting with an underscore) is callable by any user who can reach the server, and why you must check access in methods, not only in views.

{% hint style="warning" %}
Methods that start with `_` are not exposed through RPC. Put helpers there. Anything public is an endpoint: if it does `sudo()` internally, an authenticated user can trigger it.
{% endhint %}

## Transactions

One request is one transaction on one database cursor. This has practical effects:

- A `raise` anywhere rolls back every write in the request. Expected, and the reason a UI error leaves no half-written data.
- Writes become visible to other transactions only at commit. Another worker handling a concurrent request cannot see your changes during the handler.
- Code that sends an email or calls an external service from inside the handler cannot be undone if the transaction later fails. Queue the side effect, or trigger it after commit.

```python
def action_confirm(self):
    self.write({'state': 'confirmed'})
    # runs after the transaction commits, not before
    self.env.cr.postcommit.add(lambda: self._notify_external())
```

`cr.postcommit` and `cr.precommit` are available as callback registries on the cursor in recent versions (introduced around 14). Verify the exact API in your branch before depending on it, and keep callbacks idempotent.

`env.cr.commit()` inside request code ends the transaction early. After it, a later error cannot roll back what came before. Use it only in batch jobs that deliberately process in chunks, never in business logic reached from the UI.

## Concurrency errors

PostgreSQL runs at `REPEATABLE READ` in Odoo. Two requests that update the same row concurrently produce a serialization failure (`could not serialize access due to concurrent update`). The framework catches `psycopg2.errors.SerializationFailure` and `LockNotAvailable` in the RPC layer and retries the call a few times (`MAX_TRIES_ON_CONCURRENCY_FAILURE`, 5 in current code), so your method may run more than once.

Therefore:

- Do not do non-idempotent external work (payments, emails) in the same method as the writes that can be retried; or make the external call detect duplicates.
- Do not catch broad `Exception` around ORM calls. Swallowing a database error leaves the transaction aborted: every later statement fails with `current transaction is aborted`.
- Wrap deliberate error handling in a savepoint: `with self.env.cr.savepoint(): ...`.

## Environment and context

`request.env` is built from the session: user, company, language, timezone, and `context`. The web client sends its context with each call (`lang`, `tz`, `allowed_company_ids`, defaults such as `default_partner_id`). Methods that behave differently from the shell and from the UI usually differ in context. `allowed_company_ids` in particular controls which companies' records are visible through record rules, so a test in the shell without it sees a different world.

## Static files and assets

Requests for `/<module>/static/...` are served by the framework from disk; in production put them behind the reverse proxy cache. Bundles under `/web/assets/...` are generated on first demand from the `assets` manifest keys and stored as attachments; deleting them forces regeneration and is the first thing to try when a frontend change does not appear.

## Pitfalls

- **Calling `sudo()` and trusting the result.** `sudo()` skips ACLs and record rules; the data you return to the user is whatever it returns. Filter explicitly.
- **`auth='public'` routes with `csrf=False`.** Public routes that change state without CSRF protection are open to cross-site calls. Keep CSRF on for `POST` forms; for JSON routes, require a token or signature.
- **Long handlers.** A request holds its transaction and often row locks for its whole duration. A 60-second import in a request blocks concurrent writers and may hit `--limit-time-real`.
- **Reading data written by another transaction in the same request.** With `REPEATABLE READ`, a snapshot starts at the first query. Polling in a loop never sees new rows.
- **Multiple databases and `db` parameter.** A route called without a database selected and with `auth='none'` has no `request.env` for models. Use `request.env` only after `request.update_env(...)` or via `odoo.registry(db).cursor()` explicitly.

## Try it

```bash
# watch the SQL of one request
odoo-bin -c dev.conf -d dev --log-level=debug_sql
# call the same method through external RPC, outside the web client
python3 - <<'PY'
import xmlrpc.client as x
common = x.ServerProxy('http://localhost:8069/xmlrpc/2/common')
uid = common.authenticate('dev', 'admin', 'admin', {})
models = x.ServerProxy('http://localhost:8069/xmlrpc/2/object')
print(models.execute_kw('dev', uid, 'admin', 'library.book', 'search_count', [[]]))
PY
```
