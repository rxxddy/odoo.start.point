---
description: Kanban architecture, QWeb cards, and progress bars.
---

# Kanban views

A kanban view renders one card per record, optionally in columns by a group-by field. The card is a QWeb template run in the browser, not on the server, so the data it can use is only what the view declared as `<field>` and what the web client adds.

## Minimal view

```xml
<record id="library_book_kanban" model="ir.ui.view">
  <field name="name">library.book.kanban</field>
  <field name="model">library.book</field>
  <field name="arch" type="xml">
    <kanban default_group_by="state" class="o_kanban_small_column" quick_create="false"
            records_draggable="1" group_create="false">
      <field name="name"/>
      <field name="state"/>
      <field name="color"/>
      <field name="author_id"/>
      <progressbar field="state" colors='{"available": "success", "lent": "warning", "lost": "danger"}'/>
      <templates>
        <t t-name="card">
          <field name="name" class="fw-bold fs-5"/>
          <div class="text-muted">
            <field name="author_id"/>
          </div>
          <footer>
            <field name="tag_ids" widget="many2many_tags" options="{'color_field': 'color'}"/>
            <field name="user_id" widget="many2one_avatar_user" class="ms-auto"/>
          </footer>
        </t>
      </templates>
    </kanban>
  </field>
</record>
```

## Template mechanics

- The card template is named `card` in 18 (a `<t t-name="card">` directly under `<templates>`). In 16 and 17 it is `kanban-box`, and menus use `kanban-menu`.
- `<field name="x"/>` outputs the field with its widget. `record.x.value` gives the raw value and `record.x.raw_value` the unformatted one, available in `t-esc` expressions. Every field you read must be declared in the view, or it is not loaded.
- Standard layout classes: Bootstrap 5 utilities (`d-flex`, `fw-bold`, `ms-auto`) and Odoo's `o_kanban_*` helpers.
- `t-if`, `t-foreach`, `t-att-class`, `t-attf-class` work as in server QWeb, but the expression language is JavaScript, not Python.

```xml
<div t-attf-class="oe_kanban_color_#{record.color.raw_value} oe_kanban_global_click">
```

`oe_kanban_global_click` makes the whole card open the record; without it only the fields with links react.

## Columns, quick create, drag and drop

- `default_group_by`: the field to group columns by. Many2one, selection, and date fields work. Dragging between columns writes the field, so it must be writable and not computed.
- Empty stages: for a many2one the empty groups are shown when the comodel defines `_group_expand` or `group_expand` on the field; otherwise only groups with records appear.
- `quick_create`: the small "add" row. `on_create="module.quick_create_view"` points to a minimal form view used in a dialog.
- `records_draggable`, `groups_draggable`, `group_create`, `group_edit`, `group_delete` toggle the controls.
- `sample="1"` shows fake cards when the model is empty, which helps first-run screens.

## Progress bar

`<progressbar field="state" colors="{...}"/>` draws a bar at the top of each column, counting records by the value of `field`. An optional `sum_field` sums a numeric field instead of counting. Clicking a segment filters the column. Value keys in `colors` must match the selection keys, not the labels.

## Dropdown menu and actions

Buttons inside cards use `type="object"`, `type="action"`, or `type="open"`, `type="edit"`, `type="delete"`:

```xml
<button name="action_mark_lent" type="object" class="btn btn-sm btn-primary">Lend</button>
```

In 18, a dropdown menu is declared with a separate `<t t-name="menu">` template; in 16/17 it is `kanban-menu`. Items there are links with `type="..."` and the same classes.

## Pitfalls

- Using a field in the template without declaring it: it renders empty, with no error in production.
- Python expressions in the template: they are JS. `record.name.value` is fine; `len(...)` is not.
- Expensive related fields on a card multiply by the page size (default 40 per column, 80 in ungrouped). Store what you display.
- Grouping on a non-stored computed field fails; the group needs a database column.
- Images: use `<field name="image_128" widget="image"/>` and a small size field; never `image_1920` in a card.

## Versions

{% hint style="danger" %}
The kanban template syntax changed in 18. `<t t-name="kanban-box">` with `oe_kanban_*` markup is the 16/17 form; 18 replaces it with `t-name="card"` and a simpler structure. The legacy `kanban-box` still renders in 18 but logs a deprecation warning in the console (verified in the 18 arch parser); convert views when you touch them.
{% endhint %}

## Try it

Add `default_group_by="state"` to the view and drag a card between columns. Check the write in the server log, and then try the same with a computed `state` to see the failure.
