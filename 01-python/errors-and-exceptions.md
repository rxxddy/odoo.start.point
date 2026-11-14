---
description: try/except, raising, custom exceptions, and what Odoo does with them.
---

# Errors and exceptions

Things go wrong: a file is missing, a user types text where a number is expected, a loan is returned twice, a database constraint rejects a row. Python reports these with **exceptions**, objects that interrupt normal execution and travel up the call stack until something handles them. Odoo builds its whole user-facing error system on top of that: some exceptions become a friendly dialog, some become a log entry and a generic error page, and all of them cause the current database transaction to roll back. This chapter covers how to catch and raise exceptions correctly, how to define your own, how to clean up reliably, and how the Odoo exception classes map onto these ideas.

## What an exception is

An exception is raised when code cannot continue. If nothing handles it, the program stops and prints a traceback (see [Setup and running code](setup-and-running-code.md) for reading one).

```pycon
>>> int("abc")
Traceback (most recent call last):
    ...
ValueError: invalid literal for int() with base 10: 'abc'
>>> [1, 2, 3][5]
Traceback (most recent call last):
    ...
IndexError: list index out of range
>>> {"a": 1}["b"]
Traceback (most recent call last):
    ...
KeyError: 'b'
>>> 1 / 0
Traceback (most recent call last):
    ...
ZeroDivisionError: division by zero
>>> None.title
Traceback (most recent call last):
    ...
AttributeError: 'NoneType' object has no attribute 'title'
>>> "a" + 1
Traceback (most recent call last):
    ...
TypeError: can only concatenate str (not "int") to str
```

The common built-in exceptions and what they mean:

| Exception | Typical cause |
|---|---|
| `ValueError` | Right type, unacceptable value (`int("abc")`) |
| `TypeError` | Wrong type for the operation (`"a" + 1`, wrong argument count) |
| `KeyError` | Missing dict key |
| `IndexError` | Sequence position out of range |
| `AttributeError` | Object has no such attribute or method |
| `NameError` | Name not defined |
| `ZeroDivisionError` | Division or modulo by zero |
| `FileNotFoundError`, `PermissionError` | File system problems (subclasses of `OSError`) |
| `StopIteration` | An iterator has no more items |
| `RecursionError` | Call stack too deep |
| `ImportError` / `ModuleNotFoundError` | An import failed |

Exceptions form a class hierarchy. `KeyError` and `IndexError` are both subclasses of `LookupError`. `FileNotFoundError` is a subclass of `OSError`. Everything you normally catch derives from `Exception`. You can see the chain:

```pycon
>>> KeyError.__mro__[:4]
(<class 'KeyError'>, <class 'LookupError'>, <class 'Exception'>, <class 'BaseException'>)
```

`BaseException` also covers `KeyboardInterrupt` and `SystemExit`, which you should almost never catch.

## try / except

```pycon
>>> def parse_qty(text):
...     try:
...         return int(text)
...     except ValueError:
...         return None
...
>>> parse_qty("12"), parse_qty("twelve")
(12, None)
```

Code in the `try` block runs normally. If it raises an exception matching an `except` clause, the rest of the `try` block is skipped and the handler runs. If no clause matches, the exception continues upward.

### Catch specific exceptions

Name the exception you expect. A bare `except:` or `except Exception:` catches bugs you did not anticipate and hides them:

```pycon
>>> def bad(text):
...     try:
...         return int(text) + undefined_name      # a real bug
...     except Exception:
...         return None
...
>>> bad("5")
>>> bad("x")
```

Both calls return `None`, and the programming error (`NameError`) is invisible. A narrow `except ValueError` would have let the `NameError` surface during the first test.

Handle several types with a tuple, or with separate clauses:

```pycon
>>> def get_pages(book):
...     try:
...         return int(book["pages"])
...     except KeyError:
...         return 0
...     except (TypeError, ValueError):
...         return -1
...
>>> get_pages({"pages": "612"}), get_pages({}), get_pages({"pages": "n/a"}), get_pages({"pages": None})
(612, 0, -1, -1)
```

Clauses are checked in order and the first match wins. Put specific classes before general ones: a clause for `LookupError` placed before one for `KeyError` would swallow it.

### Getting the exception object

```pycon
>>> try:
...     int("abc")
... except ValueError as exc:
...     print(type(exc).__name__, "-", exc)
...     print(exc.args)
ValueError - invalid literal for int() with base 10: 'abc'
("invalid literal for int() with base 10: 'abc'",)
```

`exc` exists only inside the handler. Python deletes the name when the block ends, to avoid reference cycles.

### else and finally

