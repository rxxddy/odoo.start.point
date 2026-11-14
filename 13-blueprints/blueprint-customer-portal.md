---
description: "Customer-facing pages with correct access control."
---

# A portal feature

A portal feature is three things that must agree: a controller that serves `/my/...` routes, QWeb templates that render the list and detail pages, and access control that makes sure a customer sees only their own records. This blueprint builds `/my/loans`, a list and detail page for `library.loan` records (the teaching model, see [library module](blueprint-library-module.md)), using the same extension points the standard sales portal uses.

## Assumed model

```python
class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Library Loan'
    _inherit = ['portal.mixin', 'mail.thread']
    _order = 'date_loan desc, id desc'

    name = fields.Char(required=True, default='New', copy=False)
    partner_id = fields.Many2one('res.partner', required=True, index=True)
    book_id = fields.Many2one('library.book', required=True)
    date_loan = fields.Date(default=fields.Date.context_today)
    state = fields.Selection([('open', 'Open'), ('returned', 'Returned')], default='open')

    def _compute_access_url(self):
        super()._compute_access_url()
        for loan in self:
            loan.access_url = f'/my/loans/{loan.id}'
```

`portal.mixin` adds `access_url`, `access_token`, `access_warning`, and `_get_share_url()`. The standard `sale.order` does the same: its `_inherit` list contains `portal.mixin`, and it overrides `_compute_access_url` to return `/my/orders/<id>` (verified in Odoo 18). Without the mixin you have no token-based sharing and `_get_page_view_values` has nothing to read.

## Access control first

Write the security before the pages. Two layers:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_library_loan_portal,library.loan portal,model_library_loan,base.group_portal,1,0,0,0
access_library_loan_user,library.loan user,model_library_loan,base.group_user,1,1,1,1
```

```xml
<record id="library_loan_rule_portal" model="ir.rule">
    <field name="name">Library Loan: portal sees own</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="domain_force">[('partner_id', 'child_of', [user.commercial_partner_id.id])]</field>
    <field name="groups" eval="[(4, ref('base.group_portal'))]"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="False"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>
