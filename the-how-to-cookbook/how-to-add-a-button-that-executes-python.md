# How to Add a Button That Executes Python

## 🔘 How to Add a Button That Executes Python

> Status: INTERACTIVE UI | Focus: BRIDGING FRONTEND AND BACKEND

A static database is useless. To build an ERP, users must be able to trigger complex business logic directly from the interface.

In Odoo, buttons are the primary bridge between the XML Frontend and the Python Backend. When a user clicks a button on a record, Odoo packages that specific database record (or records) and hands it directly to a Python function.

Here is the exact protocol for wiring a UI button to a Python method without breaking the execution flow.

#### 🔀 1. The Two Types of Buttons

Before writing code, you must understand the `type` attribute of an Odoo button.

1. `type="object"` (The Python Trigger): The button will look for a Python method with the exact name specified in the `name` attribute. This is what we will build.
2. `type="action"` (The XML Trigger): The button will look for an `ir.actions.act_window` or `ir.actions.server` record in the database. Use this when you just want to open a menu or a view without writing custom Python logic.

#### 🐍 Phase 1: The Python Backend (The Execution Target)

First, we define the method in our Python model.

The Singleton Warning: Remember the Golden Rule of Recordsets. Even if the user clicks a button on a single form view, Odoo passes `self` as a Recordset. You must loop through `self` to prevent a `ValueError`.

Python

```python
import logging
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)

class DoomsdayProtocol(models.Model):
    _inherit = 'doomsday.protocol'

    # 1. IL METODO BERSAGLIO
    # Il nome del metodo deve corrispondere esattamente all'attributo "name" del bottone XML.
    def action_execute_protocol(self):
        # 2. IL LOOP DI SICUREZZA (Singleton Trap Prevention)
        for record in self:
            # Controllo di validazione prima dell'esecuzione
            if record.severity_level == 'low':
                raise exceptions.UserError(_("I protocolli di basso livello non richiedono esecuzione manuale."))
            
            # 3. ESECUZIONE DELLA LOGICA DI BUSINESS
            _logger.info("Avvio del protocollo di emergenza per: %s", record.name)
            
            # Scrittura nel database per aggiornare uno stato (esempio)
            record.write({
                'protocol_notes': _("Eseguito manualmente in data odierna."),
                'active': False  # Archivia il record dopo l'esecuzione
            })
            
        # 4. RITORNO (Opzionale)
        # Se si restituisce True, l'interfaccia utente si ricarica automaticamente.
        return True
```

#### 🎨 Phase 2: The XML Frontend (The UI Anchor)

Now we must inject the button into the user interface. The most common place for an action button is inside the `<header>` of a Form View (the status bar at the top).

We use standard XPath injection to locate the header and append our button.

XML

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_doomsday_protocol_form_button" model="ir.ui.view">
        <field name="name">doomsday.protocol.form.button</field>
        <field name="model">doomsday.protocol</field>
        <field name="inherit_id" ref="custom_doomsday_module.view_doomsday_protocol_form"/>
        <field name="arch" type="xml">
            
            <xpath expr="//header" position="inside">
                
                <button name="action_execute_protocol" 
                        string="Esegui Protocollo" 
                        type="object" 
                        class="oe_highlight" 
                        confirm="Sei assolutamente sicuro di voler eseguire questo protocollo?"/>
                        
            </xpath>
            
        </field>
    </record>
</odoo>
```

**🛡️ Button Attributes You Should Know:**

* `class="oe_highlight"`: Makes the button the primary call-to-action (colored).
* `class="btn-secondary"`: Makes the button a standard grey outline.
* `confirm="Testo"`: A built-in JS feature that throws a native browser confirmation pop-up before the Python method is even called. Incredibly useful for dangerous operations.
* `invisible="state != 'draft'"`: Hides the button dynamically based on the record's current data (using Odoo 17+ domain syntax).

#### 🎆 Phase 3: Returning UI Actions (Advanced)

By default, clicking a `type="object"` button simply executes the Python code in the background and silently refreshes the current record.

However, you can force the user's browser to do something specific by returning a dictionary at the end of your Python method.

**Example A: Triggering a Rainbow Man Success Effect**

Python

```python
    def action_execute_protocol(self):
        for record in self:
            record.severity_level = 'low'
            
        # Ritorna un'azione per mostrare l'animazione di successo
        return {
            'effect': {
                'fadeout': 'slow',
                'message': _('Crisi scongiurata con successo.'),
                'type': 'rainbow_man',
            }
        }
```

**Example B: Opening a URL (e.g., Redirecting to an external tracking page)**

Python

```python
    def action_track_shipment(self):
        self.ensure_one() # Garantisce che ci sia un solo record selezionato
        
        tracking_url = f"https://www.dhl.com/track?tracking={self.tracking_ref}"
        
        # Forza il browser dell'utente ad aprire il link in una nuova scheda
        return {
            'type': 'ir.actions.act_url',
            'url': tracking_url,
            'target': 'new',
        }
```
