---
description: Logging queries, counting them, and finding the slow ones.
---

# Inspecting SQL

Most Odoo performance problems are query problems: too many queries (N+1), or a few queries that scan a large table. You find both by looking at what the database actually receives.

## Log every query

```bash
./odoo-bin -d mydb --log-level=debug_sql
# or one handler only
./odoo-bin -d mydb --log-handler=odoo.sql_db:DEBUG
```

Each statement is logged with its duration. It is very verbose, so use it against one action on a development database, not for a day of traffic.

In the shell:

```bash
./odoo-bin shell -d mydb --no-http --log-handler=odoo.sql_db:DEBUG
```

## Count queries in code

The cursor counts them:

```python
cr = env.cr
before = cr.sql_log_count   # verified in Odoo 18 (odoo/sql_db.py, used by odoo/tools/profiler.py)
env['library.loan'].search([]).mapped('book_id.name')
print(cr.sql_log_count - before)
```

If the attribute is missing in your version, wrap the call with `odoo.tools.misc.mute_logger`-style logging, or compare counts from the debug log. A more portable approach is a small context manager that patches `cr.execute`:

```python
import contextlib

@contextlib.contextmanager
def count_queries(cr):
    original = cr.execute
    stats = {"n": 0}
    def wrapper(query, params=None, *a, **kw):
        stats["n"] += 1
        return original(query, params, *a, **kw)
    cr.execute = wrapper
    try:
        yield stats
    finally:
        cr.execute = original
```

In tests, `with self.assertQueryCount(admin=12):` asserts a budget and fails when code regresses.

## Recognising N+1

```python
for loan in loans:
    print(loan.book_id.name)   # fine: prefetching loads books for the whole recordset
```

The ORM prefetches fields for all records of the recordset, so this is normally fine. N+1 appears when the recordset is rebuilt each iteration:

```python
for loan_id in ids:
    loan = env['library.loan'].browse(loan_id)   # new recordset, no shared prefetch
    print(loan.book_id.name)
```

Fix: browse once (`env['library.loan'].browse(ids)`) and iterate over that. Also watch for `search` inside a loop, and for `read` per record. Batch with `search(domain_in)` and group in Python, or use `read_group` (renamed `_read_group` / `formatted_read_group` in later versions) for aggregates.

## Get the SQL of a search

```python
>>> query = env['library.loan']._search([('state', '=', 'open')])
>>> print(query.select())          # (sql, params)
```

Query internals changed between versions (`_where_calc`, `Query.get_sql` in older ones). Treat the exact method as version-specific. The log is the reliable source.

## Explain it

Copy the statement from the log into `psql` against a copy of the database:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT "library_loan".id FROM "library_loan"
WHERE "library_loan"."state" = 'open'
ORDER BY "library_loan"."id" DESC LIMIT 80;
```

Read it for:

- `Seq Scan` on a large table where you expected an index.
- Estimated rows far from actual rows (stale statistics; run `ANALYZE`).
- `Sort` with disk use, large `Rows Removed by Filter`.

`EXPLAIN ANALYZE` runs the statement. On `UPDATE` or `DELETE`, wrap in `BEGIN; ... ROLLBACK;`.

## Find slow queries on the server

```sql
-- requires the pg_stat_statements extension
SELECT calls, round(total_exec_time::numeric) AS total_ms,
       round(mean_exec_time::numeric, 1) AS mean_ms, left(query, 120)
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
```

PostgreSQL's `log_min_duration_statement = 500` logs every statement slower than 500 ms. Locks:

```sql
SELECT pid, state, wait_event_type, now() - query_start AS age, left(query, 100)
FROM pg_stat_activity WHERE datname = 'mydb' AND state <> 'idle' ORDER BY age DESC;
```

## Indexes

A frequently searched stored field benefits from `index=True` on the field definition. Indexes cost writes and disk, so add them for measured cases. For `ilike '%text%'` a btree index does not help; the field option `index='trigram'` (available in recent versions) needs the `pg_trgm` extension.

## Pitfalls

- **Measuring on an empty database.** Plans differ with data volume.
- **Judging by count alone.** One query with a bad plan costs more than fifty indexed ones.
- **Related and computed stored fields.** A write may trigger recomputes of dependants, a burst of queries you did not write.
- **Raw SQL bypasses the ORM.** No access rules, no recomputes, stale cache.
- **Logging SQL with parameters in production.** Parameters can contain personal data.

## Try it

Run a list search in the shell with `--log-handler=odoo.sql_db:DEBUG`, then paste the statement into `EXPLAIN (ANALYZE)` on a development copy.
