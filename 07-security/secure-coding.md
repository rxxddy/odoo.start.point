---
description: "The mistakes that turn a custom module into a vulnerability: SQL built from strings, sudo that leaks, controllers that trust input, unescaped HTML, weak tokens, and unsafe file paths, with the safe form of each."
---

# Secure coding

The ORM's three access layers protect you only while your code goes through them. Custom modules leak data in a handful of recurring ways: a SQL string built with formatting, a `sudo()` that returns what rules were hiding, a controller route that trusts a parameter, HTML marked safe that came from a user, a token compared with `==`. This chapter lists each failure with the unsafe form, the safe form and the source behind the safe form. It is a checklist you can run on any module before it goes to production.

Checked against Odoo 18 (`odoo/tools/sql.py`, `odoo/sql_db.py`, `odoo/api.py`, `odoo/http.py`, `odoo/tools/misc.py`, `odoo/fields.py`, `odoo/tools/mail.py`) and the 20 tree where noted.

## 1. SQL injection

Any SQL built by formatting user-influenced text into the query is injectable:

```python
# WRONG: the text becomes SQL.
self.env.cr.execute("SELECT id FROM library_book WHERE name = '%s'" % name)
self.env.cr.execute(f"SELECT id FROM library_book WHERE isbn = '{isbn}'")
self.env.cr.execute("SELECT id FROM library_book WHERE name = '" + name + "'")
```

The safe form passes values as parameters, and since Odoo 17 the preferred container is the `SQL` object, which refuses to mix code and values:

```python
from odoo.tools import SQL

# Parameters.
self.env.cr.execute("SELECT id FROM library_book WHERE name = %s", (name,))

# The SQL object: code is a literal, values are parameters.
query = SQL("SELECT id FROM library_book WHERE name = %s AND state = %s", name, "available")
rows = self.env.execute_query(query)        # returns a list of tuples
```

How the `SQL` class works (from `tools/sql.py` in 18):

- `SQL("... %s ...", value, ...)` takes a `%`-format string and the parameters. `query.code` is the text with placeholders, `query.params` the values.
- If `code` is a string **literal** (not a dynamic string), the object is guaranteed to be safe, provided the objects it embeds are `SQL` objects too. Passing a computed string as `code` is exactly what bypasses the protection, so it is the one thing never to do.
- `SQL.identifier(name)` quotes a table or column name. Use it when an identifier must vary:

```python
column = "name" if by_name else "isbn"
query = SQL(
    "SELECT id FROM %s WHERE %s = %s",
    SQL.identifier("library_book"),
    SQL.identifier(column),
    value,
)
```

- `SQL.join(parts)` combines several `SQL` fragments, for example a list of conditions.
- `cr.execute` accepts an `SQL` object (it unpacks `code` and `params` and asserts no extra parameters were given); `env.execute_query(sql)` additionally flushes the fields mentioned in the query's metadata and returns rows.

Identifiers that come from the user, such as a sort column, must be validated against an allow-list **and** quoted with `SQL.identifier`; parameters cannot carry identifiers.

Raw SQL also bypasses every access layer: ACLs, record rules and field groups. Every raw query on a model with rules needs its own company and ownership conditions. The raw SQL chapter in the ORM part covers the cache and flush implications.

## 2. Domains and `eval`

A domain is data, not code. If it comes from outside, parse it as data:

```python
# WRONG: executes whatever arrives.
domain = eval(self.env.context["domain_text"])

# Better: safe_eval, restricted to a whitelist of operations.
from odoo.tools.safe_eval import safe_eval
domain = safe_eval(text, {"user": self.env.user, "time": time})

# Best: build the domain yourself from validated pieces.
domain = [("state", "=", "open")]
if member_id:
    domain.append(("member_id", "=", int(member_id)))
```

`eval` on request data is remote code execution. `safe_eval` removes most dangerous builtins, and the record rules use it for `domain_force`, but it is still meant for administrators' input, not anonymous visitors'. For filters coming from a web form, accept a field name from an allow-list and a value, and build the leaf yourself. Convert numbers with `int()` so a string cannot change the meaning of a condition, and do not allow arbitrary operators or paths: `('partner_id.user_ids.password', '!=', False)` is a way to probe data through a relational path.

