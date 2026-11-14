---
description: Input, processing, and output as one feature.
---

# A wizard with a PDF report

A wizard asks the user for parameters, a report turns data into a document. Together they are the most common "small feature" in Odoo: pick a date range and a member, press Print, get a PDF. This blueprint builds one on the neutral `library` module, file by file, for Odoo 18. Each file is complete; add them to the manifest in the order shown.

The feature: **Loan summary**. The user opens Library > Reports > Loan summary, chooses a date range and optionally a member, and receives a PDF listing the loans in that range, grouped by member, with a count of overdue ones.

## Assumed starting point

The module already has two models. Shown here so the rest is checkable.

```python
# library/models/library_book.py
from odoo import fields, models


class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Book'

    name = fields.Char(required=True)
    isbn = fields.Char()
```

```python
# library/models/library_loan.py
from odoo import api, fields, models


class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Book loan'
    _order = 'date_loan desc, id desc'

    book_id = fields.Many2one('library.book', required=True, ondelete='restrict')
    member_id = fields.Many2one('res.partner', string='Member', required=True)
    date_loan = fields.Date(required=True, default=fields.Date.context_today)
    date_due = fields.Date(required=True)
    date_return = fields.Date()
    is_overdue = fields.Boolean(compute='_compute_is_overdue', store=True)

    @api.depends('date_due', 'date_return')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for loan in self:
            loan.is_overdue = not loan.date_return and loan.date_due < today
```

{% hint style="info" %}
`is_overdue` is stored but depends on today's date, so it goes stale at midnight. For a report it is cleaner to compute overdue in the report code, as done below. The stored field is kept here only because other chapters use it.
{% endhint %}

## Manifest

```python
# library/__manifest__.py
{
    'name': 'Library',
    'version': '18.0.1.0.0',
    'depends': ['base', 'web'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'wizard/loan_summary_wizard_views.xml',
        'report/loan_summary_report.xml',
        'report/loan_summary_templates.xml',
        'views/library_menus.xml',
    ],
}
```

Order matters: the wizard view defines the action the menu points to, and the menu file loads last. `web` provides the report layouts (`web.external_layout`, `web.html_container`).

## The wizard model

A wizard is a `TransientModel`: a normal model whose rows are temporary and vacuumed automatically. It holds the form's field values and the button's logic.

```python
# library/wizard/loan_summary_wizard.py
from odoo import api, fields, models
from odoo.exceptions import UserError


class LoanSummaryWizard(models.TransientModel):
    _name = 'library.loan.summary.wizard'
    _description = 'Loan summary wizard'

    date_from = fields.Date(
        string='From', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string='To', required=True,
        default=fields.Date.context_today,
    )
    member_ids = fields.Many2many(
        'res.partner', string='Members',
        help='Leave empty to include every member.',
    )
    only_overdue = fields.Boolean(string='Only overdue')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from > wiz.date_to:
                raise UserError(self.env._("The start date must not be after the end date."))

    def _get_loan_domain(self):
        self.ensure_one()
        domain = [
            ('date_loan', '>=', self.date_from),
            ('date_loan', '<=', self.date_to),
        ]
        if self.member_ids:
            domain.append(('member_id', 'in', self.member_ids.ids))
        if self.only_overdue:
            domain += [('date_return', '=', False),
                       ('date_due', '<', fields.Date.context_today(self))]
        return domain

    def action_print(self):
        self.ensure_one()
        loans = self.env['library.loan'].search(self._get_loan_domain())
        if not loans:
            raise UserError(self.env._("No loans match the selected criteria."))
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'loan_ids': loans.ids,
        }
        return self.env.ref('library.action_report_loan_summary').report_action(
            loans, data=data,
        )
```

```python
# library/wizard/__init__.py
from . import loan_summary_wizard
```

```python
# library/__init__.py
from . import models
from . import wizard
from . import report
```

Points worth reading twice:

- `report_action(docs, data=...)` returns a client action dictionary. The wizard does not render anything itself; it hands the client a URL to fetch the PDF from.
- The wizard searches once and passes ids. The report must not search again with different criteria, or the PDF and the validation ("no loans match") can disagree.
- `self.env._()` is the Odoo 18 shorthand for translation. In 16 and 17 import and use `from odoo import _` and `_("...")`.

## Wizard view, action and menu

```xml
<!-- library/wizard/loan_summary_wizard_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="loan_summary_wizard_form" model="ir.ui.view">
        <field name="name">library.loan.summary.wizard.form</field>
        <field name="model">library.loan.summary.wizard</field>
        <field name="arch" type="xml">
            <form string="Loan summary">
                <group>
                    <group>
                        <field name="date_from"/>
                        <field name="date_to"/>
                    </group>
                    <group>
                        <field name="member_ids" widget="many2many_tags"/>
                        <field name="only_overdue"/>
                    </group>
                </group>
                <footer>
                    <button name="action_print" type="object"
                            string="Print" class="btn-primary" data-hotkey="q"/>
                    <button string="Cancel" class="btn-secondary"
                            special="cancel" data-hotkey="x"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="loan_summary_wizard_action" model="ir.actions.act_window">
        <field name="name">Loan summary</field>
        <field name="res_model">library.loan.summary.wizard</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>
</odoo>
```

