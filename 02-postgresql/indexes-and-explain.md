---
description: Reading a query plan and deciding when an index helps.
---

# Indexes and EXPLAIN

A slow Odoo screen, a cron job that takes hours, a report that times out: almost every case ends with the same two tools. `EXPLAIN ANALYZE` tells you what PostgreSQL did and where the time went; an index (or a rewritten query) fixes it. This chapter teaches how to read a plan, how B-tree and the other index types work, which indexes Odoo creates, when the planner refuses to use yours, and how to add an index to a live system without blocking it.

The plans below are representative output from a 500,000-row lab table. Costs and timings differ on your machine; what matters is the node types, the estimate-versus-actual comparison, and the reasoning. The plan shapes are what you will meet on real Odoo databases.

## A table big enough to matter

On six-row tables PostgreSQL correctly ignores every index, because reading one page is cheaper than any lookup. To see the effects you need volume. Create a synthetic log of loans in the lab database:

```sql
CREATE TABLE loan_log AS
SELECT g                                       AS id,
       (g % 5000) + 1                          AS book_id,
       (g % 800) + 1                           AS member_id,
       date '2020-01-01' + (g % 1500)          AS loaned_on,
       CASE WHEN g % 50 = 0 THEN NULL
            ELSE date '2020-01-01' + (g % 1500) + 10 END AS returned_on
FROM generate_series(1, 500000) AS g;

ALTER TABLE loan_log ADD PRIMARY KEY (id);

CREATE TABLE catalog AS
SELECT g AS id, 'Book ' || g AS title FROM generate_series(1, 5000) AS g;
ALTER TABLE catalog ADD PRIMARY KEY (id);

ANALYZE loan_log;
ANALYZE catalog;
```

It has 500,000 rows; each `book_id` appears 100 times, each `member_id` 625 times, and 2% of rows (10,000) have `returned_on` NULL, so they are "still open". `ANALYZE` collects the statistics the planner needs. Without it, the first plans are made on guesses.

## EXPLAIN and EXPLAIN ANALYZE

`EXPLAIN` shows the plan the planner would choose, without running the query:

```sql
EXPLAIN SELECT * FROM loan_log WHERE book_id = 42;
```

```
                        QUERY PLAN
-----------------------------------------------------------
 Seq Scan on loan_log  (cost=0.00..9435.00 rows=100 width=20)
   Filter: (book_id = 42)
(2 rows)
```

`EXPLAIN ANALYZE` actually runs it and adds measured numbers:

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM loan_log WHERE book_id = 42;
```

```
 Seq Scan on loan_log  (cost=0.00..9435.00 rows=100 width=20) (actual time=0.021..38.412 rows=100 loops=1)
   Filter: (book_id = 42)
   Rows Removed by Filter: 499900
   Buffers: shared hit=3185
 Planning Time: 0.084 ms
 Execution Time: 38.455 ms