## 3. `sudo()` and privilege escalation

`sudo()` is the largest source of leaks because it makes the right thing and the wrong thing look identical. Concrete rules, drawn from what the ORM does in superuser mode (ACL, record rules and field groups are skipped, `env.company` sanity checks are skipped):

```python
# WRONG: a public route that returns every loan.
@http.route("/library/loans", auth="public", type="json")
def loans(self):
    return request.env["library.loan"].sudo().search_read([], ["name", "member_id"])

# RIGHT: a user route, no elevation, rules do their job.
@http.route("/my/loans", auth="user", type="json")
def my_loans(self):
    return request.env["library.loan"].search_read([], ["name", "state"])
```

Guidelines:

1. Before any `sudo()`, name the reason in a comment, and ask whether the check can be done with `check_access` instead.
2. **Check first, elevate second.** If a portal user must trigger a write to a model they cannot touch, check that they may act on *this* record, then write the minimum:

```python
def action_extend(self, days):
    self.ensure_one()
    self.check_access("write")                 # as the caller
    self.sudo().write({"due_date": self.due_date + timedelta(days=days)})
```

3. Elevate the smallest scope: `record.sudo().field`, not `self.sudo()` for a whole method.
4. Never return a sudoed recordset or its data straight to the caller without deciding which fields are safe.
5. Never elevate based on a model name or record id from the request. `request.env[model].sudo().browse(id)` with both taken from parameters reads any record of any model.
6. In multi-company databases add the company explicitly to sudoed searches (see the multi-company chapter).
7. `with_user(SUPERUSER_ID)` is superuser mode by convention; treat it like `sudo()`.

## 4. Controllers

A route is the boundary between the world and your ORM code. For each route decide, from `odoo/http.py`:

| Decision | Options | Guidance |
| --- | --- | --- |
| Authentication | `auth='user'` / `'bearer'` (18) / `'public'` / `'none'` | `user` unless the content is truly public. `public` runs as the shared public user (or the logged-in one). `none` has no user at all. |
| Method | `methods=['POST']` | restrict; state changes belong to `POST` |
| CSRF | `csrf=True` (default for `type='http'`) | keep it. It is **off by default for `type='json'`** |
| CORS | `cors='*'` | only for APIs meant for other origins |

CSRF protection for `http` routes means forms must include the token:

```xml
<form method="post" action="/library/return">
    <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
    ...
</form>
```

Disabling it (`csrf=False`) is acceptable only for endpoints authenticated by something other than the browser session, such as a signature on a webhook, and then the signature check replaces it:

```python
from werkzeug.exceptions import Forbidden
from odoo import http
from odoo.http import request
from odoo.tools import consteq, hmac


@http.route("/library/webhook", type="http", auth="public", methods=["POST"], csrf=False)
def webhook(self, **kw):
    body = request.httprequest.get_data()
    sent = request.httprequest.headers.get("X-Signature", "")
    expected = hmac(request.env(su=True), "library-webhook", body)
    if not consteq(sent, expected):
        raise Forbidden()
    ...
```

Here the route is `auth="public"`, not `none`: with `auth="none"` there is no database environment to build the superuser environment from. (A real webhook from an external service signs with a secret shared with that service; use the `secret=` argument of `hmac` for that.)

Input handling rules:

- Treat every parameter as untrusted text. Convert with `int()` and catch `ValueError`; never pass `**kw` straight into `write` or `create` (mass assignment lets a caller set `state`, `user_id`, `company_id`):

```python
# WRONG
loan.write(kw)
# RIGHT
allowed = {"note"}
loan.write({k: v for k, v in kw.items() if k in allowed})
```

- Load records through the user's environment and let rules decide. For a record accessed with a token, use the portal helper that checks the token and then renders read-only, as the portal chapter shows.
- Do not echo exception messages from the database to the client.
- Redirect targets taken from parameters (`?redirect=/path`) must be validated, or the route is an open redirect. Accept only relative paths that start with a single `/`.
- `type='json'` routes receive JSON; routes that accept file uploads must check size, type and name.

## 5. HTML output and XSS

QWeb escapes by default: `t-out` and `t-esc` escape text. The danger is values wrapped as safe:

