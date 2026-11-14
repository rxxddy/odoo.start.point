---
description: Row locks, FOR UPDATE, SKIP LOCKED, advisory locks, and deadlocks.
---

# Locks

MVCC lets readers and writers run side by side, but two transactions that want to change the same row cannot both win, and some operations (schema changes, index builds) need exclusive access to a whole table. PostgreSQL arbitrates with locks. When Odoo "hangs" for a minute and then recovers, when an update of a module freezes the whole system, when a cron job and a user trip over each other, you are looking at locks. This chapter explains which locks exist, how to see who is waiting for whom, how to take locks deliberately (`FOR UPDATE`, `NOWAIT`, `SKIP LOCKED`, advisory locks), how deadlocks arise, and how to avoid them. It follows [Transactions and isolation](transactions-and-isolation.md) and uses the library schema.

## Why locks exist, and the two scales

Locks live at two levels:

- **Row locks** protect individual rows. `UPDATE` and `DELETE` take them automatically, and `SELECT ... FOR UPDATE` takes them on request. They are held until the transaction ends (commit or rollback).
- **Table locks** protect a table as a whole. Every statement takes one automatically, in a mode matching what it does. Most are harmless (a plain `SELECT` takes `ACCESS SHARE`, which conflicts with almost nothing); a few, notably `ALTER TABLE`, take `ACCESS EXCLUSIVE`, which conflicts with everything including `SELECT`.

A lock is released only when the transaction ends. A long transaction therefore keeps every lock it ever took, which is why "do not leave transactions open" appears in so many places.

## Row locks in action

Two sessions again, A and B. B tries to update the row A has just updated:

```
Session A                                     Session B
BEGIN;
UPDATE books SET price = 13.00 WHERE id = 1;
                                              UPDATE books SET price = 14.00 WHERE id = 1;
                                              (waits; no output)
COMMIT;
                                              (continues: UPDATE 1)
```

B did not fail. It waited for A's transaction to end and then proceeded. In READ COMMITTED it applied its update to the row as A left it. In REPEATABLE READ (Odoo's level) B would instead fail with `could not serialize access due to concurrent update` once A committed, and a retry would follow. If A had issued `ROLLBACK`, B would have proceeded with the original row.

What B waits on is a lock held on the row version A created, taken by writing it. Note that readers are not blocked: a plain `SELECT` from a third session during all this simply sees the old committed row.

### Which updates conflict

Row locks come in four strengths:

| Mode | Taken by | Conflicts with |
|---|---|---|
| `FOR KEY SHARE` | foreign-key checks (an insert into a child table locks the parent row) | `FOR UPDATE` only |
| `FOR SHARE` | explicit | `FOR NO KEY UPDATE`, `FOR UPDATE` |
| `FOR NO KEY UPDATE` | `UPDATE` that does not change key columns | `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE` |
| `FOR UPDATE` | `DELETE`, `UPDATE` of key columns, explicit `SELECT ... FOR UPDATE` | all of them |

The split exists for foreign keys: inserting a loan locks the book row in `KEY SHARE` mode (to make sure the book is not deleted meanwhile), and a concurrent `UPDATE books SET price = ...` takes `NO KEY UPDATE`, which does not conflict with `KEY SHARE`. So price changes on a book do not block loans of that book. Before PostgreSQL 9.3 this combination blocked.

## Locking on purpose: SELECT FOR UPDATE

To read a row and then change it based on what you read, lock it at read time, so nobody else can change it in between:

```sql
BEGIN;
SELECT copies FROM book_stock WHERE book_id = 1 FOR UPDATE;
-- decide in the application ...
UPDATE book_stock SET copies = copies - 1 WHERE book_id = 1;
COMMIT;
```

(`book_stock` is the small table from the previous chapter: `CREATE TABLE book_stock (book_id integer PRIMARY KEY REFERENCES books (id), copies integer NOT NULL CHECK (copies >= 0)); INSERT INTO book_stock VALUES (1, 3);`.) A second session running the same `SELECT ... FOR UPDATE` waits until the first one commits or rolls back, and then sees the updated value.

