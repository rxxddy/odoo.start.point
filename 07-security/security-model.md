---
description: "The layers that decide who can see and change what in Odoo, in the order they are applied, with the exact source behind each."
---

# The security model

Odoo security is not one mechanism. It is five layers stacked on top of each other, each answering a different question, and almost every security bug in a custom module comes from a developer assuming one layer does the work of another. This chapter lays out the layers, shows where each is enforced in the source, explains the superuser and `sudo()`, and gives a decision procedure for "where should this rule live?". The following chapters go deep on each layer.

Checked against the Odoo 18 source (`odoo/models.py`, `odoo/api.py`, `odoo/addons/base/models/ir_model.py`, `ir_rule.py`, `res_users.py`). Version differences are at the end.

## The five layers

| Layer | Question it answers | Defined by | Enforced by |
| --- | --- | --- | --- |
| 1. Authentication | Who is this? | login, session cookie, API key | `odoo/http.py` (`auth=` on routes) |
| 2. Entry points | Which menus, actions, buttons and views does this user see? | `groups` on menus, actions, views, view nodes | the web client and `ir.ui.view` processing |
| 3. Model access (ACL) | May this user read/write/create/delete records of this model at all? | `ir.model.access` | `ir.model.access.check` |
| 4. Record rules | On which rows of that model? | `ir.rule` | `ir.rule._compute_domain` |
| 5. Field access | Which columns? | `groups=` on fields | `Field.is_accessible`, `check_field_access_rights` |

Layers 3 to 5 live in the ORM. They apply to **every** ORM call from every caller: a button, an RPC, a cron, a controller, an `odoo shell` session. They do not apply when the code runs in superuser mode.

Layers 1 and 2 are not security boundaries on their own. A hidden menu is not a locked door: the user can still call the underlying model over RPC. Only layers 3 to 5 protect data, and only code in your own methods protects anything beyond them.

## Layer 1: authentication

Every route declares how its caller is identified (`@http.route(auth=...)`, documented in `odoo/http.py`):

| `auth` | Meaning |
| --- | --- |
| `'user'` | a logged-in user is required; the request runs with that user's rights |
| `'bearer'` | the `Authorization: Bearer <api token>` header identifies the user; without the header the request must belong to a session, as for `user` |
| `'public'` | the user may be anonymous; if so the request runs as the shared public user |
| `'none'` | active even without a database; no user available. For framework and login code |

`'bearer'` appears in the 18 docstring; do not assume it exists on 16 or 17. For JSON-RPC and XML-RPC calls to the ORM from outside, authentication is by login plus password or API key, and the call then runs as that user with all of layers 3 to 5.

CSRF protection is also a property of the route, enabled by default for `type='http'` and disabled by default for JSON routes. The secure-coding chapter covers it.

## Layer 2: entry points

`groups` can be set on `ir.ui.menu`, `ir.actions.act_window` and the other action types, `ir.ui.view` records, and on individual nodes in view XML (`<field groups="...">`, `<button groups="...">`, `<group groups="...">`). The server strips nodes the user's groups do not allow before sending the view, and the client does not show menus the user cannot open.

This is a usability layer. The security statement you can make about it is weak: "a user without the group will not normally see this". Anything that must hold goes into layers 3 to 5.

## Layer 3: model access control lists

`ir.model.access` rows grant `perm_read`, `perm_write`, `perm_create` and `perm_unlink` on a model to a group. Rules about them:

- **Additive, never subtractive.** A user gets the union of the rows of all their groups. There is no deny.
- A model with **no ACL rows at all** is closed to everybody except the superuser: the check is "is this model in the set of models this user may access in this mode", computed from the rows of the user's groups (`_get_allowed_models` in `ir_model.py`).
- A row with an **empty group** grants everyone. Odoo logs a warning when you create one: "Every access-granting rule should specify a group."
- The result is cached in the registry and cleared when ACL rows change (`call_cache_clearing_methods`).

