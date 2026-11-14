---
description: Window, URL, server and client actions, plus menus.
---

# Actions and menus

An action tells the web client what to do when the user clicks something: open a list, run code, open a URL, show a client-side screen. A menu is only a pointer to an action. Understanding the action record gets you most of the way, because buttons, menu items and the "Action" dropdown all use the same machinery.

## Window actions

```xml
<record id="library_book_action" model="ir.actions.act_window">
  <field name="name">Books</field>
  <field name="res_model">library.book</field>
  <field name="view_mode">list,kanban,form</field>
  <field name="domain">[('active', '=', True)]</field>
  <field name="context">{'search_default_available': 1, 'default_state': 'draft'}</field>
  <field name="search_view_id" ref="library_book_search"/>
  <field name="help" type="html">
    <p class="o_view_nocontent_smiling_face">Create the first book</p>
  </field>
</record>
```

Key fields:

- `res_model`: the model to display.
- `view_mode`: comma-separated view types, in tab order. The first is the default. It is `list`, not `tree`, from Odoo 18 on.
- `view_id` / `view_ids`: pin specific views. Without them, the highest-priority view of each type is used. `view_ids` (`ir.actions.act_window.view`) pins a view per mode and sets sequence.
- `domain`: a permanent filter the user cannot remove. Use `context` plus a search default when the user should be able to clear it.
- `context`: `default_<field>` pre-fills new records; `search_default_<filter_name>` turns on a filter from the search view; `group_by` sets default grouping.
- `target`: `current` (default, replaces the view), `new` (dialog), `fullscreen`, `main` (replaces and clears breadcrumb).
- `limit`: page size, default 80.
- `res_id`: open one fixed record; combine with `view_mode` `form`.

### Opening an action from Python

```python
def action_open_loans(self):
    self.ensure_one()
    return {
        "type": "ir.actions.act_window",
        "name": "Loans",
        "res_model": "library.loan",
        "view_mode": "list,form",
        "domain": [("book_id", "=", self.id)],
        "context": {"default_book_id": self.id},
    }
```

For a stable, overridable action prefer `self.env["ir.actions.actions"]._for_xml_id("library.library_loan_action")` and amend the returned dict. It reads the XML record, so customizations of the action apply.

## Other action types

- `ir.actions.act_url`: `url` and `target` (`new`, `self`, `download`). Use it for external links or controller downloads.
- `ir.actions.server`: runs code or writes records; see the server actions chapter. When returned from a button, its result action is executed by the client.
- `ir.actions.client`: opens a registered JavaScript action by `tag`; `params` pass through. The tag must exist in the `actions` registry of the web client.
- `ir.actions.report`: prints a report; see the PDF reports chapter.

## Menus

```xml
<menuitem id="menu_library_root" name="Library" web_icon="library,static/description/icon.png"
          sequence="40"/>
<menuitem id="menu_library_books" name="Books" parent="menu_library_root"
          action="library_book_action" sequence="10"/>
<menuitem id="menu_library_config" name="Configuration" parent="menu_library_root"
          groups="library.group_manager" sequence="90"/>
```

A menu without a `parent` is an app tile. A menu without an `action` is a folder; it only shows if at least one child is visible to the user. `groups` restricts the menu, but it does not secure the model: users in other groups can still reach the data through URLs and RPC. Real protection is in access rights.

## Bindings: the Action and Print menus

Setting `binding_model_id` on an action adds it to the Action dropdown of that model's views. `binding_type` is `action` (the Action menu) or `report` (the Print menu), and `binding_view_types` limits it to `list`, `form`, or both.

```xml
<record id="library_book_archive_action" model="ir.actions.server">
  <field name="name">Archive selected</field>
  <field name="model_id" ref="model_library_book"/>
  <field name="binding_model_id" ref="model_library_book"/>
  <field name="binding_view_types">list</field>
  <field name="state">code</field>
  <field name="code">records.write({'active': False})</field>
</record>
```

## Pitfalls

- A user-visible `domain` on the action that conflicts with filters produces an empty list with no hint why. Keep domains narrow and document them.
- `context` on the action is evaluated in the client, with `uid`, `active_id`, `active_ids`, `context_today`; it is not Python server-side.
- Menus appear in order of `sequence`, ties broken by id; leaving all sequences at default produces install-order menus.
- Deleting an action that a menu still references breaks the menu cache for everyone; remove the menu first, or declare both in one file.
- Menu visibility is cached per user and group; after changing `groups`, update the module and reload.

## Versions

{% hint style="info" %}
Odoo 16 uses `tree` in `view_mode`; 17 and 18 use `list`. `ir.actions.server` gained the `webhook` state in 18. The old `ir.actions.act_window` `view_type` field is gone.
{% endhint %}

## Try it

Find every action bound to your model and where its menus point:

```sql
select a.id, a.name->>'en_US', a.res_model, a.view_mode from ir_act_window a where a.res_model = 'library.book';
```
