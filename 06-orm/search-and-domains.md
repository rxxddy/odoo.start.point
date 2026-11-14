---
description: Domain syntax, operators, and performance of search.
---

# Search and domains

A domain is a list that filters records. The ORM compiles it to SQL in `search`, evaluates it in Python in `filtered_domain`, and clients send it as JSON. This chapter covers the syntax, the operators in the Odoo 18 source, and the habits that keep searches fast and correct.

## Syntax

A domain is a list of conditions and logical operators in prefix (Polish) notation. A condition is a tuple `(field_path, operator, value)`.

```python
[('state', '=', 'available'), ('pages', '>', 300)]       # implicit AND
['|', ('state', '=', 'draft'), ('state', '=', 'lost')]    # OR of two
['!', ('title', 'ilike', 'guide')]                        # NOT
['&', ('a', '=', 1), '|', ('b', '=', 2), ('c', '=', 3)]   # a AND (b OR c)
```

Logical operators are `&`, `|`, `!`. `&` and `|` take two operands, `!` takes one. Conditions with no operator between them are ANDed, so the leading `&` is rarely written. The common mistake is forgetting that `|` binds only the next two items:

```python
# Intended: (a OR b) AND c. This is not it.
['|', ('a', '=', 1), ('b', '=', 2), ('c', '=', 3)]   # fine here: c is ANDed after
# Intended: a OR b OR c needs two '|'.
['|', '|', ('a', '=', 1), ('b', '=', 2), ('c', '=', 3)]
```

`odoo.osv.expression` has helpers: `AND([d1, d2])`, `OR([d1, d2])`, `NOT_OPERATOR`, `normalize_domain`. Prefer them when composing domains from parts, since concatenating lists by hand breaks the prefix structure when one part is already an OR.

## Operators

These are the term operators defined in the 18 source (`TERM_OPERATORS` in `odoo/osv/expression.py`):

`=`, `!=`, `<`, `<=`, `>`, `>=`, `=?`, `=like`, `=ilike`, `like`, `not like`, `ilike`, `not ilike`, `in`, `not in`, `child_of`, `parent_of`, `any`, `not any`.

Behaviour worth knowing:

- `like` and `ilike` wrap the value in `%...%`. `=like` and `=ilike` do not, so you provide the wildcards yourself.
- `=?` means "equals unless the value is falsy": `('partner_id', '=?', False)` is ignored. Useful for optional filters.
- `in` takes a list or tuple. `('id', 'in', [])` matches nothing, and `('id', 'not in', [])` matches everything.
- `= False` on a Many2one or Char matches both `NULL` and, for Char, the empty string in some paths. For stricter logic, test with `('field', '=', False)` and check the result set, or use a custom search.
- `child_of` and `parent_of` follow `_parent_name` (default `parent_id`) over the hierarchy, using `parent_path` when `_parent_store` is on.
- `any` and `not any` test the comodel with a sub-domain:

```python
[('loan_ids', 'any', [('state', '=', 'late')])]
[('author_id', 'any', [('country_id.code', '=', 'FR')])]
```

`any` is the clear way to say "at least one related record matches these conditions together". A dotted path with two conditions on the same x2many does not guarantee the same related record satisfies both.

{% hint style="info" %}
**Versions.** In 16 `any` and `not any` exist as well, but the domain was a plain list with a `normalize_domain`-style pass. Odoo 18 still uses `odoo/osv/expression.py` for this; I did not check any other module layout. Do not rely on a `Domain` class in code that must run on 16 to 18.
{% endhint %}

## Dotted paths

```python
[('book_id.author_id.name', 'ilike', 'tolstoy')]
```

A path through Many2one joins or sub-selects automatically, subject to the access rules of the comodel. Through x2many the result is "any related record", and the ORM runs a sub-query. Paths over non-stored computed fields work only if the field has a `search` method.

## The search methods

```python
Book = self.env['library.book']
Book.search(domain, offset=0, limit=None, order=None)
Book.search_count(domain, limit=None)
Book.search_read(domain, fields, offset=0, limit=None, order=None)   # RPC oriented
Book.search_fetch(domain, field_names, offset=0, limit=None, order=None)
```

`search_count` accepts a `limit` in 18, which stops counting early; use it for "are there at least N" checks. `_search` returns a `Query` object instead of records, used when building sub-selects or in overrides that must not load ids.

### Active records

For models with an `active` field, `search` adds `('active', '=', True)` automatically. Override with `with_context(active_test=False)`, or put an explicit `('active', ...)` condition in the domain.

### Ordering

`order` is a comma-separated string: `'pages desc, title'`. If omitted, `_order` of the model applies. The ORM appends `id` to make the order stable. Sorting is on stored fields only (or related fields that resolve to stored ones).

### Access rules are part of search

`search` applies record rules of the current user. Under `sudo()` it does not. A search that returns a record for an admin and nothing for a regular user is almost always a record rule, not a bug in the domain.

## Performance

- Search on indexed columns. A filter on an unindexed Char with `ilike '%x%'` is a sequential scan; give the field `index='trigram'`.
- `search([...])` followed by `len()` loads ids; `search_count` runs `COUNT`.
- Do not search inside loops. Collect keys, search once with `in`, and `grouped()`.
- Large `in` lists (tens of thousands of ids) are slow. Use a sub-domain with `any` or restructure.
- Use `limit=1` when you need existence, or `search_count(domain, limit=1)`.
- Non-stored computed fields in a domain need a `search` method, and that method decides the cost.

## Writing a search method for a computed field

```python
is_late = fields.Boolean(compute='_compute_is_late', search='_search_is_late')

def _search_is_late(self, operator, value):
    if operator not in ('=', '!=') or not isinstance(value, bool):
        raise UserError(_("Unsupported search on is_late."))
    positive = (operator == '=') == value
    domain = [('due_date', '<', fields.Date.context_today(self))]
    return domain if positive else ['!'] + domain
```

The method returns a domain; return only fields that are stored or themselves searchable. Validate the operator instead of assuming `=`.

## Pitfalls

{% hint style="warning" %}
Unsaved changes are flushed before a search that depends on them, but only for fields the ORM can detect from the domain. A search through a raw SQL path, or after `cr.execute` writes, sees stale data. Call `flush_model()` first.
{% endhint %}

- `('field', '=', record)` works for Many2one, but passing a multi-record recordset to `=` is wrong; use `in` with `.ids`.
- Concatenating domains with `+` is correct for AND only when both parts are complete. A part starting with `|` that has fewer terms than needed corrupts the result.
- `('name', 'ilike', False)` is not "no filter". Use `=?` or build the domain conditionally.
- A domain stored as a string in a record (filters, rules) is evaluated with a limited context; `user`, `time`, and `company_ids` exist, arbitrary names do not.
- `search` with `limit` but no `order` uses `_order`; without a stable order, pagination can skip or repeat rows.

## Try it

```python
domain = ['|', ('is_company', '=', True), ('email', '!=', False)]
print(env['res.partner'].search_count(domain))
from odoo.osv import expression
print(expression.AND([domain, [('active', '=', True)]]))
```
