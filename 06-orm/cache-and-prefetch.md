---
description: Why N+1 happens and how the ORM avoids it.
---

# Cache and prefetch

The ORM keeps a per-transaction cache of field values. Reading one field of one record normally loads many records and many fields in a single query, so most Python loops over recordsets cost far fewer queries than they appear to. When they do not, the cause is almost always one of a short list of mistakes.

## How a read works

```python
books = self.env['library.book'].search([('shelf', '=', 'A')])
for book in books:
    print(book.name)
```

`search` returns ids only. The first `book.name` finds the value missing from the cache and issues one `SELECT` for the stored fields of all records in the same prefetch set (the ids that came from the same search), up to 1000 records per batch (`PREFETCH_MAX` in `odoo/models.py`). The remaining iterations read from the cache.

Details:

- Only stored, non-relational-heavy fields are loaded in that query: columns of the table. Many2one values are loaded as ids; the related record's own fields are loaded when you first read them, again for the whole prefetch set of that related model.
- One2many and Many2many are fetched with a query per field, for the whole set.
- Computed non-stored fields are computed on first access for all records in the prefetch set at once. A compute method must therefore loop over `self`.
- The cache is per environment transaction: `sudo()`, `with_context` and `with_user` create new environments that share the underlying cache storage, but entries for context-dependent fields are keyed by their context.

## The N+1 shapes

```python
# Bad: one query per book, no prefetch set
for book_id in ids:
    book = self.env['library.book'].browse(book_id)
    print(book.name)
```

`browse(single_id)` in a loop builds one-record sets. Browse once with the whole list: `self.env['library.book'].browse(ids)`.

```python
# Bad: search inside the loop
for partner in partners:
    loans = self.env['library.loan'].search([('partner_id', '=', partner.id)])
```

Replace with one search or a grouped read:

```python
loans = self.env['library.loan'].search([('partner_id', 'in', partners.ids)])
by_partner = loans.grouped('partner_id')
```

`grouped(key)` returns a dictionary of recordsets (18 has it; earlier versions use `itertools.groupby` after sorting or `_read_group`).

For counts and sums, do not load records at all: use `_read_group` or `read_group`, covered in the grouping chapter.

## Prefetch control

```python
books = books.with_context(prefetch_fields=False)   # read only the requested field
```

`prefetch_fields=False` makes a read load only the field you asked for. Use it when records have heavy columns you will not use, such as images or long text.

`fields.Binary(attachment=True)` is excluded from the default prefetch group, and fields with `prefetch=False` are loaded only on explicit access. Set `prefetch=False` on large Text or HTML fields that are rarely read.

To read specific columns in bulk without building records:

```python
rows = books.read(['name', 'isbn'])          # list of dicts
names = books.mapped('name')                  # list of values
```

## Flush and invalidate

Writes in the ORM are not sent to PostgreSQL immediately. They sit in the cache as dirty values and are flushed before any query that could depend on them (`search`, `read_group`, `execute_query`), at the end of the request, and by explicit calls:

```python
self.env.flush_all()                       # everything pending
books.flush_recordset(['state'])           # specific fields, specific records
self.env['library.book'].flush_model(['state'])
```

Invalidate is the reverse: drop cached values so that the next read goes to the database.

```python
self.env.invalidate_all()
self.env['library.book'].invalidate_model(['state'])
books.invalidate_recordset(['state'])
```

`invalidate_model` and `invalidate_recordset` accept `flush=True` by default, so pending writes are saved before the cache is dropped. You need these calls when you change data behind the ORM's back, which is mostly raw SQL and external processes in a long transaction.

{% hint style="info" %}
Versions: `flush_model`, `flush_recordset`, `invalidate_model` and `invalidate_recordset` exist in 16, 17 and 18. The older `flush()` and `refresh()` methods are removed. `Environment.invalidate_all(flush=True)` also takes the flag.
{% endhint %}

## Measuring

Count queries rather than guessing:

```python
with self.assertQueryCount(__system__=3):
    process(books)
```

In tests, `assertQueryCount` fails with the executed queries printed. Interactively, enable query logging with `--log-sql` on a development server, or run:

```python
import logging
logging.getLogger('odoo.sql_db').setLevel(logging.DEBUG)
```

## Pitfalls

{% hint style="warning" %}
Looping over a recordset inside `sudo()` or `with_context()` created per iteration. Each call produces a new environment and a new prefetch set. Apply `sudo()` once, before the loop.
{% endhint %}

- Reading a relational field on a record before it is flushed: `search` flushes for you, a raw `cr.execute` does not.
- After raw SQL that writes, the cache still holds the old values. Call `invalidate_model(['field'])` for the affected model.
- `mapped('partner_id.name')` is efficient; a Python loop with `if book.partner_id.name` is too. A loop that calls `search` or `create` per row is not.
- Computed stored fields recompute lazily. Reading one forces the recompute of the whole pending set, which can look like a slow read.
- Unbounded `search([])` on a large table loads ids only, but a following loop will prefetch in batches of 1000: memory is bounded, time is not.

## Try it

In `odoo shell` on a throwaway database with `--log-sql` enabled, run:

```python
books = env['library.book'].search([])
[b.name for b in books]
```

You should see one `SELECT` for the table, not one per record. Replace it with `[env['library.book'].browse(b.id).name for b in books]` and compare.
