---
description: Savepoints, commits, rollbacks, and what breaks when you mix them.
---

# Transactions in practice

Every Odoo request is one database transaction. It commits when the request ends successfully and rolls back on an exception. Most bugs in this area come from code that works against that model: committing early, swallowing exceptions inside a transaction, or doing irreversible work before the outcome is known.

## The default: one request, one transaction

You do not call `commit()` in normal business code. If a method raises, everything it wrote disappears, including the writes of the methods that called it. That is the feature: a half-finished confirmation never exists.

```python
def action_confirm(self):
    for loan in self:
        loan._reserve_copy()      # writes
        loan._compute_due_date()  # writes
        loan.state = 'active'     # if anything above raised, none of it persists
```

## Savepoints: partial failure inside a transaction

When one failing item must not cancel the rest, wrap it in a savepoint:

```python
def action_send_reminders(self):
    failed = []
    for loan in self:
        try:
            with self.env.cr.savepoint():
                loan._send_reminder()
        except Exception as e:
            _logger.warning("Reminder failed for loan %s: %s", loan.id, e)
            failed.append(loan.id)
    return failed
```

On exception the savepoint rolls back to its start and the transaction continues. By default `savepoint()` flushes pending ORM writes first (`flush=True`), so the rollback boundary is exact, and it invalidates the cache on rollback so you do not read values from the discarded work.

Without the savepoint, a database error (a constraint violation, for example) leaves PostgreSQL in an aborted state: every later statement fails with `current transaction is aborted`. Catching the Python exception is not enough; the savepoint is what restores the transaction.

{% hint style="warning" %}
A savepoint only protects the database. In-memory state, files, and external calls made inside the block are not undone.
{% endhint %}

Catch narrow exceptions when you can. Catching `Exception` around a block that may raise a serialization failure hides it from the retry loop (see [Concurrency](concurrency.md)); re-raise `psycopg2.errors.SerializationFailure`, `LockNotAvailable` and `DeadlockDetected`.

## Savepoints are cheap, but not free

Each savepoint is a round trip and PostgreSQL tracks subtransactions. A savepoint per record on a loop of 100,000 rows is slow. Use one savepoint per chunk and fall back to per-record only for a chunk that failed:

```python
for chunk in split_every(500, self.ids):
    records = self.browse(chunk)
    try:
        with self.env.cr.savepoint():
            records._process()
    except Exception:
        for rec in records:
            try:
                with self.env.cr.savepoint():
                    rec._process()
            except Exception:
                _logger.exception("Record %s failed", rec.id)
```

## Committing manually

Sometimes you must commit: a cron that processes thousands of items and must keep progress, or a job that records an attempt before calling a remote service. Rules:

1. Only in code that owns the transaction: crons, queue jobs, scripts. Never in a method a user can call from the UI, and never in code another module may call inside its own transaction. You would commit their half-finished work.
2. Flush before, and expect the cache to be invalidated after.
3. Commit per unit of work, and make each unit safe to repeat.

```python
def _cron_process(self):
    todo = self.search([('state', '=', 'pending')], limit=200)
    for rec in todo:
        rec._process()
        rec.state = 'done'
        self.env.cr.commit()
```

In tests, `cr.commit()` is neutralized by the test cursor; code that relies on a commit being visible to another cursor needs care. Do not commit in a `@api.constrains`, `create`, `write` or compute.

## After-commit work

External side effects belong after the commit, so a rollback or retry does not repeat them. Use the cursor's postcommit hook:

```python
def action_confirm(self):
    self.state = 'active'
    self.env.cr.postcommit.add(self._notify_remote)
```

In Odoo 18 `cr.postcommit` is a callback list run after a successful commit. Callbacks execute outside the transaction: they cannot write through the same cursor without opening a new one, and an exception in them cannot undo the commit. For anything that must not be lost, write a job row in the transaction and let a cron or queue process it; that survives a crash between commit and callback.

{% hint style="info" %}
Versions: `cr.savepoint()` exists in 16, 17 and 18. `cr.postcommit` and `cr.precommit` are available in 16 and later as callback hooks; in 18 they are `Callbacks` objects, so register with `.add(func)` and pass data with `.data`. Check the signature in your installed `odoo/sql_db.py` before using the data dictionary.
{% endhint %}

## Pitfalls

- **try/except without savepoint.** After a SQL error the cursor is unusable. Always pair a catch of a database error with a savepoint.
- **Email or HTTP inside the transaction.** If the commit later fails or the request is retried, the message goes out twice. Queue it, or send post-commit.
- **Commit inside a loop over self.** After `commit()` the records in `self` still exist, but cached values are stale and locks are gone.
- **Assuming rollback undoes sequences.** `ir.sequence` values drawn with `nextval` are not rolled back. Gaps are normal.
- **Mixing cursors.** A second cursor opened with `registry.cursor()` does not see uncommitted data from the first, and can block waiting for a lock the first holds. This is a classic self-deadlock.

## Try it

Read-only: watch transaction state from another shell while a long action runs.

```sql
SELECT pid, state, xact_start, now() - xact_start AS age, left(query, 80)
  FROM pg_stat_activity
 WHERE datname = current_database() AND state <> 'idle'
 ORDER BY xact_start;
```

Rows stuck in `idle in transaction` point to code that opened a transaction and then waited on something slow.
