# How to Add a Custom Field to an Existing Model

## 🧩 How to Add a Custom Field to an Existing Model

> Status: SURVIVAL TACTIC | Focus: NON-DESTRUCTIVE INJECTION

In a functioning ERP, you rarely build isolated systems from scratch. 90% of your architectural work involves augmenting existing core models (like `sale.order`, `res.partner`, or `account.move`) with custom business logic.

Adding a custom field requires a surgical, two-pronged attack:

1. The Backend (Python): Instructing PostgreSQL to alter the database schema.
2. The Frontend (XML): Injecting the new field into the user interface without breaking the original view layout.

Here is the flawless execution protocol for extending an existing Odoo entity.

#### 🐍 Phase 1: The Python Backend (Schema Extension)

To add a field to an existing model, you must use Classical Extension (`_inherit`). This tells Odoo: _"Do not create a new table. Find the existing table in PostgreSQL and append my new columns to it."_

In this example, we will add an "Emergency Clearance Level" to the standard Contact (`res.partner`) model.

_(Note: As per our strict architectural standards, inline code comments within the module ecosystem are written in Italian)._

Python

```python
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    # 1. IDENTIFICAZIONE DEL BERSAGLIO
    # Utilizziamo _inherit senza _name. Questo modifica la tabella esistente 'res_partner'.
    _inherit = 'res.partner'

    # 2. DEFINIZIONE DEI NUOVI CAMPI
    # Questi campi verranno aggiunti come nuove colonne nel database PostgreSQL.
    doomsday_clearance_level = fields.Selection([
        ('none', 'Nessuna'),
        ('level_1', 'Livello 1 (Base)'),
        ('level_2', 'Livello 2 (Avanzato)'),
        ('omega', 'Direttiva Omega')
    ], string="Livello di Sicurezza", default='none', tracking=True)

    is_essential_personnel = fields.Boolean(
        string="Personale Essenziale", 
        default=False,
        help="Selezionare se il contatto è critico per la continuità aziendale."
    )
```

The Butterfly Effect Warning: Whenever you add a new field to a core model like `res.partner`, remember that this model is accessed thousands of times a minute across the system. Avoid making new fields `required=True` unless you also provide a `default=` value, otherwise, you will instantly crash all downstream code attempting to create generic partners (like website signups).

#### 🎨 Phase 2: The XML Frontend (UI Injection)

Defining the field in Python alters the database, but it remains completely invisible to the user. You must inject it into the XML View.

To do this safely, we use XPath Inheritance. We do not copy the original view; we reference its unique ID (`inherit_id`) and inject our field relative to an existing element.

XML

```python
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form_inherit_doomsday" model="ir.ui.view">
        <field name="name">res.partner.form.inherit.doomsday</field>
        <field name="model">res.partner</field>
        
        <field name="inherit_id" ref="base.view_partner_form"/>
        
        <field name="arch" type="xml">
            
            <xpath expr="//field[@name='category_id']" position="after">
                <field name="doomsday_clearance_level" widget="badge"/>
                <field name="is_essential_personnel" widget="boolean_toggle"/>
            </xpath>
            
        </field>
    </record>
</odoo>
```

**🎯 How to Find the Target (`ref` and `expr`) in the Dark:**

If you do not have AI to tell you the name of the original view, you must find it manually:

1. Turn on Developer Mode in Odoo.
2. Open the form you want to modify (e.g., a Customer profile).
3. Click the Debug Bug icon (top right) ➔ Edit View: Form.
4. Look at the External ID field at the top. That is your `inherit_id` (e.g., `base.view_partner_form`).
5. Look at the Architecture tab to find a field name you want to use as an anchor for your XPath expression.

#### ⚙️ Phase 3: The Manifest Link (The Final Check)

The most common reason developers tear their hair out is writing perfect Python and XML, restarting the server, upgrading the module... and seeing absolutely nothing change.

You must declare your new XML file in your `__manifest__.py`.

If you saved the XML snippet above as `views/res_partner_views.xml`, you must add it to the `data` array in your manifest.

Python

```python
    'data': [
        # ... i tuoi file di sicurezza ...
        
        # Le viste devono essere dichiarate qui per essere caricate nel database
        'views/res_partner_views.xml',
    ],
```

Once declared, restart your server and update the module from the command line:

`python3 odoo-bin -c /etc/odoo.conf -d my_database -u my_custom_module`
