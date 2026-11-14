---
description: "Defining groups and access rights for a module: groups, implied groups, ir.model.access, how rights combine, and how to check them in code."
---

# Groups and access rights

Groups answer "who", access rights (ACLs) answer "what on which model".

Checked against `odoo/addons/base/models/res_users.py`, `ir_model.py`, `security/base_groups.xml` (18) and `models/res_groups.py`, `security/base_groups.xml`, `addons/hr/security/hr_security.xml` (20).

## What a group is

A `res.groups` record has, in 18:

| Field | Meaning |
| --- | --- |
| `name` | label, translatable |
| `category_id` | the application (`ir.module.category`) the group is shown under |
| `implied_ids` | groups granted automatically to its members |
| `trans_implied_ids` | computed: everything implied, transitively |
| `users` | its members |
| `model_access` | the `ir.model.access` rows granting this group rights |
| `rule_groups` | the `ir.rule` records scoped to this group |
| `menu_access`, `view_access` | menus and views restricted to this group |
| `comment` | description shown on the user form |
| `share` | marks a group created for sharing, not a real role |

Names are unique per application (`name_uniq` on `(category_id, name)`).

A user's effective groups are the groups assigned plus everything they imply. On 18 the user field is `groups_id`; `user._get_group_ids()` returns its ids as a cached tuple.

## Defining groups in a module (Odoo 17 and 18)

```xml
<odoo>
    <record id="module_category_library" model="ir.module.category">
        <field name="name">Library</field>
        <field name="sequence">40</field>
    </record>

    <record id="group_library_user" model="res.groups">
        <field name="name">User</field>
        <field name="category_id" ref="module_category_library"/>
        <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
        <field name="comment">Can borrow and return books.</field>
    </record>

    <record id="group_library_manager" model="res.groups">
        <field name="name">Manager</field>
        <field name="category_id" ref="module_category_library"/>
        <field name="implied_ids" eval="[(4, ref('group_library_user'))]"/>
        <field name="comment">Manages the catalogue and all loans.</field>
        <field name="users" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
    </record>
</odoo>
```

What the pieces do:

- `category_id` puts the groups of one application together. On the user form, an application with two or more groups where each implies the previous becomes a **single selection field** (Library: none, User, Manager). Groups that are not in a ladder appear as separate checkboxes. The form is generated from the groups, which is why changing groups needs a view refresh.
- `implied_ids` makes membership transitive. A manager gets the user group, which gets `base.group_user` (internal user). When you add a user to a group, the implied groups are added too.
- The `users` line puts the superuser (`base.user_root`) and the administrator in the top group so a fresh install is usable. `(4, id)` is the "link" command.
- `base.group_user` is the **Internal User** group. Making your lowest group imply it is what turns a role into "an employee who may log into the backend".

## Defining groups in Odoo 20

Odoo 20 replaces the category with a **privilege**: a named scope for a family of groups, itself filed under an application category. Groups point at the privilege, and the user-side fields were renamed. From `addons/hr/security/hr_security.xml` in the 20 tree:

```xml
<record model="res.groups.privilege" id="res_groups_privilege_employees">
    <field name="name">Employees</field>
    <field name="sequence">9</field>
    <field name="category_id" ref="base.module_category_human_resources"/>
</record>

<record id="group_hr_user" model="res.groups">
    <field name="name">Officer: Manage all employees</field>
    <field name="sequence">10</field>
    <field name="privilege_id" ref="res_groups_privilege_employees"/>
    <field name="implied_ids" eval="[(6, 0, [ref('base.group_user')])]"/>
</record>

<record id="group_hr_manager" model="res.groups">
    <field name="name">Administrator</field>
    <field name="privilege_id" ref="res_groups_privilege_employees"/>
    <field name="implied_ids" eval="[(4, ref('group_hr_user'))]"/>
    <field name="user_ids" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
</record>
```

Differences you will hit when porting 18 to 20, all read from the two source trees:

