---
description: How PostgreSQL isolates concurrent work, why Odoo runs in REPEATABLE READ, and what that means for your code.
---

# Transactions and isolation

Every Odoo request, cron run, and shell session works inside a database transaction, and every strange concurrency bug in Odoo is, underneath, a question about what a transaction can see and when it fails. "Could not serialize access due to concurrent update", a record that is invisible although another user just saved it, a stock quantity that went negative, a total that lost an update: all of them are explained by the material in this chapter. It covers atomicity and savepoints, MVCC, the three isolation levels PostgreSQL offers, the anomalies each allows (demonstrated with two sessions), and how Odoo's default level shapes the code you write. It builds on the library schema from [Relational basics](relational-basics.md).

## Transactions: all or nothing

A transaction groups statements so that they take effect together or not at all. Without `BEGIN`, psql runs each statement as its own transaction (autocommit). With it:

```sql
BEGIN;
UPDATE books SET status = 'lost' WHERE id = 2;
UPDATE books SET status = 'lost' WHERE id = 99999;   -- matches nothing, no error
SELECT id, status FROM books WHERE id = 2;
ROLLBACK;
```

```
BEGIN
UPDATE 1
UPDATE 0
 id | status
----+--------
  2 | lost
(1 row)

ROLLBACK
```

Inside the transaction you see your own change. After `ROLLBACK`, it is as if it never happened. `COMMIT` makes it permanent and visible to others. The four properties, "ACID":

- **Atomicity**: all statements apply or none do.
- **Consistency**: constraints hold at commit (an update violating a `CHECK` fails and aborts).
- **Isolation**: concurrent transactions do not see each other's half-done work; how strongly is a setting (below).
- **Durability**: after `COMMIT` returns, the data survives a crash (it is in the write-ahead log on disk).

DDL is transactional in PostgreSQL too: `ALTER TABLE`, `CREATE INDEX` (not the concurrent kind), `DROP TABLE` can be rolled back. That makes schema migrations safer here than on most databases. Sequences are the exception (a `nextval` never rolls back), which is why ids have gaps.

### Aborted transactions

When a statement inside a transaction raises an error, the transaction enters the aborted state. Everything after is refused until you end it:

```sql
BEGIN;
SELECT 1 / 0;
SELECT 1;
```

```
ERROR:  division by zero
ERROR:  current transaction is aborted, commands ignored until end of transaction block
```

The only way out is `ROLLBACK` (a `COMMIT` of an aborted transaction is silently turned into a rollback). In Odoo this shows up as `psycopg2.errors.InFailedSqlTransaction`, almost always because Python code caught the first exception, swallowed it, and continued using the same cursor.

### Savepoints: a partial rollback

A savepoint marks a point inside a transaction that you can roll back to without abandoning the whole transaction:

```sql
BEGIN;
INSERT INTO members (name, email, joined_on) VALUES ('Tess', 'tess@example.com', '2024-07-01');

SAVEPOINT before_risky;
INSERT INTO members (name, email, joined_on) VALUES ('Dup', 'tess@example.com', '2024-07-01');
```

```
ERROR:  duplicate key value violates unique constraint "members_email_key"
```

```sql
ROLLBACK TO SAVEPOINT before_risky;
SELECT name FROM members WHERE email = 'tess@example.com';
COMMIT;
```

```
  name
--------
 Tess
(1 row)
```

`Tess` survived and the duplicate attempt vanished, and the transaction is usable again. Odoo wraps this in `with self.env.cr.savepoint():`. Use it around any code that may legitimately fail on a database error (an `unlink` that may be blocked by a foreign key, a `create` that may hit a unique constraint) and that you intend to survive:

```python
# fragment: inside an Odoo method
for vals in vals_list:
    try:
        with self.env.cr.savepoint():
            self.env['library.book'].create(vals)
    except Exception:
        _logger.exception("skipping %s", vals)
```

Without the savepoint the first failure poisons the transaction and every later `create` fails with `InFailedSqlTransaction`. Savepoints are cheap, but not free: tens of thousands of them in one transaction slow it down (each one is a subtransaction), so do not wrap each of a million records.

(Remove the lab row afterwards: `DELETE FROM members WHERE email = 'tess@example.com';`.)

## MVCC: why readers do not block writers

PostgreSQL keeps multiple versions of each row. An `UPDATE` does not overwrite: it writes a new version and marks the old one as ended by your transaction. Each row version records the id of the transaction that created it (`xmin`) and the one that deleted or replaced it (`xmax`); you can look:

