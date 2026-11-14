---
description: Report actions, QWeb PDF templates, paper formats, and wkhtmltopdf.
---

# PDF reports

A PDF report is a QWeb template rendered to HTML on the server, then converted to PDF by `wkhtmltopdf`. A report action (`ir.actions.report`) links the template to a model and puts a button in the Print menu.

## Report action and template

```xml
<record id="action_report_loan" model="ir.actions.report">
  <field name="name">Loan slip</field>
  <field name="model">library.loan</field>
  <field name="report_type">qweb-pdf</field>
  <field name="report_name">library.report_loan_document</field>
  <field name="report_file">library.report_loan_document</field>
  <field name="print_report_name">'Loan - %s' % (object.name or 'draft')</field>
  <field name="binding_model_id" ref="model_library_loan"/>
  <field name="binding_type">report</field>
  <field name="paperformat_id" ref="library.paperformat_a5"/>
</record>

<template id="report_loan_document">
  <t t-call="web.html_container">
    <t t-foreach="docs" t-as="doc">
      <t t-call="web.external_layout">
        <div class="page">
          <h2>Loan <span t-field="doc.name"/></h2>
          <p>Borrower: <span t-field="doc.borrower_id"/></p>
          <table class="table table-sm">
            <tr t-foreach="doc.line_ids" t-as="line">
              <td t-out="line.book_id.name"/>
              <td class="text-end" t-field="line.fee"/>
            </tr>
          </table>
        </div>
      </t>
    </t>
  </t>
</template>
```

Essentials:

- `report_name` is the XML ID of the template; `docs` is the recordset being printed, `doc_ids` and `doc_model` are also passed.
- `web.html_container` provides the HTML shell; `web.external_layout` adds the company header and footer; `web.internal_layout` is the plain variant. Content goes in `<div class="page">`.
- `print_report_name` is a Python expression with `object`; it sets the download filename.
- `binding_type` of `report` shows the action in the Print dropdown. `attachment` and `attachment_use` store the generated PDF on the record and reuse it, which freezes the output; set them only for legal documents.

## Custom data: report models

When the template needs computed data, define an abstract model named `report.<report_name>`:

```python
class ReportLoan(models.AbstractModel):
    _name = "report.library.report_loan_document"
    _description = "Loan slip report"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["library.loan"].browse(docids)
        return {"doc_ids": docids, "doc_model": "library.loan", "docs": docs,
                "total_fee": sum(docs.mapped("fee"))}
```

The returned dict becomes the template context.

## Paper format

```xml
<record id="paperformat_a5" model="report.paperformat">
  <field name="name">A5 library</field>
  <field name="format">A5</field>
  <field name="orientation">Portrait</field>
  <field name="margin_top">30</field>
  <field name="margin_bottom">20</field>
  <field name="header_spacing">25</field>
  <field name="dpi">90</field>
</record>
```

`header_spacing` is the gap between the header and content; if the header overlaps the body, raise it and `margin_top` together. Use `dpi` 90 to match what wkhtmltopdf renders consistently.

## Rendering from code

```python
pdf, _fmt = self.env["ir.actions.report"]._render_qweb_pdf("library.action_report_loan", res_ids=loan.ids)
```

The first argument is the report reference (XML ID or `report_name`). Attach it to a mail with `ir.attachment` and `attachment_ids`.

## wkhtmltopdf

wkhtmltopdf with patched Qt is required; the unpatched distro build ignores header and footer templates and spacing. Odoo checks the binary and logs a warning on start if it is missing or unpatched. It renders an old WebKit: no CSS grid, limited flexbox. Use tables and Bootstrap's grid (`row`/`col-*` work, but print with `col-6` rather than responsive classes).

For local debugging, add `?debug=1` to the report URL `/report/html/<report_name>/<id>` to see the HTML before conversion.

## Pitfalls

- Header and footer are rendered in separate processes; assets (fonts, images) must be reachable at the base URL (`web.base.url`) from the server itself. A wrong `web.base.url` gives blank logos.
- `t-field` with `widget: "image"` on large images produces large PDFs; use the sized variants.
- Report changes not showing: a stored attachment is reused. Delete the attachment or clear `attachment` on the action.
- Fonts: wkhtmltopdf uses system fonts; if a glyph is missing, install the font on the server, not in CSS.
- Multi-record prints loop `docs`; page breaks need `style="page-break-after: always;"` on each doc.

## Versions

{% hint style="info" %}
From 17 to 18 the layouts are `web.external_layout` with company-selectable styles; `report_type`, `report_name`, and `_render_qweb_pdf` keep the same shape. In 16, `_render_qweb_pdf` took `res_ids` as the first argument after a report reference, in 17+ the report is resolved through the action record; check your call site when porting.
{% endhint %}

## Try it

Open `/report/html/library.report_loan_document/1` in a browser (developer mode) to iterate on the layout without PDF conversion, then print the same report from the UI to compare.
