# How to Create a Model from Scratch

## 🏗️ How to Create a Model from Scratch

> Status: GROUND ZERO | Focus: BASE ARCHITECTURE

Everything in Odoo begins with a Model. When you define a class inheriting from `models.Model`, you are not just writing Python; you are issuing a direct architectural command to PostgreSQL to forge a new database table.

In a scenario where you have no external assistance, your model definition must be structurally flawless. A poorly designed base model creates technical debt that cascades through every view, API endpoint, and access rule in your ecosystem.

This is your absolute blueprint for scaffolding a robust, production-grade model from nothing.

#### 🏛️ 1. The Immutable Master Template

Do not start from a blank screen. Copy this template. It contains the standard reserved fields, relational hooks, and structural metadata required to make a model immediately usable within the Odoo framework.

Python

```python
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class DoomsdayProtocol(models.Model):
    # 1. METADATA: The Database Identity
    _name = 'doomsday.protocol'
    _description = "Emergency Execution Protocol"
    _order = 'sequence asc, create_date desc'
    
    # 2. MAGIC FIELDS: The Odoo Standards
    # 'name' is the default field used in Many2one dropdowns
    name = fields.Char(
        string="Protocol Reference", 
        required=True, 
        copy=False, 
        readonly=True, 
        default=lambda self: _('New')
    )
    
    # 'active' enables the "Archive" standard functionality. 
    # If False, the record is hidden from default searches (Soft Delete).
    active = fields.Boolean(string="Active", default=True)
    sequence = fields.Integer(string="Sequence", default=10)

    # 3. BASE DATA FIELDS
    execution_date = fields.Datetime(string="Scheduled Execution")
    severity_level = fields.Selection([
        ('low', 'Low (Observation)'),
        ('medium', 'Medium (Containment)'),
        ('critical', 'Critical (Total Lockdown)')
    ], string="Severity", default='low', required=True)
    
    protocol_notes = fields.Text(string="Architectural Notes")

    # 4. RELATIONAL FIELDS: Tying into the Ecosystem
    # Links this record to the user who created it
    responsible_id = fields.Many2one(
        'res.users', 
        string="Responsible Architect", 
        default=lambda self: self.env.user,
        tracking=True
    )
    
    # Links to the target companies (Multi-company environment safety)
    company_id = fields.Many2one(
        'res.company', 
        string="Company", 
        required=True, 
        default=lambda self: self.env.company
    )

    # 5. CORE METHOD OVERRIDES (The entry point for custom logic)
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                # Automatically generate a sequential ID (requires an ir.sequence XML record)
                vals['name'] = self.env['ir.sequence'].next_by_code('doomsday.protocol.seq') or _('New')
        return super(DoomsdayProtocol, self).create(vals_list)
```

_(Note: As established in your architectural directives, while these blueprint comments are in English for your personal survival repository, remember to enforce strict Italian commenting if you deploy this directly into a live corporate ERP module)._

#### 🔬 2. Dissecting the Anatomy

If you are forced to debug or expand this model without internet access, you must understand exactly how the ORM interprets these attributes.

**The `_name` Attribute (The SQL Forger)**

When you write `_name = 'doomsday.protocol'`, Odoo takes that string, replaces the dots with underscores, and creates a PostgreSQL table named `doomsday_protocol`.

* Cardinal Rule: Once this model is deployed and the table is created, changing the `_name` will cause Odoo to create an entirely _new_ table, abandoning all your existing data. Choose this name carefully.

**The Magic Fields (`name` and `active`)**

Odoo heavily relies on convention over configuration.

* If you include a `name` field, Odoo will automatically use it as the display title whenever this record is referenced in another model (via a Many2one). If you do not have a `name` field, you will be forced to manually write a `_compute_display_name` function, or your records will show up in dropdowns as `doomsday.protocol,1`.
* If you include an `active` field, Odoo automatically adds "Archive/Unarchive" actions to your tree and form views. Unarchived records (`active=False`) are silently filtered out of SQL queries unless specifically requested.

**Multi-Company Safety (`company_id`)**

In modern architectures, failing to include a `company_id` field is a fatal error. Without it, records will bleed across company boundaries, violating data segregation rules. Always include it, and default it to `self.env.company`.

#### 🔏 3. The Invisible Wall: Access Rights

You have written the Python code. You restart the server and upgrade the module. You will not see your model in the UI.

Why? Because Odoo operates on a strict "deny-by-default" security paradigm. A model without explicitly defined access rights is completely invisible to the framework, even for the Administrator.

To bring your model to life, you must immediately create (or update) the `security/ir.model.access.csv` file.

Code snippet

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_doomsday_protocol_user,doomsday.protocol.user,model_doomsday_protocol,base.group_user,1,1,1,0
access_doomsday_protocol_manager,doomsday.protocol.manager,model_doomsday_protocol,base.group_erp_manager,1,1,1,1
```

How to read this CSV in the dark:

1. `model_id:id`: Must be `model_` followed by your `_name` with underscores (`model_doomsday_protocol`).
2. `group_id:id`: The security group gaining access. `base.group_user` is standard internal users; `base.group_erp_manager` is administrators.
3. Permissions (`1` for allow, `0` for deny): Read, Write, Create, Unlink (Delete). In the example above, standard users cannot delete records (`perm_unlink=0`), but managers can.