`else` runs when the `try` block raised nothing. `finally` runs always, whether the block succeeded, raised, returned, or was left via `break`:

```pycon
>>> def read_number(text):
...     try:
...         value = int(text)
...     except ValueError:
...         print("bad input")
...         return None
...     else:
...         print("parsed")
...         return value
...     finally:
...         print("cleanup")
...
>>> read_number("7")
parsed
cleanup
7
>>> read_number("x")
bad input
cleanup
```

Keep the `try` block as small as possible: only the statements whose failure you intend to handle. Put follow-up code in `else`. Then an exception from unrelated code is not caught by accident.

```python
# Too broad: a ValueError from process() is mistaken for a parse error
try:
    value = int(text)
    process(value)
except ValueError:
    ...

# Precise
try:
    value = int(text)
except ValueError:
    ...
else:
    process(value)
```

`finally` is the place for cleanup that must happen regardless: releasing a lock, closing a connection, restoring a state. For files and similar resources, `with` is better.

## Resources and `with`

A **context manager** guarantees setup and teardown. Files are the standard example:

```python
with open("loans.txt", encoding="utf-8") as handle:
    data = handle.read()
# the file is closed here, even if read() raised
```

This is shorthand for a `try/finally` that closes the file. Compare the manual version:

```python
handle = open("loans.txt", encoding="utf-8")
try:
    data = handle.read()
finally:
    handle.close()
```

Prefer `with`. Several context managers can share one statement:

```python
with open("in.csv", encoding="utf-8") as src, open("out.csv", "w", encoding="utf-8") as dst:
    for line in src:
        dst.write(line.upper())
```

### Writing your own

Any class with `__enter__` and `__exit__` works, and `contextlib.contextmanager` turns a generator into one (see [Comprehensions and generators](comprehensions-and-generators.md)):

```pycon
>>> from contextlib import contextmanager
>>> @contextmanager
... def section(name):
...     print(f"enter {name}")
...     try:
...         yield name.upper()
...     finally:
...         print(f"exit {name}")
...
>>> with section("db") as label:
...     print("working in", label)
enter db
working in DB
exit db
>>> with section("db"):
...     raise RuntimeError("fail")
Traceback (most recent call last):
    ...
RuntimeError: fail
```

The `exit db` line printed before the traceback in the second case (output order is clearer in a real terminal, because the traceback goes to the error stream). The teardown ran even though the body failed.

Odoo uses context managers for several things, including `with self.env.cr.savepoint():` for partial rollbacks (shown below). The idea is always: enter sets something up, exit undoes it even on failure. `contextlib.suppress(SomeError)` is a compact "ignore this exception" form:

```pycon
>>> from contextlib import suppress
>>> with suppress(FileNotFoundError):
...     open("/definitely/not/here.txt")
...
```

## Raising exceptions

Use `raise` when your code detects a condition it cannot handle:

```pycon
>>> def return_book(loan):
...     if loan["state"] == "returned":
...         raise ValueError("loan already returned")
...     loan["state"] = "returned"
...     return loan
...
>>> loan = {"state": "open"}
>>> return_book(loan)
{'state': 'returned'}
>>> return_book(loan)
Traceback (most recent call last):
    ...
ValueError: loan already returned
```

Raise early and loudly. A function that receives data it cannot work with should say so at the entry point, not several calls deeper where the symptom is far from the cause.

### Re-raising

Inside an `except` block, a bare `raise` re-raises the exception currently being handled, with its original traceback. Use it to add logging or cleanup and then let the error continue:

```pycon
>>> def risky():
...     raise KeyError("missing")
...
>>> try:
...     try:
...         risky()
...     except KeyError:
...         print("log it")
...         raise
... except KeyError as exc:
...     print("outer caught", exc)
log it
outer caught 'missing'
```

Do not write `raise exc` for this; the bare `raise` is what preserves the traceback faithfully.

### Chaining: `raise ... from ...`

When you catch a low-level error and raise a higher-level one, chain them so the original cause stays visible:

```pycon
>>> def load_limit(raw):
...     try:
...         return int(raw)
...     except ValueError as exc:
...         raise RuntimeError(f"bad loan limit {raw!r}") from exc
...
>>> try:
...     load_limit("many")
... except RuntimeError as exc:
...     print(exc, "| caused by:", repr(exc.__cause__))
bad loan limit 'many' | caused by: ValueError("invalid literal for int() with base 10: 'many'")
```

Without `from`, raising a new exception inside an `except` still records the original as context (`__context__`), and the traceback reads "During handling of the above exception, another exception occurred". `raise ... from None` suppresses the chain when the original is only noise.

