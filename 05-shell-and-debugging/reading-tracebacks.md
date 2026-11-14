---
description: How to find the real cause in a long stack.
---

# Reading tracebacks

An Odoo traceback can run to fifty frames of framework code. The cause is almost never at the top and rarely at the bottom alone. This chapter gives a method for reading one quickly.

## Anatomy

```
Traceback (most recent call last):
  File "odoo/http.py", line 1989, in _transactioning
    return service_model.retrying(func, env=self.env)
  File "odoo/service/model.py", line 133, in retrying
    result = func()
  ...
  File "odoo/addons/library/models/library_loan.py", line 54, in action_confirm
    loan._check_availability()
  File "odoo/addons/library/models/library_loan.py", line 71, in _check_availability
    if loan.book_id.copies_available < 1:
  File "odoo/fields.py", line 1201, in __get__
    ...
AttributeError: 'library.book' object has no attribute 'copies_available'
```

Python prints the oldest call first and the failing line last. The final line is the exception type and message. Read it first, then go up.

## The method

1. **Read the last line.** Exception class and message. `ValidationError`, `UserError`, `AccessError`, `MissingError` are Odoo's own; `psycopg2.errors.*` are from the database; the rest are Python.
2. **Find the last frame in your code.** Scan upward for the first path under your addons (not `odoo/`, `werkzeug`, `psycopg2`). Framework frames show the route, your frame shows the decision.
3. **Read the frame just below it.** If your line calls into the ORM and it fails, the cause is the data or the arguments you passed.
4. **Ignore the repetitive middle.** `_transactioning`, `retrying`, `call_kw`, `_call_kw_multi`, `dispatch` are plumbing.
5. **Check whether it is the first exception.** Chained errors print "During handling of the above exception, another exception occurred". The cause is the first block, not the last.

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "library_book_isbn_uniq"
DETAIL:  Key (isbn)=(9780000000000) already exists.

During handling of the above exception, another exception occurred:
...
```

Here the database message names the constraint and the value. Everything after is cleanup.

## Frames that tell you something

| Frame | Meaning |
| --- | --- |
| `odoo/models.py` `_compute_field_value` / `fields.py` `__get__` | A computed field raised; the next frame down is its compute method |
| `models.py` `_check_*` / `_validate_fields` | A `@api.constrains` method failed |
| `models.py` `create` / `write` | Your override, or an inherited one, runs between this and the caller |
| `odoo/addons/base/models/ir_qweb.py` | A template failed; the message includes the template and expression |
| `odoo/tools/safe_eval.py` | A domain, server action or automation expression failed |
| `odoo/sql_db.py` `execute` | A query failed; the exception below is a psycopg2 error |

## Client errors versus server errors

The browser dialog shows a trimmed version. The full text is in the server log, and the dialog's "Copy" or "See details" button gives the server-side traceback in recent versions. JavaScript errors appear in the browser console, with source maps only in debug assets mode.

## Reproduce it in the shell

Once you know the record and method, call it directly:

```python
>>> loan = env['library.loan'].browse(12)
>>> loan.action_confirm()
```

You get the same traceback without the HTTP frames, and you can add `breakpoint()` (see [Debugging](debugging-with-pdb-and-debugpy.md)).

## What the exception class suggests

- `KeyError: 'name'` on a dict: missing key in values or a context; print the dict.
- `AttributeError: ... has no attribute`: field not defined on this model, module not loaded in this database, or a typo.
- `TypeError: ... got an unexpected keyword argument`: override signature mismatch after a version change.
- `ValueError: Expected singleton`: `self` holds zero or several records; see the catalog.
- `RecursionError`: a compute depending on itself, or an `@api.onchange` and write loop.
- `MissingError`: the record was deleted since the id was read.
- `psycopg2.errors.SerializationFailure` / `DeadlockDetected`: concurrency; Odoo retries these a few times before giving up.

## Pitfalls

- **Fixing the symptom at the top.** Wrapping the failing line in `try/except` hides the cause.
- **Reading only the dialog.** It omits the chain and the SQL detail.
- **Stale code.** A traceback line number that does not match the file means the server runs older code; restart.
- **Truncated logs.** Reverse proxies and log shippers can cut long tracebacks; read the file on the server.

## Try it

Trigger a unique violation from the shell on a throwaway database and read both blocks of the chained traceback.
