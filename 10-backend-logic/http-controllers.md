---
description: Routes, authentication types, request handling, and safe controller code.
---

# HTTP controllers

Controllers expose HTTP endpoints for the website, for portals, for webhooks and for custom JSON APIs. They are the least protected entry point of the system, because the caller is not always a logged-in user. Keep them short, explicit about who may call them, and delegate to models (see [Thin controllers, fat models](thin-controllers-fat-models.md)).

## A minimal controller

```python
from odoo import http
from odoo.http import request

class LibraryController(http.Controller):

    @http.route('/library/books', type='http', auth='user', methods=['GET'])
    def books(self, **kw):
        books = request.env['library.book'].search([], limit=50)
        return request.render('library.book_list', {'books': books})

    @http.route('/library/api/borrow', type='json', auth='user', methods=['POST'])
    def borrow(self, book_id):
        book = request.env['library.book'].browse(int(book_id)).exists()
        if not book:
            raise request.not_found()
        return {'loan': book.borrow(request.env.user.partner_id).id}
```

The class must be imported from the module's `controllers/__init__.py`, which the module `__init__.py` imports. A controller that is not imported does not exist.

## Authentication types

| `auth=` | Who runs it | Use for |
| --- | --- | --- |
| `user` | Logged-in user, their access rights | Backend and portal actions |
| `public` | The website's public user if not logged in | Public pages and forms |
| `none` | No user, no database selected automatically | Database-agnostic endpoints, health checks |

Under `public` you are running as an anonymous user with minimal rights. When you need more, use `sudo()` on the smallest possible call and validate everything the caller sent. Under `auth='none'`, `request.env` has no usable user; pick the database and user explicitly if you need them.

## type=http versus type=json

`type='http'` receives form or query parameters and returns any response. `type='json'` expects a JSON-RPC request body and wraps your return value in a JSON-RPC envelope. Errors raised in a `json` route are serialized into the envelope with an HTTP 200, which surprises clients that watch status codes. For third-party callers that expect plain REST semantics, use `type='http'`, read `request.httprequest.get_json()` (or `request.get_json_data()`) yourself and build the response with `request.make_json_response(data, status=...)`.

## CSRF, methods and CORS

- State-changing `type='http'` routes with `auth='user'` or `'public'` are CSRF-protected by default; the form must carry the token. Disable with `csrf=False` only for endpoints with their own authentication such as a signed webhook.
- Restrict `methods=[...]`; the default accepts everything.
- `cors='*'` opens the route to other origins. Do not combine it with cookie authentication.

## Validate every input

Parameters arrive as strings and are fully attacker-controlled. Cast, check ranges, and re-check ownership:

```python
loan = request.env['library.loan'].browse(int(loan_id)).exists()
if not loan or loan.partner_id != request.env.user.partner_id:
    raise request.not_found()
```

Do not use `sudo()` before the ownership check. Return the same response for "does not exist" and "not yours", so ids cannot be probed. Never build SQL or domains by string concatenation; pass parameters.

## Transactions and retries

Each request is one transaction, committed after the controller returns. As described in [Concurrency](concurrency.md), the dispatcher can run the request again after a serialization failure. Keep non-idempotent external calls out of the controller body: write a job record, commit, process later. For endpoints that clients may retry, accept an idempotency key and store it with a unique constraint.

## Errors and responses

Raise `UserError`, `AccessError`, `ValidationError` or `werkzeug.exceptions.NotFound`; do not catch broadly and return a 200 with an error text. Log with enough context to find the request, without logging tokens or personal data.

## Pitfalls

- **Controllers that do the work.** A 120 line route handler with business rules cannot be called from a cron or a test.
- **`auth='public'` plus `sudo()` as a default.** This is an unauthenticated write path to your data. Review each such route as if it were an open API.
- **Trusting `request.env.user` under `auth='none'`.** It is not the logged-in user.
- **Large responses built in memory.** Stream exports or generate them as attachments.
- **Route path collisions.** Two modules defining the same route: the last loaded wins. Prefix your routes with the module name.
- **Overriding a standard controller without calling `super()`.** You silently drop the behavior other modules added.

{% hint style="info" %}
Versions: Odoo 16 uses `type='json'` and `type='http'` with `request.jsonrequest` for the body. In 17 and 18 the JSON body is read through the parameters of your method and `request.get_json_data()`, and `request.jsonrequest` is gone. Check the exact request helpers in `odoo/http.py` of your version before copying code between them. In 18, `type='json'` is the JSON-RPC route type; plain JSON routes are served by `type='http'`.
{% endhint %}

## Try it

List the routes your database actually serves (read-only):

```bash
grep -rn "@http.route" /path/to/custom-addons --include=*.py | grep -v "auth='user'"
```

Every line it prints is a route that is public or unauthenticated. Read each one.
