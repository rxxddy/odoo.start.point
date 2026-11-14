---
description: "How Odoo finds and runs pre, post and end migration scripts, which versions trigger them, and how to write them so a rerun is harmless."
---

# Migration scripts

When a module's version in the manifest goes up and the module is updated (`-u`), Odoo can run your Python scripts before the module's data is loaded, after it, and after all modules are updated. This is where you rename columns, backfill new fields and clean data that the ORM cannot convert by itself. The mechanism below is read from `odoo/modules/migration.py` (18.0; the 20 tree has the same logic).

## Where scripts live

```
library/
  __manifest__.py              # 'version': '18.0.1.2.0'
  migrations/
    1.1/
      pre-rename-isbn.py
      post-fill-shelf.py
      end-cleanup.py
    18.0.1.2.0/
      post-recompute-fees.py
    0.0.0/
      end-invariants.py
```

Rules from `MigrationManager`:

- Scripts are looked up in `<module>/migrations/<version>/` and `<module>/upgrades/<version>/`, and in the `odoo.upgrade` package paths under a folder named after the module.
- The folder name must match the version pattern, otherwise Odoo logs `Invalid version for upgrade script` and ignores it. A folder named `tests` is skipped.
- A file's stage is its prefix: `pre-` runs before the module's data files are loaded, `post-` after them, `end-` after **all** modules have been updated. Files in one stage run in file-name order.
- Files without these prefixes, and anything not ending in `.py`, are ignored.

## Which versions trigger a script

For a module being updated, a folder `V` runs when the installed version is lower than `V` and `V` is lower than or equal to the new manifest version:

```
installed < V <= current
```

- A folder with two or three parts such as `1.1` is a "majorless" version: Odoo prepends the server series (`18.0.1.1`) for ordering but compares only the module part, so a `1.1` script does not run again when you move the same module from series 17 to series 18.
- A folder with the full server version (`18.0.1.2.0`) is processed only by that server series.
- `0.0.0` runs on **any** version change. In the `pre` stage its scripts run first; in `post` and `end` they run last.

Scripts run only for modules that are being **updated**. A fresh install runs none of them, so initial data belongs in the module's normal data files.

## The function

```python
# library/migrations/1.1/pre-rename-isbn.py
def migrate(cr, version):
    # `version` is the installed version before the update, or '' if unknown.
    cr.execute("SELECT 1 FROM information_schema.columns "
               "WHERE table_name = 'library_book' AND column_name = 'isbn_code'")
    if cr.fetchone():
        cr.execute("ALTER TABLE library_book RENAME COLUMN isbn_code TO isbn")
```

The loader checks the signature: the parameters must be exactly `(cr, version)`, or the underscore variants (`_cr`, `_version`), positional. Anything else raises `TypeError`, and a file without `migrate` raises `AttributeError` naming the file. Each file is imported as `odoo.upgrade.<module>.<version>.<name>` and logged as `Running upgrade [>1.1] pre-rename-isbn` (pre), `[1.1>]` (post) or `[$1.1]` (end).

## Which stage for which job

| Job | Stage | Why |
| --- | --- | --- |
| Rename a column or table the new model expects under a new name | `pre` | the ORM creates missing columns during the update and would make an empty duplicate |
| Drop a constraint or index that blocks the new schema | `pre` | the new definition cannot load while the old one stands |
| Backfill a new stored field from old data | `post` | the column exists only after the module loaded |
| Fix data using new ORM methods | `post` | models and fields are available |
| Cleanup that depends on other modules being updated | `end` | all modules have finished |
| An invariant to re-check on every upgrade | `0.0.0/end-...` | runs last, on any change |

## Writing scripts that can run twice

An upgrade is rehearsed several times, and a failed run is retried. Write every script so a second run changes nothing:

```python
def migrate(cr, version):
    cr.execute("""
        UPDATE library_loan
           SET state = 'returned'
         WHERE state = 'closed'
    """)
```

`UPDATE ... WHERE state = 'closed'` is safe to repeat. `ALTER TABLE ... RENAME` is not, which is why the example above checks `information_schema` first. Read-only counterpart first:

```sql
SELECT state, count(*) FROM library_loan GROUP BY state ORDER BY 2 DESC;
```

Rules:

1. **SQL for volume, the ORM for logic.** A table of a million rows is `UPDATE` in `pre`, not a loop in `post`. When you need ORM behaviour, build the environment: `env = api.Environment(cr, SUPERUSER_ID, {})`.
2. **Never commit.** The loader owns the transaction. A script that calls `cr.commit()` breaks rollback of a failed upgrade.
3. **Be explicit about data you cannot convert.** Log it (`_logger.warning`) or raise, rather than skipping rows silently.
4. **Do not import models in `pre`.** The registry for the new code is not built yet.
5. **Keep scripts small and named after the job**: `pre-rename-isbn.py`, not `pre-fixes.py`.

## Testing

Restore a copy of production, install the old version of your module, bump the manifest version, run the update with the script and compare:

```bash
odoo-bin -d upgrade_test -u library --stop-after-init --log-level=info
```

Then run the same command again. The second run must log the scripts and change nothing. Check the log for `Running upgrade` lines to confirm which scripts fired. If a script did not run, compare the installed version (`SELECT latest_version FROM ir_module_module WHERE name = 'library'`) with the folder name and the manifest version using the `installed < V <= current` rule.

## Pitfalls

- A folder named `1.1.0` when the manifest says `18.0.1.2.0`: it is lower than the installed version on later runs and never fires.
- Forgetting to bump the manifest `version`. Without a higher version the module updates but no script folder qualifies.
- Putting initial data in a script. Fresh installs skip scripts.
- Renaming a model or a field without a `pre` script, which leaves the old column and the data in it behind.
- Importing the module's own models in `pre`.
- Calling `cr.commit()`.

## Try it

1. Create `migrations/1.1/pre-rename-isbn.py` as above and bump the version.
2. Run the update twice and compare the logs.
3. Add `migrations/0.0.0/end-log.py` that logs one line, and see when it fires.

<details>

<summary>Solution notes</summary>

1. The first run logs `Running upgrade [>1.1] pre-rename-isbn` and renames the column; the second sees no `isbn_code` and does nothing.
2. The second run does not log the `1.1` script at all if the installed version is already at or above it.
3. The `0.0.0` script fires on every version change, last in the `end` stage.

</details>