| Concept | Odoo 18 | Odoo 20 |
| --- | --- | --- |
| Group's home | `category_id` on `res.groups` | `privilege_id` on `res.groups`; `category_id` is on `res.groups.privilege` |
| Group members | `users` | `user_ids` |
| User's explicit groups | `groups_id` on `res.users` | `group_ids`; `all_group_ids` adds implied groups |
| Ordering | by name | `sequence` field, ordered by privilege, sequence, name |

A module that must support both versions needs two group files, one per layout, chosen by branch. Odoo 19 is not covered here because its source was not available to check.

## Access rights: `ir.model.access`

A row grants four permissions on a model to a group:

| Field | Meaning |
| --- | --- |
| `model_id` | the model |
| `group_id` | the group; empty means everyone (deprecated, logged as a warning) |
| `perm_read`, `perm_write`, `perm_create`, `perm_unlink` | the four permissions |
| `name` | label, required |
| `active` | switch an ACL off without deleting it |

The usual way to write them is `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_library_book_user,library.book user,model_library_book,group_library_user,1,0,0,0
access_library_book_manager,library.book manager,model_library_book,group_library_manager,1,1,1,1
access_library_loan_user,library.loan user,model_library_loan,group_library_user,1,1,1,0
access_library_loan_manager,library.loan manager,model_library_loan,group_library_manager,1,1,1,1
access_library_member_user,library.member user,model_library_member,group_library_user,1,0,0,0
access_library_member_manager,library.member manager,model_library_member,group_library_manager,1,1,1,1
```

Rules for the file:

- `model_id:id` is the external id `model_<model name with dots replaced by underscores>`, which Odoo creates for every model when it registers the model.
- `group_id:id` is the group's external id. A group of another module needs its module prefix (`base.group_user`).
- A row's `id` must be unique across modules, so prefix it with the module name.
- List the file in the manifest `data` **after** the XML that defines the groups.
- Transient models (wizards) need ACL rows too: `_check_access` in 18 has no exception for them, so without a row an ordinary user cannot use the wizard. Grant it to the lowest group that opens it.
- A model without any ACL row is closed to everyone but the superuser: `check` only passes for models in the set computed from the ACL rows of the user's groups.

### How rights combine

Rights are additive. A user in several groups gets the union of all rows. There is no deny. Therefore:

- Design groups as a ladder, with each ACL row granted to the **lowest** group that needs it, and let `implied_ids` give the higher groups the same.
- If a user can do something you did not intend, find which of their groups grants it. A SQL query makes that quick, see Try it.
- You cannot revoke a permission another module grants. You can only change which groups the user belongs to, or add a record rule that restricts the rows.

## User types

Beyond application groups there are three mutually exclusive **user types** in the category `base.module_category_user_type`:

| Group | Meaning |
| --- | --- |
| `base.group_user` | Internal user: backend access, subject to the ACLs of their other groups |
| `base.group_portal` | Portal: external users who see the portal pages only |
| `base.group_public` | Public: the anonymous website visitor (a single shared user) |

A constraint (`_check_one_user_type`) rejects a user with more than one of them, which could otherwise happen through `implied_ids`. Never make a portal-visible group imply `base.group_user`.

Other base groups worth knowing: `base.group_system` (Settings: administration), `base.group_erp_manager` (Access Rights), `base.group_multi_company`, `base.group_multi_currency`, `base.group_no_one` (technical features, effective only in debug mode), `base.group_allow_export`, `base.group_partner_manager` (Contact Creation), `base.group_sanitize_override` (may bypass HTML sanitisation on fields that allow it).

## Assigning access to menus, actions, views

`groups` on `ir.ui.menu` hides the menu from other users. `groups` on an action or a view makes it unavailable. On a node inside a view, `groups="library.group_library_manager"` removes the node for others:

```xml
<menuitem id="menu_library_config" name="Configuration" parent="menu_library_root"
          groups="group_library_manager"/>

<button name="action_write_off" type="object" string="Write off"
        groups="library.group_library_manager"/>
```

`groups` in a view accepts the same syntax as the field attribute: comma-separated external ids, each optionally preceded by `!` (`groups="base.group_user,!base.group_system"`). The 18 `has_groups` docstring gives that exact example.