```sql
SELECT xmin, xmax, id, price FROM books WHERE id = 1;
```

```
 xmin | xmax | id | price
------+------+----+-------
  742 |    0 |  1 | 12.50
(1 row)
```

(Your numbers differ.) A query reads through a **snapshot**: a description of which transactions had committed at a certain moment. For each row version the query asks "was its creator committed in my snapshot, and was its deleter not?", and uses only versions that satisfy that. The consequences:

- Readers never wait for writers, and writers never wait for readers. A long report does not block order entry.
- Two writers to the same row do conflict, and one has to wait or fail (the [locks chapter](locks.md)).
- Old row versions pile up until `VACUUM` removes the ones nobody can see. A transaction that stays open forever keeps its snapshot, and nothing newer than it can be cleaned up.

The isolation level decides when a snapshot is taken: per statement or per transaction.

## The isolation levels

PostgreSQL implements three levels (a fourth, READ UNCOMMITTED, behaves as READ COMMITTED). Check the current one with `SHOW transaction_isolation;`.

### READ COMMITTED (the PostgreSQL default)

Each statement takes a fresh snapshot, so a transaction sees data committed by others between its statements. Two sessions, A and B, on a lab row, with time flowing downward:

```
Session A                                     Session B
BEGIN;
SELECT price FROM books WHERE id = 1;
  -> 12.50
                                              UPDATE books SET price = 13.00 WHERE id = 1;
                                              (autocommit: committed)
SELECT price FROM books WHERE id = 1;
  -> 13.00     (the same query, a different answer)
COMMIT;
```

This is a **non-repeatable read**: within one transaction the same query returned different results. For a report that runs several queries it means the numbers may not add up to each other. Restore the price (`UPDATE books SET price = 12.50 WHERE id = 1;`) before going on.

### REPEATABLE READ (what Odoo uses)

The snapshot is taken at the first statement of the transaction and kept until the end. The transaction sees a frozen view of the database, plus its own changes:

```
Session A                                     Session B
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT price FROM books WHERE id = 1;
  -> 12.50
                                              UPDATE books SET price = 13.00 WHERE id = 1;
                                              (committed)
SELECT price FROM books WHERE id = 1;
  -> 12.50     (still the old value)
UPDATE books SET price = price + 1 WHERE id = 1;
  -> ERROR:  could not serialize access due to concurrent update
ROLLBACK;
```

The two points to understand:

1. The snapshot is taken at the first query, not at `BEGIN`. A `BEGIN` followed by idle time sees data as of the first `SELECT`.
2. If A tries to modify a row that another transaction changed and committed after A's snapshot, PostgreSQL cannot apply A's change on top of a version A never saw, so it aborts A with SQLSTATE `40001` (`serialization_failure`). The correct reaction is to roll back and run the whole transaction again from the start, where the new snapshot sees the new row.

PostgreSQL's REPEATABLE READ is stronger than the SQL standard requires: it also prevents phantom reads (rows appearing in a repeated range query), because the snapshot is a complete view.

Odoo sets its connections to REPEATABLE READ. Hence:

- A request sees a consistent view of the database as of its first query. A record that another worker committed while your request ran stays invisible to it. A scheduled action that loops for twenty minutes without committing works on twenty-minute-old data.
- Writing to a row that someone else has modified since your snapshot fails with a serialization error instead of silently overwriting. That is safer than READ COMMITTED, and it makes retries a core part of the framework.
- A `cr.commit()` ends the transaction; the next statement begins a new one with a fresh snapshot. That is the legitimate reason to commit in a long batch, and the reason it breaks atomicity (below).

### SERIALIZABLE

The strictest: the outcome is as if the transactions had run one at a time in some order. PostgreSQL implements it (SSI) by tracking read and write dependencies and aborting a transaction when it would produce a result no serial order could. Anything that goes wrong becomes a `40001`, so applications must retry. Odoo does not use it, but it is the level that stops write skew (next section). You choose it per transaction: `BEGIN ISOLATION LEVEL SERIALIZABLE;`.

| Anomaly | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| Dirty read (see uncommitted data) | no | no | no |
| Non-repeatable read | possible | no | no |
| Phantom read | possible | no (in PostgreSQL) | no |
| Lost update | possible | prevented by failure | prevented by failure |
| Write skew | possible | possible | prevented by failure |

## Lost updates

The most common real-life concurrency bug is "read, compute in the application, write back". Set up a stock table:

