---
description: Branches, builds, staging, logs, and the shell on a hosted platform.
---

# Odoo.sh and deployment

Whether you deploy to a hosted platform or to your own server, the shape of the job is the same: code arrives from version control, an environment builds from it, modules are updated against a database, and processes restart. This chapter describes the hosted platform's model (branches, builds, three stages) and then the checklist for a self-managed server. Where the platform's behaviour is documented by the vendor and not by the framework source, details can change; confirm against the vendor documentation.

## The hosted model

On Odoo.sh, a Git repository is the source of truth and every branch can become a running environment ("build"). Branches have one of three stages:

| Stage | Database | Purpose |
|---|---|---|
| Development | Fresh, demo or restored data, destroyed on rebuild | Try a change, run tests |
| Staging | A copy of production data, mail and crons neutralised | Validate a change on real data |
| Production | The real database | Serving users |

Pushing to a branch triggers a build: the platform checks out the commit, installs requirements, creates or updates the database, and starts the server. On a development branch the build installs modules on an empty database and runs tests. On a staging branch the database is a restored copy of production on which the changed modules are updated, which is the closest rehearsal of an upgrade you get. Production builds update the existing database in place after a push.

A build has states you will read in the build list: green (succeeded), yellow (succeeded with warnings in the log), red (failed). A failed update on production leaves the previous build still serving; read the failure before pushing again.

## Repository conventions

The platform scans the repository for modules; top-level directories with a manifest are modules, and submodules are supported for third-party code. Add a `requirements.txt` at the root for Python dependencies; it is installed during the build, not on a running instance. Keep the module layout described in [Project layout and addons path](project-layout-and-addons-path.md), and pin third-party submodules to a commit so a build is reproducible.

Branch naming follows the series: a branch whose name the platform recognises with a version prefix is built for that Odoo version. Check the vendor documentation for the exact rule before branching.

## Day-to-day workflow

1. Create a feature branch from production. It builds as development.
2. Push commits; each push is a build with logs and test results.
3. Open the web client of that build, the shell, and the logs in the platform interface.
4. Merge to a staging branch, or promote the feature branch to staging; validate on production data.
5. Merge to production. The platform updates the modules that changed (it detects them from the diff and manifest versions) and restarts.

{% hint style="warning" %}
The platform updates only the modules whose files changed. If you rely on a data record that changed in a module you did not touch, it will not be updated. Bumping the manifest `version` of the affected module makes the intent explicit and triggers migrations.
{% endhint %}

## Logs and shell

Each build has log files and a browser-based shell attached to the instance. The useful logs: the server log (`odoo.log`), the install/update log from the build, the PostgreSQL log, and the HTTP access log. Search with `grep` in the shell; logs rotate, so a failure from three days ago may be gone.

The shell gives you `odoo-bin shell` against the build's database, same as locally. On production, the shell is not a place to experiment: anything you commit there is production data.

## Backups and restores

Production databases are backed up automatically; the platform keeps several daily backups and lets you restore into a staging branch or download them. Rules that follow from the model:

- Restore to a staging branch to test migrations, not directly onto production.
- A restored database on staging carries production data. Respect privacy rules for that environment.
- Test a restore periodically. A backup you have not restored is a hope, not a backup.

## Self-managed deployment checklist

For a server you run yourself, build the same discipline by hand.

1. **Package.** A tagged commit of your repositories and the exact Odoo checkout commit. Deploy artifacts, not "git pull on the server".
2. **Install dependencies** in a versioned virtualenv from `requirements.txt`.
3. **Back up** the database and the filestore, and check that the dump is readable.
4. **Update on a copy first.** Restore the production dump to a scratch database, run `odoo-bin -d copy -u module --stop-after-init`, read the log, and run smoke tests. Time it: the duration is your downtime estimate.
5. **Maintenance window.** Stop the service, or route traffic to a maintenance page.
6. **Update production**: `odoo-bin -c prod.conf -d prod -u module1,module2 --stop-after-init`. The update runs without worker limits.
7. **Start the service** under systemd; check logs for warnings that were not there before.
8. **Verify** with a scripted login and a few model reads.
9. **Rollback plan:** the previous code tag plus the pre-update dump. Rolling back code without the dump rarely works, since the schema has changed.

A minimal systemd unit:

```ini
[Unit]
Description=Odoo
After=postgresql.service

[Service]
User=odoo
ExecStart=/srv/odoo/venv/bin/python /srv/odoo/18.0/odoo-bin -c /etc/odoo/odoo.conf
Restart=on-failure
KillMode=mixed

[Install]
WantedBy=multi-user.target
```

Behind a reverse proxy, set `--proxy-mode`, bind HTTP to localhost, enable `--workers`, and route the live-update port as described in [Workers, cron, and longpolling](workers-cron-and-longpolling.md). Set `list_db = False` and a strict `dbfilter`, and put the master password (`admin_passwd`) in a file readable only by the service account.

## Pitfalls

- **Pushing to production with a red staging build.** The same update will fail on production. Do not.
- **Migrations that work on demo data only.** Development builds use small data. Test on the staging copy, where volumes, nulls, and odd historic records exist.
- **Forgetting the filestore** when copying an instance by hand: the database restores, images and attachments are gone.
- **Staging sending real mail.** On the platform, outgoing mail is blocked on non-production builds; on your own staging, disable `ir.mail_server` and crons yourself.
- **Long updates.** A recompute of a stored field on a large table can hold locks for many minutes. Estimate on the staging copy; consider a migration script that fills the column in batches.
- **Version drift.** Production on one commit of the framework, staging on another. Pin the Odoo commit as well as your own.
- **Uncommitted shell changes.** Fixing data in a production shell without recording the script in the repository makes the next environment differ. Put one-off fixes in a migration script.

## Try it

```bash
# rehearse an update on a restored copy (self-managed)
createdb -T template0 copy && pg_restore -d copy prod.dump
odoo-bin -c prod.conf -d copy -u library --stop-after-init --log-level=info 2>&1 | tee update.log
grep -E "WARNING|ERROR|CRITICAL" update.log | sort | uniq -c | sort -rn | head
```
