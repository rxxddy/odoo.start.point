---
description: "The SQL helper, flush and invalidate, and when raw SQL is justified."
---

# Raw SQL from the ORM

Most code never needs SQL. Reach for it when the ORM cannot express the query (window functions, CTEs, aggregate filters), or when a set-based update replaces a loop over a hundred thousand records. When you do, three things have to be right: parameterisation, flushing before the query, and invalidating the cache after it.

## The SQL helper

`odoo.tools.SQL` is a composable wrapper that keeps code and parameters together and discourages string concatenation:

```python
from odoo.tools import SQL

query = SQL(
    "SELECT book_id, COUNT(*) FROM %s WHERE state = %s GROUP BY book_id",
    SQL.identifier('library_loan'),
    'open',
)
```

Arguments are either parameters (bound by the driver) or other `SQL` objects, which are merged with their own parameters. `SQL.identifier(name)` quotes a table or column name; use it for anything that is not a literal. Named arguments work too: `SQL("... %(state)s", state='open')`. Literal percent signs cannot be escaped in this form.

Fragments combine:

```python
where = SQL("state = %s", 'open')
if partner:
    where = SQL("%s AND partner_id = %s", where, partner.id)
query = SQL("SELECT id FROM library_loan WHERE %s", where)
```

The model API also produces `SQL` objects for you, which keeps field names and company-dependent or translated columns right:

```python
Loan = self.env['library.loan']
sql_state = Loan._field_to_sql('library_loan', 'state')
```

`_field_to_sql(alias, field_expr, query=None)` returns the SQL for a field, handling translations and related paths. Use it instead of hardcoding column names for anything translated or inherited.

## Executing

```python
rows = self.env.execute_query(query)            # list of tuples
dicts = self.env.execute_query_dict(query)      # list of dicts
```

`env.execute_query(SQL)` flushes the fields declared in the query's metadata and fetches the result. Pass an `SQL` object, not a string; there is an assertion on the type. The older, lower-level form still works:

```python
self.env.cr.execute(query)
rows = self.env.cr.fetchall()
```

`cr.execute` accepts an `SQL` object as well as the `(string, params)` form. With the raw cursor, flushing is your job.

{% hint style="info" %}
Versions: the `SQL` class and `env.execute_query` exist in 17 and 18. In 16, call `cr.execute(query_string, params)` and flush by hand. `Query` objects returned by `_search` convert to SQL through `query.subselect()` or by passing the query itself as an argument to `SQL(...)` in 18.
{% endhint %}

## Flush before, invalidate after

The ORM writes lazily (see the cache chapter). Before a raw read, pending values must reach the database. After a raw write, cached values are stale.

```python
Loan = self.env['library.loan']
Loan.flush_model(['state', 'date_due'])      # before reading state and date_due

self.env.cr.execute(SQL(
    "UPDATE library_loan SET state = 'late' WHERE state = 'open' AND date_due < %s",
    fields.Date.today(),
))

Loan.invalidate_model(['state'])             # after writing state
```

`execute_query` does the flush step for you only for the fields it knows about, so it is still worth naming them for hand-written SQL. Flush the model whose columns you touch, and every model you join. A computed stored field that depends on the changed column is not recomputed by raw SQL: neither dependants nor tracking nor constraints run.

## Reading from the ORM, then joining in SQL

Use ORM for the access-controlled part, then SQL for the rest. `_search` returns a `Query` that applies record rules:

```python
query = self.env['library.loan']._search([('state', '=', 'open')])
ids = [row[0] for row in self.env.execute_query(query.select())]
```

Going through `_search` keeps record rules and company filters in the SQL. Raw SQL by itself sees every row of every company.

## When raw SQL is justified

- Reports on large tables with window functions or CTEs.
- Bulk updates that need not trigger business logic (denormalised counters after an import).
- Migrations in `pre-` and `post-migration` scripts where the ORM models may not match the schema yet.
- Locking, such as `SELECT ... FOR UPDATE SKIP LOCKED` in a queue worker.

It is not justified to avoid learning `search` or `_read_group`, or to skip access rights.

## Pitfalls

{% hint style="danger" %}
Never build SQL with f-strings or `%` on user input. Pass values as parameters and identifiers through `SQL.identifier`. A bare string in `cr.execute` that contains user input is an injection.
{% endhint %}

- Skipping the invalidate after a write: the next read in the same transaction returns the old value and the bug disappears in the next request.
- Skipping the flush before a read: your query misses records the same method created a moment ago.
- Raw `INSERT` bypasses defaults, sequences, `create_uid`, `create_date`, translations and access checks. The columns the ORM fills automatically are NOT NULL without defaults in the table.
- Raw SQL ignores company and user record rules.
- A failed statement aborts the transaction in PostgreSQL. To catch the error and continue, wrap the statement in `with self.env.cr.savepoint():`.
- Translated columns (`translate=True`) are JSONB in 16 and later; `WHERE name = 'x'` does not work, use `_field_to_sql`.

## Try it

Read-only, in `odoo shell`:

```python
from odoo.tools import SQL
print(env.execute_query(SQL("SELECT COUNT(*) FROM %s", SQL.identifier('res_partner'))))
```

Compare with `env['res.partner'].search_count([])`; the SQL count ignores record rules and the `active` filter.
