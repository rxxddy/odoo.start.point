---
description: Columns, editable lists, decorations, optional columns, and grouping.
---

# List views

The list view shows many records as rows. It is the default entry point to most menus, so its columns decide what users see first and how much the server reads per page. Odoo 18 names the root element `<list>`.

{% hint style="info" %}
**Versions.** Up to Odoo 17 the root element was `<tree>` and the view type was `tree`. In Odoo 18 core views, including `sale.sale_order_tree` (checked in the source), use `<list>`. The view type string in actions is `list` as well: `view_mode="list,form"`. Existing `<tree>` arch in custom modules is still accepted on 18 for compatibility, but write `<list>` in anything new and `//list` in new xpaths. Odoo 16 only knows `<tree>`.
{% endhint %}

## Basic list

```xml
<record id="library_book_view_list" model="ir.ui.view">
    <field name="name">library.book.list</field>
    <field name="model">library.book</field>
    <field name="arch" type="xml">
        <list string="Books" default_order="name">
            <field name="name"/>
            <field name="author_id"/>
            <field name="published_on" optional="hide"/>
            <field name="state" widget="badge"
                   decoration-success="state == 'available'"
                   decoration-warning="state == 'borrowed'"/>
            <field name="company_id" groups="base.group_multi_company" optional="show"/>
        </list>
    </field>
</record>
```

## Row decorations

On the `<list>` element, `decoration-*` attributes style whole rows from an expression over the row's fields:

```xml
<list decoration-danger="date_due and date_due &lt; current_date"
      decoration-muted="state == 'returned'"
      decoration-bf="state == 'overdue'">
```

Available suffixes: `bf`, `it`, `danger`, `info`, `muted`, `primary`, `success`, `warning`. The same attributes work on a single `<field>` to colour one cell. `current_date` is available in these expressions. All fields in the expression must appear in the list, as invisible columns if needed: `<field name="date_due" column_invisible="1"/>`.

In 17 and 18 the expressions are Python-like (`state == 'x'`). Older versions used the same decoration syntax, but `invisible` on columns used `attrs`; see the form chapter for the replacement.

## Optional columns

`optional="show"` or `optional="hide"` puts the column in the toggle dropdown at the right of the header, with the stated default. The user's choice is stored in the browser, per list view and user. Use it for everything beyond the three or four columns that identify the record.

## Hiding a column by condition

```xml
<field name="price" column_invisible="parent.kind == 'service'"/>
```

`column_invisible` hides the whole column and is evaluated once for the list (against the parent record when the list is inside an x2many). `invisible` on a field in a list hides the cell per row. The two are different; using `invisible` and expecting the header to disappear is a frequent surprise.

## Editable lists

```xml
<list editable="bottom">
```

`editable="top"` or `"bottom"` makes rows editable inline, with new rows added at that end. Without it, clicking a row opens the form. Related attributes:

* `create="0"`, `edit="0"`, `delete="0"` disable the corresponding action.
* `import="0"` hides the import button.
* `multi_edit="1"` allows editing a field across all selected rows.
* `open_form_view="1"` adds an arrow to open the full form from an editable x2many.
* `on_create="module.action_xml_id"` replaces the quick-add row with an action (typically a wizard).

Inside an editable list, `required` and `readonly` accept expressions over the row:

```xml
<field name="date_due" readonly="state == 'returned'" required="state == 'borrowed'"/>
```

## Widgets worth knowing

| widget | use |
|---|---|
| `handle` | drag handle, requires an integer `sequence` field and `default_order="sequence"` |
| `badge` | coloured pill for Selection/Many2one |
| `many2many_tags` | tags, short and wrapped |
| `boolean_toggle` | inline switch |
| `progressbar` | percentage with `options="{'current_value': 'x', 'max_value': 'y'}"` |
| `monetary` | respects the row's currency |

## Totals and grouping

```xml
<field name="amount" sum="Total"/>
<field name="qty" avg="Average"/>
```

`sum`, `avg`, `min`, `max` on a field display a footer value for the loaded page. For exact totals over the whole result, rely on group headers: a grouped list shows the aggregate of each group computed in the database by `read_group`. Aggregation needs the field to be stored; a non-stored computed field shows no aggregate.

Group by a field from the search view or by default through the action context: `{'search_default_group_by_author': 1}` with a matching filter in the search view, or `{'group_by': ['author_id']}` for a direct default.

`groups_limit`, `limit` on the list, and `default_group_by` are available on the root element: `<list default_group_by="state" limit="40">`.

## x2many lists inside a form

The `<list>` inside a `<field name="loan_ids">` is an inline view used only there. It can differ from the model's standalone list:

```xml
<field name="loan_ids">
    <list editable="bottom">
        <field name="partner_id"/>
        <field name="date_out"/>
    </list>
</field>
```

If you omit the inline `<list>`, Odoo uses the model's default list view, which may have many columns. Define the inline view when the sub-table must be compact.

## Pitfalls

* **Columns that compute per row.** A non-stored compute or a related field across several relations is evaluated for every row on the page. 80 rows with a compute that runs a search inside is 80 queries. Store it or batch the computation.
* **`optional` columns still load.** The server reads the fields whether or not the user displays the column. Hiding a costly column does not make the list faster.
* **Decoration fields not in the view.** The decoration silently never fires. Add the field as `column_invisible="1"`.
* **Using `sum` on the page as a global total.** It sums only the loaded records (up to `limit`). Mislabelled totals cause real accounting confusion; label the footer or use a pivot/report for exact figures.
* **Editable list with required fields on a hidden column.** The user cannot save a row because a field they cannot see is empty. Give it a default or make it visible.
* **Changing the standard list through `xpath` on `tree`.** On Odoo 18 core views the element is `list`; an xpath on `//tree` does not match and the module update fails.

## Try it

Check which fields and decorations the client receives, read-only:

```python
arch = env['library.book'].get_view(view_type='list')['arch']
print(arch)
```

Compare with the model's `_fields` to see which columns are stored and therefore sortable and aggregatable:

```python
print({n: f.store for n, f in env['library.book']._fields.items()})
```