`target="new"` opens the form as a dialog; the `<footer>` buttons are placed in the dialog footer. `special="cancel"` closes it without calling the server.

```xml
<!-- library/views/library_menus.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_library_root" name="Library" sequence="50"/>
    <menuitem id="menu_library_reports" name="Reports"
              parent="menu_library_root" sequence="90"/>
    <menuitem id="menu_loan_summary" name="Loan summary"
              parent="menu_library_reports"
              action="loan_summary_wizard_action"
              groups="library.group_library_manager"
              sequence="10"/>
</odoo>
```

## The report action

```xml
<!-- library/report/loan_summary_report.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="action_report_loan_summary" model="ir.actions.report">
        <field name="name">Loan summary</field>
        <field name="model">library.loan</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">library.report_loan_summary</field>
        <field name="report_file">library.report_loan_summary</field>
        <field name="print_report_name">'Loan summary'</field>
        <field name="paperformat_id" ref="base.paperformat_euro"/>
    </record>
</odoo>
```

No `binding_model_id`, deliberately. Setting it would add this report to the Print menu of every loan list, where it would run without the wizard's parameters. Reports reached only through a wizard stay unbound.

`report_name` is `<module>.<template id>`, and it also names the abstract model that supplies the data: `report.library.report_loan_summary`.

## The data provider

```python
# library/report/loan_summary_report.py
from collections import defaultdict

from odoo import api, fields, models


class ReportLoanSummary(models.AbstractModel):
    _name = 'report.library.report_loan_summary'
    _description = 'Loan summary report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        loans = self.env['library.loan'].browse(data.get('loan_ids') or docids).exists()
        today = fields.Date.context_today(self)

        by_member = defaultdict(lambda: self.env['library.loan'])
        for loan in loans:
            by_member[loan.member_id] |= loan

        groups = []
        for member, member_loans in sorted(by_member.items(), key=lambda kv: kv[0].name or ''):
            overdue = member_loans.filtered(
                lambda l: not l.date_return and l.date_due < today
            )
            groups.append({
                'member': member,
                'loans': member_loans,
                'overdue_count': len(overdue),
            })

        return {
            'doc_ids': loans.ids,
            'doc_model': 'library.loan',
            'docs': loans,
            'date_from': data.get('date_from'),
            'date_to': data.get('date_to'),
            'groups': groups,
            'today': today,
            'total': len(loans),
        }
```

```python
# library/report/__init__.py
from . import loan_summary_report
```

If the abstract model is missing, Odoo falls back to rendering the template with just `docs` for the selected records. That is fine for simple documents; here we need the grouping, so we provide the model. Passing `data` through `report_action` is what lets the PDF reflect the wizard's choice instead of whatever was highlighted in a list.

## The QWeb template

```xml
<!-- library/report/loan_summary_templates.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="report_loan_summary">
        <t t-call="web.html_container">
            <t t-call="web.external_layout">
                <div class="page">
                    <h2>Loan summary</h2>
                    <p>
                        Period:
                        <span t-out="date_from" t-options="{'widget': 'date'}"/>
                        to
                        <span t-out="date_to" t-options="{'widget': 'date'}"/>
                        &#8212; <span t-out="total"/> loans
                    </p>

                    <t t-foreach="groups" t-as="group">
                        <h4 class="mt-4">
                            <span t-out="group['member'].display_name"/>
                            <small t-if="group['overdue_count']" class="text-danger">
                                (<span t-out="group['overdue_count']"/> overdue)
                            </small>
                        </h4>
                        <table class="table table-sm o_main_table">
                            <thead>
                                <tr>
                                    <th>Book</th>
                                    <th>Loaned</th>
                                    <th>Due</th>
                                    <th>Returned</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="group['loans']" t-as="loan">
                                    <td><span t-field="loan.book_id.name"/></td>
                                    <td><span t-field="loan.date_loan"/></td>
                                    <td><span t-field="loan.date_due"/></td>
                                    <td><span t-field="loan.date_return"/></td>
                                </tr>
                            </tbody>
                        </table>
                    </t>
                </div>
            </t>
        </t>
    </template>
</odoo>
```

`t-field` renders a record field with the user's formatting and language and respects access rights; use it for record fields. `t-out` prints a plain value and is what you use for computed numbers and dictionary values. `t-esc` is the older name for `t-out`.

{% hint style="info" %}
Versions: `t-out` replaced `t-esc` in 15 and both work in 16 to 18. The `<list>` tag replaced `<tree>` for list views in 18; the form used here is unaffected. Inline `invisible="..."` expressions replaced `attrs` in 17, so a 16 port of a form that hides fields must use `attrs`.
{% endhint %}

