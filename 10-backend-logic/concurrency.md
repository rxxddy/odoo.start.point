---
description: Race conditions, row locks, advisory locks, and idempotency.
---

# Concurrency

Odoo runs several worker processes against one PostgreSQL database. Two requests will eventually touch the same record at the same moment, and code that is correct in a single thread will then lose updates, double-process records, or deadlock. This chapter covers the tools for that: the retry loop Odoo gives you for free, row locks, advisory locks, and idempotency keys.

## What Odoo already does for you

Each request runs in its own transaction with the default `REPEATABLE READ` isolation. When two transactions modify the same row, PostgreSQL aborts one with a serialization failure. In `odoo/service/model.py`, `retrying()` catches `LockNotAvailable`, `SerializationFailure` and `DeadlockDetected`, rolls back, and runs the request again, up to `MAX_TRIES_ON_CONCURRENCY_FAILURE = 5` times, sleeping a random time of up to `2 ** tryno` seconds between attempts.

This applies to RPC calls and to HTTP controllers dispatched through the normal request path. It has a direct consequence for your code: **a request can run more than once.** Anything with a side effect outside the database (an HTTP call, an email sent directly, a file written) is repeated if the transaction is retried.

```python
# Wrong: the retry sends the request twice if the commit later fails
def action_confirm(self):
    self._push_to_remote()      # irreversible
    self.state = 'confirmed'    # may raise a serialization failure at commit
```

Do the database work first, and trigger the external effect after commit (see [Transactions in practice](transactions-in-practice.md)).

{% hint style="info" %}
Retries happen on a fresh cursor and a fresh environment. Do not keep records, caches or flags from the failed attempt. Do not catch `psycopg2.errors.SerializationFailure` yourself unless you re-raise it; swallowing it hides the failure from `retrying()` and leaves the transaction aborted.
{% endhint %}

## Never coordinate with time.sleep

`time.sleep()` holds a worker, which is a scarce resource, and it proves nothing: the other transaction may take longer than your guess, or not have started yet. Coordination must come from the database. Use a lock, a unique constraint, or a state column changed atomically. If you need to wait for something external, schedule a later run with a cron or a queued job instead of blocking.

## Row locks: SELECT ... FOR UPDATE

When you read a value, decide, and write it back, another transaction can change the value in between. Take a lock on the row before reading:

```python
def _next_ticket_number(self):
    self.env.cr.execute(
        "SELECT id FROM library_book WHERE id = %s FOR UPDATE", [self.id]
    )
    # The row is locked until commit or rollback.
    self.invalidate_recordset()      # drop values read before the lock
    return self.last_ticket + 1
```

Two details matter. The ORM cache may hold values read before the lock, so invalidate after acquiring it. And pending ORM writes are not in the database yet; call `self.env.flush_all()` (or `flush_model`) before raw SQL that depends on them.

Use `FOR UPDATE NOWAIT` to fail immediately with `LockNotAvailable` (which `retrying()` handles) instead of queueing behind the other transaction.

### SKIP LOCKED for work queues

When several workers take items from a pool, you do not want them to wait for each other. Skip what is already taken:

```python
def _claim_batch(self, limit=50):
    self.env.cr.execute("""
        SELECT id FROM library_loan
         WHERE state = 'to_notify'
         ORDER BY id
         LIMIT %s
           FOR UPDATE SKIP LOCKED
    """, [limit])
    ids = [row[0] for row in self.env.cr.fetchall()]
    return self.browse(ids)
```

Each worker gets a disjoint set. Process and mark the records in the same transaction so the lock covers the whole unit of work. If a record fails, use a savepoint so one bad row does not discard the batch.

## Advisory locks

A row lock needs a row. When you need to serialize something that is not a record (an import of one file, a sync of one remote account, a cron that must never overlap with itself), use an advisory lock:

```python
def _try_lock(self, key):
    self.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
    return self.env.cr.fetchone()[0]

def sync_account(self):
    key = hash_key('library.sync', self.id)   # a stable 64-bit integer
    if not self._try_lock(key):
        return False                          # another worker has it, skip
    ... # do the work
```

The `_xact_` variant releases the lock automatically at the end of the transaction. Prefer it: session-level advisory locks outlive the transaction, survive in pooled connections, and leak if you forget to unlock. Derive the integer with a stable function (not Python's `hash()`, which is randomized per process). A 64-bit value from a SHA-1 prefix is enough.

## Idempotency keys

Locks prevent simultaneous duplicates. They do not prevent a client retrying five minutes later. For anything that creates records on behalf of an external caller, store a key and enforce it with a unique constraint:

```python
class LibraryLoan(models.Model):
    _inherit = 'library.loan'

    request_key = fields.Char(index=True, copy=False)

    _sql_constraints = [
        ('request_key_uniq', 'unique(request_key)', 'Duplicate request.'),
    ]

    @api.model
    def create_idempotent(self, key, vals):
        existing = self.search([('request_key', '=', key)], limit=1)
        if existing:
            return existing
        try:
            with self.env.cr.savepoint():
                return self.create({**vals, 'request_key': key})
        except psycopg2.errors.UniqueViolation:
            return self.search([('request_key', '=', key)], limit=1)
```

The search is the fast path; the constraint is the guarantee. The savepoint keeps the outer transaction usable after the violation.

## Pitfalls

- **Lock ordering.** Two transactions locking the same rows in different order deadlock. Always lock in a fixed order (`ORDER BY id`).
- **Long transactions with locks.** A lock held while you call a remote service blocks everyone else for the duration of the call. Lock late, release early.
- **Read, then write in Python.** `record.counter += 1` is a lost-update race. Use a locked read or `UPDATE ... SET counter = counter + 1`.
- **Searching for "does it exist" without a constraint.** Two requests both see nothing and both create. Only a unique constraint closes the gap.
- **Locks across commits.** A cron that commits in batches releases its transaction locks at each commit. Re-acquire for each batch.

{% hint style="info" %}
Versions: the retry loop and the constants are the same in 16, 17 and 18. In 16 and 17 the code lives in `odoo/service/model.py` as `retrying()` under the same name; check `MAX_TRIES_ON_CONCURRENCY_FAILURE` in your installed copy before relying on the number.
{% endhint %}

## Try it

Read-only: see who holds locks while you reproduce a race in two shells.

```sql
SELECT l.pid, l.locktype, l.mode, l.granted, a.query
  FROM pg_locks l JOIN pg_stat_activity a USING (pid)
 WHERE a.datname = current_database() AND l.locktype IN ('transactionid', 'advisory', 'tuple');
```
