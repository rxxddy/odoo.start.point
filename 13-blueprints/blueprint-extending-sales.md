---
description: Adding fields, buttons, and rules to sales and invoicing.
---

# Extending a standard workflow

This blueprint extends `sale.order` the way a production module should: new fields, a confirmation guard that keeps `super()` and the state machine intact, a view inheritance anchored on real view ids, a record rule, and a test. The module is `sale_extra_checks`. The requirement is deliberately small: an order may only be confirmed when a "customer reference" is filled in, if the order's partner is flagged as requiring one.

## Module layout

```
sale_extra_checks/
  __manifest__.py
  __init__.py
  models/__init__.py
  models/sale_order.py
  models/res_partner.py
  views/sale_order_views.xml
  security/ir_rules.xml
  tests/__init__.py
  tests/test_confirm.py
```

```python
# __manifest__.py
{
    'name': 'Sale Extra Checks',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'depends': ['sale'],
    'data': [
        'security/ir_rules.xml',
        'views/sale_order_views.xml',
    ],
    'license': 'LGPL-3',
}
```

`depends` lists `sale` only. Do not depend on `sale_management` or `account` unless you use something from them; every extra dependency is a module your customer must install.

## Fields

```python
# models/res_partner.py
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_requires_customer_ref = fields.Boolean(
        string="Requires Customer Reference",
        help="Orders for this partner cannot be confirmed without a customer reference.",
    )
```

```python
# models/sale_order.py
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_customer_ref_required = fields.Boolean(
        compute='_compute_x_customer_ref_required',
        string="Customer Reference Required",
    )
    x_internal_check_note = fields.Text(string="Internal Check Note", copy=False)

    @api.depends('partner_id.commercial_partner_id.x_requires_customer_ref')
    def _compute_x_customer_ref_required(self):
        for order in self:
            order.x_customer_ref_required = (
                order.partner_id.commercial_partner_id.x_requires_customer_ref
            )
```

The standard `client_order_ref` field already holds the customer reference on `sale.order`, so we reuse it instead of adding a duplicate. Check what exists before you add a field: [model catalogue](../14-reference/model-catalogue.md).

The computed boolean is non-stored on purpose. It exists to drive `required`/`invisible` in the view; storing it would add a column and a recompute chain for no query benefit. See [ORM](../06-orm/) for the trade-offs of stored computes.

Prefix custom fields with `x_` only if your team's convention says so; on a module (as opposed to Studio) it is optional, but it keeps your additions greppable next to the standard ones.

## Overriding the confirm button

The button in the form calls `action_confirm` (verified in Odoo 18: `sale/models/sale_order.py`). The standard method first runs `_confirmation_error_message()` per order, raises `UserError` if it returns text, then writes the state, locks, and sends mails.

There are two hooks. Pick the lighter one.

```python
    def _confirmation_error_message(self):
        """Return an error string if the order cannot be confirmed."""
        error = super()._confirmation_error_message()
        if error:
            return error
        if self.x_customer_ref_required and not self.client_order_ref:
            return _("This customer requires a customer reference before confirmation.")
        return False
```

`_confirmation_error_message` is called inside a `for order in self` loop in `action_confirm`, so `self` is a singleton there. If you override it, return the parent's message first: that preserves the standard checks (state must be draft or sent, every line has a product on non-section lines).

Overriding `action_confirm` itself is only needed when you must do something after confirmation:

```python
    def action_confirm(self):
        res = super().action_confirm()
        for order in self.filtered(lambda o: o.state == 'sale'):
            order.message_post(body=_("Confirmed with customer reference %s", order.client_order_ref or "-"))
        return res
```

Rules for this override:

1. Call `super()` exactly once and return its result. The return value can be a wizard action (for example when a context key asks for it); dropping it breaks callers.
2. Never write `state` yourself. The state machine (`draft` -> `sent` -> `sale`, or `cancel`) belongs to the standard method; setting `state = 'sale'` skips locking, analytic validation, the confirmation date, and the mail template.
3. Filter after `super()`, not before. The standard method already raised for invalid records, so everything left in `self` is confirmed.
4. Operate on the recordset, not on `self[0]`. The method is also called on multi-record selections from the list view and by automated actions.

{% hint style="warning" %}
Do not raise from `action_confirm` after calling `super()`. The transaction rolls back, so nothing persists, but mails and external calls made inside `super()` may already have fired. Validate before, through the hook.
{% endhint %}

## View inheritance

The sales order form is `sale.view_order_form` (see the [view id catalogue](../14-reference/view-id-catalogue.md)). In Odoo 18 the form holds `payment_term_id` inside the "sale_info" group, and there are two Confirm buttons, one per state, both with `name="action_confirm"`. Because the name is not unique, anchor on a field, not on the button.

```xml
<odoo>
    <record id="view_order_form_extra_checks" model="ir.ui.view">
        <field name="name">sale.order.form.extra.checks</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">

            <!-- 1. make the reference required when the partner demands it -->
            <field name="client_order_ref" position="attributes">
                <attribute name="required">x_customer_ref_required</attribute>
            </field>

            <!-- 2. the computed flag must be present in the view to be usable in a domain/attrs -->
            <field name="partner_id" position="after">
                <field name="x_customer_ref_required" invisible="1"/>
            </field>

            <!-- 3. internal note next to the payment terms -->
            <xpath expr="//field[@name='payment_term_id']" position="after">
                <field name="x_internal_check_note"
                       placeholder="Notes for the team, not shown to the customer"/>
            </xpath>

        </field>
    </record>
</odoo>
```

