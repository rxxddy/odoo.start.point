---
description: Groups, categories, implied groups and ir.model.access.
---

# Groups and access rights

Groups answer "who", access rights (ACLs) answer "what on which model". This chapter shows how to define both for the `library` module, and how to keep the hierarchy maintainable.

## Defining groups

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
  </record>

  <record id="group_library_manager" model="res.groups">
    <field name="name">Manager</field>
    <field name="category_id" ref="module_category_library"/>
    <field name="implied_ids" eval="[(4, ref('group_library_user'))]"/>
    <field name="users" eval="[(4, ref('base.user_root')), (4, ref('base.user_admin'))]"/>
  </record>
</odoo>
```

Three things to note. `category_id` makes the groups appear as one selection field (Library: User / Manager) on the user form. `implied_ids` means that a Manager automatically has the User group, and Odoo applies it transitively when the user is saved. The `users` line puts the superuser and admin into the top group so that a fresh install is usable.

{% hint style="info" %}
Versions: in Odoo 16, 17 and 18 the user field is `groups_id` and the group has `category_id` (verified in 18's `res_users.py`). Odoo 19 restructures this with privileges, so do not copy 18 group XML blindly into a later version.
{% endhint %}

## Access rights

The usual way is a CSV in `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_library_book_user,library.book user,model_library_book,group_library_user,1,0,0,0
access_library_book_manager,library.book manager,model_library_book,group_library_manager,1,1,1,1
access_library_loan_user,library.loan user,model_library_loan,group_library_user,1,1,1,0
```

`model_id:id` uses the external ID `model_<model_name_with_underscores>`, which Odoo generates when the model is registered. `group_id:id` is the group's XML ID, prefixed with the module name if the group lives elsewhere (`base.group_user`).

An empty `group_id:id` means "everyone". Use it deliberately.

## How rights combine

Rights are additive. If user is in `library_user` (read only) and in some other group with a write line on the same model, they can write. There is no deny. The consequence: design groups as a ladder (User implies nothing more than what they need, Manager implies User), and keep each ACL line minimal.

## Reading access in code

```python
class LibraryBook(models.Model):
    _name = 'library.book'

    def action_archive_old(self):
        if not self.env.user.has_group('library.group_library_manager'):
            raise AccessError(_("Only library managers can do this."))
```

`has_group` takes the full XML ID with the module prefix. It checks the cached groups of the user in the current environment. In views, use `groups="library.group_library_manager"` on fields, buttons and menus. In XML modifiers (18), you can also use `groups` on a `<field>`, but not inside a Python domain.

For a check that follows both ACL and rules, prefer `records.check_access('write')` over a group check: the group check goes stale when someone adds a more specific rule later.

## Menus and actions

```xml
<menuitem id="menu_library_root" name="Library"
          groups="group_library_user" web_icon="library,static/description/icon.png"/>
```

A menu with no group is visible to every internal user, even if they cannot open the model. A child menu without groups inherits visibility from the parent only for display, not for access.

## Pitfalls

{% hint style="warning" %}
Never edit `ir.model.access` or `res.groups` through the UI on a production database and expect it to persist. Records loaded from XML in your module are overwritten on the next `-u` unless you mark them `noupdate="1"`. Decide which parts are data, and which are configuration.
{% endhint %}

- **Wrong CSV id prefix.** The `model_id:id` must be `model_library_book`, not `library.book`. The error appears at install: "No matching record found for external id".
- **ACL on `base.group_user` for sensitive models.** Every internal user is in that group. For finance or HR data use a dedicated group.
- **Forgetting the portal.** If portal users read `library.loan` through a controller or portal view, they need a read ACL and a rule restricting them to their own records.
- **CSV loaded before the group.** In the manifest, list `library_security.xml` before `ir.model.access.csv`.
- **Changing `implied_ids` later.** Adding an implied group to an existing group only affects users when their groups are recomputed. Existing members get it on module update for newly added implications, but removing an implication does not remove the group from users who already had it.

## Try it

List every ACL line that applies to a model, read-only:

```sql
SELECT a.name, g.name AS grp, a.perm_read, a.perm_write, a.perm_create, a.perm_unlink
FROM ir_model_access a
JOIN ir_model m ON m.id = a.model_id
LEFT JOIN res_groups g ON g.id = a.group_id
WHERE m.model = 'library.book';
```
