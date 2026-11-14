---
description: "Cron-driven queues and splitting work into batches."
---

# Queues and background work

A request has a few seconds to answer. Anything slower, flakier or larger than that belongs in a queue: a table of work items and a cron that drains it. Odoo has no job-queue framework in core, and for most integrations you do not need one. A model, a state field and `ir.cron` cover it.

## The shape of a queue

Make the work item a record. The record is the queue, the retry counter and the audit trail at once.

```python
from odoo import api, fields, models


class LibraryExportJob(models.Model):
    _name = "library.export.job"
    _description = "Pending export to an external catalogue"
    _order = "id"

    book_id = fields.Many2one("library.book", required=True, ondelete="cascade")
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("failed", "Failed")],
        default="pending", required=True, index=True,
    )
    attempts = fields.Integer(default=0)
    last_error = fields.Text()
    not_before = fields.Datetime(index=True)
```

Producers insert rows and return. They never call the remote system themselves:

```python
def action_publish(self):
    jobs = self.env["library.export.job"].create(
        [{"book_id": b.id} for b in self]
    )
    self.env.ref("library_sync.cron_export_jobs")._trigger()
    return jobs
```

`_trigger()` asks the cron worker to run that cron at the next opportunity instead of waiting for `nextcall`. It creates a row in `ir.cron.trigger` and notifies the cron worker. Pass `at=` a datetime (or a list of them) to schedule a delayed run; precision is about a minute. The cron must exist and be active. The trigger does not bypass the cron's own `active` flag.

## Batch and commit

The consumer takes a bounded slice, processes each item, and commits after each one so a failure at item 40 does not undo items 1 to 39.

```python
@api.model
def _cron_process_jobs(self, batch_size=100):
    jobs = self.search(
        [("state", "=", "pending"),
         "|", ("not_before", "=", False), ("not_before", "<=", fields.Datetime.now())],
        limit=batch_size,
    )
    done = 0
    for job in jobs:
        try:
            with self.env.cr.savepoint():
                job._send()
            job.write({"state": "done", "last_error": False})
        except Exception as exc:
            job.write({
                "attempts": job.attempts + 1,
                "last_error": str(exc),
                "state": "failed" if job.attempts + 1 >= 5 else "pending",
            })
        self.env.cr.commit()
        done += 1
    remaining = self.search_count([("state", "=", "pending")])
    self.env.ref("library_sync.cron_export_jobs")._notify_progress(
        done=done, remaining=remaining
    )
    if remaining:
        self.env.ref("library_sync.cron_export_jobs")._trigger()
```

Three details matter here.

The savepoint isolates the ORM changes of `_send()`, so a half-written failure rolls back while the bookkeeping write of the failed attempt survives. Without it you are left with either a poisoned transaction or a lost error message.

The commit after each item makes progress durable. In a cron it is allowed, and in Odoo 18 the cron runner is designed around it (see Versions). Never commit inside code that can also be called from a user request: the caller loses its atomicity.

`_notify_progress(done=, remaining=)` tells the runner how much is done. If the cron is killed by its time limit, the runner uses this to decide whether to run it again straight away. The loop re-triggers itself when there is more to do, which is how you drain a large backlog without one giant run.

{% hint style="info" %}
The Odoo 18 runner calls a cron job in a loop of at most `MAX_BATCH_PER_CRON_JOB` (10) runs while progress is reported. After `CONSECUTIVE_TIMEOUT_FOR_FAILURE` (3) consecutive timeouts the job is marked as failed and deactivated. Both constants are in `odoo/addons/base/models/ir_cron.py`.
{% endhint %}

## Choosing the batch size

Pick it from the time budget, not from the row count. If the remote call takes 300 ms and the cron limit is a few minutes, 100 items per run is comfortable. Make the size a system parameter or a cron argument so operations can change it without a deploy.

Order by `id` (or by `not_before`) so old work is not starved by new work. Add an index on `state`; a queue table grows with history, and an unindexed `search` on `state` gets slower every month. Delete or archive done rows on a schedule.

## Concurrent runs

Two cron workers do not run the same cron simultaneously, since the runner locks the cron row. But a manual "Run now" from the UI, or a second cron that touches the same table, can overlap. Claim rows explicitly when that matters:

```python
self.env.cr.execute("""
    SELECT id FROM library_export_job
     WHERE state = 'pending'
     ORDER BY id
     LIMIT %s
       FOR UPDATE SKIP LOCKED
""", (batch_size,))
ids = [r[0] for r in self.env.cr.fetchall()]
jobs = self.browse(ids)
```

`SKIP LOCKED` lets each runner take rows nobody else holds. Note that the lock lives until commit, so a commit inside the loop releases the rest of your claimed rows. Claim one batch, process it fully, commit once, or mark rows `running` first in a short transaction.

## Retries and backoff

Count attempts and compute `not_before` from the attempt number:

```python
delay = min(60 * 2 ** job.attempts, 6 * 3600)  # seconds, capped
job.not_before = fields.Datetime.now() + timedelta(seconds=delay)
```

Stop after a fixed number of attempts and leave the row in `failed` with `last_error`. A failed state that someone can see and requeue by hand is worth more than an endless silent retry.

## Pitfalls

* Calling the remote API inside the user's request "just this once". The first time the remote is slow, your workers all block on it.
* Committing in the middle of a method that a test, a wizard or an import also calls. Keep commits in the cron entry point only.
* Passing recordsets or lambdas through the queue. Store ids and plain values; the consumer rereads the current state, which also makes stale jobs harmless.
* A job that fails before its bookkeeping write, for instance on a unique-constraint error in the same transaction. Hence the savepoint.
* A cron with `numbercall`-style assumptions copied from old tutorials. In 18 the field is gone; control repetition by the interval and by `_trigger`.

## Versions

{% hint style="info" %}
16 and 17 have no `_notify_progress` and no automatic re-run loop; the cron body runs once per tick, so keep batches small and use `_trigger` or a short interval to drain. `_trigger` exists since 16. In 18 the runner commits progress between runs. Check `ir_cron.py` of your exact build before relying on the batch loop.
{% endhint %}

## Try it

Read-only, to see what is waiting and what is scheduled:

```sql
SELECT state, count(*) FROM library_export_job GROUP BY state;
SELECT cron_id, call_at FROM ir_cron_trigger ORDER BY call_at;
```
