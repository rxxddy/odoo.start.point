---
description: "Move a real database to a new Odoo version, safely."
---

# Upgrading a database

A database upgrade is a data project, not a deployment. The goal is to prove on a copy that the upgraded database behaves, and only then repeat on production in a maintenance window.

## Plan

1. Inventory: which modules are installed, which are custom, which are community.
2. Port every custom module to the target version (see [Upgrading a module](upgrading-a-module.md)).
3. Restore a copy of production on a test server.
4. Run the upgrade on the copy; fix; restore the copy again; repeat until a clean run needs no manual steps.
5. Have business users test their flows on the final copy.
6. Freeze production, take a backup, run the same scripted steps, validate.

Repeating from a fresh restore each time is the point: a run that needs a manual fix in the middle is not yet reproducible.

## Read-only inventory

```sql
SELECT name, state, latest_version FROM ir_module_module
WHERE state = 'installed' ORDER BY name;
```

```sql
SELECT relname, n_live_tup FROM pg_stat_user_tables
ORDER BY n_live_tup DESC LIMIT 20;
```

The second query finds the tables where a recompute or a loop script will take hours.

## Run the upgrade

Odoo's own modules are migrated by the upgrade service or the open-source `OpenUpgrade` project, depending on the version path; custom modules by your scripts. Whichever tool moves the standard schema, finish with your modules:

```bash
pg_restore -d lib_test backup.dump
odoo-bin -d lib_test -u all --stop-after-init --log-level=info 2>&1 | tee upgrade.log
```

Jumping several series is done step by step (16 to 17 to 18), not in one run, because each series' migration assumes the previous one's schema.

## After the run

```bash
grep -cE "ERROR|CRITICAL" upgrade.log
```

Then check data, not just logs:

```sql
SELECT count(*) FROM library_book WHERE isbn13 IS NULL;
SELECT model, count(*) FROM ir_model_data WHERE module = 'library' GROUP BY model;
```

Open the main menus as a normal user, not as admin: access rules and record rules are where an upgrade quietly hides records.

## Things that break only on real data

- Views stored in the database (customised from the UI) that point at removed fields. List them: `SELECT id, name FROM ir_ui_view WHERE arch_updated`.
- Server actions and automations containing Python or domains in the old syntax.
- Mail templates using removed fields in QWeb.
- Reports with custom paper formats.
- Attachments: confirm the filestore is copied with the database dump, or every file is gone.

{% hint style="danger" %}
Never run `-u all` on production for the first time. Always restore a copy, and never point a copy at the production outgoing mail server or crons; neutralise them first.
{% endhint %}

## Pitfalls

- Testing with a small anonymised database that lacks the data shapes that break (null parents, archived records, multi-company).
- A copy that still sends email or calls external APIs through live cron jobs.
- Forgetting that dumps do not include the filestore.
- No rollback plan. The rollback is the backup plus the old server, so keep both until sign-off.