(5 rows)
```

{% hint style="danger" %}
`EXPLAIN ANALYZE` executes the statement. On an `UPDATE`, `DELETE`, or `INSERT` it changes data. Wrap it: `BEGIN; EXPLAIN ANALYZE UPDATE ...; ROLLBACK;`. On a production database, run it on a copy, or on a `SELECT` you know is safe. A heavy `SELECT` still takes as long as it takes.
{% endhint %}

How to read one node:

- `Seq Scan on loan_log` is the operation (a full table scan) and its target.
- `cost=0.00..9435.00` are the planner's estimates in arbitrary units: startup cost (before the first row) and total cost. They only compare plans to each other; they are not milliseconds. The default unit: one sequential page read costs 1.0.
- `rows=100` is the estimated number of output rows; `width=20` the estimated bytes per row.
- `actual time=0.021..38.412` is real time in milliseconds: first row, last row. `rows=100` the real output, `loops=1` how many times the node ran. For a node inside a nested loop, multiply actual time and rows by `loops`.
- `Rows Removed by Filter: 499900` is the work thrown away. A large number next to a small result is the signature of a missing index.
- `Buffers: shared hit=3185` counts 8 kB pages read from the shared cache (`hit`) or from disk or the OS cache (`read`). It is the most stable measure when timings vary.

Two comparisons find 90% of problems:

1. **Estimated rows against actual rows.** If `rows=100` but `actual rows=250000`, the planner worked from wrong statistics and may have chosen a poor plan. Fix the statistics (`ANALYZE`), not the query.
2. **Where the time goes.** In a tree of nodes, the actual time of a node includes its children. Find the deepest node whose own time (its time minus its children's) is large.

Read a plan from the innermost, most-indented node outward. Data flows up the tree; an arrow `->` marks a child.

## Scan types

### Sequential scan

Read the whole table in physical order. Cheap per row, but proportional to table size. It is the right choice for tiny tables and for queries that need a large fraction of the rows (above roughly 5-10% selectivity it often beats an index).

### Index scan

Create an index on the column and run the same query:

```sql
CREATE INDEX loan_log_book_id_idx ON loan_log (book_id);
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM loan_log WHERE book_id = 42;
```

```
 Bitmap Heap Scan on loan_log  (cost=5.30..342.00 rows=100 width=20) (actual time=0.060..0.311 rows=100 loops=1)
   Recheck Cond: (book_id = 42)
   Heap Blocks: exact=100
   Buffers: shared hit=103
   ->  Bitmap Index Scan on loan_log_book_id_idx  (cost=0.00..5.27 rows=100 width=0) (actual time=0.037..0.037 rows=100 loops=1)
         Index Cond: (book_id = 42)
         Buffers: shared hit=3
 Planning Time: 0.120 ms
 Execution Time: 0.352 ms
(9 rows)
```

38 ms became 0.35 ms, and 3,185 buffers became 103. The plan uses a bitmap scan here: the index finds the 100 matching row locations, they are sorted by page, and the heap pages are visited once each. A plain `Index Scan` walks the index and visits each row's heap page immediately; PostgreSQL picks it for very few rows or when the order of the index is useful (for `ORDER BY ... LIMIT`). Both are "using the index".

### Index Only Scan

If the index contains every column the query needs, PostgreSQL answers from the index alone and skips the table:

```sql
EXPLAIN SELECT book_id FROM loan_log WHERE book_id BETWEEN 10 AND 12;
```

```
 Index Only Scan using loan_log_book_id_idx on loan_log  (cost=0.42..30.12 rows=300 width=4)
   Index Cond: ((book_id >= 10) AND (book_id <= 12))
```

It depends on the visibility map being current (`VACUUM` maintains it); on a freshly loaded table you may see `Heap Fetches: 300`, meaning it still had to check the table.

### Bitmap scans combine indexes

`Bitmap Index Scan` nodes can be combined with `BitmapAnd` and `BitmapOr` to use two single-column indexes for one query. That is why many single-column indexes can serve many query shapes reasonably, and also why a purpose-built multicolumn index is better for the hot query.

## What a B-tree index serves

The default index type is a B-tree. It keeps keys sorted, so it supports:

- equality: `col = x`, `col IN (...)`
- ranges: `<`, `<=`, `>`, `>=`, `BETWEEN`
- sorting: `ORDER BY col` and `ORDER BY col DESC` (a B-tree is scannable backwards), `min()` and `max()`
- prefix matching: `col LIKE 'abc%'`, but only if the database collation is `C`, or the index is created with the `text_pattern_ops` operator class
- `IS NULL` and `IS NOT NULL` (NULLs are stored in the index)

It does not help `col LIKE '%abc'`, `col ILIKE '%abc%'`, or any condition that applies a function to `col`.

Indexes cost something on every write: each `INSERT` adds an entry to every index, each `UPDATE` of an indexed column too, and they occupy disk and memory. Add indexes for queries you actually run, not for every column.

## Multicolumn indexes and column order

An index on `(member_id, loaned_on)` is sorted by `member_id`, and within equal `member_id` by `loaned_on`. It serves a query that constrains the leftmost columns:

```sql
CREATE INDEX loan_log_member_loaned_idx ON loan_log (member_id, loaned_on);

