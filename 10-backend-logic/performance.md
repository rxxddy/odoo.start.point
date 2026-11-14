---
description: Measuring first, then batching, indexing, and caching.
---

# Performance

Slow Odoo code is slow for a small number of reasons, and guessing which one costs more than measuring. This chapter is the measuring habit first, then the three causes behind most slowness: queries in loops, missing indexes, and work done per record that could be done per batch.

## Measure before changing anything

Find out where the time goes. Three tools cover most cases:

* **Query count and time.** Run with `--log-level=debug_sql` on a test database, or watch `pg_stat_statements` on a busy one. Count the queries for one operation. A hundred identical queries differing by id is the signature of an N+1.
* **Python profile.** Odoo ships a profiler: enable it from the developer menu, or in code:

```python
from odoo.tools import profiler

with profiler.Profiler(db=self.env.cr.dbname):
    records.action_heavy()
```

The recorded sessions show Python time and SQL per call stack.
* **`EXPLAIN (ANALYZE, BUFFERS)`** on the slow query, to see sequential scans, row estimates that are off by orders of magnitude, and sorts that spill.

Change one thing, measure again, keep the number. If you cannot show a before and after, you do not know whether you fixed it.

## N+1 queries

The classic form:

```python
for loan in loans:
    loan.book_id.title        # fine: prefetched
    self.env["library.book"].search([("id", "=", loan.book_id.id)])  # one query per loop
```

Field reads on records of the same recordset are prefetched: reading `loan.book_id` for one record loads it for the whole recordset in one query, up to `PREFETCH_MAX` (1000 in `odoo/models.py`) records at a time. The ORM protects you as long as you stay in the recordset. You lose it by calling `search`, `browse` on single ids, `read` or `create` inside the loop.

Fix by moving the query out and grouping:

```python
books = self.env["library.book"].search([("id", "in", loans.book_id.ids)])
by_id = {b.id: b for b in books}
```

Or let the database aggregate:

```python
groups = self.env["library.loan"]._read_group(
    [("state", "=", "open")], ["book_id"], ["__count"]
)
```

`_read_group` (the public `read_group` is for the web client) returns tuples of group values and aggregates, computed in SQL, with no records instantiated.

## Prefetch, and when it hurts

Prefetch loads every stored field of the model for the whole batch on first access, except large binaries and, by default, fields in other groups the user cannot read. For a wide model and a loop that needs one field, that loads far more than needed. Use `read` with explicit fields, or `mapped`/`_read_group` for a single column:

```python
titles = books.mapped("title")                        # one query
rows = books.read(["title", "isbn"])                  # explicit columns
```

Opposite problem: a recordset rebuilt inside the loop breaks the prefetch group. `self.browse(rec.id)` inside a loop makes a one-record prefetch set every time. Keep the original recordset; pass `with_prefetch()` only if you deliberately construct new ones.

## Write and create in bulk

```python
Loan.create([{"book_id": b, "member_id": m} for b, m in pairs])   # one call, list of dicts
records.write({"state": "done"})                                  # one write for all
```

`create` with a list batches inserts and computes once. Per-record `write` in a loop triggers recomputes and constraints each time. Group records by the value they receive and write once per group.

## Computed fields

A stored compute on a field read often, with correct `@api.depends`, is cheap. A non-stored compute that does a `search` per record is the usual culprit; compute for the whole recordset instead:

```python
@api.depends("loan_ids.state")
def _compute_open_loans(self):
    data = dict(self.env["library.loan"]._read_group(
        [("book_id", "in", self.ids), ("state", "=", "open")],
        ["book_id"], ["__count"],
    ))
    for book in self:
        book.open_loans = data.get(book, 0)
```

Over-broad `@api.depends` (depending on a whole one2many, or on fields that change constantly) causes mass recomputes on unrelated writes. Depend on the narrowest path.

## Indexes

An index helps filters, joins and orderings you actually run. Declare `index=True` on fields used in `search` domains over large tables (state, foreign keys you filter by, external ids). Every index costs write time and disk, so do not index everything. Many2one fields get a foreign key index for `ondelete` handling only in some cases; check with `\d table` rather than assuming.

Confirm with `EXPLAIN` that the planner uses it. Low-selectivity columns (a boolean split 50/50) rarely benefit.

## Batching long work

Process large sets in chunks, with `flush` and a cache clear so memory stays flat:

```python
for chunk in tools.split_every(500, ids):
    records = self.browse(chunk)
    records._do_work()
    self.env.flush_all()
    self.env.invalidate_all()
```

Commit between chunks only in cron or script contexts (see Queues and background work).

## Pitfalls

* Optimising from intuition. Profile first; the slow line is rarely the one you suspect.
* `search` followed by `len()`. Use `search_count`.
* `sudo()` or `with_context` inside the loop, creating a new environment and cache each time.
* Reading related fields through long chains (`a.b.c.d`) per record without prefetch benefit.
* `ORDER BY` on a non-stored computed field, forcing Python sorting of everything.
* Testing performance on a ten-record dev database. Test with realistic volume.

## Versions

{% hint style="info" %}
`_read_group` with the `["__count"]` aggregate style and tuple results is the 17 and 18 API. In 16 `_read_group` returns dicts and uses `groupby`/`fields` arguments differently, so verify the signature in your build. `invalidate_all` and `flush_all` exist from 16. `PREFETCH_MAX` is 1000 in 18.
{% endhint %}

## Try it

See the heaviest statements on a database you may read:

```sql
SELECT calls, round(total_exec_time) AS ms, left(query, 100)
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;
```
