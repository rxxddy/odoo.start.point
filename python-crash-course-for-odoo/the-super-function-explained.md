# The super() Function Explained

## 🧬 The super() Function Explained

> Status: CRITICAL MECHANIC | Focus: COLLABORATIVE INHERITANCE

If there is one concept that separates an Odoo Architect from an amateur, it is the mastery of the `super()` function.

Odoo is not a blank canvas; it is a massive, highly interconnected ecosystem. When you need to add a new rule to a Sales Order, you do not write a new Sales Order model from scratch. You inherit the existing one and inject your logic.

However, if you overwrite a core method (like `action_confirm` or `write`) without calling `super()`, you obliterate the original Odoo code. The system will stop generating invoices, inventory will freeze, and external integrations will crash.

Calling `super()` ensures you add to the chain, rather than breaking it.

#### ⛓️ 1. The Inheritance Chain (How it Works)

When multiple modules inherit the same model (e.g., `sale.order`), Odoo stacks their methods on top of each other like a ladder.

When a user clicks "Confirm", Odoo looks at the top of the ladder (your custom module). If you use `super()`, you tell Odoo: _"Execute my code, and then pass the execution down to the next module on the ladder."_

#### 🧱 2. The Standard Anatomy of `super()`

While modern Python 3 allows a simplified `super()` call, the Odoo core codebase and enterprise modules heavily utilize the explicit syntax. You must understand and use this format to guarantee context is preserved across the ORM.

Python

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        # 1. YOUR CUSTOM CODE BEFORE THE ORIGINAL METHOD
        _logger.info("Executing custom pre-confirmation logic...")

        # 2. THE SUPER CALL (Passing execution down the chain)
        # Syntax: super(CurrentClassName, self).method_name(arguments)
        res = super(SaleOrder, self).action_confirm()

        # 3. YOUR CUSTOM CODE AFTER THE ORIGINAL METHOD
        _logger.info("Executing custom post-confirmation logic...")

        # 4. ALWAYS RETURN THE RESULT OF SUPER
        return res
```

#### ⏱️ 3. Timing is Everything: Before vs. After

Where you place your custom logic in relation to the `super()` call fundamentally changes how your module interacts with the database.

**Scenario A: Intercepting Inputs (Code BEFORE `super`)**

Place code here when you need to validate data, block an action, or modify the incoming dictionary (`vals`) _before_ the database processes it.

Python

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        # We intercept the 'vals' dictionary before it hits the database
        if 'credit_limit' in vals and vals['credit_limit'] > 100000:
            if not self.env.user.has_group('account.group_account_manager'):
                # We raise an error, stopping execution. super() is never reached.
                raise exceptions.UserError(_("You lack authorization to grant this credit limit."))
        
        # If the check passes, we allow the database write to proceed
        return super(ResPartner, self).write(vals)
```

**Scenario B: Reacting to the Database (Code AFTER `super`)**

Place code here when you need to react to something Odoo just did. For example, if you need the ID of a newly created record, you must wait for `super()` to execute the SQL `INSERT` statement first.

Python

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        # 1. Execute the core Odoo creation logic first
        # This writes the data to PostgreSQL and generates the database IDs
        records = super(SaleOrder, self).create(vals_list)
        
        # 2. Now that the records exist in the database, we can interact with them
        for record in records:
            if record.amount_total > 50000:
                record._trigger_high_value_alert()
                
        # 3. Return the generated recordset back to the UI
        return records
```

#### 💀 4. Doomsday Traps (Common Mistakes)

If the system crashes after you override a method, you likely committed one of these three cardinal sins.

**Trap 1: Forgetting to return `res`**

Many core Odoo methods return actions (like opening a new window) or booleans. If your method ends without `return res`, it returns `None`. The UI will freeze, or downstream methods relying on that return value will throw a `TypeError`.

* The Fix: Always assign `res = super(...)` and end your function with `return res`.

**Trap 2: Altering the Method Signature**

If the original Odoo method requires three arguments, your overridden method must accept three arguments.

* The Fix: Always check the Odoo source code before overriding. If the original is `def _prepare_invoice(self, journal=False):`, yours must be `def _prepare_invoice(self, journal=False):`.

**Trap 3: The Infinite Recursion Loop**

If you accidentally call a method that triggers another write inside your overridden `write()` method without context flags, you will create an infinite loop that crashes the server.

* The Fix: We will cover this in detail in the Preventing Infinite Sync Loops section, but always be cautious about triggering database updates inside a `write` override.