EXPLAIN SELECT * FROM loan_log
WHERE member_id = 7 AND loaned_on >= '2023-01-01'
ORDER BY loaned_on;
```

```
 Index Scan using loan_log_member_loaned_idx on loan_log  (cost=0.42..216.30 rows=380 width=20)
   Index Cond: ((member_id = 7) AND (loaned_on >= '2023-01-01'::date))
```

One index handled the equality, the range, and the sort (no `Sort` node appears). The rules:

- The index is usable for a query that constrains `member_id` alone, or `member_id` and `loaned_on`.
- It is poor for a query on `loaned_on` alone, because dates are scattered across all the `member_id` groups. A leading-column filter is what makes the key range narrow.
- Put equality columns first, then the range or sort column. Among equality columns, put the more selective one first unless other queries need another prefix.
- A separate single-column index on `member_id` is redundant after this one and just adds write cost.

## Partial, expression, and covering indexes

**Partial index.** Index only the rows you search for. The 10,000 open loans are 2% of the table, and "open loans per book" is the question an application asks all day:

```sql
CREATE INDEX loan_log_open_idx ON loan_log (book_id) WHERE returned_on IS NULL;

SELECT pg_size_pretty(pg_relation_size('loan_log_book_id_idx')) AS full_index,
       pg_size_pretty(pg_relation_size('loan_log_open_idx'))    AS partial_index;
```

```
 full_index | partial_index
------------+---------------
 11 MB      | 264 kB
(1 row)
```

The partial index is 40 times smaller and cheaper to maintain. The query must contain the index predicate (or something that implies it) to be eligible: `WHERE book_id = 42 AND returned_on IS NULL` can use it; `WHERE book_id = 42` cannot. A partial `UNIQUE` index also expresses rules like "one open loan per member and book" (the exercise in chapter 1).

**Expression index.** Index the value the query computes. A case-insensitive email lookup:

```sql
-- fragment: against a table with an email column
CREATE INDEX members_lower_email_idx ON members (lower(email));
SELECT id FROM members WHERE lower(email) = 'nora@example.com';
```

The query must use the identical expression, `lower(email)`. A plain index on `email` is useless for `lower(email) = ...`, and `ILIKE 'x'` without wildcards does not use it either.

**Covering index (`INCLUDE`, PostgreSQL 11+).** Add payload columns that are not part of the search key so that an index-only scan can return them:

```sql
CREATE INDEX loan_log_member_cover_idx ON loan_log (member_id) INCLUDE (loaned_on);
```

Use it sparingly: it enlarges the index.

## Unique indexes

`UNIQUE` constraints and primary keys are unique indexes. `CREATE UNIQUE INDEX ... WHERE ...` gives conditional uniqueness. Odoo's `_sql_constraints` entries of the form `unique(a, b)` create a unique constraint with its backing index; Odoo does that, the index is a side effect you do not manage separately.

## Index types beyond B-tree

| Type | Good for | Odoo relevance |
|---|---|---|
| B-tree | equality, ranges, sorting | `index=True` on almost every field |
| GIN | membership in composite values: jsonb keys, arrays, full-text, trigrams | trigram indexes for `ILIKE '%x%'`; `jsonb` search |
| GiST | geometric, ranges, nearest neighbour | exclusion constraints on ranges |
| BRIN | huge append-only tables where the column correlates with physical order (timestamps) | tiny index for log-like tables such as logs |
| Hash | equality only | rarely worth it |

Trigram indexes make `ILIKE '%term%'` fast. They need the `pg_trgm` extension:

```sql
-- fragment
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX res_partner_name_trgm_idx ON res_partner USING gin (name gin_trgm_ops);
```

{% hint style="info" %}
Versions. Odoo 16 gives a field `index=True` and creates a plain B-tree, named `<table>_<field>_index`. From Odoo 17 the `index` attribute also accepts `'btree'`, `'btree_not_null'` (index excluding NULLs) and `'trigram'` (GIN with `pg_trgm`; Odoo creates the extension when it can). Check your release's `fields.py` before relying on the extra values. In Odoo 16 to 18 translated fields are `jsonb`, so a trigram index on a translated `name` must target an extracted language key, not the raw column.
{% endhint %}

## Joins in plans

The planner picks one of three join algorithms for each join:

- **Nested Loop**: for each row of the outer side, look up matches on the inner side. Excellent when the outer side is small and the inner side has an index on the join column. Terrible when both are large and there is no index.
- **Hash Join**: build a hash table from one input, probe it with the other. Good for large unsorted inputs and equality joins, needs memory (`work_mem`).
- **Merge Join**: both inputs sorted on the join key, walk them together. Good when they are already sorted (from indexes).

A hash join in a plan:

```sql
EXPLAIN (ANALYZE)
SELECT c.title, count(*)
FROM loan_log l
JOIN catalog c ON c.id = l.book_id
WHERE l.loaned_on >= '2024-01-01'
GROUP BY c.title;
```

```
 HashAggregate  (cost=11112.33..11162.33 rows=5000 width=40) (actual time=41.2..42.3 rows=5000 loops=1)
   Group Key: c.title
   ->  Hash Join  (cost=143.00..11047.00 rows=13000 width=32) (actual time=1.4..37.8 rows=13000 loops=1)
         Hash Cond: (l.book_id = c.id)
         ->  Seq Scan on loan_log l  (cost=0.00..10685.00 rows=13000 width=4) (actual time=0.02..31.9 rows=13000 loops=1)
               Filter: (loaned_on >= '2024-01-01'::date)
               Rows Removed by Filter: 487000
         ->  Hash  (cost=80.50..80.50 rows=5000 width=36) (actual time=1.3..1.3 rows=5000 loops=1)
               Buckets: 8192  Batches: 1  Memory Usage: 372kB
 Planning Time: 0.3 ms
 Execution Time: 43.1 ms