Notes:

- `required="x_customer_ref_required"` is a Python expression evaluated client-side. Since Odoo 17 the `attrs` dictionary is gone; use direct attributes (`invisible`, `readonly`, `required`). In 16 you write `attrs="{'required': [('x_customer_ref_required', '=', True)]}"`.
- A field used in an expression must be in the view. Without the invisible field in step 2 the form raises an error on load.
- Prefer `<field name=... position=...>` over a long absolute xpath. When you do need `xpath`, anchor on `@name` or `@id`. The first Confirm button carries `id="action_confirm"`; the second has no id, so `//button[@name='action_confirm']` matches two nodes and Odoo uses the first one. That is silent and wrong half the time.
- `<attribute name="required">` replaces the whole attribute, it does not merge. Check what the parent already sets.

## Record rule

Requirement: salespeople who are not managers can only see orders of their own teams' partners flagged internal. For the example, a simpler rule: orders with `x_internal_check_note` set are readable only by sales managers.

```xml
<odoo>
    <record id="sale_order_rule_internal_note" model="ir.rule">
        <field name="name">Sale Order: restricted when internal note is set</field>
        <field name="model_id" ref="sale.model_sale_order"/>
        <field name="domain_force">[('x_internal_check_note', '=', False)]</field>
        <field name="groups" eval="[(4, ref('sales_team.group_sale_salesman'))]"/>
        <field name="perm_read" eval="True"/>
        <field name="perm_write" eval="True"/>
        <field name="perm_create" eval="False"/>
        <field name="perm_unlink" eval="True"/>
    </record>
</odoo>
```

Rules of the same model and group are OR-ed; rules without group are global and AND-ed with everything. The standard rules grant salespeople "all documents" through a group-bound rule (`sale.sale_order_personal_rule` and `sale_order_see_all`), so a new group-bound restriction is simply OR-ed with them and does nothing. To really restrict, either make the rule global (no `groups`) and add an exemption for managers in the domain, or restructure the groups. Test with a user, never as superuser: the superuser bypasses rules entirely.

For a global rule that still lets managers through:

```xml
<field name="domain_force">['|', ('x_internal_check_note', '=', False),
    ('user_id', '=', user.id)]</field>
```

{% hint style="info" %}
The portal has its own rule on `sale.order` (`sale.sale_order_rule_portal`, based on `message_partner_ids child_of commercial_partner`). Global rules apply to portal users too. A global rule that references internal-only fields can lock customers out of their own orders. See [A portal feature](blueprint-customer-portal.md).
{% endhint %}

## Test

```python
# tests/test_confirm.py
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.sale.tests.common import SaleCommon


@tagged('post_install', '-at_install')
class TestConfirmCheck(SaleCommon):

    def test_confirm_blocked_without_reference(self):
        self.partner.x_requires_customer_ref = True
        order = self.empty_order
        order.order_line = [(0, 0, {
            'product_id': self.product.id,
            'product_uom_qty': 1,
        })]
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_confirm_allowed_with_reference(self):
        self.partner.x_requires_customer_ref = True
        order = self.empty_order
        order.order_line = [(0, 0, {
            'product_id': self.product.id,
            'product_uom_qty': 1,
        })]
        order.client_order_ref = 'REF-001'
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_flag_not_set_keeps_standard_behaviour(self):
        order = self.empty_order
        order.order_line = [(0, 0, {
            'product_id': self.product.id,
            'product_uom_qty': 1,
        })]
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
```

`SaleCommon` ships with `partner`, `product`, and `empty_order` fixtures in 17 and 18. In 16 the equivalent base is `sale.tests.common.TestSaleCommon` with a different fixture set; adapt the setup rather than copying these names. Note that `self.empty_order` is created in `setUpClass` and shared across the class, but each test method runs in a savepoint, so changes roll back.

## Pitfalls

- Overriding `action_confirm` and writing `state` directly. You skip locking, mails, and analytic validation.
- Forgetting `super()` in a hook such as `_confirmation_error_message`. All standard checks silently disappear.
- A non-stored compute used in a search domain or `groupby`. Add a `search=` method or store it.
- `required` on a field whose value is set by an onchange later in the same save: the client validates before the server round trip.
- Using `//button[@name='action_confirm']`. Two matches, first wins.
- Testing record rules as admin. Use `with_user()` on a non-superuser.
- Dropping the return value of `super().action_confirm()`.

## Versions

{% hint style="info" %}
16: view modifiers use `attrs` and `states`; 17 and 18 use inline Python expressions. The `required="expr"` form above does not work in 16. `action_confirm` and the `_confirmation_error_message` hook exist in 16, 17 and 18. In 16, the test base class and fixtures differ.
{% endhint %}

## Try it

Read-only, in a Odoo shell on a development database you own:

```python
env['ir.ui.view'].search([('inherit_id.key', '=', 'sale.view_order_form')]).mapped('name')
env['ir.rule'].search([('model_id.model', '=', 'sale.order')]).mapped('name')
```

The first lists every view extending the form, including yours. The second shows the rules you must stay compatible with. Then run the tests:

```
odoo-bin -d dev_db -i sale_extra_checks --test-tags /sale_extra_checks --stop-after-init
```