### Assertions

`assert condition, message` raises `AssertionError` when the condition is false:

```pycon
>>> assert 1 + 1 == 2, "arithmetic broke"
>>> assert 1 + 1 == 3, "arithmetic broke"
Traceback (most recent call last):
    ...
AssertionError: arithmetic broke
```

Assertions state internal assumptions (things that are bugs if false) and are removed when Python runs with `-O`. Never use `assert` to validate user input or business rules, because those checks would disappear under optimisation. Use them in tests and for programmer-error checks.

## Defining your own exceptions

Subclass `Exception` (or a more specific built-in) when callers need to tell your errors apart from others:

```pycon
>>> class LoanError(Exception):
...     """Base class for loan problems."""
...
>>> class AlreadyReturned(LoanError):
...     def __init__(self, loan_id):
...         super().__init__(f"loan {loan_id} was already returned")
...         self.loan_id = loan_id
...
>>> class LimitExceeded(LoanError):
...     pass
...
>>> def check_in(loan_id, returned):
...     if returned:
...         raise AlreadyReturned(loan_id)
...
>>> try:
...     check_in(7, returned=True)
... except LoanError as exc:
...     print(type(exc).__name__, "->", exc, "| id:", exc.loan_id)
AlreadyReturned -> loan 7 was already returned | id: 7
```

A shared base class (`LoanError`) lets a caller catch "any loan problem" in one clause, or a specific one when it cares. Keep hierarchies shallow, and put useful data on the exception as attributes, not only in the message string.

## EAFP versus LBYL

Two styles for handling uncertain situations:

- **LBYL**, "look before you leap": check first, then act (`if key in d: value = d[key]`).
- **EAFP**, "easier to ask forgiveness than permission": act, and handle the exception (`try: value = d[key] except KeyError`).

Python code leans to EAFP where checking is as costly as acting, or where checking leaves a window for the situation to change in between (a file existing when checked, gone when opened). LBYL is better when the check is cheap and the failure is common, because raising and catching exceptions costs more than a conditional. For dictionaries, `d.get(key, default)` is usually clearer than either.

```pycon
>>> data = {"a": 1}
>>> data.get("b", 0)
0
```

## Logging errors

Printing is not logging. The `logging` module records messages with a level and a source name, and the server decides where they go. Odoo modules conventionally declare a module-level logger:

```python
import logging

_logger = logging.getLogger(__name__)
```

`__name__` is the dotted module path, so log lines identify where they came from. Use levels deliberately:

| Level | Use |
|---|---|
| `debug` | detail for developers, off in production |
| `info` | normal milestones ("imported 120 rows") |
| `warning` | something unexpected that was handled |
| `error` | an operation failed |
| `exception` | like `error`, from an `except` block: adds the traceback |

```pycon
>>> import logging, sys
>>> logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True)
>>> _logger = logging.getLogger("library.loan")
>>> _logger.info("imported %d rows from %s", 120, "loans.csv")
INFO library.loan: imported 120 rows from loans.csv
>>> try:
...     1 / 0
... except ZeroDivisionError:
...     _logger.exception("computing ratio failed")        # doctest: +ELLIPSIS
ERROR library.loan: computing ratio failed
Traceback (most recent call last):
  File ...
ZeroDivisionError: division by zero
```

Note the form: `_logger.info("imported %d rows from %s", 120, "loans.csv")`. The arguments are passed separately and the logging system formats the message **only if the record is emitted**. An f-string would format the text always, even for suppressed levels, and loses the ability to group identical messages by template. Use `%s` placeholders with arguments.

`_logger.exception(...)` inside an `except` block records the message plus the full traceback. It is the right call in a handler that does not re-raise, so the failure leaves a trace. Swallowing an exception with `pass` and no log is how problems vanish for months.

## Odoo's exceptions

Odoo defines its own exception classes in `odoo.exceptions`. The ones you will use constantly:

| Class | Meaning | What the user sees |
|---|---|---|
| `UserError` | An operation is not allowed or cannot proceed, for a reason the user can act on | A warning dialog with your message |
| `ValidationError` | Data violates a business rule (typically raised from `@api.constrains`) | A validation dialog with your message |
| `AccessError` | The user lacks permission | An access error dialog |
| `MissingError` | A record no longer exists | A "record does not exist" dialog |

`ValidationError` is a subclass of `UserError` in recent versions, so catching `UserError` also catches it. All of these carry a human message as their first argument. Raise one with a translatable message:

