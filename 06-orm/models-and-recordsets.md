---
description: "Model types, recordsets, and the idioms for working with them."
---

# Models and recordsets

Every ORM call returns or consumes a recordset: an ordered collection of record ids bound to an environment. Most ORM bugs come from misunderstanding what a recordset is, so this chapter fixes the mental model before the API chapters build on it.

## Three model classes

```python
from odoo import models, fields

class Book(models.Model):                 # persistent, one table
    _name = 'library.book'
    _description = 'Book'

class LoanWizard(models.TransientModel):  # persistent, vacuumed automatically
    _name = 'library.loan.wizard'
    _description = 'Loan wizard'

class LoanHelpers(models.AbstractModel):  # no table, mixin or service
    _name = 'library.loan.helpers'
    _description = 'Loan helpers'
```

- `Model` creates a table `library_book` with the standard columns `id`, `create_uid`, `create_date`, `write_uid`, `write_date`.
- `TransientModel` has a table, but rows are removed by a scheduled vacuum. Use it for wizards, never for data you need tomorrow.
- `AbstractModel` has no table. Use it as a mixin (`_inherit = ['library.loan.helpers']`) or as a namespace for methods.

`_description` is required in practice: without it the registry logs a warning at load, and the model has no readable label in the UI or in access errors.

## What a recordset is

`self.env['library.book']` is an empty recordset of the model. `browse(ids)` builds one without touching the database. `search()` builds one from a query. There is no separate "record" class.

```python
books = self.env['library.book'].search([('pages', '>', 300)])
books.ids          # [3, 8, 11]
len(books)         # 3
books[0]           # recordset of length 1, a "singleton"
books[:2]          # slicing returns a recordset
bool(books)        # False when empty
```

A recordset behaves like an immutable ordered set of ids. It is hashable, iterable, and supports:

```python
a | b      # union, no duplicates
a & b      # intersection
a - b      # difference
a + b      # concatenation, keeps duplicates
x in a     # membership of a singleton
```

Two recordsets are equal if model, ids, and order match.

## Singletons and ensure_one

Reading a field on a multi-record set raises `ValueError: Expected singleton`. Iterating yields singletons.

```python
books.title                       # ValueError if len(books) > 1
books.write({'active': False})    # fine, one UPDATE for all
for book in books:
    book.title                    # fine
```

Call `self.ensure_one()` at the top of any method that needs exactly one record, such as a button action. It fails loudly instead of silently reading the wrong record.

An empty recordset is falsy and field reads on it return the empty value (`False`, `0`, an empty recordset). That is why `book.author_id.name` is safe when `author_id` is unset.

## Idioms

### Batch the write

```python
# Bad: one UPDATE per record
for loan in loans:
    loan.state = 'returned'

# Good: one UPDATE
loans.write({'state': 'returned'})
```

When values differ per record a loop is unavoidable, but group first (`filtered`, `grouped`) and write once per group.

### mapped

```python
loans.mapped('book_id')                 # recordset of books, deduplicated
loans.mapped('book_id.title')           # list of strings
loans.mapped(lambda l: l.days_late)     # list of values
```

With a relational path `mapped` returns a recordset without duplicates; with a scalar field it returns a list and keeps duplicates.

### filtered, filtered_domain, sorted

```python
late = loans.filtered(lambda l: l.days_late > 0)
late = loans.filtered('is_late')                      # by truthiness of a field
late = loans.filtered_domain([('days_late', '>', 0)])
by_due = loans.sorted('due_date', reverse=True)
```

`filtered_domain` evaluates the domain in Python over records already in memory. No SQL runs, so it is cheap for small sets and wrong tool for large ones.

### grouped

Partition a recordset in memory by a field name or a callable. The method exists in the 18 source (`models.py`, `def grouped(self, key)`).

```python
for member, member_loans in loans.grouped('member_id').items():
    ...
```

The result is a dict from key to recordset, and all values share one prefetch set, so field reads in the loop stay cheap. It is a partition, not an aggregation; for sums and counts over many rows use `_read_group`.

### exists

```python
if not record.exists():
    return
```

`browse(id)` never checks that the row is present. After a concurrent `unlink`, a cached recordset still holds the id and the first field read raises `MissingError`. `exists()` returns the subset that still exists.

## Environments travel with the recordset

Each recordset carries `env` (cursor, user, context, su flag). `with_context`, `with_user`, `sudo`, and `with_company` return a new recordset over the same ids; they never mutate the original.

```python
book = book.with_context(lang='fr_FR')   # rebind, do not drop the result
```

Calling `book.with_context(...)` without using the result does nothing, a common mistake. The environment chapter covers sudo and context rules.

## Pitfalls

{% hint style="warning" %}
`if record:` is true for a stale record. A recordset with one id is truthy even if the row was deleted. Use `exists()`.
{% endhint %}

- `search(...)[0]` raises `IndexError` on an empty result. Use `search(..., limit=1)` and test truthiness, or `ensure_one()` when exactly one is required.
- `record == 5` is always `False`. Compare `record.id`.
- `a + b` keeps duplicates, `a | b` does not. Merging search results with `+` can process records twice.
- Building a big recordset by repeated `|=` is quadratic. Collect ids in a list and `browse` once.
- Do not keep recordsets in module-level variables or class attributes. They are bound to a cursor that will be closed.
- Do not call `len(search(...))` just to count; use `search_count`.

{% hint style="info" %}
**Versions.** `grouped` and `search_fetch` are present in 18; I did not check 16 and 17 for them, so verify before using in a module that must run on those. `filtered_domain`, `mapped`, `sorted`, `exists`, and `ensure_one` are available in 16 through 18.
{% endhint %}

## Try it

In an Odoo shell on a development database:

```python
partners = env['res.partner'].search([], limit=5)
print(partners.ids, len(partners))
print(partners.mapped('name'))
print((partners[:2] | partners[1:3]).ids)
```
