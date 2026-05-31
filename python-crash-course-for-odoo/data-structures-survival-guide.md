# Data Structures Survival Guide

## 🗃️ Data Structures Survival Guide

> **Status:** CORE MECHANICS | **Focus:** PYTHON DATA HANDLING

You do not need a computer science degree to survive Odoo. You will rarely, if ever, need to build a binary tree or a linked list. Odoo’s architecture abstracts the heavy lifting away, but it demands absolute mastery over three fundamental Python data structures: **Dictionaries, Lists, and Tuples**.

If you do not understand how these three structures hold and pass data, you will not be able to interact with the ORM, process a webhook, or write a single database record.

Here is your crash course on how Odoo actually uses them.

***

#### 📖 1. Dictionaries (`{}`) — The Payload Carrier

A dictionary is a collection of `key: value` pairs. Think of it as a JSON object. In Odoo, dictionaries are the universal language for creating and updating database records. When an external system (like a PrestaShop storefront) sends data to Odoo, it arrives as a dictionary.

**How Odoo uses them:** Every time you call `.create()` or `.write()`, you must pass a dictionary where the keys are the exact database field names.

```python
# A standard dictionary payload representing an incoming order
order_payload = {
    'partner_id': 104,
    'date_order': '2026-05-31 10:00:00',
    'state': 'draft',
    'amount_total': 250.50
}

# Writing the dictionary to the database
# self.env['sale.order'].create(order_payload)

```

**Survival Skills for Dictionaries:** Never access a dictionary key directly using brackets (e.g., `payload['state']`) unless you are 100% sure the key exists. If the external API forgot to send 'state', your code will throw a `KeyError` and crash the transaction. Always use `.get()`.

```python
# DANGEROUS: Will crash if 'carrier' is missing from the payload
# carrier_name = payload['carrier']

# SAFE: Returns None if 'carrier' is missing, preventing a crash
carrier_name = payload.get('carrier')

# SAFE WITH DEFAULT: Returns 'GLS Italy' if 'carrier' is missing
carrier_name = payload.get('carrier', 'GLS Italy')

# Merging dictionaries (useful for adding default values to payloads)
base_vals = {'company_id': 1}
base_vals.update(order_payload) 

```

***

#### 📋 2. Lists (`[]`) — The Batch Processor

A list is an ordered collection of items. In the Odoo ecosystem, lists are used to handle multiple records at once, process bulk data, and return search results.

**How Odoo uses them:** When you extract IDs from a database search or parse multiple tracking numbers from a DHL webhook, they are stored in a list.

```python
# A list of external tracking codes
dhl_tracking_codes = ['JD014600000000000001', 'JD014600000000000002']

# Adding a new item to the list
dhl_tracking_codes.append('JD014600000000000003')

# Checking if an item is inside a list (Very common for state checks)
if 'JD014600000000000001' in dhl_tracking_codes:
    _logger.info("Tracking code found!")

```

**Survival Skill: List Comprehensions** This is the most "Pythonic" concept you must learn. It is a shorthand way to create a new list from an existing one. You will see this in almost every professional Odoo module.

```python
# Imagine you have a list of order dictionaries
orders = [
    {'id': 1, 'state': 'done'}, 
    {'id': 2, 'state': 'draft'},
    {'id': 3, 'state': 'done'}
]

# THE SLOW WAY (Do not do this):
done_ids = []
for order in orders:
    if order.get('state') == 'done':
        done_ids.append(order.get('id'))

# THE ODOO ARCHITECT WAY (List Comprehension):
# Syntax: [expression for item in list if condition]
done_ids = [order.get('id') for order in orders if order.get('state') == 'done']

```

***

#### 🔗 3. Tuples (`()`) — The Immutable Domain

A tuple looks exactly like a list, but it uses parentheses `()` instead of brackets `[]`. The critical difference is that **tuples are immutable**—once created, you cannot change, add, or remove items from them.

**How Odoo uses them:** Because they cannot be accidentally modified, Odoo uses tuples exclusively to define **Search Domains** (the SQL `WHERE` clauses).

A standard Odoo domain is a _list of tuples_. Each tuple contains exactly three elements: `('field_name', 'operator', 'value')`.

```python
# A search domain is a List [] containing Tuples ()
# Notice the parentheses inside the brackets.
search_domain = [
    ('is_company', '=', True),          # Tuple 1
    ('country_id.code', '=', 'IT'),     # Tuple 2
    ('customer_rank', '>', 0)           # Tuple 3
]

# Executing the search
italian_b2b_customers = self.env['res.partner'].search(search_domain)

```

***

#### 🧬 4. The "Recordset" (Odoo's Custom Super-Structure)

When you run a search in Odoo (like `self.env['sale.order'].search([])`), it does not return a standard Python list. It returns an **Odoo Recordset**.

A Recordset acts like a list, but it is deeply connected to the database. If you try to print it, it looks like this: `sale.order(14, 25, 88)`.

**Survival Skills for Recordsets:** Never write a loop if Odoo has a built-in Recordset method.

```python
records = self.env['sale.order'].search([('state', '=', 'draft')])

# 1. Getting a pure Python list of IDs from a Recordset
order_ids = records.ids  # Returns [14, 25, 88]

# 2. Extracting specific field values across all records without a loop using .mapped()
# This returns a list of all partner_ids linked to these orders
partner_ids = records.mapped('partner_id.id')

# 3. Filtering records in memory without hitting the database again using .filtered()
# lambda is just an anonymous inline function. 
high_value_orders = records.filtered(lambda r: r.amount_total > 1000.0)

```