```python
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LibraryLoan(models.Model):
    _name = "library.loan"
    _description = "Loan"

    date_start = fields.Date()
    date_end = fields.Date()
    state = fields.Selection(
        [("open", "Open"), ("returned", "Returned")], default="open"
    )

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for loan in self:
            if loan.date_start and loan.date_end and loan.date_end < loan.date_start:
                raise ValidationError(_("The end date cannot be before the start date."))

    def action_return(self):
        for loan in self:
            if loan.state == "returned":
                raise UserError(_("Loan %s was already returned.") % loan.display_name)
            loan.state = "returned"
```

Points to notice:

- The message goes through `_()` so it can be translated, and the value is inserted **after** translation with `%`, matching the rule from [Values and types](values-and-types.md).
- The check loops over `self`, because the method may run on several records.
- `UserError` is for the user, and its text should say what happened and, where possible, what to do. An exception raised with a message such as `"Error"` is useless in a dialog.

### What happens when an exception escapes

A request to Odoo runs inside a database transaction. The behaviour is the same for every exception type:

1. The exception propagates up to the framework's request handler.
2. The transaction is **rolled back**. Every change made earlier in that request (writes, creates, deletes) disappears from the database.
3. The error is reported to the client. `UserError` and its relatives become a dialog with the message. Other exceptions become a generic server error; in the server log, you get the full traceback.

Rollback is why raising from inside `write` or `create` is a safe way to reject an operation: nothing partial persists. It is also why you must not swallow an exception you need to reach the framework. If you catch a `ValidationError` to "handle it" and continue, the request proceeds and commits everything done so far.

Caught exceptions and the database interact in one important way. If an SQL statement fails (a constraint violation, for instance), PostgreSQL marks the current transaction as aborted, and all further statements fail until a rollback, **even if your Python code caught the exception**. To attempt a risky database operation and continue on failure, wrap it in a savepoint:

```python
try:
    with self.env.cr.savepoint():
        self.create(vals)          # may violate a constraint
except Exception:
    _logger.warning("could not create record from %s", vals, exc_info=True)
```

The savepoint rolls back only the work inside the `with` block, leaving the outer transaction usable. Without it, the next query raises an error about a transaction that is already aborted, and the real cause hides behind it. The PostgreSQL part explains savepoints and transactions in depth.

Not every kind of exception represents a failure. In a **cron job** or batch import, you often want to process the remaining items when one fails. That means catching exceptions per item, logging them with the item's identifier, and continuing, with a savepoint around each item so one failure does not abort the others.

### Choosing which exception to raise

- A **user did something not allowed** or the data is wrong from the user's point of view: `UserError` or `ValidationError`, with a clear translated message.
- A **programming error**, a state that should be impossible: let a normal Python exception (`ValueError`, `AssertionError`) propagate. It becomes a server error with a traceback, which is correct for a bug you need to see.
- An **external system failure** (HTTP timeout, missing file): log the technical details, and raise a `UserError` with a message the user can act on ("Could not reach the shipping service. Try again in a few minutes."), chaining the original with `from exc` so the log keeps the cause.

```python
import requests

def fetch_rate(self, url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        _logger.error("rate service failed: %s", exc)
        raise UserError(_("The rate service is not reachable. Try again later.")) from exc
    return response.json()
```

Set a `timeout` on every network call; without it a hung server blocks the worker.

## Pitfalls

- **Bare `except:` and `except Exception: pass`.** They hide bugs and make failures invisible. Catch specific classes and log what you catch.
- **Catching too much code.** A large `try` block catches errors from unrelated lines. Keep it to the lines you expect to fail.
- **Swallowing exceptions that the framework needs.** In Odoo, catching a `UserError` and continuing lets the transaction commit partial work.
- **Continuing after a failed SQL statement without a savepoint.** The transaction is aborted. Subsequent queries fail with an error that hides the original.
- **Assertions for validation.** `assert` is stripped under `-O` and is not for user errors.
- **Losing the cause.** Raising a new exception inside `except` without `from exc` obscures the original. Use `from exc`, or `from None` deliberately.
- **`raise exc` instead of `raise`.** Rewrites the traceback to point at the re-raise. Use a bare `raise`.
- **Using exceptions for ordinary flow in hot loops.** Raising and catching is much slower than a conditional. Prefer a check when the failure is common.
- **Unhelpful messages.** `raise UserError("Error")` tells the user nothing. Say what is wrong and what to do, in a translatable string.
- **Formatting before translation.** `_(f"Loan {name} failed")` creates a new untranslatable text per value. Use `_("Loan %s failed") % name`.
- **f-strings in log calls.** `_logger.info(f"...")` formats always and cannot be grouped. Use `%s` arguments.
- **Retrying without limits.** A loop that retries on failure forever blocks a worker. Always bound attempts and wait between them.
- **Missing timeouts.** Network calls without `timeout=` can hang a worker indefinitely.
- **Writing to disk or calling external services before `super()` returns.** Those effects are not rolled back with the transaction. Do them after the database work succeeds.
- **Catching `KeyboardInterrupt` or `SystemExit`.** `except BaseException` interferes with shutdown. Catch `Exception` at most.