The check is `ir.model.access.check(model, mode, raise_exception)`. In the ORM it is reached through `check_access`, `has_access` and the CRUD methods.

## Layer 4: record rules

`ir.rule` rows add a domain to a model for the operations they cover. The ORM computes, for the current user, model and operation, one final domain:

```
AND( global_rule_domains..., OR( domains of the group rules the user belongs to ) )
```

with two details that surprise people, both visible in `_compute_domain` of `ir_rule.py`:

1. **If the model has group rules but the user belongs to none of those groups, the OR part vanishes and only global rules remain.** So a model with only group-scoped rules is *unrestricted* for users outside those groups, as long as their ACL lets them in. Restricting "everyone except managers" needs a global rule.
2. For models using `_inherits`, the parents' rules are folded in as `('parent_field', 'any', parent_domain)`.

The record rules chapter is the detailed treatment.

## Layer 5: field access

A field with `groups="library.group_library_manager"` is invisible and unwritable for users outside the group: `Field.is_accessible(env)` returns `True` when the field has no groups or the environment is superuser, `False` when `groups == '.'` (a special value meaning "always forbidden"), and otherwise whether `env.user.has_groups(self.groups)`. Reading or writing such a field as a user without the group raises an `AccessError` that names the fields, and the field disappears from `fields_get`.

## The order in which the ORM applies them

For `records.read()`, `search()`, `write()`, `unlink()` and `create()` as a normal user the sequence is:

1. ACL check for the operation on the model (`ir.model.access.check`). Failing here raises `AccessError` mentioning the groups that would grant access.
2. For operations on existing records, the record rule domain for that operation. For `search` and `read` it is added to the SQL query, so unauthorised rows silently disappear. For `write` and `unlink` the records are checked and failing ones produce an `AccessError` that names the rule.
3. Field-level check for the fields involved.

In Odoo 18 steps 1 and 2 are exposed together through three methods on recordsets:

```python
records.check_access("write")          # raises AccessError if forbidden on the model or any record
records.has_access("write")            # same, returns a boolean
records._filtered_access("write")      # subset of records the user may write
```

Calling `check_access` on an **empty** recordset checks the model-level ACL only, which is the right way to ask "may this user write to this model at all?" before showing a button.

The older names `check_access_rights`, `check_access_rule` and `_filter_access_rules` still exist in 18 but are deprecated since 18.0 and emit a `DeprecationWarning`.

## The superuser and `sudo()`

Superuser mode (`env.su` is true) turns layers 3 to 5 off:

- `ir.model.access.check` returns `True` immediately.
- `ir.rule._get_rules` returns an empty set, so no rule applies.
- `Field.is_accessible` returns `True`.
- `check_access` does nothing.

Two ways to be in it:

- `records.sudo()` keeps the current user (so `env.user` is unchanged, `create_uid` is still them) but switches the checks off. `sudo(False)` switches them back on.
- User id 1, `base.user_root` ("OdooBot"), is always in superuser mode by convention. `with_user(user)` returns an environment with `su=False` unless the user is the superuser.

The administrator user (`base.user_admin`, id 2) is a normal user who belongs to many groups. It is **not** in superuser mode. Record rules apply to it, and a multi-company rule can hide records from the administrator.

The environment exposes `env.is_superuser()`, `env.is_admin()` (has the "Access Rights" group, or superuser) and `env.is_system()` (has the "Settings" group, or superuser).

The docstring of `sudo` in 18 warns in so many words that it "could cause data access to cross the boundaries of record rules, possibly mixing records that are meant to be isolated (e.g. records from different companies)", and that methods which select one record among many, such as getting the default company, can give unintuitive results. Treat every `sudo()` as a line in a security review.

```python
# Wrong: returns data the caller cannot see, to the caller.
def action_show_all_loans(self):
    loans = self.env["library.loan"].sudo().search([])
    return {"domain": [("id", "in", loans.ids)], ...}

# Right: let the rules decide.
def action_show_loans(self):
    loans = self.env["library.loan"].search([])
```