## Security

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_library_loan_user,library.loan user,model_library_loan,library.group_library_user,1,0,0,0
access_library_loan_manager,library.loan manager,model_library_loan,library.group_library_manager,1,1,1,1
```

Save as `library/security/ir.model.access.csv`. Notes:

- Transient models need no access line since Odoo 14: any internal user may create and read their own wizard rows. A line for `library.loan.summary.wizard` is not required and the file above omits it. In 12 and earlier one was needed.
- The report reads `library.loan` as the printing user, so that user needs read access on loans and on `res.partner`. The menu is limited to the manager group, but the report URL itself is checked by the same ACLs, not by the menu.
- The abstract report model has no table and no ACL.

The groups themselves live in `security/library_security.xml` (define `group_library_user` and `group_library_manager` there and list the file before the CSV in `data`).

## The test

```python
# library/tests/test_loan_summary.py
from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLoanSummary(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.env['res.partner'].create({'name': 'Test Member'})
        cls.book = cls.env['library.book'].create({'name': 'Test Book'})
        cls.loan = cls.env['library.loan'].create({
            'book_id': cls.book.id,
            'member_id': cls.member.id,
            'date_loan': '2025-01-10',
            'date_due': '2025-01-24',
        })

    def _wizard(self, **vals):
        base = {'date_from': '2025-01-01', 'date_to': '2025-01-31'}
        return self.env['library.loan.summary.wizard'].create({**base, **vals})

    def test_print_returns_report_action(self):
        action = self._wizard().action_print()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'library.report_loan_summary')
        self.assertEqual(action['data']['loan_ids'], self.loan.ids)

    def test_no_matches_raises(self):
        wiz = self._wizard(date_from='2024-01-01', date_to='2024-01-31')
        with self.assertRaises(UserError):
            wiz.action_print()

    def test_bad_dates_raise(self):
        with self.assertRaises(UserError):
            self._wizard(date_from='2025-02-01', date_to='2025-01-01')

    def test_report_values_group_by_member(self):
        wiz = self._wizard()
        data = wiz.action_print()['data']
        values = self.env['report.library.report_loan_summary']._get_report_values(
            self.loan.ids, data=data)
        self.assertEqual(values['total'], 1)
        self.assertEqual(values['groups'][0]['member'], self.member)
        self.assertEqual(values['groups'][0]['overdue_count'], 1)

    def test_pdf_renders(self):
        report = self.env.ref('library.action_report_loan_summary')
        html = report._render_qweb_html(
            report.report_name, self.loan.ids,
            data=self._wizard().action_print()['data'])[0]
        self.assertIn(b'Test Member', html)
```

```python
# library/tests/__init__.py
from . import test_loan_summary
```

Run it:

```bash
odoo-bin -d test_db -i library --test-tags /library --stop-after-init
```

The test renders HTML, not PDF. Producing a real PDF needs `wkhtmltopdf`, which test databases often lack; HTML rendering exercises the template and the data provider, which is where the bugs are.

## Pitfalls

- **The report shows records from a stale selection.** If you omit `data` and rely on `docids`, the PDF reflects whatever the click carried, not the wizard criteria. Pass ids in `data` and read them in `_get_report_values`.
- **`report_name` mismatch.** The abstract model name must be exactly `report.` plus `report_name`. A typo gives no error: Odoo silently falls back to the default values and your `groups` variable is undefined in the template.
- **Template renders in HTML but PDF is blank or missing styles.** wkhtmltopdf fetches assets through `web.base.url`. Behind a proxy or with a wrong `web.base.url` the layout loses its CSS. Check the system parameter before debugging the template.
- **Heavy `search` inside the template.** QWeb has no query planning. Compute in the provider, iterate in the template.
- **Wizard fields stored in the PDF by accident.** Transient rows are vacuumed after a while; never reference a wizard record from a long-lived record.
- **Report bound to the model by habit.** `binding_model_id` on a wizard-driven report exposes it with no parameters.
- **Constraints on wizard fields that need the user's context.** `@api.constrains` runs on `create` as well as `write`; raising there blocks the dialog before Print is pressed, which is usually what you want.

## Versions

- **16**: use `from odoo import _`; hide fields with `attrs="{'invisible': [...]}"` in forms; list views use `<tree>`.
- **17**: `invisible="expr"` replaces `attrs`; `<tree>` still used for list views.
- **18**: `<list>` is the list view tag; `self.env._()` is available for translation; the report engine and `report_action` are unchanged.

## Try it

Add a `group_by` field to the wizard (`selection` with `member` and `book`), branch on it in `_get_report_values`, and add a test for each branch. Then open the report as HTML without a PDF engine by visiting `/report/html/library.report_loan_summary/<loan id>` while logged in, which is quicker for iterating on layout.
