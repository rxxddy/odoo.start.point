# Custom PDF Report Template

## 📄 Custom PDF Report Template

> Status: PRESENTATION LAYER | Focus: QWEB & DOCUMENT GENERATION

When external systems fail, physical documentation becomes your only proof of transaction. Generating legally compliant, perfectly formatted PDFs (Commercial Invoices, Waybills, Doomsday Manifests) is a non-negotiable requirement for an ERP.

Odoo uses wkhtmltopdf to convert HTML/QWeb templates into PDF documents. A poorly written QWeb template will not just look bad; it will consume massive amounts of CPU and memory, potentially crashing the worker thread during batch printing operations.

Here is the enterprise-grade blueprint for building a custom PDF report from the ground up, including the Action, the Template, the Paper Format, and the Python Data Parser.

#### ⚙️ 1. The Paper Format (XML)

Before designing the document, you must define the canvas. By default, Odoo uses A4 or US Letter based on the company's country. If you are generating specialized documents (like 4x6 inch shipping labels or custom manifests), you must define an `report.paperformat`.

Create a file named `data/report_paperformat.xml`:

XML

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <record id="paperformat_doomsday_manifest" model="report.paperformat">
            <field name="name">Doomsday Manifest Format</field>
            <field name="default" eval="False"/>
            <field name="format">A4</field>
            <field name="page_height">0</field>
            <field name="page_width">0</field>
            <field name="orientation">Portrait</field>
            <field name="margin_top">40</field>
            <field name="margin_bottom">20</field>
            <field name="margin_left">7</field>
            <field name="margin_right">7</field>
            <field name="header_line" eval="False"/>
            <field name="header_spacing">35</field>
            <field name="dpi">90</field>
        </record>
    </data>
</odoo>
```

#### 🖨️ 2. The Report Action (XML)

This is the bridge between the UI and the template. Creating this record adds the "Print" option to the "Action" dropdown menu at the top of your model's form and tree views.

Create a file named `views/report_actions.xml`:

XML

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="action_report_doomsday_manifest" model="ir.actions.report">
        <field name="name">Execution Manifest</field>
        <field name="model">doomsday.protocol</field>
        <field name="report_type">qweb-pdf</field>
        
        <field name="report_name">custom_doomsday_module.report_manifest_template</field>
        <field name="report_file">custom_doomsday_module.report_manifest_template</field>
        
        <field name="print_report_name">'Manifest_%s' % (object.name)</field>
        <field name="binding_model_id" ref="model_doomsday_protocol"/>
        <field name="binding_type">report</field>
        <field name="paperformat_id" ref="custom_doomsday_module.paperformat_doomsday_manifest"/>
    </record>
</odoo>
```

#### 🎨 3. The QWeb Template (XML)

This is the actual structure of the PDF. It is written in HTML, utilizing Bootstrap 5 classes (native to Odoo 18) and QWeb rendering directives (`t-`).

The Architectural Rule for QWeb: Never perform complex calculations or ORM searches inside the XML. The template's _only_ job is presentation.

Create a file named `views/report_templates.xml`:

XML

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="report_manifest_template">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="doc">
                <t t-call="web.external_layout">
                    
                    <div class="page">
                        
                        <div class="row">
                            <div class="col-12 text-center mb-4">
                                <h2 style="font-weight: bold; border-bottom: 2px solid black;">
                                    PROTOCOL MANIFEST: <span t-field="doc.name"/>
                                </h2>
                            </div>
                        </div>

                        <div class="row mb-4">
                            <div class="col-6">
                                <strong>Responsible Architect:</strong>
                                <p t-field="doc.responsible_id"/>
                            </div>
                            <div class="col-6 text-end">
                                <strong>Execution Date:</strong>
                                <p t-field="doc.execution_date" t-options='{"widget": "datetime", "format": "yyyy-MM-dd HH:mm:ss"}'/>
                            </div>
                        </div>

                        <div class="row">
                            <div class="col-12">
                                <t t-if="doc.severity_level == 'critical'">
                                    <div class="alert alert-danger" role="alert">
                                        <strong>CRITICAL WARNING:</strong> Total lockdown procedures apply.
                                    </div>
                                </t>
                                <t t-elif="doc.severity_level == 'medium'">
                                    <div class="alert alert-warning" role="alert">
                                        <strong>NOTICE:</strong> Containment procedures apply.
                                    </div>
                                </t>
                                <t t-else="">
                                    <p>Standard observation protocols in effect.</p>
                                </t>
                            </div>
                        </div>

                        <div class="row mt-4">
                            <div class="col-12">
                                <strong>Architectural Notes:</strong>
                                <p t-out="doc.protocol_notes or 'No notes provided.'"/>
                            </div>
                        </div>

                    </div>
                </t>
            </t>
        </t>
    </template>
</odoo>
```

**🛡️ QWeb Survival Skills:**

* `t-field` vs `t-out`: Always use `t-field` for database fields (Dates, Monetary values, Many2one). Odoo will automatically format them according to the active user's language and currency settings. Use `t-out` only for raw Python strings, variables, or static text.
* Translation: Wrap static text in standard HTML, and Odoo's translation engine will pick it up. No need for `_()` inside QWeb.

#### 🧠 4. The Python Parser (Advanced Data Injection)

By default, Odoo passes the `docs` variable (the selected records) to your QWeb template. But what if your report requires data that does not exist directly on the record? What if you need to calculate an aggregate total, or fetch data from an external API _at the exact moment_ the PDF is generated?

You must intercept the rendering engine by defining an `AbstractModel` whose name matches your report action.

Create a file named `models/report_parser.py`:

Python

```python
import logging
from odoo import models, api, exceptions, _

_logger = logging.getLogger(__name__)

class ReportDoomsdayManifest(models.AbstractModel):
    # The _name MUST be exactly 'report.' followed by the module_name.report_name
    _name = 'report.custom_doomsday_module.report_manifest_template'
    _description = "Custom Parser for Doomsday Manifest"

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        This method is intercepted by the Odoo rendering engine before the PDF is built.
        It allows you to inject custom variables into the QWeb template.
        """
        # Fetch the selected records
        docs = self.env['doomsday.protocol'].browse(docids)

        if not docs:
            raise exceptions.UserError(_("No records found to generate the manifest."))

        # 1. CALCULATE COMPLEX OR EXTERNAL DATA
        # Example: Querying the database for related system logs that aren't directly linked
        system_uptime = self.env['ir.config_parameter'].sudo().get_param('system.uptime.metric', 'Unknown')
        
        active_critical_threats = self.env['doomsday.protocol'].search_count([
            ('severity_level', '=', 'critical'),
            ('active', '=', True)
        ])

        # 2. RETURN THE RENDER DICTIONARY
        # Anything returned in this dictionary becomes a callable variable inside your QWeb XML.
        return {
            'doc_ids': docids,
            'doc_model': 'doomsday.protocol',
            'docs': docs,
            
            # Injecting our custom calculated variables into the template
            'current_uptime': system_uptime,
            'global_threat_count': active_critical_threats,
        }
```

_Inside your QWeb template, you can now use `<t t-out="current_uptime"/>` directly, without needing to store that value on the database record!_

#### 🧩 5. Manifest Declaration

Ensure all files are loaded in the correct order in your `__manifest__.py`. Paper formats must be loaded before the report actions.

Python

```python
    'data': [
        'security/ir.model.access.csv',
        'data/report_paperformat.xml',      # 1. Define the canvas
        'views/report_actions.xml',         # 2. Define the print button
        'views/report_templates.xml',       # 3. Define the QWeb HTML
    ],
```
