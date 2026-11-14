---
description: "What env carries, how to change it, and when sudo is the wrong answer."
---

# Environment, context, and sudo

Every recordset carries an environment: the cursor, the user, the context dictionary and (in 17 and 18) the company set. Changing any of them creates a new recordset bound to a new environment. The original is untouched.

## What env holds

```python
self.env.cr          # database cursor, one transaction
self.env.uid         # user id
self.env.user        # res.users record
self.env.context     # frozen dict
self.env.company     # current company
self.env.companies   # allowed companies, selected in the UI
self.env.lang        # context['lang']
```

`env.context` is immutable. You never modify it; you derive a new one.

## with_context

```python
books = self.with_context(active_test=False).search([])      # include archived
books = self.with_context(lang='fr_FR')                      # read translations
```

`with_context(**kw)` merges keys into the existing context. `with_context(dict)` replaces the whole context, dropping `lang`, `tz`, `allowed_company_ids` and everything else. Merge on purpose:

```python
ctx = dict(self.env.context, default_state='draft')
```

Context keys with a meaning in the framework:

| Key | Effect |
|---|---|
| `active_test` | `False` makes `search` ignore `active` |
| `lang`, `tz` | translation and timezone of reads |
| `allowed_company_ids` | companies the user selected; first one is the current company |
| `default_<field>` | default for that field on `create` and `default_get` |
| `tracking_disable`, `mail_notrack` | no chatter tracking |
| `prefetch_fields` | `False` disables fetching other fields when you read one |

## with_user and sudo

```python
self.with_user(other_user)   # runs with that user's rights and rules
self.sudo()                  # superuser: bypasses access rights and record rules
```

`sudo()` returns a recordset in superuser mode: access rights and record rules do not apply. In Odoo 13 and later it does not switch the user: `self.env.user` stays the same, and `create_uid` / `write_uid` still record the real user. Only `env.su` becomes `True`.

```python
self.env.su          # True inside sudo
self.env.is_superuser()
self.env.is_admin()  # user is in base.group_system, or superuser
```

`sudo(False)` goes back to normal mode. Use `with_user(SUPERUSER_ID)` only when you need the superuser as the actual user; it behaves differently from `sudo()` for `create_uid` and for rules that mention `user`.

Records read through a `sudo` recordset keep the superuser flag when you follow relations, so `book.sudo().partner_id.company_id` is entirely unrestricted.

## with_company and companies

```python
self.with_company(company)   # changes env.company and prepends it in allowed_company_ids
```

Company-dependent fields (`company_dependent=True`) and multi-company record rules read the context, so a method that works for one company silently returns another company's values if you forget `with_company`. Many fields use `@api.depends_context('company')` for exactly this reason.

## with_env and new cursors

`with_env(env)` rebinds records to another environment. A new cursor is for work that must commit independently of the caller, such as logging an error that survives a rollback:

```python
from odoo import api, registry

with self.pool.cursor() as cr:
    env = api.Environment(cr, self.env.uid, self.env.context)
    env['library.log'].create({'message': 'failed'})
```

The new cursor sees only committed data and commits on exit. Records created in the parent transaction are invisible to it, and it can deadlock against rows the parent holds.

## Access checks in 18

`check_access_rights` and `check_access_rule` still exist, but Odoo 18 adds `records.check_access('read')` which does both in one call, and `records.has_access('read')` which returns a boolean. Use those in new code.

{% hint style="info" %}
Versions: `check_access` and `has_access` exist from 18. In 16 and 17, use `check_access_rights(op)` plus `check_access_rule(op)`.
{% endhint %}

## When sudo is the wrong answer

`sudo()` is a decision about trust. Reach for it when the code runs on behalf of the system for a legitimate reason: reading a sequence, reading a configuration record, posting a technical message. Do not use it to make an error go away.

Narrower options:

- `with_user` to a service user with the minimum groups.
- Add a record rule or an access line that expresses the real requirement.
- Have the method run in a controller with `auth='public'` plus an explicit lookup, not a blanket `sudo()` on an entire search.
- Sudo a single read, not the whole method: `self.env['ir.config_parameter'].sudo().get_param(...)` instead of `self = self.sudo()` at the top.

## Pitfalls

{% hint style="danger" %}
`self.sudo().write(vals)` where `vals` came from a request is privilege escalation. Validate which fields are allowed, then sudo the minimum.
{% endhint %}

- Records created with `sudo()` have `create_uid` of the real user, so rules based on ownership still match, but company rules read the context and may not.
- `self.env.user` inside `sudo` is not the superuser. Code that tests `self.env.user.has_group(...)` is evaluated against the real user.
- `with_context(dict)` replaces the context. Forgetting to merge loses `lang` and `allowed_company_ids`.
- A recordset passed to another method keeps its environment. A `sudo` recordset leaks the privilege to every callee.
- `ir.rule` evaluation caches by context; changing `allowed_company_ids` mid-method invalidates it.

## Try it

```python
print(env.su, env.uid, env.user.name)
sudo_books = env['library.book'].sudo()
print(sudo_books.env.su, sudo_books.env.uid)   # True, same uid
```
