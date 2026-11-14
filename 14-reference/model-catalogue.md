---
description: Standard Odoo 18 models and the fields developers touch most.
---

# Model catalogue

The models below come up in almost every customisation. Names and fields were read from the Odoo 18 source (`_name` and the field declarations in each module's `models` folder). The list is a starting point, not a schema dump: for a full list use `env[model]._fields` in a shell.

## Core (base)

| Model | Purpose | Notes |
|---|---|---|
| `res.partner` | contacts, companies, addresses | fields include `name`, `is_company`, `vat`, `email`, `lang`, `type`, `parent_id`, `child_ids`, `category_id`, `commercial_partner_id` |
| `res.users` | users | each user delegates to a `res.partner` through `partner_id` |
| `res.groups` | security groups | referenced as `module.group_xml_id` |
| `res.company` | companies | multi-company filters use `company_id` |
| `res.currency`, `res.currency.rate` | currencies and rates | |
| `ir.model`, `ir.model.fields` | model and field registry | |
| `ir.ui.view` | views | `inherit_id`, `arch`, `mode`, `priority` |
| `ir.actions.act_window` | window actions | |
| `ir.actions.act_window.view` | per-action view binding | |
| `ir.actions.server` | server actions | |
| `ir.actions.client`, `ir.actions.act_url` | client and URL actions | |
| `ir.cron` | scheduled actions | |
| `ir.cron.trigger`, `ir.cron.progress` | one-off triggers and batch progress | |
| `ir.rule` | record rules | |
| `ir.attachment` | files | `res_model`, `res_id`, `res_name` |
| `ir.sequence`, `ir.sequence.date_range` | numbering | |
| `ir.config_parameter` | system parameters | |

## Sales

| Model | Key fields (as declared in source) |
|---|---|
| `sale.order` | `name`, `company_id`, `partner_id`, `state`, `date_order`, `origin`, `user_id`, `order_line`, `amount_total`, `invoice_ids` |
| `sale.order.line` | order lines; related to `sale.order` through `order_id` |

`sale.order.state` is the usual place where custom flows attach: drafts are quotations, confirmed orders are the same record in a later state.

## Accounting

| Model | Key fields |
|---|---|
| `account.move` | `name`, `state`, `move_type`, `company_id`, `partner_id`, `line_ids`, `invoice_line_ids`, `amount_total`, `payment_state`, `user_id` |
| `account.move.line` | journal items and invoice lines |

Invoices, bills, credit notes and journal entries are all `account.move`, told apart by `move_type`. `invoice_line_ids` is a subset of `line_ids`; the source says so in a comment. Write product lines to `invoice_line_ids`, and let Odoo build the balancing lines.

## Inventory and products

| Model | Key fields |
|---|---|
| `stock.picking` | `name`, `origin`, `move_type`, `state`, `move_ids`, `picking_type_id`, `partner_id`, `company_id`, `user_id` |
| `stock.picking.type` | operation types |
| `stock.move` | stock movements |
| `stock.quant` | on-hand quantities per location |
| `stock.quant.package` | packages |
| `product.template` | product master: `uom_id`, `weight_uom_name`, `volume_uom_name`, and so on |
| `product.product` | product variants |

`product.template` is what users see as "Product"; `product.product` is the variant that sales lines and stock moves reference. Mixing them up is a common source of wrong joins.

## Purchasing

`purchase.order` and `purchase.order.line` mirror the sales pair. View IDs for both are in the [view ID catalogue](view-id-catalogue.md).

## Mail

| Model | Purpose |
|---|---|
| `mail.thread` | abstract mixin for chatter, tracking, `message_post` |
| `mail.activity.mixin` | abstract mixin adding activities |
| `mail.message` | messages and notes |
| `mail.mail` | outgoing emails queue |
| `mail.followers` | followers |
| `mail.activity` | scheduled activities; `_rec_name` is `summary` |

## Reading a model definition

```python
Model = env['sale.order']
print(Model._name, Model._description, Model._order)
print(Model._inherit)
f = Model._fields['state']
print(f.type, f.selection, f.store, f.tracking)
```

## Pitfalls

* **Treating `res.users` as a contact.** A user has a partner; customer data belongs on the partner. Writing to the user's `name` writes through to the partner.
* **Writing to `line_ids` on invoices.** It is easy to unbalance an entry. Use `invoice_line_ids` for business lines.
* **Searching `product.product` when you meant the template.** A product with variants appears once as a template and many times as variants.
* **Using `ir.config_parameter` for secrets** or large payloads. It is world-readable by admins and loaded on many code paths.

{% hint style="info" %}
**Versions.** The models listed exist in 16, 17 and 18, but fields move: Odoo 17 and 18 reworked UoM, tax and stock reservation fields. Confirm any field on your target version with `env[model]._fields` before relying on it. Odoo 20 is not covered.
{% endhint %}

## Try it

Find which module defines a model and its fields, read-only:

```python
rec = env['ir.model'].search([('model', '=', 'sale.order')])
print(rec.modules)
print(env['ir.model.fields'].search([('model', '=', 'sale.order'), ('name', 'like', 'amount')]).mapped('name'))
```