Details that matter:

- It locks only the rows returned. With `LIMIT`, only the rows actually returned are locked (but the rows examined may be more, so be careful with ordering and filters).
- With joins, lock only the table you mean: `SELECT ... FROM loans l JOIN books b ON ... FOR UPDATE OF l`. Without `OF`, every table in the join is locked.
- `FOR UPDATE` cannot be applied to the nullable side of an outer join (`FOR UPDATE cannot be applied to the nullable side of an outer join`); lock before joining, in a subquery or a separate statement.
- Locks are on the row, not on "the absence of a row". `SELECT ... FOR UPDATE` on a key that does not yet exist locks nothing, so two sessions can both see "not found" and both insert. Use a unique constraint plus `ON CONFLICT`, or lock a parent row, for existence checks.
- `FOR NO KEY UPDATE` is enough when you will not change key columns and want to avoid blocking foreign-key checks from other sessions; it is the lock a plain `UPDATE` takes.

### NOWAIT and lock_timeout

By default a lock request waits indefinitely. Two ways to refuse waiting:

```sql
SELECT * FROM book_stock WHERE book_id = 1 FOR UPDATE NOWAIT;
```

```
ERROR:  could not obtain lock on row in relation "book_stock"
```

`NOWAIT` fails immediately with SQLSTATE `55P03` (`lock_not_available`) if another transaction holds the row. `SET lock_timeout = '2s'` applies a deadline to any lock wait in the session, with the same error on expiry. Odoo's retry mechanism treats `55P03` as retryable, so a `NOWAIT` that loses just reruns the request later. It also makes a good guard for anything that must not queue (a cron job that does the same work every minute should skip a minute, not pile up).

### SKIP LOCKED: the work queue

`SKIP LOCKED` ignores rows that are currently locked, returning only the free ones. It turns a table into a queue that many workers drain without waiting on each other. Create a queue of notifications:

```sql
CREATE TABLE notify_queue (
    id       serial PRIMARY KEY,
    loan_id  integer NOT NULL,
    sent     boolean NOT NULL DEFAULT false
);
INSERT INTO notify_queue (loan_id) SELECT g FROM generate_series(1, 6) g;
```

Each worker claims a batch inside a transaction:

```
Worker A                                      Worker B
BEGIN;                                        BEGIN;
SELECT id FROM notify_queue
 WHERE NOT sent
 ORDER BY id LIMIT 2
 FOR UPDATE SKIP LOCKED;
  -> 1, 2
                                              SELECT id FROM notify_queue
                                               WHERE NOT sent
                                               ORDER BY id LIMIT 2
                                               FOR UPDATE SKIP LOCKED;
                                                -> 3, 4
UPDATE notify_queue SET sent = true           UPDATE notify_queue SET sent = true
 WHERE id IN (1, 2);                           WHERE id IN (3, 4);
COMMIT;                                       COMMIT;
```

B was not delayed by A's locks, and got different rows. If a worker crashes mid-batch, its locks vanish with its transaction and the rows return to the pool automatically. The cost: results are not a consistent view of the queue ("skipped" rows are invisible to that query), so use it for work distribution only, never for reports.

Odoo uses row locking for scheduled actions: the cron runner locks the `ir_cron` row of a job while it runs, so that two workers (or two Odoo servers on one database) never run the same job simultaneously. If a job's row is locked, the other worker skips it. Whether it is `NOWAIT` or `SKIP LOCKED` depends on the release; the effect is the same.

## Seeing who blocks whom

When something hangs, find the blocker. `pg_stat_activity` lists sessions and what they wait for; `pg_blocking_pids()` (PostgreSQL 9.6+) names the sessions blocking one:

