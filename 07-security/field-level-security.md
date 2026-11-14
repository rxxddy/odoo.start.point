---
description: "The groups attribute on fields: what the ORM does with restricted fields on read, write, search and in views, and how not to leak them through computed fields."
---

# Field-level security

Sometimes the model is open but one column is not: a member's phone number, a loan's internal notes, a price. A field's `groups` attribute removes the field from every user outside the listed groups.

Checked against `odoo/fields.py` (`Field.is_accessible`, `NO_ACCESS`) and `odoo/models.py` (`check_field_access_rights`, `fields_get`, `_fetch_field`) of Odoo 18, and the 20 tree where noted.

## The attribute

```python
class LibraryMember(models.Model):
    _name = "library.member"

    name = fields.Char(required=True)
    phone = fields.Char(groups="library.group_library_manager")
    internal_note = fields.Text(groups="library.group_library_manager,base.group_system")
    legacy_token = fields.Char(groups=fields.NO_ACCESS)     # nobody, ever, but the superuser
```

`groups` is a comma-separated list of fully-qualified group external ids. A user passes if they are in **at least one** of them. Each id may be preceded by `!` to exclude a group (`groups="base.group_user,!base.group_system"`), the same syntax as in views. The constant `fields.NO_ACCESS` is the string `'.'`: a field with it is accessible to nobody but superuser mode.

The rule, in one function (`Field.is_accessible`):

```python
if not self.groups or env.is_superuser():
    return True
if self.groups == '.':
    return False
return env.user.has_groups(self.groups)
```

The check applies to every ORM path below. It does **not** apply to raw SQL, and it does not apply in `sudo()` mode.

## What the ORM does

| Operation | Behaviour for a user outside the groups |
| --- | --- |
| `fields_get()` | the field is **not in the result**, so it is also unknown to the web client |
| `read()` / `search_read()` with **no field list** | returns only the accessible fields |
| `read(["phone"])` naming the field | raises `AccessError`: "You do not have enough rights to access the fields ..." |
| `record.phone` | triggers a read of that field: `AccessError` |
| `write({"phone": ...})` / `create({"phone": ...})` | `AccessError` |
| `search([("phone", "=", ...)])`, `order` or `groupby` on it | `AccessError`: every use of a column in SQL goes through `_field_to_sql`, which calls `check_field_access_rights('read', ...)` |
| `_fetch_field` / prefetch | fields the user cannot access are **excluded from the prefetch group**, so touching `name` never pulls `phone` into the cache |

The message names the fields. For users with `base.group_no_one` (technical features, debug mode) it adds the groups that would give access, or "always forbidden" for `NO_ACCESS`, which helps administrators and nobody else.

Two things follow:

- **Leaking by absence is not a leak.** A form view that contains `<field name="phone"/>` is processed for the user; because the field is not in `fields_get` for them, the node is dropped. You need no `groups` on the view node for the protection to hold, but you should add it so the view is self-explanatory and the arch stays valid for users who lack the field.
- **Code that reads the field must expect `AccessError`.** A method that does `self.phone` runs as the calling user. If any ordinary user may trigger it, it fails for them. Either do not read the field there, or use a deliberate escalation (below).

## Reading a protected value on purpose

When a feature must use a protected value without revealing it, read it in a narrow `sudo()` and return only what is safe:

```python
def _phone_is_set(self):
    # exposes whether a phone exists, never the number
    return bool(self.sudo().phone)

def action_call_member(self):
    self.ensure_one()
    self.check_access("read")                    # record rules still apply to the caller
    return {"type": "ir.actions.act_url", "url": f"tel:{self.sudo().phone}"}
```

The second example deliberately returns the number to anyone who can reach the button. If only managers should do that, check `has_group` first. Field `groups` stops accidental exposure; it is not an authorization system for features.

## Computed and related fields

A computed field is **its own field** with its own `groups` (none by default). If it derives from a protected field, it can leak it:

```python
# Leaks: anyone can read masked_phone, and the mask may reveal too much.
phone_last4 = fields.Char(compute="_compute_phone_last4")

@api.depends("phone")
def _compute_phone_last4(self):
    for rec in self:
        rec.phone_last4 = (rec.phone or "")[-4:]
```

Questions to ask, in order:

1. Does the compute method run as the reading user? For a **non-stored** field, yes: the method reads `rec.phone` as that user, so for an unauthorised user the computation raises `AccessError`. That is safe but turns into an error. For a **stored** field the recompute runs as superuser (see 2), so the value is stored and readable by everyone who can read the new field, which is a leak.
2. `compute_sudo=True` makes the compute run elevated. That is what you need when the value is meant for everybody, and what makes a leak possible. In the 18 source the default is `compute_sudo = store`: stored computed fields recompute as superuser, non-stored ones run as the reading user.
3. Put the same `groups` on the derived field when it carries the sensitive information, or reduce what it carries so that publishing it is harmless.