```

(`catalog` is the 5,000-row table created above.) The inner `Hash` builds the small side (5,000 rows); the scan of `loan_log` probes it. `Batches: 1` means the hash fit in `work_mem`; `Batches` above 1 means it spilled to disk, a common cause of mysterious slowness that raising `work_mem` for the session cures. The seq scan removed 487,000 rows to keep 13,000, so an index on `loaned_on` is the likely improvement here.

## Why the planner ignores your index

You create an index, the plan still shows `Seq Scan`. In rough order of frequency:

1. **The query returns a large share of the table.** Reading 30% of the rows through an index is slower than a sequential scan. The planner is right.
2. **A function or cast on the column.** `WHERE lower(name) = 'x'`, `WHERE created::date = '2024-01-01'`, `WHERE amount + 0 > 10`. Rewrite the condition so the column stands alone (`created >= '2024-01-01' AND created < '2024-01-02'`), or create an expression index.
3. **Type mismatch.** Comparing an `integer` column to a `numeric` or text parameter may force a cast of the column. Pass parameters with the right type.
4. **Leading wildcard.** `LIKE '%x'` or `ILIKE '%x%'` needs a trigram index.
5. **Stale statistics.** After a bulk load or a big delete, run `ANALYZE table`. Autovacuum does it eventually, "eventually" being the problem right after your script.
6. **The table is small.** Under a few hundred rows no index is worth it.
7. **OR across columns.** `a = 1 OR b = 2` needs both columns indexed to use a `BitmapOr`; otherwise it scans.
8. **Wrong multicolumn order.** The query constrains the second column only.
9. **The index is invalid or not built yet.** A failed `CREATE INDEX CONCURRENTLY` leaves an `INVALID` index (`\d table` marks it); drop and recreate it.

To test whether an index could help, you can discourage sequential scans for one session:

```sql
SET enable_seqscan = off;
EXPLAIN SELECT * FROM loan_log WHERE member_id = 7;
RESET enable_seqscan;
```

If the plan with the index has a lower cost and is faster when you run it, the planner underestimated something (statistics, `random_page_cost`). If it is slower, the planner was right. This is a diagnostic only; never leave `enable_*` switches on in application code or `postgresql.conf`.

## Statistics

The planner's estimates come from `pg_stats`, filled by `ANALYZE`: the number of distinct values, the most common values and their frequencies, and a histogram of the rest.

```sql
SELECT attname, n_distinct, null_frac
FROM pg_stats
WHERE tablename = 'loan_log' AND attname IN ('book_id', 'member_id', 'returned_on');
```

```
   attname   | n_distinct | null_frac
