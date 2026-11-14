---
description: TransientModel wizards, default_get, and returning actions.
---

# Wizards

A wizard is a dialog that collects input and then does something to other records. Technically it is a `TransientModel`: a normal model whose rows are temporary and cleaned by a vacuum job. It gives you a real form, validation, and onchange without a permanent table of junk.

## A complete example

```python
from odoo import api, fields, models
from odoo.exceptions import UserError


class LibraryLoanWizard(models.TransientModel):
    _name = "library.loan.wizard"
    _description = "Lend books"

    borrower_id = fields.Many2one("res.partner", required=True)
    book_ids = fields.Many2many("library.book", string="Books")
    due_date = fields.Date(default=lambda self: fields.Date.add(fields.Date.today(), days=14))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("active_model") == "library.book":
            res["book_ids"] = [(6, 0, self.env.context.get("active_ids", []))]
        return res

    def action_confirm(self):
        self.ensure_one()
        if not self.book_ids:
            raise UserError("Select at least one book.")
        loans = self.env["library.loan"].create([
            {"book_id": b.id, "borrower_id": self.borrower_id.id, "due_date": self.due_date}
            for b in self.book_ids
        ])
        return {
            "type": "ir.actions.act_window",
            "res_model": "library.loan",
            "view_mode": "list,form",
            "domain": [("id", "in", loans.ids)],
        }
```

```xml
<record id="library_loan_wizard_form" model="ir.ui.view">
  <field name="name">library.loan.wizard.form</field>
  <field name="model">library.loan.wizard</field>
  <field name="arch" type="xml">
    <form>
      <group>
        <field name="borrower_id"/>
        <field name="due_date"/>
        <field name="book_ids" widget="many2many_tags"/>
      </group>
      <footer>
        <button name="action_confirm" type="object" string="Confirm" class="btn-primary" data-hotkey="q"/>
        <button string="Cancel" special="cancel" data-hotkey="x"/>
      </footer>
    </form>
  </field>
</record>

<record id="library_loan_wizard_action" model="ir.actions.act_window">
  <field name="name">Lend books</field>
  <field name="res_model">library.loan.wizard</field>
  <field name="view_mode">form</field>
  <field name="target">new</field>
  <field name="binding_model_id" ref="model_library_book"/>
  <field name="binding_view_types">list,form</field>
</record>
```

## Moving parts

- `target="new"` opens the form in a dialog. The `<footer>` holds the buttons; buttons outside it render inside the form body.
- `binding_model_id` puts the wizard in the Action menu of the books list and form. The selected records arrive as `active_ids` and `active_model` in the context.
- `default_get` seeds fields from the context. Alternatively pass `default_<field>` keys in the action context.
- Buttons call methods on the wizard record. `self` is the wizard; the target records are in `self.book_ids` or `self.env[...].browse(self.env.context["active_ids"])`.
- A method can return an action dict to navigate, or `{"type": "ir.actions.act_window_close"}` to close the dialog, or a notification:

```python
return {"type": "ir.actions.client", "tag": "display_notification",
        "params": {"title": "Done", "message": "3 loans created", "type": "success", "next": {"type": "ir.actions.act_window_close"}}}
```

## Opening a wizard from a button

```python
def action_lend(self):
    return {
        "type": "ir.actions.act_window",
        "res_model": "library.loan.wizard",
        "view_mode": "form",
        "target": "new",
        "context": {"default_book_ids": self.ids},
    }
```

## Access and cleanup

Transient models need no `ir.model.access.csv` entries since 14; any user can create and access their own wizard records, with a record rule that limits them to the creator. Rows are removed by an autovacuum (`ir.autovacuum` calls `_transient_vacuum`), by default after a few hours or when the number of rows exceeds a limit, so never store anything you need to keep.

## Pitfalls

- Using `self.env.context["active_ids"]` after the wizard has already moved on: the context is lost once you return another action; pass ids explicitly.
- Many2one fields pointing to a transient model from a persistent model: records disappear and leave a broken reference (the database refuses it by a constraint, or it errors on vacuum).
- Long processing inside the button: the dialog freezes and the request may time out. Queue the work in a cron or a job and tell the user.
- Forgetting `ensure_one()` when the button was triggered on several wizard records.
- Returning nothing from a button leaves the dialog open on some versions; return the close action explicitly.

## Versions

{% hint style="info" %}
The `ir.actions.act_window` dialog and footer mechanics are the same in 16, 17 and 18. The visible difference is in view XML: `attrs` and `states` on wizard fields and buttons were removed in 17; write `invisible="not book_ids"` instead of `attrs="{'invisible': [...]}"`.
{% endhint %}

## Try it

Select two books in the list, open Action, and run "Lend books". Check the created loans, then look at the leftovers:

```sql
select id, create_date from library_loan_wizard order by id desc limit 5;
```