```python
from markupsafe import Markup

# WRONG: a user-controlled string marked safe.
body = Markup(user_text)

# RIGHT: escape, or build with Markup.format, which escapes arguments.
body = Markup("<p>%s</p>") % user_text
body = Markup("<b>{}</b>").format(user_text)
from odoo.tools import html_escape         # markupsafe.escape in 18
safe_text = html_escape(user_text)
```

Rules:

- `Markup(x)` is a promise that `x` is already safe HTML. Applying it to user text breaks the promise. Interpolate into a `Markup` template with `%` or `.format`; both escape the arguments.
- `t-out` of a `Markup` value is not escaped. In OWL JavaScript, `t-out` renders HTML only for values wrapped with `markup()`; never wrap user text.
- `t-raw` and `t-esc` are marked deprecated in the QWeb reference of 18 ("please use `t-out`"). If you meet `t-raw` in an old module, replace it with `t-out` and check that every value rendered unescaped is intended.
- **`fields.Html` sanitises by default.** The parameters in 18 are `sanitize` (default `True`), `sanitize_overridable` (default `False`; when true, users in `base.group_sanitize_override` may bypass it), `sanitize_tags`, `sanitize_attributes`, `sanitize_style` (default `False`), `sanitize_form`, `sanitize_conditional_comments` (default `True`). Turning sanitisation off (`sanitize=False`) for a field that users can edit is stored XSS for everyone who views it. Leave the default unless the content comes only from trusted staff.
- `html_sanitize(src)` in `odoo.tools.mail` is the function the field uses; call it explicitly when you accept HTML into a non-Html field.
- Do not put user data into `<script>` blocks, `href="javascript:"` URLs, or inline event handlers. Encode data attributes with `t-att-` instead of string concatenation.
- Mail templates: values rendered into HTML bodies are escaped; subject and `Markup` handling follow the same rules.

## 6. Secrets, tokens and comparisons

- **Never store credentials in code or in the repository.** Use system parameters (`ir.config_parameter`) read through the ORM as superuser, or environment variables, or the configuration file. System parameters are readable only by the Settings group; do not expose `ir.config_parameter` to ordinary users.
- **Tokens must be unguessable.** Use `secrets.token_urlsafe(32)` or `uuid.uuid4().hex` for access tokens, not a counter, a timestamp, or an id.
- **Compare secrets in constant time.** `tools.misc.consteq` is `hmac.compare_digest`; use it for tokens and signatures, never `==`.
- **Sign, do not just encode.** `odoo.tools.hmac(env, scope, message)` computes a SHA-256 HMAC with the database's `database.secret` as key. The mandatory non-empty `scope` makes the same message produce different signatures in different features, so a token minted for one purpose cannot be replayed for another. `env` must be a sudo environment (it reads the config parameter). For tokens that carry data, `odoo.tools.hash_sign(env, scope, message_values, expiration=None, expiration_hours=None)` produces a URL-safe signed payload with optional expiry (the docstring compares it to a JWT), and `verify_hash_signed` checks it.
- API keys of users (`res.users.apikeys`) are managed by core. Do not invent a parallel scheme; for outbound calls from your module, store third-party keys in a protected system parameter or a field with `groups=` and read it with `sudo()` in the one method that needs it.
- Do not log secrets, request bodies containing passwords, or full tokens. Logging a truncated hash is fine.

## 7. Files and paths

- `tools.file_open(name, mode, filter_ext)` opens a file located **inside an addons path directory** and rejects anything else; prefer it to `open()` for module resources. Pass `filter_ext` to restrict extensions.
- When you build a path from a request parameter, join it with `werkzeug.security.safe_join(directory, path)` (the web controller does exactly this for static files). It returns `None` for a path that escapes the directory.
- Never use a user-supplied name directly as a filename or as `ir.attachment` `name` for a file served back with that name. Strip path separators and control characters.
- Uploaded files: check size and content type; remember attachments are served by `/web/content` according to the access of the record they belong to, and a `public=True` attachment is readable by anyone with the URL.
- Do not unpickle, `yaml.load`, or `eval` uploaded data. Use `json` or `yaml.safe_load`.
- Temporary files: use `tempfile` and delete them; `file_open_temporary_directory` exists for code that must read from a temp directory.

