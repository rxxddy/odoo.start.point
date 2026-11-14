---
description: The errors you will meet, what causes them, and the fix.
---

# Common errors catalog

Each entry gives the message as you will see it, the cause, and the fix. Message wording varies slightly between versions.

## ORM and Python

### `ValueError: Expected singleton: library.book(1, 2)`

Cause: code written for one record received several (or none) and accessed a field or called a method as if single.
Fix: loop (`for book in self:`), or `ensure_one()` where one record is the contract and let it fail loudly. For zero records, check `if not self`.

### `AttributeError: 'library.book' object has no attribute 'x'`

Cause: the field is not defined on this model, the defining module is not installed in this database, or the code was not reloaded.
Fix: check `env['library.book']._fields`, check the module state, restart or update.

### `KeyError: 'library.book'` / `Object library.book doesn't exist`

Cause: model not in the registry. The module is not installed, not loaded by `--load`/`-u`, or failed to import.
Fix: check the module state and the log at startup for an import error.

### `MissingError: Record does not exist or has been deleted`

Cause: an id outlived its record, often from a cached id in a wizard, a stale browser tab, or an `unlink` earlier in the same flow.
Fix: `exists()` before use, or re-read the ids.

### `RecursionError: maximum recursion depth exceeded`

Cause: a compute reading its own result, parent and child dependencies that loop, or `write` inside `write` without a guard.
Fix: break the cycle; use `@api.depends` with the minimal set; guard with a context key.

### `TypeError: ... missing 1 required positional argument` after a version change

Cause: an overridden method's signature changed upstream.
Fix: read the parent's signature in the target version; use `*args, **kwargs` in overrides that only wrap.

### `Compute method failed to assign library.book(5,).total`

Cause: a compute method did not set the field on every record in `self`, including the branch with no data.
Fix: assign in all branches, or set a default first: `rec.total = 0.0`.

## Validation and access

### `odoo.exceptions.AccessError: You are not allowed to access 'Book' (library.book) records`

Cause: no `ir.model.access` line gives the user's groups the operation. Common in a new model without `ir.model.access.csv`, or with a wrong `model_id:id` name.
Fix: add the access row; update the module; check the CSV loads in the manifest `data` list, in the right order.

### `AccessError: ... due to security restrictions (record rule)`

Cause: a record rule excludes the record for this user, often a company rule.
Fix: inspect Record Rules for the model; test with `env(user=...)`. Use `sudo()` in code only when bypassing is intended and reviewed.

### `ValidationError` from a constraint

Cause: an `@api.constrains` method or a `_sql_constraints` check rejected the data.
Fix: the message is yours; check the values passed. In scripts, catch it per batch (see [Safe bulk scripts](safe-bulk-scripts.md)).

### `UserError: You cannot delete ...`

Cause: an `ondelete` override or `@api.ondelete(at_uninstall=False)` blocks it.
Fix: archive instead of deleting, or satisfy the condition stated in the message.

## Database

### `psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint`

Cause: a duplicate on a unique index. The DETAIL line names the field and value.
Fix: deduplicate before the insert, or use the existing record. When adding a new `_sql_constraints` unique to a table with duplicates, the module update fails; clean the data first.

### `psycopg2.errors.NotNullViolation: null value in column`

Cause: a required field not set, often a new `required=True` on a table that has rows.
Fix: provide a default and, in a migration, fill existing rows before the column constraint applies.

### `psycopg2.errors.ForeignKeyViolation`

Cause: deleting a record that is still referenced with `ondelete='restrict'`, or inserting a bad id.
Fix: remove or reassign dependants first.

### `psycopg2.errors.InFailedSqlTransaction: current transaction is aborted, commands ignored until end of transaction block`

Cause: a previous SQL error in this transaction was caught and ignored, and the code continued.
Fix: wrap the risky statement in `with env.cr.savepoint():`, or roll back. Find the first error in the log; this message is the follow-up.

### `psycopg2.errors.SerializationFailure: could not serialize access due to concurrent update`

Cause: two transactions changed the same row. Odoo retries the request a few times.
Fix: keep transactions short; avoid hot rows such as a global counter; commit batches in scripts.

### `psycopg2.errors.DeadlockDetected`

Cause: two transactions lock rows in opposite order.
Fix: process records in a consistent order (`order="id"`); smaller batches.

### `psycopg2.OperationalError: connection ... too many clients already`

Cause: more connections than PostgreSQL's `max_connections`; too many workers or leaked scripts.
Fix: lower `db_maxconn` and workers, close stray scripts, or raise `max_connections` with care.

## Module loading and views

### `ParseError: while parsing ... ` or `Invalid view definition`

Cause: XML error in a data file; the message names the file and line.
Fix: fix the XML; check field names exist on the model.

### `Element '<xpath expr="...">' cannot be located in parent view`

Cause: an inherited view's locator matches nothing, because the parent changed, the module order is wrong, or the expression is wrong.
Fix: inspect the combined parent arch (see [Developer mode](developer-mode-and-tools.md)); use a more stable anchor such as a field name; add the parent module to `depends`.

### `ValueError: External ID not found in the system: library.view_book_form`

Cause: a reference to an XML ID in a module not in `depends`, or loaded later in the manifest.
Fix: add the dependency, order the data files.

### `ModuleNotFoundError: No module named 'x'` at startup

Cause: a Python dependency is not installed in the virtualenv, or the addon is outside the addons path.
Fix: `pip install` into the right environment; check `addons_path`.

### `Some modules are not loaded, some dependencies or manifest may be missing`

Cause: a module in `depends` is not found.
Fix: check the addons path and spelling in the manifest.

### `Field "x" does not exist in model "y"` (view validation)

Cause: a view references a field not defined, or defined in a module that is not a dependency.
Fix: add the field or the dependency.

## HTTP and RPC

### `werkzeug.exceptions.NotFound` / `404`

Cause: wrong route, wrong database selection when several databases exist, or a missing `--db-filter`.
Fix: set `dbfilter`, or pass the db in the session.

### `odoo.exceptions.AccessDenied` on RPC

Cause: wrong login, expired or revoked API key, or two-factor requirement on the account with a password.
Fix: generate a new key; use it as the password.

### `Object ... doesn't exist` via RPC on a private method

Cause: methods starting with `_` are not callable remotely.
Fix: expose a public method.

### `TypeError: cannot marshal None unless allow_none is enabled`

Cause: XML-RPC with a `None` value.
Fix: `allow_none=True`, or send `False`.

## Workers and limits

### `Worker (pid) CPU time limit (limit_time_cpu) reached` or `Virtual memory limit (limit_memory_hard) reached`

Cause: a request or cron exceeded limits.
Fix: reduce the work per call, chunk it, or run it from the shell. Raise limits only for a measured need.

## Pitfalls when reading this catalog

- A message in the UI may be translated. Search the log, which is in English, rather than the dialog text.
- The last error is often a follow-up. Look for the first `ERROR` of the request.
- A fix that makes the message disappear without explaining the cause usually moves the failure.
