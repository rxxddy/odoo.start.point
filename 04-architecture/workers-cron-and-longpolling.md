---
description: The process model and why it matters for your code.
---

# Workers, cron, and longpolling

Odoo runs in one of two process models, and the choice changes what your code may assume: whether a request can run for ten minutes, whether a cron job shares memory with the web server, and how a browser learns that something changed. Development usually runs in threaded mode; production should not. Behaviour that works on a laptop can fail the first week on a server.

## Threaded mode

With `--workers=0` (the default), one process serves HTTP requests on a pool of threads and runs cron jobs on `--max-cron-threads` additional threads. Characteristics:

- Easy to debug; `--dev=reload`, breakpoints, and the Werkzeug debugger work.
- All threads share one Python process, so one CPU-bound request competes for the GIL with everything else.
- `--limit-memory-*` and `--limit-time-*` are not enforced. A runaway request runs forever.
- Live-update traffic (chat, bus notifications) is served by the same process on the same port.

## Multi-process mode

With `--workers=N` where N is greater than 0, Odoo starts a prefork server:

- N HTTP worker processes, each handling one request at a time.
- `--max-cron-threads` cron worker processes (the option sets the number of cron workers in this mode).
- A separate process for live updates (gevent), listening on its own port (default 8072).

Each worker is killed and replaced if it exceeds its limits:

| Option | Effect |
|---|---|
| `--limit-memory-soft` | Worker finishes its current request, then is recycled. |
| `--limit-memory-hard` | Worker is killed immediately. |
| `--limit-time-cpu` | CPU seconds per request. |
| `--limit-time-real` | Wall-clock seconds per request. |
| `--limit-time-real-cron` | Wall-clock limit for cron workers. Defaults to `-1`, meaning it falls back to `--limit-time-real`; `0` removes the limit (verified in Odoo 18). |
| `--limit-request` | Requests served before the worker is recycled. |

Sizing is rough arithmetic. A worker process uses a few hundred MB under load. A common starting rule is workers around `(CPU cores * 2) + 1` for web traffic, memory budget `workers * soft limit` plus the gevent process plus PostgreSQL, and `--db_maxconn` large enough for workers and cron combined. Measure under real traffic; the rule is a place to start, not an answer.

{% hint style="info" %}
Versions: the gevent process serves `/websocket` in 16 and later for the bus on Odoo 17 and 18; on 16, the bus used HTTP long polling at `/longpolling/poll` with the same separate process. Port naming also changed (`longpolling_port` to `gevent_port`). The deployment shape stays the same: a second port that the reverse proxy must route to.
{% endhint %}

## Why your code must care

A request that exceeds `limit-time-real` is killed with no chance to clean up; the transaction rolls back. This applies to:

- Imports triggered from a button.
- "Recompute everything" actions on large tables.
- Reports that aggregate a year of data.

Move long work out of the request: into a cron job processing in batches, or into a queued job that the request creates and returns immediately.

A worker serves one request at a time. A handler that calls an external service with a 30-second timeout occupies a worker for that time. With four workers, four slow calls make the whole site stall while the CPU is idle.

## Cron jobs

A scheduled action is a record of `ir.cron` with a model, a method, an interval, and a number of calls. Define it in data:

```xml
<odoo>
  <record id="cron_library_overdue" model="ir.cron">
    <field name="name">Library: flag overdue loans</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="state">code</field>
    <field name="code">model._cron_flag_overdue()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
    <field name="active" eval="True"/>
  </record>
</odoo>
```

In 16 you could also set `numbercall` and `doall`. Neither appears in `ir_cron.py` of Odoo 18 (verified); check 17 yourself if you migrate through it. The job runs as the user in the `user_id` field (a superuser-equivalent internal user by default).

How the scheduler works:

1. A cron worker wakes every minute (or on a trigger, see below), lists `ir_cron` rows whose `nextcall` is due.
2. It locks one row with `SELECT ... FOR NO KEY UPDATE SKIP LOCKED` so only one worker runs a given job, even across processes and servers.
3. It runs the job in its own transaction and commits.
4. It updates `nextcall` and `lastcall`.

