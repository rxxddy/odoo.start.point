---
description: Every odoo-bin switch you will actually use.
---

# Command line reference

`odoo-bin --help` prints a wall of options. In daily work about twenty matter, and a handful of them are routinely misused. This chapter groups them by task and says what each one does in the framework. Option definitions live in `odoo/tools/config.py` in each branch; when a switch behaves differently from what you read here, that file is the authority for your version.

## Selecting the database

| Switch | Meaning |
|---|---|
| `-d`, `--database` | Database to operate on. A comma-separated list is accepted for batch `-i` / `-u`. |
| `-r`, `--db_user` / `-w`, `--db_password` | PostgreSQL credentials. |
| `--db_host`, `--db_port` | Connection target. An empty host means the Unix socket. |
| `--db-filter` | Regular expression limiting which databases the web client shows and accepts. `%d` expands to the first label of the host name, `%h` to the full host. |
| `--no-database-list` | Hide the database manager and selector (`list_db = False`). |
| `--db_maxconn` | Connection pool size per process. |

`--db-filter` is the multi-database switch that causes the most support tickets. If a login page keeps returning to the database selector, the filter matches zero or several databases for that host name. In production, aim for one filter that matches exactly one database per host name.

## Modules: install, update, test

```bash
odoo-bin -d dev -i library --stop-after-init          # install
odoo-bin -d dev -u library --stop-after-init          # update
odoo-bin -d dev -u all --stop-after-init              # update everything (slow, upgrade day)
```

- `-i` installs modules and their dependencies. If a module is already installed, it is skipped; use `-u` to apply changes.
- `-u` reloads the module's data files and applies schema changes for the models it defines or extends. It does not reload Python code in a running server; restart the process (or use `--dev=reload` in development).
- `-u` on a module also updates the modules that depend on it, which is why updating `base` is effectively updating everything.
- `--without-demo=all` (or a module list) controls demo data at install time.

{% hint style="warning" %}
`-u` changes the database. On anything that is not a disposable copy, run it first on a restored backup and keep the previous dump. A failed update can leave a half-migrated schema.
{% endhint %}

## Running tests

```bash
odoo-bin -d test_db -i library --test-enable --stop-after-init --log-level=test
odoo-bin -d test_db -u library --test-tags /library:TestLoan.test_overdue --stop-after-init
```

`--test-enable` runs the tests of the modules being installed or updated. `--test-tags` filters; the grammar is `[-][tag][/module][:Class][.method]`. Tags include `at_install` and `post_install`; a leading `-` excludes. Pass both `--test-enable` and `--test-tags` unless you have verified in your branch that tags alone enable tests.

## HTTP and process model

| Switch | Meaning |
|---|---|
| `-p`, `--http-port` | Port for HTTP. Default 8069. |
| `--http-interface` | Bind address. Use `127.0.0.1` behind a reverse proxy. |
| `--gevent-port` (older: `--longpolling-port`) | Port of the separate process for live updates (bus, chat). Odoo 18 documents only `--gevent-port` (verified in `odoo/tools/config.py`); 16 uses `--longpolling-port`. Default 8072. |
| `--workers` | Number of HTTP worker processes. `0` means threaded mode. |
| `--max-cron-threads` | Number of cron threads (threaded mode) or cron workers (multi-process). |
| `--proxy-mode` | Trust `X-Forwarded-*` headers. Only behind a proxy that sets them. |
| `--limit-memory-soft`, `--limit-memory-hard` | Per-worker memory ceilings in bytes. |
| `--limit-time-cpu`, `--limit-time-real`, `--limit-time-real-cron` | Per-request CPU and wall-clock limits in seconds. |
| `--limit-request` | Requests a worker serves before being recycled. |

The last group is explained in [Workers, cron, and longpolling](workers-cron-and-longpolling.md).

## Development switches

```bash
odoo-bin -c dev.conf -d dev --dev=all
odoo-bin -c dev.conf -d dev --dev=xml,reload
```

`--dev` takes a comma-separated list. In Odoo 18 the help text lists `all`, `reload`, `qweb`, `xml` (verified in `odoo/tools/config.py`): `reload` restarts on Python file change, `xml` reads views and QWeb templates from disk on each request, `qweb` enables template debugging, and `all` is the shorthand. Older branches also document `werkzeug` (browser debugger, never on a reachable server) and `pdb` (post-mortem debugger); check `--help` on your branch before relying on them.

Two details save time. `reload` depends on the `watchdog` package being installed; without it, expect a warning and no reload. And `xml` re-reads only views that come from files: a view edited through the UI lives in the database and is unaffected.

## Logging

```bash
--log-level=debug_sql
--log-handler=odoo.addons.library:DEBUG
--log-handler=odoo.sql_db:DEBUG
--logfile=/var/log/odoo/odoo.log
```

`--log-level` accepts, among others, `critical`, `error`, `warn`, `info`, `debug`, `debug_rpc`, `debug_rpc_answer`, `debug_sql`, and `test`. `debug_sql` prints every query with its duration and is the fastest way to find an N+1 pattern. `--log-handler` takes `logger:LEVEL` pairs and is repeatable, which is how you raise one module to debug without drowning in the rest.

Without `--logfile`, logs go to stderr, which is what you want under systemd or in containers.

## Subcommands

`odoo-bin` has subcommands beside the server:

```bash
odoo-bin shell -d dev                       # interactive shell with env
odoo-bin scaffold library ./custom          # module skeleton
odoo-bin db dump dev dev.zip                # database management
odoo-bin db load newdev dev.zip
odoo-bin populate -d dev --models library.book --size small
```

`shell` opens a Python console with `env` bound to the database. It runs in a transaction that is not committed unless you call `env.cr.commit()`.

{% hint style="info" %}
Versions: in Odoo 18 the `db` subcommand offers `load`, `dump`, `duplicate`, `rename` and `drop` (verified in `odoo/cli/db.py`), and the other built-in commands are `shell`, `scaffold`, `server`, `start`, `deploy`, `neutralize`, `populate`, `cloc` and `upgrade_code`. The `db` subcommand (dump, load, duplicate, drop) and the way translation export is invoked have changed between 16, 17 and 18. Run `odoo-bin --help` and `odoo-bin db --help` in your checkout before scripting against them. On older branches translations are exported with `--i18n-export=file --modules=... -l ...`.
{% endhint %}

## Configuration precedence

1. Command line switch.
2. Value in the `-c` config file (or the file named by the `ODOO_RC` environment variable, or `~/.odoorc`).
3. Built-in default.

`-s` writes the effective values back to the config file, including passwords given on the command line. Check the file afterwards and never commit it.

## Pitfalls

- **`-u` with a misspelled module name** logs a warning and carries on. Read the log after a scripted update.
- **`-i` on an installed module** is skipped. Use `-u`.
- **`--stop-after-init` forgotten** in a deploy script: the "update" step never returns because the server stays up.
- **`--workers` on a developer machine** gets in the way of `--dev=reload` and debuggers. Develop in threaded mode.
- **`--db-filter` and `-d` together.** `-d` names the database for batch operations; the filter still applies to web requests.
- **`--test-enable` on a populated database.** Tests roll back, but side effects such as queued mails and external calls can leave traces. Use a copy.

## Try it

```bash
odoo-bin --help | grep -E "dev|workers|limit|gevent|longpolling"
odoo-bin -c dev.conf -d dev -u library --stop-after-init --log-level=debug_sql 2>&1 | tail -50
```