```sql
SELECT a.pid                          AS blocked_pid,
       pg_blocking_pids(a.pid)        AS blocked_by,
       a.wait_event_type,
       a.wait_event,
       now() - a.query_start          AS waiting_for,
       left(a.query, 50)              AS query
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
```

```
 blocked_pid | blocked_by | wait_event_type |  wait_event   |  waiting_for  |                       query
-------------+------------+-----------------+---------------+---------------+----------------------------------------------------
        4121 | {4107}     | Lock            | transactionid | 00:00:41.2    | UPDATE books SET price = 14.00 WHERE id = 1
(1 row)
```

`wait_event_type = Lock` and `wait_event = transactionid` is the signature of waiting for a row lock: the waiter waits for the blocker's transaction to finish. Now look at the blocker:

```sql
SELECT pid, state, now() - xact_start AS xact_age, left(query, 60) AS last_query
FROM pg_stat_activity WHERE pid = 4107;
```

```
 pid  |        state        |  xact_age  |                          last_query
------+---------------------+------------+--------------------------------------------------------------
 4107 | idle in transaction | 00:03:02.1 | UPDATE books SET price = 13.00 WHERE id = 1
```

The blocker is `idle in transaction`: someone updated a row, forgot to commit, and walked away. `last_query` is the last statement it ran, not necessarily the one holding the lock, but it is the best clue. Who is it? `usename`, `application_name`, `client_addr` in the same view. Resolve it by having that person commit or roll back. As a last resort a DBA can end the session:

```sql
SELECT pg_cancel_backend(4107);     -- cancel the running statement, keep the session
SELECT pg_terminate_backend(4107);  -- end the session; its transaction rolls back
```

Terminating a session rolls back whatever it did. On a production Odoo database, check that the session is not a worker in the middle of a legitimate long job, and ask first.

The complete picture of what is locked is `pg_locks`:

```sql
SELECT l.pid, l.locktype, l.mode, l.granted, c.relname
FROM pg_locks l
LEFT JOIN pg_class c ON c.oid = l.relation
WHERE l.pid = 4107;
```

```
 pid  |   locktype    |       mode       | granted |  relname
------+---------------+------------------+---------+-----------
 4107 | relation      | RowExclusiveLock | t       | books_pkey
 4107 | relation      | RowExclusiveLock | t       | books
 4107 | virtualxid    | ExclusiveLock    | t       |
 4107 | transactionid | ExclusiveLock    | t       |
(4 rows)
```

You will not read `pg_locks` often; `pg_blocking_pids` answers the question you actually have. (Row locks themselves are stored in the row version, not in `pg_locks`, which is why you see the `transactionid` instead.)

## Table locks and the lock queue

Every statement takes a table-level lock. The ones to know:

| Mode | Taken by | Blocks |
|---|---|---|
| `ACCESS SHARE` | `SELECT` | only `ACCESS EXCLUSIVE` |
| `ROW EXCLUSIVE` | `INSERT`, `UPDATE`, `DELETE` | `SHARE` and stronger (index builds, DDL) |
| `SHARE UPDATE EXCLUSIVE` | `VACUUM`, `ANALYZE`, `CREATE INDEX CONCURRENTLY` | itself and stronger; ordinary reads and writes continue |
| `SHARE` | plain `CREATE INDEX` | writes (`ROW EXCLUSIVE`) |
| `ACCESS EXCLUSIVE` | `DROP TABLE`, `TRUNCATE`, `VACUUM FULL`, most `ALTER TABLE` forms | everything, reads included |

The behaviour that surprises people is the **queue**. Locks are granted in request order, and a request waits for the locks held and for the earlier waiters it conflicts with. Suppose a report is running a ten-minute `SELECT` on `books` (holding `ACCESS SHARE`). A migration then issues `ALTER TABLE books ADD COLUMN ...`, which needs `ACCESS EXCLUSIVE` and must wait for the report. While it waits, every new `SELECT` on `books` queues behind the `ALTER`: the table is unreadable although nothing has been changed yet. Users see the application freeze, and it recovers the moment the report ends or the `ALTER` is cancelled.

