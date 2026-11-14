---
description: "Branches, commits, and moving changes between environments."
---

# Git workflow for modules

A module repository has an unusual constraint: the code is only half of the deployed state. The database holds data loaded from your XML, and an upgrade script may have to transform it. A good workflow treats the branch, the version bump and the migration as one unit.

## Repository layout

Either one repository per module group (the usual choice for a customer project) or one monorepo with modules at the top level, added to `addons_path`. Keep third-party modules in separate repositories or submodules, pinned to a commit, never copied into yours.

```
repo/
  library/
  library_loan_extras/
  .gitignore         # *.pyc, __pycache__, .venv, *.po~ , filestore never
  .pre-commit-config.yaml
  README.md
```

Do not commit the database, the filestore, `odoo.conf` with secrets, or exported production data. Add them to `.gitignore` before the first commit, because removing them from history later is painful.

## Branches

Name the long-lived branches after the Odoo version when you maintain more than one: `16.0`, `17.0`, `18.0`. Odoo.sh requires that anyway: the branch you push is built into its own environment. Short-lived feature branches come off the version branch and return via a pull request:

```
18.0
 └─ feature/loan-overdue-cron
 └─ fix/loan-due-date-timezone
```

Rules that pay for themselves:

- One concern per branch and per pull request.
- Rebase the feature branch on the version branch before merging if your team prefers linear history; otherwise merge commits. Pick one and stick to it.
- Never force-push a branch other people use. On a private feature branch it is fine.
- Forward-port fixes across version branches with `git cherry-pick -x`, so the commit message records where it came from.

## Commits

Use a short imperative subject with a module tag, as the Odoo project does:

```
[FIX] library: compute due date in the user timezone

The cron compared naive UTC datetimes with a date, so loans due
today were flagged overdue after 22:00 local time.
```

Common tags: `[ADD]`, `[IMP]`, `[FIX]`, `[REF]`, `[REM]`, `[MIG]`, `[I18N]`. The body explains why, not what; the diff already says what. Reference the ticket in the body or the footer.

Keep commits atomic enough to revert. A commit that changes a model, its view, its security and its tests together is fine; a commit that also reformats five other files is not.

## What a module change must carry

1. **Version bump** in `__manifest__.py`, following `<odoo_version>.<major>.<minor>.<patch>` (for example `18.0.1.2.0`). Bump it whenever a migration script is needed.
2. **Migration script** when you rename a field or model, change a stored computed value, or change data semantics: `migrations/18.0.1.2.0/pre-migrate.py` and `post-migrate.py`, each with `def migrate(cr, version):`. Pre scripts run before the ORM loads the new definitions (rename columns here); post scripts run after (recompute, backfill).
3. **Tests** for the behaviour.
4. **Data files** loaded by the manifest, with `noupdate` chosen deliberately.
5. **Translations** if strings changed (`.pot` export can wait until release).

```python
# migrations/18.0.1.2.0/pre-migrate.py
def migrate(cr, version):
    if not version:
        return
    cr.execute("ALTER TABLE library_loan RENAME COLUMN due TO due_date")
```

Guard with `if not version` because the script also runs on fresh installs in some tooling. Test the migration on a restored copy of production, not on an empty database.

{% hint style="info" %}
Versions: migration folders and the `pre-`, `post-`, `end-` script names work the same in 16, 17 and 18. The upgrade only runs when the manifest version is higher than the installed one.
{% endhint %}

## Moving between environments

The path is feature branch, staging (a copy of production data), then production. On Odoo.sh: push the feature branch to get a development build, merge to the staging branch to build on a copy of production data, merge to production once staging passes.

Before every production deployment:

1. Upgrade a restored copy of the production database with the exact merged code, using `-u your_module --stop-after-init`.
2. Run the test suite for changed modules on that copy.
3. Click through the changed screens as a normal user, not only as admin.
4. Take a backup and note the commit hash you deploy.

Deploying is `git pull` plus `-u module` plus a service restart; on a multi-worker server, restart all workers so that none runs old code against a new schema. For rollbacks, you need the backup: Odoo upgrades are not reversible by checking out the old commit, because the schema and data have moved on.

## Pre-commit

A small `.pre-commit-config.yaml` with `ruff`, `pylint-odoo` and a trailing-whitespace check removes style debates from review. Run it in CI as well, so a missing local install does not skip the checks.

## Pitfalls

- **Editing already-merged migration scripts.** Environments that ran the old version will not rerun it. Add a new version with a new script instead.
- **Forgetting the version bump.** The code is deployed, but `-u` sees the same version and your pre-migrate script never runs.
- **Secrets in the history.** Rotate, then clean; a deleted file still lives in older commits.
- **Dev data committed as `data/`.** Demo or test records in `data/` land in production. Put them in `demo/`.
- **Long-running branches.** Odoo modules touch the same models; a month-old branch produces painful conflicts in views. Merge small and often.

## Try it

Show what would change in the manifest and migrations between your branch and the version branch, read-only:

```bash
git diff --stat 18.0...HEAD -- '*/__manifest__.py' '*/migrations/*'
```