## Try it

1. Write `safe_int(text, default=None)` that returns `int(text)` or the default, catching only the right exceptions (consider `None` input too). Test it with `"12"`, `"x"`, `""`, `None`, and `" 7 "`.
2. Define `LoanError`, `AlreadyReturned(LoanError)` with a `loan_id` attribute, and `NotFound(LoanError)`. Write `return_loan(loans, loan_id)` that raises them as appropriate, and a caller that handles `AlreadyReturned` separately from the general `LoanError`.
3. Write a context manager `timer(label)` with `contextlib.contextmanager` that records elapsed time in a list even when the body raises. Demonstrate both paths.
4. Write `process_all(items, handler)` that calls `handler(item)` for every item, collects failures as `(item, message)` pairs without stopping, and returns `(successes, failures)`. Log each failure using `%s` style arguments.
5. Explain why this Odoo-style method is unsafe, and rewrite it: it creates a record inside a `try/except Exception: pass`, then continues querying the database.

<details>
<summary>Solution</summary>

1.

```pycon
>>> def safe_int(text, default=None):
...     try:
...         return int(text)
...     except (TypeError, ValueError):
...         return default
...
>>> [safe_int(v) for v in ["12", "x", "", None, " 7 "]]
[12, None, None, None, 7]
```

`int(None)` raises `TypeError`, and `int("x")` raises `ValueError`.

2.

```pycon
>>> class LoanError(Exception):
...     pass
...
>>> class AlreadyReturned(LoanError):
...     def __init__(self, loan_id):
...         super().__init__(f"loan {loan_id} already returned")
...         self.loan_id = loan_id
...
>>> class NotFound(LoanError):
...     pass
...
>>> def return_loan(loans, loan_id):
...     loan = loans.get(loan_id)
...     if loan is None:
...         raise NotFound(f"no loan {loan_id}")
...     if loan["returned"]:
...         raise AlreadyReturned(loan_id)
...     loan["returned"] = True
...
>>> loans = {1: {"returned": False}, 2: {"returned": True}}
>>> for lid in (1, 2, 3):
...     try:
...         return_loan(loans, lid)
...         print(lid, "ok")
...     except AlreadyReturned as exc:
...         print(lid, "already", exc.loan_id)
...     except LoanError as exc:
...         print(lid, "error:", exc)
1 ok
2 already 2
3 error: no loan 3
```

3.

```pycon
>>> import time
>>> from contextlib import contextmanager
>>> timings = []
>>> @contextmanager
... def timer(label):
...     start = time.perf_counter()
...     try:
...         yield
...     finally:
...         timings.append((label, time.perf_counter() - start))
...
>>> with timer("ok"):
...     pass
>>> try:
...     with timer("fail"):
...         raise RuntimeError("x")
... except RuntimeError:
...     pass
>>> [label for label, _ in timings]
['ok', 'fail']
```

4.

```pycon
>>> import logging
>>> _logger = logging.getLogger("library.import")
>>> def process_all(items, handler):
...     successes, failures = [], []
...     for item in items:
...         try:
...             handler(item)
...         except Exception as exc:
...             _logger.warning("item %s failed: %s", item, exc)
...             failures.append((item, str(exc)))
...         else:
...             successes.append(item)
...     return successes, failures
...
>>> process_all([1, 0, 2], lambda n: 10 / n)
WARNING library.import: item 0 failed: division by zero
([1, 2], [(0, 'division by zero')])
```

Catching `Exception` here is deliberate: the purpose is isolation of per-item failures, the failure is logged, and the information is returned. In Odoo you would add a savepoint around each item if the handler writes to the database.

5. After a failed SQL statement the PostgreSQL transaction is aborted, so the following queries fail with an unrelated error, and `pass` hides why. Also, any partial work stays pending. Rewrite:

```python
try:
    with self.env.cr.savepoint():
        record = self.env["library.loan"].create(vals)
except Exception:
    _logger.warning("loan creation failed for %s", vals, exc_info=True)
    record = self.env["library.loan"]
```

The savepoint rolls back just the failed creation, the log records the cause with a traceback, and the code continues with an empty recordset as a defined fallback.

</details>
