---
description: Layout, buttons, statusbar, notebooks, and smart buttons.
---

# Form views

A form view is the single-record editor. Most of the work in a module's UI goes here: laying out fields, exposing workflow buttons, and showing related records. The structure is fixed by convention, and following it gets you responsive behaviour, chatter placement, and readonly handling for free.

## Skeleton

```xml
<record id="library_book_view_form" model="ir.ui.view">
    <field name="name">library.book.form</field>
    <field name="model">library.book</field>
    <field name="arch" type="xml">
        <form string="Book">
            <header>
                <button name="action_borrow" string="Borrow" type="object"
                        class="btn-primary" invisible="state != 'available'"/>
                <button name="action_return" string="Return" type="object"
                        invisible="state != 'borrowed'"/>
                <field name="state" widget="statusbar"
                       statusbar_visible="available,borrowed"/>
            </header>
            <sheet>
                <div class="oe_button_box" name="button_box">
                    <button name="action_view_loans" type="object"
                            class="oe_stat_button" icon="fa-book">
                        <field name="loan_count" widget="statinfo" string="Loans"/>
                    </button>
                </div>
                <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger"
                        invisible="active"/>
                <field name="image_1920" widget="image" class="oe_avatar"/>
                <div class="oe_title">
                    <label for="name"/>
                    <h1><field name="name" placeholder="Title"/></h1>
                </div>
                <group>
                    <group name="main">
                        <field name="author_id"/>
                        <field name="isbn"/>
                    </group>
                    <group name="dates">
                        <field name="published_on"/>
                        <field name="company_id" groups="base.group_multi_company"/>
                    </group>
                </group>
                <notebook>
                    <page string="Loans" name="loans">
                        <field name="loan_ids">
                            <list>
                                <field name="partner_id"/>
                                <field name="date_out"/>
                                <field name="date_due"/>
                            </list>
                        </field>
                    </page>
                    <page string="Notes" name="notes">
                        <field name="note"/>
                    </page>
                </notebook>
            </sheet>
            <chatter/>
        </form>
    </field>
</record>
```

`<chatter/>` is the Odoo 18 shorthand for the followers/messages/activities block. It requires the model to inherit `mail.thread` (and `mail.activity.mixin` for activities).

{% hint style="info" %}
**Versions.** Before 17 the chatter was written as `<div class="oe_chatter">` with three `<field name="message_follower_ids"/>`, `<field name="activity_ids"/>`, `<field name="message_ids"/>` children. The old markup still renders in 17 and 18 core views that have not been converted, but new code should use `<chatter/>`. Verify on your target version before publishing a module for 16.
{% endhint %}

## Layout primitives

* **`<sheet>`** gives the centred white paper look. Without it, the form uses the full width and has no padding; use that for wizards and dialog forms.
* **`<group>`** lays out label/field pairs. Two sibling groups inside a parent group render as two columns. `col="4"` on a group sets the number of columns; `colspan` on a child spans them.
* **`<separator string="..."/>`** is a labelled rule between blocks inside a group.
* **`<notebook>` / `<page>`** are tabs. Always set `name` on pages: it is the stable anchor other modules use in `xpath`.
* **`<div class="oe_title">`** with `<h1>` is the large title area under the button box.
* **`<field ... nolabel="1"/>`** hides the label; to supply your own, use `<label for="field"/>`.

## Buttons

```xml
<button name="action_borrow" string="Borrow" type="object"/>
<button name="%(library.action_loan_wizard)d" string="Loan..." type="action"/>
```

* `type="object"` calls a method on the model with `self` set to the current record. The method must be public (no leading underscore) because it is callable from the client.
* `type="action"` runs an action by ID. `%(module.xml_id)d` resolves to the numeric ID at load time.
* `class="btn-primary"` marks the main action of a given state; keep one primary per state.
* `confirm="Return this book?"` adds a confirmation dialog.
* `data-hotkey="q"` binds a keyboard shortcut.

