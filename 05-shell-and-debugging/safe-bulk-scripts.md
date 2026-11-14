---
description: "Dry runs, batching, savepoints, and scripts you can trust on production data."
---

# Safe bulk scripts

A script that touches thousands of records fails in the middle, or succeeds and is wrong. The patterns here make both survivable: look before you write, write in bounded batches, isolate failures, and leave a record of what changed.

## The order of work

1. **Read-only counterpart first.** Count and list what the script would touch.
2. **Dry run on a copy** of production.
3. **Backup**, then run on production in batches, with a log.
4. **Verify** with a query that proves the end state.

```python
domain = [("state", "=", "draft"), ("create_date", "<", "2025-01-01")]
Loan = env["library.loan"]
print(Loan.search_count(domain))
print(Loan.search(domain, limit=10).read(["name", "state", "create_date"]))
```

## Skeleton

```python
import logging
import os

_logger = logging.getLogger("script.archive_old_loans")
APPLY = os.environ.get("APPLY") == "1"
BATCH = 500

Loan = env["library.loan"].with_context(tracking_disable=True, mail_notrack=True)
ids = Loan.search([("state", "=", "draft"), ("create_date", "<", "2025-01-01")], order="id").ids
_logger.info("to process: %d (apply=%s)", len(ids), APPLY)

done = failed = 0
for start in range(0, len(ids), BATCH):
    chunk = Loan.browse(ids[start:start + BATCH])
    try:
        with env.cr.savepoint():
            chunk.write({"active": False})
        if APPLY:
            env.cr.commit()
        else:
            env.cr.rollback()
        done += len(chunk)
    except Exception:
        _logger.exception("batch starting at %d failed, ids %s", start, chunk.ids[:5])
        env.cr.rollback()
        failed += len(chunk)
    env.invalidate_all()
    _logger.info("progress %d/%d (failed %d)", start + len(chunk), len(ids), failed)

_logger.info("finished: done=%d failed=%d", done, failed)
```

Why each part exists:

- **Ids first, then `browse` per chunk.** The id list is fixed up front, so the script does not chase a domain that changes as it writes, and memory stays bounded.
- **Batches with a commit** release locks and make a stop recoverable: the next run's domain no longer matches processed records.
- **`savepoint()`** lets a failed statement roll back without poisoning the whole transaction. After a SQL error the transaction is aborted until you roll back to a savepoint.
- **`invalidate_all()` between batches** keeps the cache from growing without limit.
- **`tracking_disable` and `mail_notrack`** stop chatter messages and mail for every record.

## Isolating a bad record

When a batch fails, retry it record by record to find the offender instead of losing the batch:

```python
def process(records):
    try:
        with env.cr.savepoint():
            records.write({"active": False})
    except Exception:
        if len(records) == 1:
            _logger.error("record %s failed", records.id, exc_info=True)
            return
        mid = len(records) // 2
        process(records[:mid])
        process(records[mid:])
```

This bisects: a thousand-record batch with one bad record costs about twenty extra writes, not a thousand.

## Idempotency

A script must be safe to run twice. Build the domain so processed records drop out, or mark them:

```python
Loan.search([("x_migrated", "=", False)])
```

If you cannot, compute the target value from the current data, so a second run writes the same value.

## Record what changed

Before a destructive step, save the old values:

```python
import csv
with open("old_values.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "name", "state"])
    for r in Loan.browse(ids).read(["name", "state"]):
        w.writerow([r["id"], r["name"], r["state"]])
```

That file is your undo. Keep it with the run log. Store it outside the repository when it contains personal data.

## Choosing ORM or SQL

| | ORM `write` | SQL `UPDATE` |
| --- | --- | --- |
| Constraints, computes, overrides | Run | Skipped |
| Speed on 1M rows | Slow | Fast |
| Access rules | Bypassed as superuser | Bypassed |
| Cache | Consistent | Stale, call `invalidate_all()` |

Use the ORM by default. Use SQL when the logic is a plain value assignment and the volume makes the ORM impractical, then recompute dependants explicitly and check constraints yourself. Always run the SELECT with the same WHERE first:

```sql
SELECT count(*) FROM library_loan WHERE state = 'draft' AND create_date < '2025-01-01';
UPDATE library_loan SET active = false WHERE state = 'draft' AND create_date < '2025-01-01';
```

## Guardrails

- Refuse to run without an explicit target: `assert os.environ.get("ODOO_DB")`, or compare `env.cr.dbname` to the expected name.
- Cap the damage: `assert len(ids) < 10000, "unexpectedly many records"`.
- Run outside business hours when locks matter; check `pg_stat_activity` for waiters.
- Stop switch: check for a file such as `/tmp/stop_script` per batch and exit cleanly.

## Pitfalls

- **One giant transaction.** Memory grows, locks last, one error discards hours.
- **Commit per record.** Needlessly slow; batch.
- **Savepoint misuse.** A savepoint protects the database, not the ORM cache; invalidate after a failure.
- **Writes that trigger side effects.** Mail, webhooks, and automations fire on `write`. Check automation rules and disable tracking.
- **Search with `limit` and no order.** Pages shift while you write. Fix the ids first.
- **Dry run that differs from the real run.** Keep one code path and switch only the commit.
