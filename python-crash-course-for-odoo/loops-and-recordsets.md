# Loops and Recordsets

## 🔄 Loops and Recordsets

> **Status:** FATAL ERROR AVOIDANCE | **Focus:** THE SINGLETON TRAP

If you are coming from traditional Python development, this is where Odoo will break you. In a standard Python class, `self` refers to a single instance of an object.

**In Odoo, `self` is NEVER a single object. It is ALWAYS a "Recordset" (a collection of records).** Even if you click a button on a single Sales Order form, Odoo passes that record to your Python function as a Recordset containing exactly one item. If you attempt to access a field directly (e.g., `self.amount_total`) on a Recordset that contains multiple records, the framework will instantly crash and throw the infamous `ValueError: Expected singleton`.

To survive, you must master the art of looping.

***

#### 🪤 1. The Singleton Trap & The Golden Rule

Every method you write inside an Odoo model must assume it is processing multiple records simultaneously. This is the cornerstone of Odoo's batch-processing architecture.

**The Golden Rule:** Unless you are absolutely, mathematically certain that a method will only ever process a single record, you must wrap your logic in a `for record in self:` loop.

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_validate_margins(self):
        # ❌ DO NOT DO THIS: 
        # If the user selects 5 orders in the list view and clicks this button,
        # self.margin will throw a ValueError: Expected singleton.
        # if self.margin < 0: 
        #     raise UserError("Margin too low!")

        # ✅ DO THIS INSTEAD (The Golden Rule):
        for order in self:
            if order.margin < 0:
                # Use the specific 'order' variable, not 'self'
                raise exceptions.UserError(_("Order %s has a negative margin.") % order.name)

```

***

#### 🧬 2. Recordset Math: Looping Without Looping

Writing `for` loops is essential, but Odoo provides highly optimized internal methods to process Recordsets without explicitly writing a Python loop. These methods are executed in C and are exponentially faster than standard Python loops.

Master these three commands to write clean, Senior-level code.

**`mapped()`: The Data Extractor**

Use this to extract a specific field from all records in a Recordset, returning a standard Python list (or a new Recordset if the field is relational). It can traverse relationships seamlessly.

```python
# Extracting a list of strings
# Returns: ['SO001', 'SO002', 'SO003']
order_names = self.mapped('name')

# Extracting a list of related records (Traversing relationships)
# Returns a unified Recordset of all partners linked to these orders
customer_records = self.mapped('partner_id')

# Deep traversal (Dot notation)
# Returns a list of the countries of all the customers of these orders
country_names = self.mapped('partner_id.country_id.name')

```

**`filtered()`: The Memory Search**

Use this to filter a Recordset that is already in memory without making another slow trip to the PostgreSQL database. It takes a lambda function (a mini, one-line function).

```python
# We have 1,000 order lines in 'self.order_line'.
# Filter them to only keep lines with a discount applied.
discounted_lines = self.order_line.filtered(lambda line: line.discount > 0.0)

# Filter for specific products
special_product_lines = self.order_line.filtered(lambda line: line.product_id.id == 99)

```

**`sorted()`: The Memory Organizer**

Use this to sort a Recordset in memory.

```python
# Sort the order lines by price, descending (highest price first)
expensive_first = self.order_line.sorted(key=lambda line: line.price_unit, reverse=True)

```

***

#### 🧮 3. Set Operations (Combining Recordsets)

Because Recordsets act like mathematical sets, you can add, subtract, and intersect them using standard Python bitwise operators. This is incredibly useful for manipulating data without writing complex, nested loops.

* `|` **(Union):** Combines two Recordsets and removes duplicates.
* `&` **(Intersection):** Returns only the records that exist in BOTH Recordsets.
* `-` **(Difference):** Returns records in the first set that are NOT in the second set.

```python
# Assume we have two Recordsets of partners
vip_customers = self.env['res.partner'].search([('grade', '=', 'vip')])
italian_customers = self.env['res.partner'].search([('country_id.code', '=', 'IT')])

# 1. UNION: Give me everyone who is EITHER a VIP or Italian (no duplicates)
target_audience = vip_customers | italian_customers

# 2. INTERSECTION: Give me ONLY the Italian VIPs
italian_vips = vip_customers & italian_customers

# 3. DIFFERENCE: Give me all VIPs who are NOT Italian
foreign_vips = vip_customers - italian_customers

```

***

#### ☢️ 4. The Doomsday Performance Killer

This is the most common reason Odoo servers lock up and crash under load.

**NEVER put database queries (`search()`) or database writes (`create()`, `write()`) inside a `for` loop.** If your loop runs 10,000 times, you are hitting the PostgreSQL database 10,000 separate times. The network latency alone will cause a timeout.

```python
    def process_data(self):
        # ❌ FATAL ERROR (Database Ddos):
        # for record in self:
        #     self.env['log.table'].create({'name': record.name})

        # ✅ SURVIVAL ARCHITECTURE (Batch Processing):
        # Build a list of dictionaries in memory first
        log_payloads = []
        for record in self:
            log_payloads.append({'name': record.name})
            
        # Execute a SINGLE insert query outside the loop
        if log_payloads:
            self.env['log.table'].create(log_payloads)

```