A `related` field is different: when it sets up, it copies `string`, `help`, `groups` and a few other attributes from the target field unless you set them yourself (`setup_related` in `fields.py` only copies an attribute that is not explicitly defined on the related field). So `related="member_id.phone"` inherits the target's `groups`. Two cautions: the copy happens only when you did not pass `groups=` yourself, so passing a weaker one on purpose overrides the protection, and related fields default to `compute_sudo=True` (through `related_sudo`), so the value is read with elevated rights and only the copied `groups` stands between the user and the number. State it explicitly so the intent is visible:

```python
member_phone = fields.Char(related="member_id.phone", groups="library.group_library_manager")
```

## Hiding in views versus protecting

| | View `groups` attribute | Field `groups` attribute |
| --- | --- | --- |
| Where | XML arch node | Python field |
| What it does | removes the node for users outside the groups | removes the field from the model for them |
| Stops RPC reads | **no** | yes |
| Stops reports, exports, search | no | yes (they use the ORM) |
| Use for | layout and convenience | data protection |

Use both: the field attribute protects the data, the view attribute keeps the form tidy for each audience and lets the same view serve groups with different access.

```xml
<group string="Contact" groups="library.group_library_manager">
    <field name="phone"/>
    <field name="internal_note"/>
</group>
```

## Exports and reports

The standard export dialog uses the ORM, so protected fields are not offered to users without access. A QWeb report reads fields as whoever renders it. If the report prints a protected field, restrict the report action itself to the authorised groups, and review any custom route that renders a report under `sudo()`: elevated rendering bypasses field access.

## Raw SQL, `search_read` on `_rec_name`, and other bypasses

- `self.env.cr.execute("SELECT phone FROM library_member")` bypasses ACLs, rules and field groups. Raw SQL is for trusted code and needs its own checks, covered in the raw SQL and secure coding chapters.
- `display_name` is computed from the record's `_rec_name` field. If that field is protected, users without access cannot build a display name for the record. Do not protect the field used as the record name.
- `Many2one` widgets read the display name through `name_search`. Make sure the comodel's `_rec_name` is accessible to everyone who can reach the relation.
- A `default_get` or an onchange that reads a protected field runs as the user and raises for those without access.

## Odoo 20

The mechanism is the same in the Odoo 20 tree: `is_accessible`, the `'.'` value (`NO_ACCESS`) and the `groups` syntax. Group external ids themselves differ per application (the groups chapter shows the privilege-based layout). Re-check group ids you name in `groups=` when you port.

## Pitfalls

{% hint style="warning" %}
A computed field that derives from a protected field is a new field with its own access. Give it the same `groups`, or make sure it carries nothing sensitive.
{% endhint %}

- **Protecting only in the view.** The data is one `search_read` away.
- **A protected `_rec_name`.** `display_name` fails for everyone outside the groups.
- **A stored computed field with `compute_sudo=True`** over a protected field. The value is computed with elevated rights and is readable by all.
- **Overriding `groups` on a related field with something weaker** than the target's. The related read runs elevated, so the related field's own `groups` is the only guard.
- **Business methods reading a protected field for ordinary users.** They raise `AccessError`. Test as an ordinary user.
- **Searching or grouping by a protected field in a default filter** shipped to everyone. It raises for those without access and the whole view fails.
- **Typos in group ids.** A wrong id makes `has_groups` fail or the field inaccessible for all; install-time checks do not always catch it.
- **Relying on field groups for the superuser case.** `sudo()` bypasses them entirely.
- **Assuming translations or attachments are covered.** Attachments have their own access through `ir.attachment` and the record they belong to.

## Versions

{% hint style="info" %}
**16 and 17:** `groups` works the same way. The `NO_ACCESS` constant should not be assumed on 16; the string `'.'` is what it stands for.

**18:** `fields.NO_ACCESS` exists and `Field.is_accessible` is the single check.

**20:** same semantics.
{% endhint %}

## Try it

1. Add `phone` with `groups` as above. As a plain user, run `env["library.member"].with_user(user).fields_get()` and look for `phone`.
2. As the same user, call `search_read([], [])`, then `read(["phone"])`. Compare.
3. Add the `phone_last4` computed field without groups, read it as the plain user, and then with `compute_sudo=True`.
4. Add `groups` to the view node but not to the field. Confirm the data is still reachable over `read`.

<details>

<summary>Solution notes</summary>

1. `phone` is absent from the result.
2. The first returns only accessible fields; the second raises an `AccessError` naming `phone`.
3. Without `compute_sudo` the compute raises for the plain user because it reads `phone`; with it the value is computed elevated and the last four digits become readable, which is the leak.
4. The form hides the field but `read(["phone"])` succeeds, because only the field attribute protects data.

</details>