```sql
CREATE TABLE book_stock (
    book_id  integer PRIMARY KEY REFERENCES books (id),
    copies   integer NOT NULL CHECK (copies >= 0)
);
INSERT INTO book_stock VALUES (1, 3);
```

Two clerks each check out a copy at the same moment. Application code reads `copies`, subtracts one, and writes the result. In READ COMMITTED:

```
Session A                                     Session B
BEGIN;                                        BEGIN;
SELECT copies FROM book_stock WHERE book_id=1;
  -> 3
                                              SELECT copies FROM book_stock WHERE book_id=1;
                                                -> 3
UPDATE book_stock SET copies = 2 WHERE book_id=1;
COMMIT;
                                              UPDATE book_stock SET copies = 2 WHERE book_id=1;
                                              COMMIT;
```

Two copies went out, and the stock fell from 3 to 2 instead of 1. Neither session errored. This is a lost update. There are three standard cures, in increasing strength:

**1. A single atomic statement.** Let the database do the arithmetic:

```sql
UPDATE book_stock SET copies = copies - 1 WHERE book_id = 1 AND copies > 0;
```

In READ COMMITTED, B's update waits for A's lock, and when A commits B re-evaluates the `WHERE` and the expression on the new row version: `copies = 2 - 1 = 1`. The row-count tag (`UPDATE 1` or `UPDATE 0`) tells the application whether a copy was available. No read step exists to go stale.

**2. Lock the row when you read it:**

```sql
BEGIN;
SELECT copies FROM book_stock WHERE book_id = 1 FOR UPDATE;
-- compute in the application
UPDATE book_stock SET copies = 1 WHERE book_id = 1;
COMMIT;
```

`FOR UPDATE` makes B's `SELECT` wait until A finishes, then return the new value. See [Locks](locks.md).

**3. Rely on REPEATABLE READ to fail loudly.** Under Odoo's level, B's `UPDATE` fails with `could not serialize access due to concurrent update`, and the request is retried from scratch against fresh data. The lost update becomes a retry. This is the safety net under every ORM `write()`, but it only works if the retry actually re-reads the data. An application that catches the error and re-applies the same stale computation defeats it.

## Write skew: the anomaly REPEATABLE READ allows

Two transactions read overlapping data, each makes a decision, and each writes a different row. No row is updated twice, so there is no conflict, yet the combination violates a rule neither checked alone. Rule: at least one member must stay active.

```
Session A                                     Session B
BEGIN ISOLATION LEVEL REPEATABLE READ;        BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM members WHERE active;    SELECT count(*) FROM members WHERE active;
  -> 3                                          -> 3
UPDATE members SET active = false WHERE id=1; UPDATE members SET active = false WHERE id=2;
COMMIT;                                       COMMIT;
```

Both transactions saw "3 active, deactivating one leaves 2" and both committed; no database constraint tells them about each other. (The lab has three active members: Nora, Omar, Petra; extend the scenario to all three and the end result is none.) Under REPEATABLE READ both commit. Under SERIALIZABLE one `COMMIT` fails:

```
ERROR:  could not serialize access due to read/write dependencies among transactions
DETAIL:  Reason code: Canceled on identification as a pivot, during commit attempt.
HINT:  The transaction might succeed if retried.
```

Odoo runs REPEATABLE READ, so such invariants are your problem. Typical examples: "only one default record per company", "stock must not go below zero across several lines", "this sequence number must be unique". The remedies:

- Express the rule as a database constraint (`UNIQUE`, a partial unique index, `CHECK`) so that the database enforces it regardless of isolation. The losing transaction fails with a unique violation. Note that Odoo does not retry unique violations automatically, since a duplicate is usually a real error; the caller sees an error and decides.
- Take a lock on a shared parent row (`SELECT ... FROM res_company WHERE id = ... FOR UPDATE`) at the start of the check-then-act sequence, so concurrent attempts queue. Cheap and effective for low-contention rules.
- Use `pg_advisory_xact_lock(key)` as a named mutex (see [Locks](locks.md)).

## How Odoo uses transactions

A few facts about the framework, all of which follow from the above:

**One transaction per request.** An HTTP request or RPC call gets a cursor; at the end of the request Odoo commits, or rolls back if an exception escapes. All ORM writes in the request, including those done by overridden methods and by `mail` automations, are one atomic unit.

**Retries on concurrency errors.** When a request fails with a serialization failure, a deadlock, or a lock that could not be acquired, the RPC layer rolls back and runs the request again, a small number of times (five in the versions this book targets; look for `PG_CONCURRENCY_ERRORS_TO_RETRY` and `MAX_TRIES_ON_CONCURRENCY_FAILURE` in `odoo/service/model.py`). This is why a rare "could not serialize" error is normally invisible to users, and why you will see it in logs as a `WARNING` or `INFO` line followed by a successful completion.