-------------+------------+-----------
 book_id     |       5000 |         0
 member_id   |        800 |         0
 returned_on |       1500 |      0.02
(3 rows)
```

`null_frac = 0.02` is exactly the 2% of open loans: the planner knows `returned_on IS NULL` matches about 10,000 rows. When estimates are wrong, fix them in this order: `ANALYZE` the table; for skewed columns raise the sample with `ALTER TABLE t ALTER COLUMN c SET STATISTICS 500` and analyze again; for correlated columns create extended statistics (`CREATE STATISTICS ... (dependencies) ON a, b FROM t`).

## Building and removing indexes safely

`CREATE INDEX` takes a lock that blocks all writes to the table for the duration. On a live database use the concurrent form:

```sql
CREATE INDEX CONCURRENTLY loan_log_loaned_on_idx ON loan_log (loaned_on);
```

It scans the table twice and waits for open transactions, so it takes longer, but writers keep working. Rules: it cannot run inside a transaction block (so no `BEGIN`, and not inside a psql script run with `--single-transaction`); if it fails or is cancelled it leaves an `INVALID` index which you must `DROP INDEX` and retry; and long-running transactions elsewhere make it wait. `DROP INDEX CONCURRENTLY` and `REINDEX CONCURRENTLY` (PostgreSQL 12+) exist as well.

To find indexes that are never used, ask the statistics (collected since the last stats reset):

```sql
SELECT relname AS table, indexrelname AS index, idx_scan,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

An index with `idx_scan = 0` over a long, representative period is a candidate for removal. Do not drop an index that backs a constraint (a primary key or unique constraint), and check that a monthly report is not its only user. The statistics reset on some operations (a crash recovery, `pg_stat_reset`), so a young counter proves little.

Indexes also go stale in another way: heavy update and delete patterns bloat them. A `REINDEX CONCURRENTLY` rebuilds one without blocking.

## Indexes on foreign keys

PostgreSQL indexes the referenced side (a primary key) but not the referencing column. Odoo does create indexes for many2one fields declared with `index=True`, and does not for the rest. Two things follow:

- Joins and filters on an unindexed many2one column read the whole child table.
- Deleting a parent row needs to check the child table for references (or to set them NULL), a scan per delete when the foreign key column has no index. Deleting 10,000 records from a parent table with an unindexed child of 5 million rows can take hours. If you see a slow `DELETE`, check the foreign keys that reference the table (the query from [INSERT, UPDATE, DELETE](writing-data.md)) and whether each child column is indexed.

## Odoo workflow: find the query, then explain it

1. Get the slow SQL: from the Odoo log with `--log-sql` or the `odoo.sql_db` logger at `DEBUG`, from `pg_stat_activity` while it runs, or from `pg_stat_statements` if the extension is enabled ([psql and operations](psql-and-operations.md)). The tools are covered in [Inspecting SQL](../05-shell-and-debugging/inspecting-sql.md).
2. Replace the `%s` placeholders with real values, in psql.
3. Run `EXPLAIN (ANALYZE, BUFFERS)` on a copy of the database with realistic data.
4. Find the node with large time and `Rows Removed by Filter`, or the estimate error.
5. Prefer fixing the query (a sargable condition, a narrower domain) before adding an index; then add the index, rerun, compare the buffers.
6. In a module, declare the index in code (`index=True` on the field) rather than hand-creating it in production, so that every database gets it on update. Build it concurrently by hand on a large live database first, if the update step would block writes for too long.

## Pitfalls

