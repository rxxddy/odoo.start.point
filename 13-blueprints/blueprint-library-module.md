---
description: Models, security, views, menus, tests, step by step.
---

# A complete module from scratch

This blueprint builds `library`, a small module with books and loans, in the order that keeps each step testable. Written for Odoo 18.0; the view syntax is also valid on 17.0.

## Layout

```
library/
  __init__.py
  __manifest__.py
  models/__init__.py
  models/book.py
  models/loan.py
  security/ir.model.access.csv
  security/library_security.xml
  views/book_views.xml
  views/loan_views.xml
  views/menus.xml
  data/sequence.xml
  tests/__init__.py
  tests/test_loan.py
```

## 1. Manifest

```python
{
    'name': 'Library',
    'version': '18.0.1.0.0',
    'category': 'Services',
    'depends': ['base', 'mail'],
    'data': [
        'security/library_security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/book_views.xml',
        'views/loan_views.xml',
        'views/menus.xml',
    ],
    'application': True,
    'license': 'LGPL-3',
}
```

Order matters: security before views, because views reference groups, and menus after the actions they open.

## 2. Models

```python
# models/book.py
from odoo import api, fields, models


class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Book'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    isbn = fields.Char(copy=False)
    active = fields.Boolean(default=True)
    loan_ids = fields.One2many('library.loan', 'book_id')
    loan_count = fields.Integer(compute='_compute_loan_count')

    _isbn_unique = models.Constraint('unique(isbn)', 'The ISBN must be unique.')

    @api.depends('loan_ids')
    def _compute_loan_count(self):
        counts = dict(self.env['library.loan']._read_group(
            [('book_id', 'in', self.ids)], ['book_id'], ['__count']))
        for book in self:
            book.loan_count = counts.get(book, 0)
```

{% hint style="info" %}
`models.Constraint` is the 18.0 declaration. On 16.0 and 17.0 use `_sql_constraints = [('isbn_unique', 'unique(isbn)', '...')]`.
{% endhint %}

```python
# models/loan.py
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Loan'
    _order = 'date_out desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    book_id = fields.Many2one('library.book', required=True, ondelete='restrict')
    member_id = fields.Many2one('res.partner', required=True)
    date_out = fields.Date(default=fields.Date.context_today)
    date_due = fields.Date(required=True)
    date_in = fields.Date()
    state = fields.Selection(
        [('open', 'Open'), ('done', 'Returned')], default='open', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('library.loan') or 'New'
        return super().create(vals_list)

    @api.constrains('date_out', 'date_due')
    def _check_dates(self):
        for loan in self:
            if loan.date_due < loan.date_out:
                raise ValidationError("The due date cannot precede the loan date.")

    def action_return(self):
        self.write({'state': 'done', 'date_in': fields.Date.context_today(self)})
```

## 3. Security

Every model needs an access line, or non-admin users get an access error.

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_book_user,library.book user,model_library_book,base.group_user,1,0,0,0
access_book_manager,library.book manager,model_library_book,group_library_manager,1,1,1,1
access_loan_user,library.loan user,model_library_loan,base.group_user,1,1,1,0
access_loan_manager,library.loan manager,model_library_loan,group_library_manager,1,1,1,1
```

```xml
<odoo>
  <record id="group_library_manager" model="res.groups">
    <field name="name">Library Manager</field>
    <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
  </record>
</odoo>
```

## 4. Sequence and views

```xml
<odoo noupdate="1">
  <record id="seq_library_loan" model="ir.sequence">
    <field name="name">Loan</field>
    <field name="code">library.loan</field>
    <field name="prefix">LN/</field>
    <field name="padding">5</field>
  </record>
</odoo>
```

```xml
<odoo>
  <record id="library_loan_view_list" model="ir.ui.view">
    <field name="name">library.loan.list</field>
    <field name="model">library.loan</field>
    <field name="arch" type="xml">
      <list>
        <field name="name"/>
        <field name="book_id"/>
        <field name="member_id"/>
        <field name="date_due"/>
        <field name="state" widget="badge"/>
      </list>
    </field>
  </record>

  <record id="library_loan_view_form" model="ir.ui.view">
    <field name="name">library.loan.form</field>
    <field name="model">library.loan</field>
    <field name="arch" type="xml">
      <form>
        <header>
          <button name="action_return" type="object" string="Return"
                  invisible="state == 'done'" class="btn-primary"/>
          <field name="state" widget="statusbar"/>
        </header>
        <sheet>
          <group>
            <field name="name"/>
            <field name="book_id"/>
            <field name="member_id"/>
            <field name="date_out"/>
            <field name="date_due"/>
            <field name="date_in" invisible="state != 'done'"/>
          </group>
        </sheet>
      </form>
    </field>
  </record>

  <record id="library_loan_action" model="ir.actions.act_window">
    <field name="name">Loans</field>
    <field name="res_model">library.loan</field>
    <field name="view_mode">list,form</field>
  </record>
</odoo>
```

```xml
<odoo>
  <menuitem id="menu_library_root" name="Library" sequence="50"/>
  <menuitem id="menu_library_loans" name="Loans" parent="menu_library_root"
            action="library_loan_action"/>
</odoo>
```

Build the book views the same way, with an action `library_book_action` and a smart button on the form showing `loan_count`.

## 5. Tests

```python
# tests/test_loan.py
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestLoan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.book = cls.env['library.book'].create({'name': 'Test Book', 'isbn': '1'})
        cls.member = cls.env['res.partner'].create({'name': 'Member'})

    def test_return(self):
        loan = self.env['library.loan'].create({
            'book_id': self.book.id, 'member_id': self.member.id,
            'date_due': '2030-01-01'})
        loan.action_return()
        self.assertEqual(loan.state, 'done')

    def test_due_before_out(self):
        with self.assertRaises(ValidationError):
            self.env['library.loan'].create({
                'book_id': self.book.id, 'member_id': self.member.id,
                'date_out': '2030-01-02', 'date_due': '2030-01-01'})
```

## Pitfalls

- A new model without an access line: tests run as superuser and pass, the first normal user fails.
- Listing a view file in `data` before the security file it needs.
- Using `date_out` default `fields.Date.today` instead of `context_today`; users in other time zones see yesterday.
- Computing `loan_count` with a loop of `search_count`; use `_read_group` as above.

## Try it

```bash
odoo-bin -d lib_dev -i library --test-tags /library --stop-after-init
```

Create a book, a loan, press Return, and confirm the statusbar changes and the button disappears.