Retrying a request means running your controller or method again from scratch. Everything must therefore be safe to repeat: no side effect outside the database (an email sent, a payment API called, a file written) may happen before the commit unless it is idempotent. The retry logic only works while the request body can be replayed, which is another reason to keep side effects at the very end or in a post-commit hook (`cr.postcommit.add(...)`, available in recent versions; check yours).

**Never catch database errors blindly.**

```python
# fragment: the bug
try:
    self.env['library.loan'].create(vals)
except Exception:
    pass          # the cursor is now unusable; the next statement raises InFailedSqlTransaction
```

Either let the error propagate, or wrap the risky call in `with self.env.cr.savepoint():`. And never swallow `psycopg2.errors.SerializationFailure` or `DeadlockDetected`: catching them stops the framework from retrying, and turns a harmless collision into lost work.

**`cr.commit()` in your code is rarely right.** It ends the transaction, makes everything so far permanent, and means that an error later leaves half the work done. It is legitimate in long cron jobs that process thousands of independent records, committing after each batch so progress survives a failure and locks are released. It is wrong in the middle of a business flow that must be atomic. Also remember: after a `commit()` the ORM cache may hold records from the old snapshot; Odoo invalidates what it knows about, but your own SQL results do not refresh themselves.

**Reading your own raw SQL writes.** If you `cr.execute("UPDATE ...")` and then `browse().field` for a record already in the cache, you may read the stale cached value. Call `self.env.invalidate_all()` (or the recordset's `invalidate_recordset`) after raw writes. Details in the ORM part under [Cache and prefetch](../06-orm/cache-and-prefetch.md) and [Raw SQL from the ORM](../06-orm/raw-sql-from-the-orm.md).

**Autocommit cursors.** A few operations run outside a transaction (creating or dropping a database, `CREATE INDEX CONCURRENTLY`, `VACUUM`), because PostgreSQL refuses them inside one. Odoo does these through a cursor in autocommit mode (`cr._cnx.autocommit = True`). If you must run such a statement from a script, open a plain psycopg2 connection with `autocommit = True`.

{% hint style="info" %}
Versions. The retry policy and its helper function have been reorganized between Odoo releases (the retry decorator moved, the maximum count and wait differ, and newer versions retry also in `odoo.http` dispatch). Treat the numbers above as "a few attempts" and read your version's `service/model.py` and `http.py` before relying on exact behaviour.
{% endhint %}

## Long transactions and idle in transaction

A transaction that stays open does damage even if it does nothing:

- Its snapshot holds back vacuum: dead row versions cannot be removed while any transaction might still need to see them. Tables bloat.
- It holds every lock it took, so others wait on rows it has modified.
- A transaction that has not committed prevents some DDL and makes `CREATE INDEX CONCURRENTLY` wait.

Find them:

```sql
SELECT pid,
       usename,
       state,
       now() - xact_start  AS xact_age,
       now() - state_change AS in_state_for,
       left(query, 60)      AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

```
  pid  | usename |        state        |    xact_age     |  in_state_for   |        last_query
-------+---------+---------------------+-----------------+-----------------+--------------------------
 18211 | odoo    | idle in transaction | 02:14:09.331    | 02:14:08.920    | SELECT "res_users"."id" FROM ...
 18390 | odoo    | active              | 00:00:00.041    | 00:00:00.041    | SELECT ...
(2 rows)
```

`idle in transaction` for hours means a client (a forgotten `psql` window, a shell session that did `env['x'].create(...)` and never committed or exited, a crashed worker connection) is holding a transaction open. Set a safety net on the server or on the role:

```sql
ALTER ROLE odoo SET idle_in_transaction_session_timeout = '10min';
```

That setting terminates sessions idle in a transaction for too long; choose a value that exceeds the slowest legitimate pause (an Odoo worker between statements) with a wide margin, and note that it also kills a developer who thinks at the prompt during a debugging session. Apply it deliberately and tell the team.

## Pitfalls

- **Assuming a transaction sees the latest data.** Under REPEATABLE READ it sees data as of its first query. Long jobs process stale input; start a new transaction (commit) per batch if freshness matters.
- **Catching an SQL error and continuing.** The transaction is aborted; use a savepoint, or let the error propagate.
- **Swallowing serialization failures.** They are signals to retry, not bugs to hide.
- **Side effects before commit.** Emails, webhooks, and payment calls inside a transaction that may be retried or rolled back leave the world and the database disagreeing. Do them after commit, and make them idempotent.
- **Read-modify-write in Python.** Under any level but SERIALIZABLE, stale-read logic can still produce wrong results between rows. Use atomic SQL expressions, `FOR UPDATE`, or a unique constraint.
- **Relying on application checks for cross-row rules.** Two concurrent requests both pass the check. Enforce it in the database or serialize with a lock.
- **`cr.commit()` mid-flow.** Breaks atomicity and leaves partial results after an error; also surprises tests, which run in one transaction.
- **Open transactions in shells.** A `psql` or Odoo shell session left at an open `BEGIN` blocks vacuum and other people's updates. Always end with `COMMIT` or `ROLLBACK`, or enable the idle timeout.
- **Counting on sequence gaplessness.** Rollbacks and retries burn numbers.
- **Reading `now()` as "the current time".** It is the transaction start time and does not advance; in a long transaction it is old. `clock_timestamp()` is the wall clock.
- **Running `VACUUM`, `CREATE INDEX CONCURRENTLY` or `CREATE DATABASE` in a transaction.** PostgreSQL refuses ("cannot run inside a transaction block"); use autocommit.

## Try it

You need two psql windows connected to `handbook_lab`; call them A and B.

1. Reproduce a non-repeatable read in READ COMMITTED, then repeat the exact sequence with `BEGIN ISOLATION LEVEL REPEATABLE READ` in A and note the difference. Restore the price afterwards.

2. In A (REPEATABLE READ) read book 1's price, then in B update and commit its price, then in A update the same row. Record the error and its SQLSTATE (`\set VERBOSITY verbose` shows it). What should the application do next?

3. Using `book_stock`, show a lost update with two sessions in READ COMMITTED that each do read, then `UPDATE ... SET copies = <value computed in the shell>`. Then redo it with `UPDATE ... SET copies = copies - 1`. Explain the difference in the final value.

4. Demonstrate that an error inside a transaction aborts it, then use a savepoint so the transaction survives and commits the first insert.

5. Write a `psql` or Python snippet that retries a transaction up to five times on SQLSTATE `40001` and `40P01`, with a short random wait between attempts. Say what must be true of the transaction body for retrying to be safe.

<details>
<summary>Solution</summary>

1. In READ COMMITTED, A's second `SELECT` returns 13.00 after B's committed update; in REPEATABLE READ it still returns 12.50, and only a new transaction in A shows 13.00. Restore with `UPDATE books SET price = 12.50 WHERE id = 1;`.

2. A fails with
```
ERROR:  could not serialize access due to concurrent update
```
SQLSTATE `40001`. A's transaction is aborted. The application must `ROLLBACK` and run the whole transaction again from the start, including reading, because its snapshot was stale. A new transaction in A sees B's value and applies the change on top of it.

3. Read-modify-write: both read 3, A writes 2 and commits, B writes 2 and commits; final value 2 although two copies left. With `SET copies = copies - 1`, B waits for A's row lock and, when A commits, recomputes `copies - 1` from the new row (2), ending with 1. Under REPEATABLE READ the second form instead fails with `40001` for B, and B retries to reach 1. Clean up with `DROP TABLE book_stock;` afterwards.

4. 
```sql
BEGIN;
INSERT INTO members (name, joined_on) VALUES ('Savepoint Test', '2024-07-01');
SAVEPOINT s;
INSERT INTO members (name, joined_on) VALUES (NULL, '2024-07-01');   -- NOT NULL violation
ROLLBACK TO SAVEPOINT s;
COMMIT;
```
After `ROLLBACK TO` the transaction is usable and the first insert commits. Without the savepoint, the `COMMIT` would behave as a `ROLLBACK`. Remove the row afterwards.

5. 
```python
import random, time
import psycopg2
from psycopg2 import errors

def run_with_retry(dsn, work, tries=5):
    for attempt in range(1, tries + 1):
        conn = psycopg2.connect(dsn)
        try:
            with conn:                      # commit on success, rollback on exception
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    return work(cur)
        except (errors.SerializationFailure, errors.DeadlockDetected):
            if attempt == tries:
                raise
            time.sleep(random.uniform(0.05, 0.3) * attempt)
        finally:
            conn.close()
```
(Use a database that is the lab only.) Retrying is safe only if `work` has no effect outside the transaction (no emails, no external calls), re-reads everything it depends on at the start of each attempt, and does not carry computed state over from a previous attempt.

</details>
