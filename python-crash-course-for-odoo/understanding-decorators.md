# Understanding Decorators

## 🏷️ Understanding Decorators

> Status: ORM BINDING | Focus: EXECUTION TRIGGERS

In pure Python, a function is just a block of code sitting in memory, waiting to be called. In Odoo, a function needs to listen to the database, react to user interface events, or calculate fields on the fly.

To bridge this gap, Odoo uses Decorators—the `@api.something` tags you place immediately above your method definitions. Decorators are the structural glue that binds your custom Python logic directly into Odoo's C-optimized ORM engine.

If you use the wrong decorator, your code will either never execute, crash the server, or create an invisible performance bottleneck. Here is the survival guide to the essential Odoo decorators.

#### ⚖️ 1. The Classic Trap: `@api.depends` vs `@api.onchange`

This is the single most common failure point for new Odoo developers. Both decorators seem to do the same thing: they react when a field changes. However, their architectural purpose is entirely different.

**`@api.depends` (The Database Architect)**

Use this exclusively for Computed Fields. It tells the PostgreSQL database exactly when a value needs to be recalculated. It triggers on the backend, ensuring data consistency whether the change came from the UI, a webhook, or a cron job.

Python

```python
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    margin = fields.Float(compute='_compute_margin', store=True)

    # The decorator binds the computation to these specific fields.
    # If price_subtotal or purchase_price changes, this method runs.
    @api.depends('price_subtotal', 'purchase_price')
    def _compute_margin(self):
        for line in self:
            line.margin = line.price_subtotal - line.purchase_price
```

_Architectural Rule:_ If a computed field is `store=True`, you must use `@api.depends`, or the database will never know when to update the stored value.

**`@api.onchange` (The UI Illusionist)**

Use this exclusively for User Interface feedback. It triggers _while_ the user is typing or selecting a value in a form view, before the record is actually saved to the database.

Python

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.onchange('partner_id')
    def _onchange_partner_id_warning(self):
        # This only runs in the user's browser/session
        if self.partner_id and self.partner_id.credit_limit < 0:
            return {
                'warning': {
                    'title': _("Credit Hold"),
                    'message': _("This customer has exceeded their credit limit.")
                }
            }
```

_Doomsday Warning:_ Never execute a database write (`self.env['...'].create()`) inside an `@api.onchange` method. Because `onchange` runs in a virtual UI record, writing to the database here will result in phantom records and ghost data that corrupts your ecosystem.

#### 🛡️ 2. Database Integrity: `@api.constrains`

SQL constraints (like `_sql_constraints`) are fast, but they are limited to simple rules (e.g., "This field must be unique"). When you need complex, logical validation before allowing a record to be saved, you use `@api.constrains`.

This decorator listens for database `create` or `write` operations on the specified fields and runs your validation logic just before the transaction is committed.

Python

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.constrains('age', 'is_company')
    def _check_legal_age(self):
        for partner in self:
            if not partner.is_company and partner.age < 18:
                # Halts the database transaction and shows a red UI error
                raise exceptions.ValidationError(_("Individuals must be at least 18 years old."))
```

#### 🏭 3. Environment & Batching: The `@api.model` Family

Sometimes, your functions do not operate on a specific record. For example, if you are creating a new record, the record doesn't exist yet, so `self` cannot contain it.

**`@api.model` (The Class Method)**

Use this when your method does not need an active Recordset to operate. The `self` parameter will simply represent an empty instance of the model, giving you access to the environment (`self.env`) but no specific database row.

Python

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def fetch_api_configuration(self):
        # self is empty, but we can still use self.env to query other tables
        api_key = self.env['ir.config_parameter'].sudo().get_param('my.api.key')
        return api_key
```

**`@api.model_create_multi` (The Batch Processor)**

Since Odoo 13, the standard `.create()` method was overhauled for batch performance. When overriding the creation of a record, you must use this decorator. It ensures that even if you pass a single dictionary to create one record, Odoo automatically wraps it in a list to process it via its highly optimized batch-insertion logic.

Python

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        # vals_list is ALWAYS a list of dictionaries, even for a single record
        for vals in vals_list:
            if not vals.get('client_order_ref'):
                vals['client_order_ref'] = 'WEB-DEFAULT'
                
        return super(SaleOrder, self).create(vals_list)
```

#### 🧹 4. The Background Sweeper: `@api.autovacuum`

In high-throughput environments (like integrating heavily with courier APIs), you often generate thousands of temporary logs or transient records. You do not want these bloating your PostgreSQL database forever.

`@api.autovacuum` is a specialized decorator that hooks your method into Odoo's internal garbage collection cron job (which runs automatically every day).

Python

```python
class SyncLog(models.Model):
    _name = 'api.sync.log'
    _description = 'Integration Logs'

    @api.autovacuum
    def _gc_clear_old_logs(self):
        # Define the threshold: Logs older than 30 days
        limit_date = fields.Datetime.now() - datetime.timedelta(days=30)
        
        # Search and destroy in batch
        old_logs = self.search([('create_date', '<', limit_date)])
        old_logs.unlink()
        
        _logger.info("Autovacuum: Cleared %s expired integration logs.", len(old_logs))
```