Failure semantics: an exception rolls back that run and is logged; the job stays active and runs again at the next interval. In recent versions a job that keeps failing may be deactivated after a threshold (in 17 and later, repeated failures can disable the job; verify the thresholds in `ir_cron.py` of your branch).

### Writing a safe cron method

```python
@api.model
def _cron_flag_overdue(self, batch_size=500):
    domain = [('state', '=', 'out'), ('due_date', '<', fields.Date.today())]
    loans = self.search(domain, limit=batch_size)
    loans.write({'state': 'overdue'})
    # tell the scheduler there is more to do (17 and later)
    remaining = self.search_count(domain)
    if remaining and hasattr(self.env['ir.cron'], '_trigger'):
        self.env.ref('library.cron_library_overdue')._trigger()
```

Process a bounded batch, commit the progress, and ask to be run again. From 16 `ir.cron._trigger()` schedules an additional run at a given time (the `ir.cron.trigger` model). Large single-run jobs hit the real-time limit and roll back completely, losing all progress.

Cron also commits per job, not per record. In 17 and later the helper `self.env['ir.cron']._commit_progress()` (mentioned in newer documentation) exists for progress tracking; do not assume it on 16.

### Cron on non-production copies

A database restored from production carries its cron jobs, outgoing mail servers, and external webhook configuration. Starting a staging server on it sends real mail and calls real services. Before first start of a copy:

```sql
update ir_cron set active = false;
update ir_mail_server set active = false;
```

Platforms that manage staging do this for you; self-hosted copies do not. Read the first query as a SELECT with the same WHERE to see what is active before changing anything.

## Longpolling, websocket, and the bus

The browser needs to learn about events (new chat message, notification, a record changed by someone else) without polling constantly. The bus module keeps rows in `bus_bus` and a long-lived connection to the gevent process delivers them.

- The gevent process holds many idle connections cheaply; HTTP workers cannot (one request per worker).
- It uses its own database connections, so it appears as extra connections to PostgreSQL.
- The reverse proxy must route the live endpoint to port 8072 and the rest to 8069:

```nginx
location /websocket { proxy_pass http://127.0.0.1:8072; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }
location /longpolling { proxy_pass http://127.0.0.1:8072; }
location / { proxy_pass http://127.0.0.1:8069; }
```

Use only the location that matches your version; keep `proxy_read_timeout` generous for it.

Sending a notification from code:

```python
self.env['bus.bus']._sendone(user.partner_id, 'library/loan_overdue', {'loan_id': loan.id})
```

The message is written in the transaction and delivered after commit. In Odoo 18 the signature is `_sendone(self, target, notification_type, message)` (verified in `addons/bus/models/bus.py`); older branches used `sendone`.

## Pitfalls

{% hint style="warning" %}
In multi-process mode, live updates do not work unless the proxy routes the live endpoint to the gevent port. Symptom: chat and notifications silent, nothing in the Odoo log, everything else fine.
{% endhint %}

- **Workers set, no proxy.** Workers without `--proxy-mode` and a proxy that sets the right headers cause wrong URLs and lost client IPs.
- **Cron in dev against shared database.** Two servers, two cron runners on the same data. Locks prevent the same job running twice at once, but not twice in succession on the dev side with half-finished code.
- **Global variables across requests.** Each worker has its own memory. A module-level cache filled in one worker is invisible to the next; use `@tools.ormcache` and the registry invalidation, or the database.
- **Time limits too low for a deploy-time update.** Update commands (`-u`) run in a separate process without worker limits; do not run updates through the web server.
- **`limit-memory-hard` too tight.** Workers killed mid-request look like random 502s from the proxy. Check kernel logs and Odoo logs for "Virtual memory limit reached".
- **Slow crons delaying others.** With one cron worker, a ten-minute job delays every job due behind it.

## Try it

```bash
# how many workers do we actually have, and who is listening where?
ps -eo pid,ppid,rss,cmd | grep odoo-bin
ss -ltnp | grep -E ":(8069|8072)"
# which crons are due, read-only
psql -d dev -c "select cron_name, nextcall, active from ir_cron order by nextcall limit 10;"
```
