---
description: Standard Odoo 18 view external IDs to use as inherit_id.
---

# View ID catalogue

External IDs of standard views that custom modules inherit most often. All names below were extracted from Odoo 18 source (the `ir.ui.view` records in each module's `views` folder). The ID in `inherit_id` is `module.record_id`. Note that some IDs still say `tree` even though the arch root is `<list>` in 18; Odoo did not rename the records.

{% hint style="info" %}
**Versions.** IDs are stable across 16, 17 and 18 for the views listed here, but arch content is not: `<tree>` became `<list>`, and `attrs`/`states` became direct `invisible`/`readonly` expressions in 17. Re-check anchors for the version you target. Odoo 20 is not covered.
{% endhint %}

To find any ID from a running instance: Settings > Technical > Views with developer mode, or `env['ir.ui.view'].search([('model','=','res.partner')])` in a shell.

## base: partners

File: `odoo/addons/base/views/res_partner_views.xml`

| View | External ID |
|---|---|
| Partner form | `base.view_partner_form` |
| Partner list | `base.view_partner_tree` |
| Partner search | `base.view_res_partner_filter` |
| Partner simple form (quick create) | `base.view_partner_simple_form` |
| Partner address form | `base.view_partner_address_form` |
| Private address form | `base.res_partner_view_form_private` |
| Partner title form / list | `base.view_partner_title_form`, `base.view_partner_title_tree` |
| Partner tag (category) form / list / search | `base.view_partner_category_form`, `base.view_partner_category_list`, `base.res_partner_category_view_search` |
| Industry form / list / search | `base.res_partner_industry_view_form`, `base.res_partner_industry_view_tree`, `base.res_partner_industry_view_search` |

Mail additions to the partner (module `mail`): `mail.res_partner_view_form_inherit_mail`, `mail.res_partner_view_kanban_inherit_mail`, `mail.res_partner_view_search_inherit_mail`, `mail.res_partner_view_tree_inherit_mail`, `mail.res_partner_view_activity`.

## base: users and companies

Files: `res_users_views.xml`, `res_company_views.xml`

| View | External ID |
|---|---|
| User form | `base.view_users_form` |
| User list | `base.view_users_tree` |
| User kanban | `base.view_res_users_kanban` |
| User search | `base.view_users_search` |
| User simple form | `base.view_users_simple_form` |
| Preferences form (own profile) | `base.view_users_form_simple_modif` |
| Group form / search | `base.view_groups_form`, `base.view_groups_search` |
| Company form | `base.view_company_form` |
| Company list | `base.view_company_tree` |
| Company kanban | `base.view_res_company_kanban` |

## sale

File: `addons/sale/views/sale_order_views.xml`

| View | External ID |
|---|---|
| Order form (quotation and sales order) | `sale.view_order_form` |
| Sales order list | `sale.view_order_tree` |
| Quotation list | `sale.view_quotation_tree` |
| Quotation list with onboarding | `sale.view_quotation_tree_with_onboarding` |
| Sales order kanban | `sale.view_sale_order_kanban` |
| Quotation kanban with onboarding | `sale.view_quotation_kanban_with_onboarding` |
| Calendar / graph / pivot | `sale.view_sale_order_calendar`, `sale.view_sale_order_graph`, `sale.view_sale_order_pivot` |
| Activity | `sale.sale_order_view_activity` |
| Search | `sale.view_sales_order_filter` |
| Search additions | `sale.sale_order_view_search_inherit_quotation`, `sale.sale_order_view_search_inherit_sale` |
| Upload variants | `sale.sale_order_tree`, `sale.sale_order_list_upload`, `sale.sale_order_kanban_upload` |

## purchase

File: `addons/purchase/views/purchase_views.xml`

| View | External ID |
|---|---|
| Purchase order form | `purchase.purchase_order_form` |
| Purchase order list | `purchase.purchase_order_view_tree`, `purchase.purchase_order_tree`, `purchase.purchase_order_kpis_tree` |
| Search | `purchase.view_purchase_order_filter`, `purchase.purchase_order_view_search` |
| Kanban | `purchase.purchase_order_view_kanban_without_dashboard` |
| Activity | `purchase.purchase_order_view_activity` |
| Line list / form / search | `purchase.purchase_order_line_tree`, `purchase.purchase_order_line_form2`, `purchase.purchase_order_line_search` |

## account

File: `addons/account/views/account_move_views.xml`

| View | External ID |
|---|---|
| Journal entry / invoice form | `account.view_move_form` |
| Entry list | `account.view_move_tree` |
| Generic invoice list | `account.view_invoice_tree` |
| Customer invoice list | `account.view_out_invoice_tree` |
| Customer credit note list | `account.view_out_credit_note_tree` |
| Vendor bill list | `account.view_in_invoice_bill_tree`, `account.view_in_invoice_tree` |
| Vendor refund / receipt lists | `account.view_in_invoice_refund_tree`, `account.view_in_invoice_receipt_tree` |
| Move kanban | `account.view_account_move_kanban` |
| Search | `account.view_account_move_filter`, `account.view_account_invoice_filter`, `account.view_account_bill_filter` |
| Journal item form / list | `account.view_move_line_form`, `account.view_move_line_tree` |
| Journal item search | `account.view_account_move_line_filter` |
| Journal item pivot | `account.view_move_line_pivot` |
| Activity | `account.account_move_view_activity` |

The invoice list variants are separate records, not one list with a switch; a field added to `view_out_invoice_tree` will not appear on vendor bills.

## stock

File: `addons/stock/views/stock_picking_views.xml`

| View | External ID |
|---|---|
| Transfer form | `stock.view_picking_form` |
| Transfer list | `stock.vpicktree` |
| Transfer search | `stock.view_picking_internal_search` |
| Activity | `stock.stock_picking_view_activity` |

## product

File: `addons/product/views/product_template_views.xml`

| View | External ID |
|---|---|
| Product form (template, product module part) | `product.product_template_only_form_view` |
| Product list | `product.product_template_tree_view` |
| Product kanban | `product.product_template_kanban_view` |
| Activity | `product.product_template_view_activity` |

## Using an ID

```xml
<field name="inherit_id" ref="sale.view_order_form"/>
```

Add the owning module to `depends`. If your inheritance targets `account.view_move_form`, `account` must be in `depends` or the update fails with `External ID not found`.

## Pitfalls

* **Guessing IDs from the menu label.** `base.view_partner_tree` is the partner list; there is no `view_partner_list`. Look the ID up instead of inferring it.
* **Inheriting the wrong variant.** Sales orders and quotations share a form but have separate lists. Check which one the action uses.
* **IDs added by other modules.** A view like `mail.res_partner_view_form_inherit_mail` is a child of `base.view_partner_form`. Extending it instead of the base view adds a dependency on `mail` that may be unwanted.
* **Different edition layout.** Enterprise modules add children to many of these views. Your anchor still resolves, but the neighbouring nodes may differ.

## Try it

List the children of a view in your instance, read-only:

```python
v = env.ref('sale.view_order_form')
for c in v.inherit_children_ids.sorted('priority'):
    print(c.priority, c.xml_id, c.name)
```