## 8. Denial of service and resource abuse

- A public route that does unbounded work (search without limit, export of all records, PDF generation) is a free DoS. Add limits and pagination, and put expensive endpoints behind authentication.
- Do not `search([])` an unbounded model inside a request.
- Sleeping, long loops or external calls inside a request hold a worker. Move them to a queue or cron (the queues chapter).
- Regular expressions on user input can backtrack catastrophically; prefer simple parsing.

## 9. Logging and information disclosure

- Do not return Python tracebacks or SQL errors to clients. The framework's default error handling for `http` routes hides them in production; a route that catches `Exception` and returns `str(e)` undoes that.
- `AccessError` messages are designed to be shown to the user; do not replace them with a message that reveals record ids or rule domains.
- Keep debug mode off in production: it adds the developer menu and technical details to access errors for users with `base.group_no_one`.

## A review checklist

Run this against every module before it ships:

1. `grep -rn "execute(" --include=*.py` and read each one: parameters or `SQL`, never `%`/`format`/f-string on the query.
2. `grep -rn "sudo()" --include=*.py`: for each, the reason, the scope, the check done before.
3. `grep -rn "eval(" --include=*.py` and `grep -rn "Markup(" --include=*.py`: where does the argument come from?
4. Every `@http.route`: `auth`, `methods`, `csrf`, what is read from `kw`, what is returned.
5. Every `fields.Html(sanitize=False)` and every `t-out` of a value that came from a user.
6. Every secret and token: how generated, how compared, where stored.
7. Every file access built from a parameter.
8. Every ACL row with an empty group, every global rule's domain, every `groups=` on a field holding personal data.
9. The test that logs in as an ordinary user and as a portal user and tries to read another user's record.

## Pitfalls

{% hint style="warning" %}
`Markup(user_text)` is not escaping. It is the opposite: it tells the template engine not to escape.
{% endhint %}

- **`cr.execute(query % value)`** and f-strings in queries.
- **A dynamic string passed as `SQL` code.** The safety guarantee is for literals.
- **`**kw` into `write` or `create`.**
- **`csrf=False` without another authentication.**
- **`auth='public'` with `sudo()` returning records.**
- **`sanitize=False` on a user-editable Html field.**
- **Comparing tokens with `==`.**
- **Using a record id or timestamp as an access token.**
- **`request.env[model]` with a model name from parameters.**
- **Open redirects through a `redirect` parameter.**
- **Logging secrets.**
- **Relying on hidden buttons and menus instead of server checks.**

## Versions

{% hint style="info" %}
**16:** the `SQL` class does not exist (absent from the 16.0 `tools/sql.py`); pass parameters to `cr.execute`. Use `check_access_rights` and `check_access_rule`. `auth='bearer'` is not available.

**17:** the `SQL` class exists in `odoo/tools/sql.py` (checked on the 17.0 branch). Check whether `env.execute_query` exists on your 17 build before using it, as it was only verified on 18.

**18:** everything above. `check_access_rights` is deprecated; `check_access` is the form to use.

**20:** `@route(type='json')` is a deprecated alias of `type='jsonrpc'` (since 19). The helpers named here (`SQL`, `consteq`, `hmac`) were checked in the 18 source; re-check them in 20 before relying on a signature.
{% endhint %}

## Try it

1. Write a controller method that searches `library.book` by a `name` parameter with the string-formatting form, then call it with `x' OR '1'='1`. Replace it with the parameterised form and repeat.
2. Run the review checklist's first three greps on your own module and fix what they find.
3. Add a webhook route that verifies an HMAC with `tools.hmac` and `consteq`, and test it with a wrong and a correct signature.
4. Log in as a portal user and request `/my/loans/<id>` for someone else's loan.

<details>

<summary>Solution notes</summary>

1. The formatted query returns every book because the injected quote closes the string and `OR '1'='1'` is always true; the parameterised version treats the whole text as one value and returns nothing.
2. Typical finds are `cr.execute(... % ...)`, `sudo()` inside `search`, and `Markup(...)` around request data.
3. The route must return 403 for a wrong signature and process the body for a correct one; the scope string you pass to `hmac` must match on both sides.
4. The route should redirect to `/my` or return 403; any data returned means the access check is missing.

</details>