- **Testing on tiny data.** Plans on a 100-row development database say nothing about production. The planner chooses by size.
- **Forgetting `ANALYZE` after a bulk load.** The first plans run on defaults; estimates are far off.
- **Indexing every column.** Each index slows writes and fills the cache. Index for real query patterns.
- **Function on the indexed column.** `lower(col)`, `col::date`, `col + 1`: the plain index is unusable.
- **`LIKE '%x'` expected to be fast.** It needs trigrams. `ILIKE` on a name field without a trigram index scans.
- **Trusting `cost` as time.** Costs are for comparing alternative plans of the same query, not for comparing queries.
- **Reading `EXPLAIN` without `ANALYZE`.** Estimates only; the error you need to find is estimate against actual.
- **Running `EXPLAIN ANALYZE` on a write.** It writes. Use a transaction and `ROLLBACK`.
- **Index-only scan expected but not happening.** The visibility map is stale after heavy writes; `VACUUM` the table.
- **Plain `CREATE INDEX` on a busy table.** It blocks writes for the build. Use `CONCURRENTLY`, and clean up an `INVALID` leftover.
- **Leaving a half-built invalid index.** It slows writes without helping reads.
- **Missing index on a foreign key.** Slow parent deletes and slow joins on the child column.
- **Raising `work_mem` globally.** It applies per sort or hash per query per connection: 200 connections with 1 GB each is an out-of-memory crash. Raise it for the one session (`SET work_mem = '256MB'`) running the heavy report.

## Try it

Use the 500,000-row `loan_log` table and its indexes as created in this chapter. Drop the extra ones as needed to reproduce each scenario.

1. Run `EXPLAIN (ANALYZE, BUFFERS)` for `WHERE member_id = 7` with no index on `member_id`. Note the rows removed. Create the right index and run it again. Compare buffers.

2. Which of these queries can use `loan_log_member_loaned_idx (member_id, loaned_on)` efficiently, and which cannot: (a) `WHERE member_id = 5`, (b) `WHERE loaned_on = '2023-05-05'`, (c) `WHERE member_id = 5 AND loaned_on > '2023-01-01'`, (d) `WHERE member_id > 700 ORDER BY loaned_on`?

3. A query `SELECT count(*) FROM loan_log WHERE returned_on IS NULL AND book_id = 42` is run thousands of times a day. Design the smallest suitable index and justify it.

4. `SELECT * FROM loan_log WHERE loaned_on::text LIKE '2024-03%'` is slow despite an index on `loaned_on`. Explain why, and rewrite it to be index-friendly.

5. You must add an index to a 200 million row table on a system that cannot stop writes. Write the statement, the check afterwards that it is valid, and what to do if it failed halfway.

<details>
<summary>Solution</summary>

1. Without an index you get a `Seq Scan` with `Rows Removed by Filter: 499375` (625 rows match) and `Buffers: shared hit=3185` or similar. After
```sql
CREATE INDEX loan_log_member_id_idx ON loan_log (member_id);
```
the plan is a `Bitmap Heap Scan` on 625 rows touching a few hundred pages; execution drops from tens of milliseconds to around one. (Drop it later if you keep the composite one: `DROP INDEX loan_log_member_id_idx;`.)

2. (a) yes: it constrains the leading column. (b) no: it does not constrain `member_id`, so the matching rows are spread through the whole index; the planner will use a seq scan or a different index. (c) yes: equality then range on the second column. (d) partially: it can scan the `member_id` range, but the order by `loaned_on` is not guaranteed by the index across multiple `member_id` values, so there will be a `Sort` node.

3. A partial index on the filter that is always present, keyed on the equality column:
```sql
CREATE INDEX loan_log_open_book_idx ON loan_log (book_id) WHERE returned_on IS NULL;
```
Only the 2% of open loans are indexed (about 264 kB instead of 11 MB), and the query's `returned_on IS NULL` implies the predicate, so it is eligible. `count(*)` can then be answered as an index-only scan if the visibility map is current.

4. `loaned_on::text` applies a cast to the column, so the plain index on `loaned_on` cannot be used and every row is converted to text. Rewrite as a range on the original type:
```sql
SELECT * FROM loan_log
WHERE loaned_on >= '2024-03-01' AND loaned_on < '2024-04-01';
```

5. 
```sql
CREATE INDEX CONCURRENTLY loan_log_xxx_idx ON loan_log (xxx);
```
(Use the real column.) Run it outside a transaction block. Afterwards check validity:
```sql
SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE indrelid = 'loan_log'::regclass;
```
`indisvalid = false` means it failed; run `DROP INDEX CONCURRENTLY loan_log_xxx_idx;` and start again, after finding out why it failed (a deadlock, a cancelled statement, a unique violation for a unique index). Run it at a quiet hour, since it waits for existing transactions to finish.

</details>
