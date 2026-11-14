---
description: "Changing data with INSERT, UPDATE, DELETE, and RETURNING, and doing it safely next to Odoo."
---

# INSERT, UPDATE, DELETE

Sooner or later a script has to change data without going through the ORM: a migration backfills a new column, a bad import needs undoing, a stuck state needs resetting, a million rows need a fix that `write()` would take hours to apply. This chapter covers the three write statements, `RETURNING`, upserts, and joins inside writes. It also covers what raw SQL skips (the ORM's recomputes, audit columns, caches, and constraints), and a repeatable workflow in which every change is preceded by its read-only twin and wrapped in a transaction. It uses the library schema from [Relational basics](relational-basics.md) and [Joins](joins.md).

{% hint style="danger" %}
Every statement in this chapter changes data. Run them in your `handbook_lab` database only. For the exercises on a real Odoo database, use a copy restored from a backup (see [psql and operations](psql-and-operations.md)), never the live system, and never without the read-only `SELECT` first.
{% endhint %}

## The workflow, before the syntax

Fix data in four steps:

1. Write the `SELECT` that returns exactly the rows you intend to change. Read the result.
2. Open a transaction (`BEGIN`) and run the write with the same `WHERE`.
3. Compare the reported row count with your expectation, and re-`SELECT` to look at the result.
4. `COMMIT` if it matches, `ROLLBACK` if it does not.

Here it is for real. Which loans are still open?

```sql
SELECT id, book_id, member_id, due_on FROM loans WHERE returned_on IS NULL ORDER BY id;
```

```
 id | book_id | member_id |   due_on
----+---------+-----------+------------
  3 |       1 |         2 | 2024-03-24
  5 |       4 |         3 | 2024-04-16
(2 rows)
```

Two rows. Now extend their due date by a week, inside a transaction, and look at the outcome before deciding:

```sql
BEGIN;

UPDATE loans
SET due_on = due_on + 7
WHERE returned_on IS NULL
RETURNING id, due_on;
```

```
 id |   due_on
----+------------
  3 | 2024-03-31
  5 | 2024-04-23
(2 rows)

UPDATE 2
```

Two rows updated, as predicted. If you were satisfied you would type `COMMIT;`. Here we are only practicing:

```sql
ROLLBACK;
```

Until `COMMIT`, no other session sees your change, and `ROLLBACK` discards it as if nothing had happened (apart from sequence values consumed). This single habit prevents most data incidents. An unexpected `UPDATE 4817` where you expected 2 is the cheapest possible warning, and only if the transaction is still open.

{% hint style="warning" %}
psql runs each statement in its own transaction unless you issue `BEGIN`. That is "autocommit": a bare `UPDATE` is committed the instant it finishes. Some GUI clients do the opposite and open a transaction silently, which is why an `UPDATE` you ran "yesterday" can still be uncommitted and holding locks today. Know which mode your tool is in.
{% endhint %}

## INSERT

The basic form names the columns and gives the values:

```sql
INSERT INTO authors (name, born_year, country)
VALUES ('Eve Quill', 1990, 'UK');
```

```
INSERT 0 1
```

`INSERT 0 1` means: oid 0 (obsolete, always 0), one row inserted. Name the columns every time. A column list protects the statement from later `ALTER TABLE` changes and lets the columns you leave out take their defaults (`id` from the sequence, `status` from `'available'`).

Several rows in one statement are faster than several statements:

```sql
INSERT INTO authors (name, born_year, country) VALUES
    ('Fay Rowan',  1985, 'US'),
    ('Gus Heller', 1971, NULL);
```

### RETURNING

`RETURNING` hands back the rows the statement wrote, including defaults and generated values. It removes the need for a second query to find the new id:

```sql
INSERT INTO books (title, author_id, published_year, price, pages)
VALUES ('Small Hours', 5, 2023, 13.00, 220)
RETURNING id, title, status;
```

```
 id |    title    |  status
----+-------------+-----------
  7 | Small Hours | available
(1 row)
```

(The `id` depends on how many failed inserts consumed sequence values earlier. After the failing examples of the first chapter it is 10; on a fresh lab it is 7.) Odoo's ORM uses exactly this, `INSERT ... RETURNING id`, in `create()`.

These example rows stay in your lab. Leave them for now; the section "Cleaning up the lab" near the end of the chapter removes them.

### INSERT from a SELECT

Any query can feed an insert, as long as the columns line up:

```sql
CREATE TABLE loans_archive (LIKE loans INCLUDING ALL);

SELECT id FROM loans WHERE returned_on < '2024-03-01' ORDER BY id;
```

```
 id
----
  1
  2
(2 rows)
```

```sql
INSERT INTO loans_archive
SELECT * FROM loans WHERE returned_on < '2024-03-01';
```

```
INSERT 0 2
```

`LIKE ... INCLUDING ALL` copies column definitions, defaults, indexes and check constraints, but not foreign keys. `INSERT INTO t SELECT *` depends on both tables having identical column order, which is brittle; in real code list the columns on both sides. `CREATE TABLE ... AS SELECT` is the quick way to take a snapshot before a risky change:

```sql
CREATE TABLE fix_backup_loans AS
SELECT * FROM loans WHERE returned_on IS NULL;
```

It copies the data but no constraints or indexes, which is what you want from a throwaway safety copy. Remember to drop such tables when the fix is verified (after asking whoever owns the database, because on a shared system someone may be using it).

### Upsert: ON CONFLICT

"Insert, or update if it exists" is a single atomic statement:

```sql
SELECT id, name, email FROM members WHERE email = 'nora@example.com';
```

```
 id | name |      email
----+------+------------------
  1 | Nora | nora@example.com
(1 row)
```

```sql
BEGIN;
INSERT INTO members (name, email, joined_on)
VALUES ('Nora Renamed', 'nora@example.com', '2024-07-01')
ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
RETURNING id, name;
ROLLBACK;
```

```
 id |     name
----+--------------
  1 | Nora Renamed
(1 row)
```

`ON CONFLICT (email)` names the unique index to check. If a row with that email exists, the `DO UPDATE` branch runs, and `EXCLUDED` refers to the row you tried to insert. `DO NOTHING` skips the conflict silently and returns no row (`INSERT 0 0`). The conflict target must be backed by a unique index or constraint, otherwise PostgreSQL errors with `there is no unique or exclusion constraint matching the ON CONFLICT specification`.

`ON CONFLICT` is safe under concurrency: two sessions upserting the same key do not both insert, and neither gets a duplicate-key error. The conflicting loser waits for the winner to commit and then takes the update branch. That is what you want in code that registers something "if it is not there yet" while other workers do the same. Note that a skipped or updated insert still consumed a sequence value, so ids have gaps.

{% hint style="info" %}
Versions. PostgreSQL 15 added the standard `MERGE` statement. Odoo 16 to 18 officially support PostgreSQL 12 and later, so code that has to run on all of them must stick to `ON CONFLICT`. For one-off scripts on a known newer server, `MERGE` is available.
{% endhint %}

## UPDATE

```sql
BEGIN;
UPDATE books SET price = price * 1.10 WHERE author_id = 1 RETURNING id, title, price;
ROLLBACK;
```

```
 id |   title    |  price
----+------------+---------
  1 | Tidewater  | 13.7500
  2 | Salt Roads | 16.5000
(2 rows)
```

(`numeric(8,2) * 1.10` gives a result with more decimals in `RETURNING`; the column itself would round to two places when stored: 13.75 and 16.50.)

The `SET` list can reference current column values and several columns at once (`SET a = b, b = a` swaps them, since the right sides all see the old row). A missing `WHERE` updates every row of the table. Leaving the `WHERE` off on a production table is the classic disaster, which is why the workflow starts with a transaction and a row-count check.

### UPDATE ... FROM: updating using another table

To set values from, or select rows by, another table, list it in `FROM` and join it in `WHERE`. Mark books that are currently out on loan. Read-only version first:

```sql
SELECT DISTINCT b.id, b.title, b.status
FROM books b
JOIN loans l ON l.book_id = b.id
WHERE l.returned_on IS NULL AND b.status = 'available'
ORDER BY b.id;
```

```
 id |    title    |  status
----+-------------+-----------
  1 | Tidewater   | available
  4 | Paper Moons | available
(2 rows)
```

```sql
BEGIN;

UPDATE books b
SET status = 'on_loan'
FROM loans l
WHERE l.book_id = b.id
  AND l.returned_on IS NULL
  AND b.status = 'available'
RETURNING b.id, b.title, b.status;
```

```
 id |    title    | status
----+-------------+---------
  1 | Tidewater   | on_loan
  4 | Paper Moons | on_loan
(2 rows)

UPDATE 2
```

```sql
ROLLBACK;
```

A hidden trap: if a target row matches several rows of the `FROM` table, PostgreSQL updates it once, using an arbitrary one of the matches, and does not warn you. Here each book has at most one open loan, but a book with two open loans would be updated with whichever came first; if the `SET` used a value from `loans` the result would be unpredictable. When values come from the joined table, make sure the join produces one row per target, by aggregating first or using `DISTINCT ON`.

The alternative is a correlated subquery in `SET`, which makes uniqueness explicit: a subquery returning more than one row raises `more than one row returned by a subquery used as an expression`, which is the failure you want instead of a silent arbitrary pick. Use it for single-value lookups; use `UPDATE ... FROM` when you set several columns from the same joined row.

### What an UPDATE really does

PostgreSQL does not overwrite a row in place. An `UPDATE` writes a new version of the row and marks the old one dead (this is MVCC, which the [transactions chapter](transactions-and-isolation.md) builds on). Consequences you can feel:

- Updating every row of a table doubles its physical size until `VACUUM` reclaims the dead versions ("table bloat"). A big backfill on a large table leaves a lot of work for autovacuum.
- Every index containing a changed column gets a new entry per updated row, too. Updating an indexed column of millions of rows is much heavier than updating an unindexed one.
- A no-op update (`SET x = x`) still creates a row version. Add `AND x IS DISTINCT FROM new_value` to the `WHERE` to skip rows that already hold the target value; it makes scripts idempotent and cheaper:

```sql
BEGIN;
UPDATE books SET status = 'available'
WHERE status IS DISTINCT FROM 'available' AND id = 3;
ROLLBACK;
```

## DELETE

```sql
SELECT id, returned_on FROM loans WHERE returned_on < '2024-03-01' ORDER BY id;
```

```
 id | returned_on
----+-------------
  1 | 2024-01-18
  2 | 2024-02-20
(2 rows)
```

```sql
BEGIN;
DELETE FROM loans WHERE returned_on < '2024-03-01' RETURNING id;
ROLLBACK;
```

```
 id
----
  1
  2
(2 rows)

DELETE 2
```

`RETURNING` on `DELETE` returns the deleted rows, so you can capture exactly what disappeared. A pattern worth using on any manual delete is to move rows into a log table in the same statement, via a data-modifying CTE:

```sql
BEGIN;
WITH gone AS (
    DELETE FROM loans WHERE returned_on < '2024-03-01' RETURNING *
)
INSERT INTO loans_archive SELECT * FROM gone;
ROLLBACK;
```

The delete and the insert are one atomic statement: either both happen or neither does.

To delete using another table, `USING` plays the role of `FROM` in an update:

```sql
BEGIN;
DELETE FROM book_genre bg
USING books b
WHERE bg.book_id = b.id AND b.status = 'lost'
RETURNING bg.book_id, bg.genre_id;
ROLLBACK;
```

```
 book_id | genre_id
---------+----------
       3 |        1
(1 row)
```

Foreign keys apply on delete: a referenced row with `ON DELETE RESTRICT` blocks the delete with an error, `CASCADE` removes the children too, `SET NULL` clears their keys. Before deleting rows from a parent table, list what references it, with `\d table` ("Referenced by") or this catalog query:

```sql
SELECT conrelid::regclass AS referencing_table,
       conname,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'f' AND confrelid = 'books'::regclass;
```

```
 referencing_table |         conname         |                          definition
-------------------+-------------------------+---------------------------------------------------------------
 loans             | loans_book_id_fkey      | FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE RESTRICT
 book_genre        | book_genre_book_id_fkey | FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
(2 rows)
```

On an Odoo database this query, run against `res_partner`, returns many dozens of rows, which is the real answer to "why can't I delete this contact".

### TRUNCATE

`TRUNCATE table` empties a table instantly, without scanning it, and unlike `DELETE` leaves no dead rows behind. It also takes an `ACCESS EXCLUSIVE` lock (blocks every reader and writer), skips row-level triggers, and `TRUNCATE ... CASCADE` truncates every table that references the target. It is transactional in PostgreSQL, so inside `BEGIN` you can roll it back, but do not touch it on an Odoo database: with `CASCADE` it reaches tables you did not know existed. Use it for your own staging tables.

## Bulk loading: COPY

For loading many rows from a file, `COPY` is an order of magnitude faster than inserts:

```sql
COPY books_stage (title, price) FROM '/var/lib/postgresql/books.csv' WITH (FORMAT csv, HEADER true);
```

That form reads the file on the database server and needs superuser rights or the `pg_read_server_files` role. In practice you use psql's client-side `\copy`, which reads the file on your machine and streams it through the connection:

```
\copy books_stage (title, price) FROM 'books.csv' WITH (FORMAT csv, HEADER true)
```

The reliable import pattern is to load into a staging table with plain `text` columns, check and clean it with `SELECT`s, and only then `INSERT ... SELECT` into the real table with casts. That way one bad cell produces a row you can inspect instead of an aborted load. `COPY (SELECT ...) TO STDOUT WITH (FORMAT csv, HEADER)` works in the other direction and is the quickest export.

## What raw SQL bypasses in Odoo

Everything above works on any PostgreSQL table. On an Odoo table the same statements skip the ORM, and the ORM does more than store values. Know what you give up:

| What the ORM does | Effect of raw SQL |
|---|---|
| sets `create_uid`, `create_date`, `write_uid`, `write_date` | the columns keep old values or stay NULL on insert; "last modified" filters and incremental syncs miss your change |
| recomputes stored computed fields (`store=True`) | dependants keep stale values, e.g. a total does not follow its lines |
| runs `@api.constrains` and `_sql_constraints` in Python | only database constraints apply |
| applies access rights and record rules | none; you act as the database owner |
| invalidates the record cache | running workers keep the old value in memory until restart or cache clear; this applies to cached models such as `ir.config_parameter` and `ir.rule` |
| creates `mail.message` tracking, activities, chatter | nothing is logged |
| maintains `ir_model_data`, `ir_attachment` links, translations | a raw delete leaves XML-id rows pointing at nothing |
| fires `ondelete` logic implemented in Python (`unlink` overrides) | skipped |

So the rule is: change data through the ORM (the Odoo shell, covered in [The Odoo shell](../05-shell-and-debugging/odoo-shell.md) and [Safe bulk scripts](../05-shell-and-debugging/safe-bulk-scripts.md)) whenever the volume allows it, and use SQL for what the ORM cannot do reasonably. When you must use SQL:

- Set the audit columns yourself. Odoo stores datetimes as UTC without a zone:

```sql
SELECT count(*) FROM library_book WHERE state IS NULL;   -- read-only counterpart first

UPDATE library_book
SET state = 'available',
    write_uid = 1,
    write_date = now() AT TIME ZONE 'utc'
WHERE state IS NULL;
```

  (`library_book` is the teaching module's table; user id 1 is the system user in standard Odoo, you can use the id of an administrative user instead.)

- If the changed column feeds stored computed fields, either update those too in SQL, or afterwards trigger the recompute from the shell: `records.modified(['state'])` followed by `env.flush_all()` (the exact API name has moved between versions; check the source of your release).
- Restart the workers, or call the cache clearing for the registry, when you changed a cached setting.
- Update translated fields as `jsonb`, not text. In Odoo 16 to 18 a translated `name` is a JSON object keyed by language code, so replacing it with a plain string breaks the column's type contract:

```sql
UPDATE library_book
SET name = jsonb_set(name, '{en_US}', to_jsonb('New title'::text))
WHERE id = 1;
```

  `jsonb_set` replaces one key and leaves the other languages intact; assigning `name = '"New title"'::jsonb` would wipe them.

- Never write to `ir_model_data` or delete from `ir_model`, `ir_model_fields`, `ir_ui_view` by hand to "clean up" a module: the next update will recreate or orphan things in confusing ways. Uninstall properly.

{% hint style="warning" %}
Never run `UPDATE` or `DELETE` on a live production Odoo database as a first attempt. Reproduce on a restored copy, check the Odoo UI and a module update against that copy, and only then repeat in production, in a transaction, with the row count you predicted.
{% endhint %}

## Large updates in batches

One `UPDATE` over ten million rows holds its row locks and a transaction snapshot until it ends, generates a single enormous WAL burst, and if it fails at the end throws all the work away. Batch it, committing between batches. Each batch picks a limited set of rows that still need the change:

```bash
#!/usr/bin/env bash
# fragment: batched backfill against a scratch database
while true; do
  n=$(psql -d handbook_lab -q -At -c "
    WITH batch AS (
      SELECT id FROM books
      WHERE status IS DISTINCT FROM 'available' AND status <> 'lost'
      LIMIT 1000
      FOR UPDATE SKIP LOCKED
    )
    UPDATE books b SET status = 'available'
    FROM batch WHERE b.id = batch.id
    RETURNING 1" | wc -l)
  echo "updated $n rows"
  [ "$n" -eq 0 ] && break
done
```

Each `psql -c` is its own transaction, so each batch commits. The `WHERE` excludes rows already processed, which makes the loop restartable and ends it with 0. `FOR UPDATE SKIP LOCKED` (next chapters) avoids waiting on rows another session holds. Pause between batches on a busy system, and run `VACUUM (ANALYZE)` on the table afterwards.

Create new indexes after a large backfill rather than before it, when the backfill rewrites many rows; and do not change a column's type with `ALTER TABLE ... TYPE` on a big table at a busy time, because most type changes rewrite the whole table under an `ACCESS EXCLUSIVE` lock.

## Guarding scripts: expecting a row count

When a fix runs as a script rather than interactively, do not rely on eyes: assert the row count and abort the whole transaction otherwise.

```sql
BEGIN;

DO $$
DECLARE
    n integer;
BEGIN
    UPDATE loans SET due_on = due_on + 7 WHERE returned_on IS NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 2 THEN
        RAISE EXCEPTION 'expected to touch 2 loans, touched %', n;
    END IF;
END
$$;

COMMIT;
```

If the count is wrong, the `RAISE EXCEPTION` puts the transaction in the aborted state, and the final `COMMIT` is turned into a rollback (psql prints `ROLLBACK`). Run with `psql -v ON_ERROR_STOP=1 -f fix.sql` so that a failure stops the script instead of continuing to later statements.

## Cleaning up the lab

The inserts and helper tables above were committed. Remove them so that later chapters match their printed results:

```sql
DELETE FROM books   WHERE title = 'Small Hours';
DELETE FROM authors WHERE name IN ('Eve Quill', 'Fay Rowan', 'Gus Heller');
DROP TABLE loans_archive, fix_backup_loans;
DROP TABLE IF EXISTS members_removed;
```

## Pitfalls

- **`UPDATE` or `DELETE` without `WHERE`.** Changes every row. Always begin a transaction, read the `UPDATE n` count, and ROLLBACK if it is not the number you expected.
- **Autocommit misunderstanding.** A statement outside `BEGIN` is committed immediately in psql; in some GUIs a hidden open transaction holds locks for hours. Check `SELECT now() - xact_start FROM pg_stat_activity` (see [psql and operations](psql-and-operations.md)).
- **`UPDATE ... FROM` with several matches.** The target row gets one arbitrary match. Make the join one-to-one.
- **Setting a value but not its dependants.** A stored computed field, a denormalized counter, a `parent_path`, or an `ir_model_data` row left stale. Update all of them, or recompute through the ORM.
- **Forgetting `write_date` and `write_uid`.** Incremental exports, "modified since" filters and cache validation keys depend on them.
- **Raw delete on a table with `ON DELETE CASCADE` children.** The children disappear with no log. List the referencing foreign keys first.
- **Not accounting for NULLs.** `WHERE state <> 'done'` skips rows where `state` is NULL; the fix script silently leaves part of the data untouched. Use `IS DISTINCT FROM`.
- **Running big writes in one transaction.** Long-held locks, replication lag, a huge rollback if it fails. Batch.
- **Inserting rows with explicit ids.** The sequence does not move. Run `setval` afterwards, and in Odoo prefer not to insert into model tables at all.
- **Assuming `RETURNING` shows the final state.** It shows the row as written by the statement; `AFTER` triggers or later statements in the same transaction can still change it.
- **Leaving backup tables lying around.** `fix_backup_*` tables accumulate in production databases. Name them with a date and a ticket reference and drop them after sign-off.

## Try it

1. Add a member `Rhea` with no email, return the generated id, and then add a second member with the email of an existing member using `ON CONFLICT DO NOTHING`, observing the command tag. Roll everything back.

2. Mark all books by authors born before 1970 as `status = 'classic'`. Write the read-only `SELECT` first, then run the update in a transaction, check the count, and roll back.

3. Delete members who are inactive and have no loans, but capture the deleted rows into a table `members_removed` in the same statement. Do it inside a transaction and show the content of `members_removed` before rolling back.

4. A migration must set `loans.returned_on = due_on` for every open loan whose book is flagged `lost`. First list affected loans (probably none in the lab data), then write the update with an `UPDATE ... FROM` form and a guard that aborts if more than 5 rows would be touched.

<details>
<summary>Solution</summary>

1. 
```sql
BEGIN;
INSERT INTO members (name, joined_on) VALUES ('Rhea', '2024-07-02') RETURNING id;
INSERT INTO members (name, email, joined_on)
VALUES ('Impostor', 'omar@example.com', '2024-07-02')
ON CONFLICT (email) DO NOTHING;
ROLLBACK;
```
The first statement returns the new id; the second prints `INSERT 0 0` because the email already exists (nothing inserted, no error).

2. 
```sql
SELECT b.id, b.title, a.born_year
FROM books b JOIN authors a ON a.id = b.author_id
WHERE a.born_year < 1970 ORDER BY b.id;
```
This returns books 1 to 4 (authors Ada born 1950 and Boris born 1962). Then:
```sql
BEGIN;
UPDATE books b SET status = 'classic'
FROM authors a
WHERE a.id = b.author_id AND a.born_year < 1970
RETURNING b.id;
ROLLBACK;
```
`UPDATE 4`. Note that book 3 was `lost`: this update overwrites that status. A real script would add `AND b.status = 'available'`, which is the point of reading the `SELECT` first.

3. 
```sql
CREATE TABLE members_removed (LIKE members);

BEGIN;
WITH gone AS (
    DELETE FROM members m
    WHERE NOT m.active
      AND NOT EXISTS (SELECT 1 FROM loans l WHERE l.member_id = m.id)
    RETURNING m.*
)
INSERT INTO members_removed SELECT * FROM gone;

SELECT id, name FROM members_removed;
ROLLBACK;
```
Result: one row, `4 | Quinn`. (The `CREATE TABLE` is outside the transaction in this sketch, so the empty table stays.) Check the read-only version first: the same `WHERE` in a `SELECT`.

4. 
```sql
SELECT l.id, l.book_id
FROM loans l JOIN books b ON b.id = l.book_id
WHERE l.returned_on IS NULL AND b.status = 'lost';
```
In the lab, book 3 is lost but has no loans, so the query returns zero rows. The guarded update:
```sql
BEGIN;
DO $$
DECLARE n integer;
BEGIN
    UPDATE loans l SET returned_on = l.due_on
    FROM books b
    WHERE b.id = l.book_id AND l.returned_on IS NULL AND b.status = 'lost';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n > 5 THEN
        RAISE EXCEPTION 'refusing to touch % loans', n;
    END IF;
END
$$;
COMMIT;
```
With zero matching rows it commits without changing anything. To see the guard fire, change the threshold to `n > 0` after making a loan of book 3 in a transaction.

</details>
