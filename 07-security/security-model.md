---
description: Layers of access control and how they combine.
---

# The security model

Odoo checks access in several independent layers, and a user needs to pass all of them for a given operation. Knowing which layer rejected a request is most of the work when you debug an `AccessError` or a "record is missing" report.

## The layers

From the outside in:

1. **Authentication.** A session (cookie), an API key, or a password. This decides who `env.user` is.
2. **Menus and actions.** `ir.ui.menu` and `ir.actions.*` can carry `groups_id`. This is navigation only: it hides entry points, it does not protect data.
3. **Model access** (`ir.model.access`). Per model, per group, four flags: read, write, create, unlink. No matching ACL means no access for non-superusers.
4. **Record rules** (`ir.rule`). Domain filters on which rows of a model a user may touch, per operation.
5. **Field groups.** The `groups=` attribute on a field removes the field for users outside the group.
6. **Code-level checks.** `check_access`, `sudo()`, controllers with `auth=` and your own validation.

Layers 3 and 4 are enforced by the ORM on every `read`, `search`, `write`, `create` and `unlink`. Layers 2 and 5 are partly cosmetic, see the pitfalls.

## How the ORM applies them

For a normal call, the sequence is: check the ACL for the model, then add the record rule domain to the query (for `search` and `read`) or check it against the records (for `write` and `unlink`). A user without the ACL gets an `AccessError`. A user who fails only the rule sees fewer rows, or gets an `AccessError` when they target a specific record.

```python
book = self.env['library.book'].browse(42)
book.check_access('write')            # ACL + rules; raises AccessError (18)
book.has_access('write')              # same check, returns bool (18)
```

{% hint style="info" %}
Versions: in Odoo 16 the methods are `check_access_rights(op, raise_exception=True)` and `check_access_rule(op)`, called separately. Odoo 17 added `has_access` and `check_access` as the preferred API; Odoo 18 deprecates the old pair in favour of them. Verify the deprecation warning on your own build before bulk-renaming.
{% endhint %}

## The superuser and sudo

User id 1 (`OdooBot`, `base.user_root`) bypasses ACLs and rules. `sudo()` returns a recordset whose environment uses that superuser flag while `env.uid` stays the same, so `create_uid` and the `env.user` expression in code still refer to the caller. `sudo()` also skips record rules in your own code path, which is the main way developers open security holes by accident.

```python
# Reads a record the user cannot see; returns data they should not get.
return self.env['library.loan'].sudo().search([]).mapped('borrower_id.email')
```

## Combining groups

A user belongs to many groups, directly or through `implied_ids`. For ACLs, permissions are cumulative: if any of the user's groups grants `write`, the user can write. For record rules the combination is different, and covered in the record rules chapter: group rules are OR-ed, global rules are AND-ed.

An ACL line with an empty group applies to everybody, including portal and public users. That is occasionally correct for a lookup table, and almost always a mistake for business data.

## Where the definitions live

The base module ships `base/security/base_groups.xml`, `base_security.xml` and `ir.model.access.csv`. Your module adds its own `security/` folder:

```
library/
  security/
    library_security.xml     # groups, categories, record rules
    ir.model.access.csv      # ACLs
```

Load order matters: the manifest `data` list must load the XML (which creates the groups) before the CSV that references them. A CSV row referencing a group that does not exist yet fails the module install.

## Pitfalls

{% hint style="warning" %}
Hiding a menu or a button is not security. Anyone who can call the model through RPC (`/web/dataset/call_kw`) bypasses the view. Always protect the model with an ACL, and the rows with a rule.
{% endhint %}

- **Models without ACLs.** A new model with no CSV line is unreadable for everyone except the superuser, and the log shows a warning at load. A transient model (wizard) does not need ACLs in 18; a regular one does.
- **`sudo()` in compute methods.** Stored computes often run as the user who triggered the recompute. Using `sudo()` inside is fine; returning sudo'd recordsets to the caller leaks privileges.
- **Testing as admin.** The admin user is in the settings group, which implies many other groups. A feature that "works" as admin may be blocked for a normal employee. Test with a plain user.
- **Portal and public users.** They are real `res.users`, with real ACL checks. Controllers using `auth='public'` run as the public user, so ORM calls there need explicit `sudo()` and manual checks.

## Try it

Check what a specific user can do without logging in as them, in a test or shell session you already own:

```python
user = env['res.users'].search([('login', '=', 'demo')], limit=1)
Book = env['library.book'].with_user(user)
Book.has_access('read'), Book.search_count([])
```