When elevation is genuinely needed (a portal user triggers a job that must write to a model they cannot touch), do the **check first as the user**, then sudo only the narrow write:

```python
def action_extend(self, days):
    self.ensure_one()
    self.check_access("write")                 # as the real user
    self.sudo().write({"due_date": self.due_date + timedelta(days=days)})
```

## Combining groups

The ladder pattern keeps this manageable: an application defines groups where each higher group *implies* the lower (`implied_ids`), and each ACL line is granted to the lowest group that needs it. The groups chapter shows it in XML.

## Where the definitions live

| Piece | File in a module | Loaded as |
| --- | --- | --- |
| Groups, categories | `security/library_security.xml` | data |
| ACLs | `security/ir.model.access.csv` | data, after the model exists |
| Record rules | `security/library_security.xml` | data |
| Field groups | Python, `fields.X(groups="...")` | code |
| Menu/action/view groups | the `groups` attribute in XML | data |

The manifest `data` list order matters: the CSV references `model_library_book`, so models must be loaded before it, which they are (models load before data files), and group XML ids must exist before the CSV that names them, so list the groups file first.

## A decision procedure

When someone says "user X must not see Y", ask in this order:

1. **Is it the whole model?** Add or remove ACL rows. Lowest group that needs it.
2. **Is it some rows?** A record rule. Decide global or group-scoped using the AND/OR rule above.
3. **Is it one or two columns on rows the user may otherwise see?** A field `groups`.
4. **Is it an action (a button) rather than data?** Check in the method with `check_access` or `user.has_group`, and hide the button with `groups` as convenience.
5. **Is it something only some code paths may do?** Put the check in that code, never only in the view.

## Pitfalls

{% hint style="warning" %}
Hiding a menu or a button is not security. Any user with the right ACL can call the model over RPC regardless of what the web client shows.
{% endhint %}

- **A model with only group-scoped rules.** Users outside those groups are not restricted. Add a global rule to restrict everybody.
- **`sudo()` on a search, then returning the records.** The caller sees what the rules were meant to hide.
- **ACL rows with an empty group.** They grant everyone, including portal and public users if the model is reachable.
- **Assuming the administrator bypasses rules.** User 2 does not; only user 1 and `sudo` do.
- **Checking `has_group` in the view only.** Re-check in the method that performs the action.
- **Using `check_access_rights` in new code on 18.** It is deprecated since 18.0; use `check_access` or `has_access`.
- **Testing as admin.** Admin passes most checks. Test with `with_user` of an ordinary user.
- **Forgetting that cron and server actions run as superuser or a configured user.** They bypass or inherit rights differently from a button click.

## Versions

{% hint style="info" %}
**16 and 17:** the deprecated method names (`check_access_rights`, `check_access_rule`) are the only ones. The `auth='bearer'` route option should not be assumed. Rule domains use `user`, `time`, `company_ids`, `company_id`.

**18:** `check_access`, `has_access`, `_filtered_access`. The deprecated names remain with warnings. `auth='bearer'` is documented in `http.route`.

**20:** groups are filed under privileges (`privilege_id`), members are `user_ids`, and the user's groups are `group_ids`/`all_group_ids`. Odoo 19 was not available to check. Do not copy 18 group XML into 20.
{% endhint %}

## Try it

1. In an Odoo shell, as the administrator, run `env["library.loan"].check_access("read")` and then `env["library.loan"].with_user(some_portal_user).check_access("read")` and compare.
2. Print the final domain a user gets for a model: `env["ir.rule"].with_user(user)._compute_domain("library.loan", "read")`.
3. Compare `env["library.loan"].with_user(user).search_count([])` with `.sudo().search_count([])`.

<details>

<summary>Solution notes</summary>

1. The administrator passes; a portal user raises `AccessError` unless an ACL row grants their group read.
2. The result is a normalised domain list: global rule domains ANDed with the OR of the group rules that the user belongs to. Run it as different users to see the difference.
3. The first count respects the rules; the second counts every row. A difference tells you the rules are doing something.

</details>