Remember the earlier chapter: this controls what is *shown*. It is not enforcement.

## Checking groups in code

```python
# the current user
if self.env.user.has_group("library.group_library_manager"):
    ...

# several groups, with negation, same syntax as the attribute
if self.env.user.has_groups("library.group_library_user,!library.group_library_manager"):
    ...
```

- `has_group` takes a fully qualified external id; there is no implicit module. `has_groups` takes a comma-separated spec with optional `!` negations, returns true if the user belongs to at least one positive group and none of the negated ones (or if there are only negatives and none matched).
- `base.group_no_one` is effective only in debug mode for these methods.
- The first call per group queries; the result is cached per user.
- A record method that acts on behalf of a group should use the ORM checks, not group membership, when the real question is "may this user write this record":

```python
def action_write_off(self):
    self.check_access("write")                      # model ACL + record rules
    if not self.env.user.has_group("library.group_library_manager"):
        raise AccessError(_("Only librarians can write off a loan."))
    ...
```

`AccessError` comes from `odoo.exceptions`. Use `has_group` for business policy ("only managers may do this step"); use `check_access` for data access.

## Data files for access rights

ACLs and groups are data. They load at install and update. Two consequences:

- **They are `noupdate`-sensitive.** A group or an ACL created from XML in a file without `noupdate` is reset to the file's values whenever the module is updated. Tune them in the UI only for experiments.
- **Order matters on first install.** The groups XML must load before the CSV that names them, and both before views that reference the group ids in `groups` attributes. List them in the manifest in that order:

```python
"data": [
    "security/library_groups.xml",
    "security/ir.model.access.csv",
    "security/library_rules.xml",
    "views/book_views.xml",
    "views/loan_views.xml",
    "views/menus.xml",
],
```

## Pitfalls

- **Giving the lowest group write access "for now".** It stays. Grant to the lowest group that needs it.
- **Empty `group_id`.** Grants everyone, portal and public included if the model is reachable. Odoo warns when you create one; do not ignore it.
- **A missing ACL row for a transient model.** The wizard opens for administrators and fails for everyone else.
- **Typo in the model's external id.** `model_library_loans` instead of `model_library_loan` fails the whole data load with a message naming the id.
- **A group implying `base.group_user` that is also given to portal users.** The user-type constraint rejects the combination.
- **Using `has_group` in a view `attrs`.** Not available there; use the `groups` attribute.
- **Deleting an ACL line from the CSV and expecting the right to disappear.** An update does not remove rows that no longer appear in the file, it only creates or updates the ones that do. Remove the record explicitly, or set `perm_*` to 0.
- **Relying on `users` or `groups_id` field names across versions.** They changed in 20.

## Versions

{% hint style="info" %}
**16 and 17:** `category_id`, `users`, `groups_id` as in 18. `check_access_rights` is the access check method.

**18:** as described here; `check_access` is the new method.

**20:** groups use `privilege_id`; members are `user_ids`; the user's groups are `group_ids` and `all_group_ids`. A ladder of groups under one privilege plays the role that a category did.
{% endhint %}

## Try it

1. List who can write `library.loan` and why, in SQL (read-only):

```sql
SELECT g.id, g.name, a.perm_read, a.perm_write, a.perm_create, a.perm_unlink
FROM ir_model_access a
JOIN ir_model m ON m.id = a.model_id
LEFT JOIN res_groups g ON g.id = a.group_id
WHERE m.model = 'library.loan' AND a.active
ORDER BY g.name;
```

2. In an Odoo shell, print the transitive groups of a user and check one: `u = env.ref("base.user_admin"); u.groups_id.mapped("full_name")` (on 18).
3. Add a user to `group_library_manager` only, open the form and check that they also show as `User` and `Internal User`.

<details>

<summary>Solution notes</summary>

1. Rows with a null group name are ACLs granting everyone; the rest are the groups that can write. Remember the union rule when reading the result.
2. `full_name` shows application and group names; the list includes groups implied through `implied_ids`.
3. The manager group implies the library user group, which implies `base.group_user`, so all three show.

</details>
