---
description: Injection, sudo misuse, exposing controllers, and secrets.
---

# Secure coding

Odoo gives you a safe ORM, a CSRF-protected HTTP layer and an access model. Most vulnerabilities in custom modules come from stepping around one of those. This chapter lists the patterns to avoid and the patterns to use instead.

## SQL injection

The ORM parameterises everything. Raw SQL through `self.env.cr.execute` does not unless you pass parameters.

```python
# Wrong: string formatting builds the query.
self.env.cr.execute("SELECT id FROM library_book WHERE name = '%s'" % name)

# Right: parameters.
self.env.cr.execute("SELECT id FROM library_book WHERE name = %s", (name,))
```

Identifiers (table and column names) cannot be parameters. Use `psycopg2.sql` or the `SQL` helper (`from odoo.tools import SQL`, available in 17+ and the preferred form in 18):

```python
query = SQL("SELECT id FROM %s WHERE %s = %s", SQL.identifier('library_book'), SQL.identifier(column), value)
self.env.cr.execute(query)
```

Never build an `IN` list by joining strings; pass a tuple: `WHERE id IN %s`, `(tuple(ids),)`.

Also, raw SQL skips ACLs, rules and the ORM cache. After a raw `UPDATE` call `invalidate_model` or `invalidate_recordset`, and apply the access checks yourself.

## Domains and `eval`

Never `eval()` user input. If you need to evaluate a domain stored as text, use `ast.literal_eval` for plain data or `odoo.tools.safe_eval` with explicit locals. `safe_eval` limits the available builtins but is not a sandbox for hostile code; treat its input as trusted-administrator only.

Domains built from request parameters should be assembled as lists, not strings, and operators from a whitelist:

```python
ALLOWED = {'=', 'ilike'}
if op not in ALLOWED:
    raise UserError(_("Invalid operator"))
```

## sudo and privilege escalation

`sudo()` is a loan of the superuser's rights. Rules:

1. Scope it narrowly: `record.sudo().field`, not `self.sudo()` for the whole method.
2. Check access on the user's behalf first: `record.check_access('read')` before reading through sudo.
3. Do not return sudo'd recordsets or ids to a caller who should not see them.
4. Put the user-visible `create_uid` back: `with_user(user)` is better than `sudo()` when you want the action attributed to a real account.

```python
def action_close(self):
    self.check_access('write')
    self.sudo()._close_internal()   # internal step touches accounting records
```

{% hint style="info" %}
Versions: `check_access('write')` is the unified form in 18 (and 17); in 16 use `check_access_rights('write')` followed by `check_access_rule('write')`.
{% endhint %}

## Controllers

```python
from odoo import http
from odoo.http import request

class LibraryController(http.Controller):

    @http.route('/library/loan/<int:loan_id>', type='http', auth='user', methods=['GET'])
    def loan(self, loan_id):
        loan = request.env['library.loan'].browse(loan_id)
        loan.check_access('read')
        return request.render('library.loan_page', {'loan': loan})
```

- `auth='user'` for authenticated pages, `auth='public'` for anonymous ones, `auth='none'` only for things that run before a database is known. `auth='public'` plus `sudo()` is where leaks happen.
- Restrict `methods`. State-changing routes should be `POST`; `type='http'` POST routes get CSRF checks by default, so do not set `csrf=False` except for webhooks, where you authenticate the sender yourself.
- Validate and cast every parameter. Route converters (`<int:...>`) do the cast; query and form values arrive as strings.
- Do not trust IDs from the client. Use `browse(id).exists()` and an access check, or use an access token (`access_token` with `_get_access_token` patterns from `portal.mixin`).

## Output encoding and XSS

QWeb escapes with `t-esc` and `t-out` for plain text. Raw HTML only goes through `Markup` or HTML fields, and is sanitised by field definition (`sanitize=True` default on `fields.Html`). Never wrap user text in `Markup()`; build messages with `Markup.format` or `escape()`:

```python
from markupsafe import Markup
body = Markup("<b>%s</b>") % user_text    # user_text is escaped
```

The same applies to values interpolated in mail templates, and to `message_post(body=...)`: a plain string is escaped, a `Markup` is not.

## Secrets

- No keys, passwords or tokens in source code or XML data. Use `ir.config_parameter` for non-secret settings, and the server config or environment variables for secrets.
- Do not log them. `_logger.info("params %s", kwargs)` is a quick way to write a token to disk.
- Compare tokens with `hmac.compare_digest`, not `==`.
- API keys (`res.users.apikeys`) are hashed in the database; show them once at creation and never store them in plain form yourself.

## Files and paths

User-uploaded file names are data. Do not join them into a filesystem path. Store attachments through `ir.attachment` and return them with `request.make_response` and the right `Content-Type`, `Content-Disposition` and `X-Content-Type-Options` headers. Serving user HTML from your own domain gives it your cookies; return it as a download.

## Pitfalls

{% hint style="warning" %}
`auth='public'` combined with `request.env['...'].sudo().search([])` and a loop that returns everything is the most common data leak in custom modules. Filter by an explicit owner or token.
{% endhint %}

- **`csrf=False` on a form route.** Any website can then post to it as the logged-in user.
- **`type='json'` as a CSRF bypass.** It is not protected by default; check origin and authentication yourself. In 18 the JSON route type is still `'json'`; routes of the newer `'jsonrpc'` kind are not available before 19, so do not rely on them.
- **Exception text to the client.** Raising `UserError` shows its message to the user; do not put SQL, paths or internal ids in it.
- **Default demo passwords.** Demo data creates users with known logins. Never load demo data in production.
- **Dependencies.** Pin and review third-party Python packages the module imports.

## Try it

Find raw SQL in your module that may be unparameterised:

```bash
grep -rnE "execute\(.*(%|\.format|f\")" library/ --include=*.py
```

Every hit needs a human look: some are fine, those with string formatting are not.