This is the classic cause of "we updated the module and the whole system froze". Odoo's module update runs `ALTER TABLE` statements for new columns and constraints; if a long transaction (a stuck cron, a long report, a forgotten shell) holds even a read lock on a table it touches, the update queues and blocks everyone. Defences:

```sql
-- before any manual DDL on a busy system
SET lock_timeout = '5s';
ALTER TABLE books ADD COLUMN subtitle varchar;
```

If the lock is not available within five seconds the statement fails instead of freezing everyone; retry later, ideally after finding and ending the long transaction (see the query above and the one in the [previous chapter](transactions-and-isolation.md)). Before an Odoo update on a live database, look for long transactions and make sure no cron job is running.

Other DDL notes:

- `ADD COLUMN` with a constant default is quick since PostgreSQL 11 (no table rewrite), but still takes the exclusive lock briefly. Adding a column with a volatile default, or changing a column type, rewrites the table under the exclusive lock.
- `ADD FOREIGN KEY` validates existing rows while holding a strong lock. For big tables add it `NOT VALID` (instant) and run `ALTER TABLE ... VALIDATE CONSTRAINT` afterwards, which takes a weaker lock.
- `CREATE INDEX` blocks writes; `CREATE INDEX CONCURRENTLY` does not (see [Indexes and EXPLAIN](indexes-and-explain.md)).
- `LOCK TABLE books IN SHARE MODE;` takes a table lock explicitly, which you rarely want in application code.

## Deadlocks

A deadlock is a cycle: A waits for B, B waits for A. Neither can proceed ever, so PostgreSQL resolves it: after waiting for `deadlock_timeout` (1 second by default) it checks for a cycle and, if found, aborts one transaction with SQLSTATE `40P01`.

```
Session A                                     Session B
BEGIN;                                        BEGIN;
UPDATE books SET price = 1 WHERE id = 1;
                                              UPDATE books SET price = 2 WHERE id = 2;
UPDATE books SET price = 1 WHERE id = 2;
(waits for B)
                                              UPDATE books SET price = 2 WHERE id = 1;
                                              (waits for A: a cycle)
                                              ERROR:  deadlock detected
```

The full error, as it appears in the log and to the aborted session:

```
ERROR:  deadlock detected
DETAIL:  Process 4121 waits for ShareLock on transaction 8123; blocked by process 4107.
Process 4107 waits for ShareLock on transaction 8124; blocked by process 4121.
HINT:  See server log for query details.
CONTEXT:  while updating tuple (0,1) in relation "books"
```

The victim rolls back; the other continues. Odoo retries the aborted request, so occasional deadlocks cost a delay, not an error, but frequent ones mean contention that wants fixing.

Where do they come from in Odoo? Two flows updating the same set of records in different orders. The ORM's own writes to a recordset are issued as `UPDATE ... WHERE id IN (...)`, and the order in which PostgreSQL locks the rows inside such a statement follows the physical scan order, not the id list. Two requests writing overlapping sets (a cron recomputing stock, a user confirming an order) can lock rows in opposing order. The cure is the standard one: **always acquire locks in a consistent global order**.

```sql
BEGIN;
SELECT id FROM books WHERE id IN (1, 2) ORDER BY id FOR UPDATE;   -- lock in id order
UPDATE books SET price = price + 1 WHERE id IN (1, 2);
COMMIT;
```

If every flow that touches several rows locks them sorted by id first, no cycle can form. In Python: `records.sorted('id')` before the loop of writes, or a `SELECT ... ORDER BY id FOR UPDATE` before a raw bulk update.

Other ways to reduce deadlocks: keep transactions short, do not mix long computation or network calls between the first lock and the commit, and avoid unnecessary updates (every `UPDATE`, even to the same value, takes the row lock).