### Visibility expressions

In Odoo 17 and 18 the attributes `invisible`, `readonly`, `required` (and `column_invisible` in lists) take a Python-like expression evaluated against the record's field values:

```xml
<field name="isbn" readonly="state != 'draft'" required="kind == 'book'"/>
<field name="date_due" invisible="not date_out"/>
```

Supported: field names, comparison and boolean operators, literals, `context.get(...)`, `parent.field` inside x2many sub-views, `id`, `uid` is not available. All fields used in an expression must be present in the view, otherwise the client does not know their value; add them as `<field name="x" invisible="1"/>` when you only need them for logic.

{% hint style="danger" %}
**Versions.** `attrs` and `states` were removed. In Odoo 16 you wrote `attrs="{'invisible': [('state', '!=', 'available')]}"` and `states="draft,sent"` on buttons; both are invalid in 17 and 18 and fail with an arch validation error at load. Convert: `states="draft,sent"` becomes `invisible="state not in ('draft', 'sent')"`. I checked the Odoo 18 sale order form and it uses direct expressions only.
{% endhint %}

## Statusbar

`widget="statusbar"` on a Selection or Many2one shows the pipeline. `statusbar_visible` lists the states shown when the record is not in them; the current state is always shown. For a Many2one stage, add `options="{'clickable': '1'}"` to allow clicking to change stage, and `options="{'fold_field': 'fold'}"` to collapse folded stages.

## Smart buttons

A smart button is a `oe_stat_button` in a `oe_button_box` at the top of the sheet. Pattern: a computed count field on the model, a button calling a method that returns a window action filtered on the record.

```python
loan_count = fields.Integer(compute='_compute_loan_count')

def _compute_loan_count(self):
    data = self.env['library.loan']._read_group(
        [('book_id', 'in', self.ids)], ['book_id'], ['__count'])
    counts = {book.id: count for book, count in data}
    for book in self:
        book.loan_count = counts.get(book.id, 0)

def action_view_loans(self):
    self.ensure_one()
    action = self.env['ir.actions.act_window']._for_xml_id('library.action_loan')
    action['domain'] = [('book_id', '=', self.id)]
    action['context'] = {'default_book_id': self.id}
    return action
```

Use `_read_group` with `__count` once per recordset, not a `search_count` per record; the latter issues one query per row when the button appears in a list or kanban.

For a boolean toggle (active, published) use `widget="boolean_button"` with `options="{'terminology': 'archive'}"`.

## Fields worth knowing

| widget | use |
|---|---|
| `many2one_avatar_user` | user with avatar |
| `many2many_tags` | tags, with `options="{'color_field': 'color'}"` |
| `monetary` | requires a `currency_field` on the model or `options="{'currency_field': 'currency_id'}"` |
| `html` | rich text; `options="{'collaborative': true}"` for live editing |
| `priority` | star rating from a Selection |
| `handle` | drag handle in an x2many list |

## Pitfalls

* **Field used in an expression but missing from the view.** The expression silently evaluates with the value undefined. Always include logic-only fields as invisible.
* **Putting `groups` on a field that other expressions depend on.** For users without the group the field is removed from the arch, and the expression that reads it fails. Guard the expression too, or move it into a group-restricted container.
* **Calling a private method from a button.** Odoo rejects `type="object"` buttons that start with an underscore.
* **Missing `ensure_one()` in button methods** that assume one record. Multi-selection actions call the method with several records.
* **Heavy computed fields in the form.** A non-stored compute with a search-per-record loops once per displayed record in x2many lists. Batch it with `_read_group`.
* **Page without `name`.** The next module that wants to add a sibling tab has to anchor on position.

## Try it

Load a form as the client would, read-only, to see what survives inheritance and group pruning:

```python
arch = env['library.book'].get_view(view_type='form')['arch']
print(arch)
```

Search it for the field names your expressions use; any missing one is the bug.