```

The ACL says portal users may read the model at all. The rule says which rows. The standard sale rule uses `message_partner_ids child_of commercial_partner_id`, which lets a company's contacts see each other's orders; `partner_id child_of commercial_partner_id` is the simpler equivalent when the record has a single owner.

{% hint style="warning" %}
Never "fix" a portal access problem with `sudo()` in the controller and a hand-written filter. The record rule is the access control; `sudo()` removes it, and the first forgotten domain becomes a data leak.
{% endhint %}

## Controller

Inherit `CustomerPortal` from `odoo.addons.portal.controllers.portal`. In Odoo 18 it provides `_prepare_home_portal_values(counters)`, `_get_page_view_values(...)`, `_document_check_access(model_name, document_id, access_token)`, and the module-level `pager(...)` helper.

```python
from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class LibraryPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'loan_count' in counters:
            values['loan_count'] = (
                request.env['library.loan'].search_count([])
                if request.env['library.loan'].has_access('read') else 0
            )
        return values

    @http.route(['/my/loans', '/my/loans/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_loans(self, page=1, sortby='date', **kw):
        Loan = request.env['library.loan']
        searchbar_sortings = {
            'date': {'label': 'Newest', 'order': 'date_loan desc, id desc'},
            'name': {'label': 'Reference', 'order': 'name'},
        }
        order = searchbar_sortings.get(sortby, searchbar_sortings['date'])['order']

        total = Loan.search_count([])
        pager = portal_pager(
            url='/my/loans', url_args={'sortby': sortby},
            total=total, page=page, step=self._items_per_page,
        )
        loans = Loan.search([], order=order, limit=self._items_per_page,
                            offset=pager['offset'])
        values = self._prepare_portal_layout_values()
        values.update({
            'loans': loans,
            'page_name': 'loan',
            'pager': pager,
            'default_url': '/my/loans',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        return request.render('library_portal.portal_my_loans', values)

    @http.route('/my/loans/<int:loan_id>', type='http', auth='public', website=True)
    def portal_my_loan(self, loan_id, access_token=None, **kw):
        try:
            loan_sudo = self._document_check_access('library.loan', loan_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._get_page_view_values(
            loan_sudo, access_token, {'loan': loan_sudo, 'page_name': 'loan'},
            'my_loans_history', False,
        )
        return request.render('library_portal.portal_my_loan', values)
```

Points that matter:

- The list uses `search([])` with the **current user's** environment, not `sudo()`. The record rule narrows it to the customer. There is no domain to forget.
- The list route is `auth='user'`: anonymous visitors are redirected to login. The detail route is `auth='public'` so a share link with `?access_token=...` works without login. `_document_check_access` then does the real check: it tries `check_access('read')` as the current user and falls back to a constant-time comparison of the token. It returns the record sudoed, so reads in the template skip rules; this is safe only because access was just verified.
- `_items_per_page` is defined on `CustomerPortal` (80 in Odoo 18). Do not hard-code your own.
- `_prepare_home_portal_values` feeds the counters on `/my`; the `/my/counters` JSON route calls it with the list of placeholders requested by the home template.
- Sort keys come from a whitelist dict. Never pass `sortby` straight into `order=`; that is SQL-injection-adjacent and an `order` error 500.

## Templates

The home page entry hooks into `portal.portal_my_home`, as `sale.portal_my_home_sale` does (it targets the `portal_client_category` div and calls `portal.portal_docs_entry` with `title`, `url`, `placeholder_count`).

```xml
<odoo>
    <template id="portal_my_home_library" name="Portal: loans entry"
              inherit_id="portal.portal_my_home" customize_show="True" priority="40">
        <xpath expr="//div[hasclass('o_portal_docs')]" position="before">
            <t t-set="portal_client_category_enable" t-value="True"/>
        </xpath>
        <div id="portal_client_category" position="inside">
            <t t-call="portal.portal_docs_entry">
                <t t-set="title">Your Loans</t>
                <t t-set="url" t-value="'/my/loans'"/>
                <t t-set="text">Follow your borrowed books</t>
                <t t-set="placeholder_count" t-value="'loan_count'"/>
            </t>
        </div>
    </template>

    <template id="portal_my_loans" name="My Loans">
        <t t-call="portal.portal_layout">
            <t t-set="breadcrumbs_searchbar" t-value="True"/>
            <t t-call="portal.portal_searchbar">
                <t t-set="title">Loans</t>
            </t>
            <t t-if="not loans">
                <p class="alert alert-warning">You have no loans.</p>
            </t>
            <t t-if="loans" t-call="portal.portal_table">
                <thead>
                    <tr class="active">
                        <th>Reference</th>
                        <th>Book</th>
                        <th class="text-end">Date</th>
                        <th class="text-end">Status</th>
                    </tr>
                </thead>
                <tbody>
                    <tr t-foreach="loans" t-as="loan">
                        <td><a t-att-href="loan.get_portal_url()"><t t-out="loan.name"/></a></td>
                        <td><t t-out="loan.book_id.display_name"/></td>
                        <td class="text-end"><span t-field="loan.date_loan"/></td>
                        <td class="text-end"><span t-field="loan.state"/></td>
                    </tr>
                </tbody>
            </t>
        </t>
    </template>

    <template id="portal_my_loan" name="My Loan">
        <t t-call="portal.portal_layout">
            <t t-set="o_portal_fullwidth_alert" t-value="True"/>
            <div class="card">
                <div class="card-body">
                    <h3 t-out="loan.name"/>
                    <p>Book: <span t-field="loan.book_id.display_name"/></p>
                    <p>Date: <span t-field="loan.date_loan"/></p>
                </div>
            </div>
        </t>
    </template>
</odoo>
```

Manifest: `'depends': ['portal', 'library']`, data files in order: security CSV, rules XML, template XML. Templates in `views/` need the `website` dependency only if you use website-only features; `website=True` on routes works when `website` is installed, which the portal pulls in on typical databases.

`t-field` renders with the viewer's language and the field's widget; `t-out` escapes. Never use `t-raw`, removed in 17 (use `t-out` with `Markup`).

## Tests

```python
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestLoanPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.p1 = cls.env['res.users'].create({
            'name': 'Portal One', 'login': 'portal_one',
            'password': 'portal_one',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.p2 = cls.env['res.users'].create({
            'name': 'Portal Two', 'login': 'portal_two',
            'password': 'portal_two',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        book = cls.env['library.book'].create({'name': 'Sample Book'})
        cls.loan1 = cls.env['library.loan'].create({
            'partner_id': cls.p1.partner_id.id, 'book_id': book.id})
        cls.loan2 = cls.env['library.loan'].create({
            'partner_id': cls.p2.partner_id.id, 'book_id': book.id})

    def test_list_shows_only_own(self):
        self.authenticate('portal_one', 'portal_one')
        res = self.url_open('/my/loans')
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.loan1.name, res.text)
        self.assertNotIn(self.loan2.name, res.text)

    def test_detail_of_foreign_record_redirects(self):
        self.authenticate('portal_one', 'portal_one')
        res = self.url_open(f'/my/loans/{self.loan2.id}', allow_redirects=False)
        self.assertEqual(res.status_code, 303)

    def test_token_gives_access(self):
        self.loan2._portal_ensure_token()
        res = self.url_open(f'/my/loans/{self.loan2.id}?access_token={self.loan2.access_token}')
        self.assertEqual(res.status_code, 200)

    def test_rule_blocks_orm(self):
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.loan2.with_user(self.p1).read(['name'])
```

Give the two loans distinct names (a sequence on `create` works) or the `assertNotIn` check is meaningless. `groups_id` is the Odoo 16-18 name on `res.users`.

## Pitfalls

- Using `sudo()` in the list controller. All customers see everything.
- No ACL line for `base.group_portal`: the page works for you as admin and returns an AccessError for every customer. Always test as a portal user.
- A global record rule elsewhere that references internal-only fields breaks portal reads (see [extending a standard workflow](blueprint-extending-sales.md)).
- `auth='public'` on a list route. Public users have no partner; the rule's `user.commercial_partner_id` is empty, so the list is empty or errors.
- Tokens: `access_token` in the URL is a bearer secret. Do not log full URLs, and do not generate tokens for records the customer should never share.
- Missing `placeholder_count` in the counters method: the home page badge stays on a spinner.
- Computing counts with `sudo().search_count`. Counts leak the existence of other customers' records.

## Versions

{% hint style="info" %}
16 to 18: the controller base class, `_document_check_access`, `_get_page_view_values` and the `portal.portal_docs_entry` pattern are the same. 17 and 18 use `has_access('read')` and `check_access('read')`; in 16 these are `check_access_rights('read', raise_exception=False)` and `check_access_rule('read')`. Home counters loaded through `/my/counters` are the model in 17 and 18; in 16 the home controller computed the values directly. `t-raw` is removed from 17.
{% endhint %}

## Try it

Read-only: list the portal rules and ACLs already on the sales model, to model yours on them.

```
select name, domain_force from ir_rule r join ir_model m on m.id = r.model_id where m.model = 'sale.order';
```

Then log in as a portal user (not admin) in a private window and open `/my/loans`.