## Unique indexes also make you wait

Two sessions inserting the same unique key serialize: the second `INSERT` waits for the first to finish. If the first commits, the second fails with a unique violation; if the first rolls back, the second proceeds. This is correct behaviour, but it is a lock wait: you will see `wait_event = transactionid` in `pg_stat_activity` for an `INSERT`. It is why an import that creates the same partner or XML ID from two parallel workers stalls and then fails.

## Advisory locks: a mutex you name

Advisory locks are locks on numbers you choose, with meaning only to your code. PostgreSQL stores and arbitrates them, but guards no data. They are the tool for "only one of these may run at a time" where no row exists to lock: a singleton job, a per-customer critical section, an import.

```sql
SELECT pg_try_advisory_xact_lock(4711);   -- true if acquired, false if held by another session
```

```
 pg_try_advisory_xact_lock
---------------------------
 t
(1 row)
```

A second session running the same statement while the first transaction is open gets `f`. The lock releases automatically at the end of the transaction (the `xact` variants). The family:

| Function | Waits? | Released |
|---|---|---|
| `pg_advisory_xact_lock(k)` | yes | at transaction end |
| `pg_try_advisory_xact_lock(k)` | no, returns boolean | at transaction end |
| `pg_advisory_lock(k)` | yes | when explicitly unlocked, or the session ends |
| `pg_try_advisory_lock(k)` | no | same |

Prefer the transaction-level variants. A session-level lock outlives the transaction, and Odoo reuses pooled connections, so a lock taken in one request with `pg_advisory_lock` and not released stays on that pooled connection, blocking other requests for as long as the connection lives, with no sign in `pg_stat_activity`'s transaction age. Always release session-level locks in a `finally`, or avoid them.

Keys are 64-bit integers (or two 32-bit). To lock by a string or a record, hash it: `pg_try_advisory_xact_lock(hashtext('library.import'))`, or combine a namespace and an id: `pg_try_advisory_xact_lock(1001, record_id)` where the first number identifies your feature. Choose keys that cannot collide with other code using advisory locks on the same database (Odoo itself or a third-party module may use them); a distinctive two-number form with your own namespace is the safest.

## Choosing between the tools

| Need | Use |
|---|---|
| change numbers based on current value | `UPDATE ... SET x = x - 1` (atomic) |
| read, decide in Python, then write one row | `SELECT ... FOR UPDATE` on that row |
| distribute work among workers | `FOR UPDATE SKIP LOCKED` |
| do not queue, fail fast | `NOWAIT` or `lock_timeout` |
| rule across several rows or a missing row | unique/partial index; or lock a parent row |
| singleton job with no natural row | `pg_try_advisory_xact_lock` |
| avoid deadlock on many rows | lock in a fixed order (`ORDER BY id FOR UPDATE`) |

## Pitfalls

- **Open transactions holding row locks.** The most common cause of "the system hangs when I edit this record". Look for `idle in transaction` in `pg_stat_activity`.
- **DDL on a busy table with no `lock_timeout`.** It queues behind a long reader and blocks all new queries on the table. Always set a short `lock_timeout` for manual DDL, and check for long transactions before module updates.
- **Locking more than you need.** `FOR UPDATE` on a join locks every table; add `OF`. A broad `FOR UPDATE` on a hot parent row serializes the whole system.
- **Locking in inconsistent order.** The root of nearly all deadlocks. Sort ids first.
- **Using `FOR UPDATE` to guard a row that does not exist.** It locks nothing. Use a unique constraint or lock a parent.
- **Session-level advisory locks through a pool.** They leak across requests. Use `xact` locks.
- **`SKIP LOCKED` for consistent reads.** It returns an arbitrary subset by design.
- **Catching `40001`/`40P01`/`55P03` in application code.** They must propagate to the retry layer, or you must implement an equivalent.
- **Holding locks across slow work.** An HTTP call, an email, or `time.sleep` between the lock and the commit multiplies every other transaction's wait.
- **Killing a backend without looking.** `pg_terminate_backend` rolls the transaction back. Check what the session was doing and ask before using it on production.
- **Assuming `SELECT` never blocks.** It takes `ACCESS SHARE`, which conflicts with `ACCESS EXCLUSIVE`; under a pending DDL even reads wait.

