---
description: "Logger names, levels, and reading logs when something is wrong."
---

# Logging

Odoo logs through Python's `logging` module, one logger per Python module name. Knowing the logger names lets you turn on exactly the detail you need, and knowing the log format lets you find the line that matters in a file of a hundred thousand.

## The log line

```
2026-01-15 10:22:31,412 4821 INFO mydb odoo.addons.library.models.library_book: Loaded 12 books
```

Fields: timestamp, process id, level, database, logger name, message. The logger name tells you where the line came from: `odoo.modules.loading` for module loading, `odoo.sql_db` for SQL, `odoo.http` for requests, `odoo.addons.<module>...` for addon code. `werkzeug` logs access lines.

## Levels and switches

```bash
./odoo-bin -d mydb --log-level=debug                       # everything, very noisy
./odoo-bin -d mydb --log-level=warn
./odoo-bin -d mydb --log-handler=odoo.addons.library:DEBUG  # one namespace
./odoo-bin -d mydb --log-handler=:INFO --log-handler=odoo.sql_db:DEBUG
./odoo-bin -d mydb --logfile=/var/log/odoo/odoo.log
```

`--log-handler` takes `LOGGER:LEVEL`, repeatable, and an empty logger name means the root. Specific values: `--log-level=debug_sql` logs queries, `debug_rpc` and `debug_rpc_answer` log RPC calls and their answers, `test` is used for test runs. These shortcuts set a preset combination of handlers; check `--help` in your version for the list.

The same options go in the config file as `log_level` and `log_handler = odoo.addons.library:DEBUG`.

## Logging from your code

```python
import logging
_logger = logging.getLogger(__name__)

class LibraryBook(models.Model):
    _inherit = "library.book"

    def action_import(self):
        _logger.info("importing %d books", len(self))
        try:
            self._do_import()
        except Exception:
            _logger.exception("import failed for books %s", self.ids)
            raise
```

Rules that matter:

- Use lazy formatting (`"%s", value`), not f-strings. With f-strings the string is built even when the level is disabled.
- `_logger.exception(...)` inside an `except` block adds the traceback. Outside one it adds nothing useful.
- Do not log secrets, tokens, or full customer records. Log ids.
- `_logger.warning` for things an operator should read, `info` for milestones, `debug` for developer detail. A module that logs per record at `info` makes the log unreadable.

## Reading a log

```bash
# Errors with a few lines before them
grep -n -B2 -A25 " ERROR " /var/log/odoo/odoo.log | less

# One database, one time window
grep "mydb" odoo.log | awk '$2 >= "10:20" && $2 <= "10:25"'

# Follow live
tail -f odoo.log | grep --line-buffered -E "ERROR|CRITICAL|WARNING"

# Slow requests and slow queries
grep -E "took|slow" odoo.log
```

When requests run in parallel, lines from different workers interleave. Follow one request by its process id (the second field) rather than reading top to bottom.

## Useful loggers

| Logger | Why |
| --- | --- |
| `odoo.sql_db` at DEBUG | Every query, see [Inspecting SQL](inspecting-sql.md) |
| `odoo.modules.loading` | Why a module failed to load |
| `odoo.modules.registry` | Registry setup, missing dependencies |
| `odoo.models.unlink` | What cascades on delete |
| `odoo.addons.base.models.ir_cron` | Cron execution, failures |
| `odoo.addons.mail.models.mail_mail` | Outgoing mail |
| `odoo.http` | Request errors |

## Pitfalls

- **Debug level in production.** `debug` on the root logger slows the server and fills the disk. Scope it to a namespace and revert.
- **Logs split across workers and files.** With several workers and a reverse proxy, the failing request may be in another worker's output.
- **Rotating logs.** Without logrotate, `--logfile` grows forever. If you rotate, Odoo reopens the file on `SIGHUP`.
- **Exceptions swallowed.** `except Exception: pass` removes the only evidence. Log and re-raise.
- **Messages that vary per record.** They defeat searching and alerting. Keep the message constant and put variable data last.

## Try it

```bash
./odoo-bin shell -d mydb --no-http --log-handler=odoo.sql_db:DEBUG <<'PY'
env['res.partner'].search_count([])
PY
```
