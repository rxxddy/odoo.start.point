---
description: ir.cron records, intervals, and running jobs safely.
---

# Scheduled actions

`ir.cron` records run a server action at an interval. They are the standard way to do periodic work: nightly cleanups, sync jobs, reminders. The scheduler picks due jobs, locks each one, runs it as a given user, and moves `nextcall` forward.

## Defining one

```xml
<odoo noupdate="1">
  <record id="cron_library_overdue" model="ir.cron">
    <field name="name">Library: remind overdue loans</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="state">code</field>
    <field name="code">model._cron_remind_overdue()</field>
    <field name="user_id" ref="base.user_root"/>
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
    <field name="nextcall" eval="(datetime.now() + timedelta(days=1)).replace(hour=3, minute=0, second=0)"/>
    <field name="priority">5</field>
    <field name="active" eval="True"/>
  </record>
</odoo>
```

`ir.cron` inherits from `ir.actions.server`, so it has `state`, `code`, `model_id`. Fields verified in the 18 source: `interval_number`, `interval_type` (`minutes`, `hours`, `days`, `weeks`, `months`), `nextcall`, `priority` (0 is highest, default 5), `active`, `user_id`.

The code calls a model method; keep the method in the model:

```python
@api.model
def _cron_remind_overdue(self):
    loans = self.search([("state", "=", "out"), ("due_date", "<", fields.Date.today())])
    template = self.env.ref("library.mail_template_loan_due")
    for loan in loans:
        template.send_mail(loan.id, force_send=False)
```

Name the method with a leading underscore so it is not callable over RPC by users.

## How the scheduler runs

A cron worker (or the main process with threads in dev) queries jobs where `active` and `nextcall <= now()`, ordered by failure count then priority. Each job is locked with `SELECT ... FOR UPDATE SKIP LOCKED`, so two workers never run the same job. After the run, `nextcall` advances by the interval, repeated until it lies in the future: a job that was down for a week does not run seven times, it runs once (missed runs are skipped).

The job runs under `user_id`, with that user's access rights and company. `base.user_root` (OdooBot) bypasses access rules; a normal user does not. Choose deliberately. Multi-company: the cron sees the user's allowed companies only.

## Long jobs: batch and commit

A cron runs in one transaction by default, with a time limit set by `limit_time_real_cron` (falls back to `limit_time_real`). Processing a million rows in one go risks a timeout and a total rollback. Process in batches and let the framework help:

```python
@api.model
def _cron_sync(self, batch=200):
    todo = self.search([("synced", "=", False)], limit=batch)
    for rec in todo:
        rec._sync_one()
    if len(todo) == batch:
        self.env.ref("library.cron_library_sync")._trigger()
```

`_trigger()` schedules an extra run soon, which is how you continue a batch without waiting a full interval. Odoo 18 also provides `self.env["ir.cron"]._notify_progress(done=..., remaining=...)`, which reports how much of the job is done and how much is left (verified in `ir_cron.py`); there is no `_commit_progress` helper in 18.

## Pitfalls

- `noupdate` omitted: every module update resets `nextcall` or overwrites the interval an admin tuned.
- `nextcall` default evaluated at install time: all your crons fire together at the same minute. Stagger them.
- Cron on a copy of production: a restored database sends real mail and calls real APIs. Odoo's neutralization script disables crons and outgoing mail; run it on every non-production copy.
- Doing work in the method that depends on `request`, the web session or the current user's company: none exists.
- Swallowing exceptions: a failing cron that logs nothing is invisible. Let it raise; failures are counted and, after repeated failures, Odoo deactivates the job and notifies.
- Running slow jobs at the same time as backups or peak hours.

## Versions

{% hint style="danger" %}
Up to 17 an `ir.cron` had `numbercall` (-1 for unlimited) and `doall` (catch up missed runs). Both are gone in 18; a data file that still sets them fails on load because the fields no longer exist. A one-shot job is now created and deactivated by the code, or triggered with `_trigger()`. Verified: `numbercall` does not appear in the 18 `ir_cron.py`.
{% endhint %}

## Try it

See what is scheduled and when, read-only:

```sql
select cron_name, nextcall, interval_number, interval_type, active, priority from ir_cron order by nextcall;
```

Run one job by hand from the UI: Settings, Technical, Scheduled Actions, open the record and press "Run Manually" (developer mode).