## Try it

Use two psql windows A and B on `handbook_lab`.

1. In A start a transaction and update a book's price without committing. In B try the same update, and while it waits, run the blocking query from this chapter in a third window (or from A). Identify the blocked pid, the blocker, and the wait event. Then roll back in A.

2. Show that `SELECT ... FOR UPDATE NOWAIT` in B fails immediately while A holds the row, and that a plain `SELECT` still works. Then repeat with `SET lock_timeout = '2s'` and a plain `UPDATE`.

3. Create a deadlock between two sessions on books 1 and 2. Read the error and log lines. Then rewrite both sessions so that they cannot deadlock.

4. Build the queue from this chapter with six rows and have two sessions claim two rows each with `SKIP LOCKED`. Show that they get different rows, and what happens to a claim whose session you disconnect before commit.

5. With A holding a transaction that has run `SELECT * FROM books;`, run `ALTER TABLE books ADD COLUMN subtitle varchar;` in B and then a `SELECT` on `books` in a third session. Explain what you see and how `lock_timeout` changes it. Roll back and, if the column was added, drop it.

<details>
<summary>Solution</summary>

1. 
```
A: BEGIN; UPDATE books SET price = 13.00 WHERE id = 1;
B: UPDATE books SET price = 14.00 WHERE id = 1;     -- waits
C: SELECT pid, pg_blocking_pids(pid), wait_event_type, wait_event, left(query, 40)
   FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;
```
B's pid appears with `blocked_by` equal to A's pid, `wait_event_type = Lock`, `wait_event = transactionid`. `ROLLBACK` in A lets B finish.

2. With A holding the row, B's `SELECT * FROM books WHERE id = 1 FOR UPDATE NOWAIT;` fails at once with `could not obtain lock on row in relation "books"`; a plain `SELECT` returns the committed row, because readers do not block. With `SET lock_timeout = '2s';` the `UPDATE` waits two seconds and then fails with `canceling statement due to lock timeout` (SQLSTATE `55P03`).

3. 
```
A: BEGIN; UPDATE books SET price = 1 WHERE id = 1;
B: BEGIN; UPDATE books SET price = 2 WHERE id = 2;
A: UPDATE books SET price = 1 WHERE id = 2;    -- waits
B: UPDATE books SET price = 2 WHERE id = 1;    -- after about 1 s: ERROR: deadlock detected
```
One session is aborted; the other continues. Fix: both sessions begin with `SELECT id FROM books WHERE id IN (1, 2) ORDER BY id FOR UPDATE;` before their updates. Then the second session simply waits for the first to finish and no cycle exists.

4. After `CREATE TABLE notify_queue ...` and the insert, session A's `SELECT ... LIMIT 2 FOR UPDATE SKIP LOCKED` returns ids 1 and 2, and B's, run while A is open, returns 3 and 4. If A disconnects before `COMMIT`, its transaction rolls back, the locks disappear, and a later claim returns ids 1 and 2 again. Clean up with `DROP TABLE notify_queue;`.

5. B's `ALTER TABLE` waits for A's `ACCESS SHARE` lock to be released. The third session's `SELECT` also waits, queueing behind the pending `ALTER`, although A is only reading. That is the lock queue. With `SET lock_timeout = '3s';` in B before the `ALTER`, B fails after three seconds with `canceling statement due to lock timeout`, the queue drains, and the `SELECT` in the third session completes. After `ROLLBACK` in A, retry; if it was added, remove with `ALTER TABLE books DROP COLUMN subtitle;`.

</details>
