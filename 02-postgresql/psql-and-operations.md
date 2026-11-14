---
description: "Connecting, dumping, restoring, and the diagnostic queries worth keeping."
---

# psql and operations

The earlier chapters of this part taught SQL. This one covers the tools and routines around it: connecting to a database, getting around in psql efficiently, making and restoring backups (including the copy-for-testing workflow that every Odoo developer uses weekly), keeping the database healthy, and a set of diagnostic queries to keep in a file. Most of it is operational hygiene; the habit that matters most is treating production as read-only by default and doing risky work on a copy.

{% hint style="warning" %}
Hosts, users, database names, and paths below are placeholders. Never put real passwords on a command line or in a script you commit. Use the mechanisms in the connection section (`~/.pgpass`, environment variables, a service file).
{% endhint %}

## Connecting

`psql` takes the same five parameters as every PostgreSQL client: host, port, user, database, and a password if the server asks for one.

```bash
psql -h db.internal.example -p 5432 -U odoo -d mydb
psql "host=db.internal.example port=5432 user=odoo dbname=mydb sslmode=require"
psql "postgresql://odoo@db.internal.example:5432/mydb"
```

Omitted parameters fall back to environment variables and then to defaults: `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE` (and `PGPASSWORD`, which you should avoid because other users on the machine can see the environment of your processes in some setups). With nothing set, psql connects through the local Unix socket as your operating-system user to a database named like that user.

Passwords belong in `~/.pgpass` (on Windows `%APPDATA%\postgresql\pgpass.conf`), one line per server, with the file readable only by you (`chmod 600`):

```
db.internal.example:5432:mydb:odoo:the-password-goes-here
```

Fields are `host:port:database:user:password`, and `*` is a wildcard. psql then never prompts. A service file (`~/.pg_service.conf`) names a whole connection:

```
[odoo-staging]
host=db.internal.example
port=5432
dbname=mydb
user=odoo
```

and `psql service=odoo-staging` connects with it.

Odoo's own settings are in its configuration file (`db_host`, `db_port`, `db_user`, `db_password`, `db_name`, `dbfilter`). When you must connect "the way Odoo does" to see what it sees, read those values from the file instead of guessing, and use the same role, because role permissions differ (the Odoo role is usually not a superuser).

On a Linux server the common local patterns are:

```bash
sudo -u postgres psql                 # superuser, via peer authentication
sudo -u odoo psql -d mydb             # as the odoo OS user, whose role has the same name
```

Peer authentication maps the operating-system user to the database role of the same name, which is why these work without a password. Remote access is governed by `pg_hba.conf` on the server: which hosts, which users, which databases, which authentication method. "no pg_hba.conf entry for host" is the error when the server was not told to accept your address; "password authentication failed" means the entry matched but the credentials did not.

List databases and check where you are connected:

```sql
\l
\conninfo
```

```
You are connected to database "mydb" as user "odoo" via socket in "/var/run/postgresql" at port "5432".
```

## Working in psql

psql's own commands start with a backslash and are not SQL: they are handled by the client, need no semicolon, and are not sent to the server. The ones worth knowing by heart:

| Command | Does |
|---|---|
| `\?` | list all backslash commands; `\h CREATE INDEX` gives SQL syntax help |
| `\c dbname` | connect to another database |
| `\l` | list databases |
| `\dt`, `\dt+` | list tables (with sizes) |
| `\dt library_*` | list tables matching a pattern |
| `\d name` | describe a table: columns, indexes, constraints, referencing tables |
| `\d+ name` | the same with storage, statistics target, comments |
| `\di`, `\dv`, `\ds`, `\df` | indexes, views, sequences, functions |
| `\du` | roles |
| `\x` or `\x auto` | expanded display: one column per line, for wide rows |
| `\timing` | print the time each statement took |
| `\e` | edit the current query in `$EDITOR` |
| `\i file.sql` | run a file of commands |
| `\o file` | send results to a file; `\o` alone restores the screen |
| `\copy ...` | client-side `COPY` (see [INSERT, UPDATE, DELETE](writing-data.md)) |
| `\set name value`, `:name` | psql variables |
| `\watch 2` | repeat the previous query every 2 seconds |
| `\g`, `\gset` | run the query buffer; store a one-row result in variables |
| `\q` | quit |

Wide rows read badly in a table; `\x` flips to a vertical layout:

```sql
\x on
SELECT * FROM members WHERE id = 1;
```

```
-[ RECORD 1 ]-------------------
id        | 1
name      | Nora
email     | nora@example.com
joined_on | 2023-01-10
active    | t
```

`\x auto` switches to vertical only when the row would not fit the screen. `\timing` shows the elapsed time of each statement, which is the fastest way to compare two versions of a query before reaching for `EXPLAIN`. `\watch` re-runs the previous statement periodically; it turns a query on `pg_stat_activity` into a live monitor:

```sql
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
\watch 2
```

`\gset` turns a one-row result into psql variables, so a script can feed one query's result into the next:

```sql
SELECT max(id) AS last_book_id FROM books \gset
SELECT * FROM books WHERE id = :last_book_id;
```

### Running SQL non-interactively

```bash
psql -d handbook_lab -c "SELECT count(*) FROM books"            # one statement
psql -d handbook_lab -f fix.sql                                 # a file
psql -d handbook_lab -At -c "SELECT id FROM books ORDER BY id"  # unaligned, tuples only: script-friendly
psql -d handbook_lab -v ON_ERROR_STOP=1 -1 -f fix.sql           # stop at first error; wrap in one transaction
```

By default psql continues after an error, so a script that fails at statement 3 happily runs statements 4 to 40 against a half-changed database. For any script that changes data use `-v ON_ERROR_STOP=1`, and `-1` (`--single-transaction`) to wrap the file in one `BEGIN ... COMMIT`, which then rolls back entirely on failure. (A file that contains `CREATE INDEX CONCURRENTLY` or `VACUUM` cannot use `-1`.)

`-A` (unaligned) and `-t` (tuples only) give clean output for shell pipelines; `--csv` produces CSV with a header, a quick way to export.

### A useful `~/.psqlrc`

psql reads `~/.psqlrc` at startup. A conservative set:

```
\set QUIET 1
\pset null '[NULL]'
\x auto
\timing on
\set HISTSIZE 5000
\set ON_ERROR_ROLLBACK interactive
\set PROMPT1 '%n@%m/%/%R%x%# '
\unset QUIET
```

- `\pset null '[NULL]'` makes NULL visible instead of an empty cell that looks like an empty string. It prevents a real class of misreadings.
- `ON_ERROR_ROLLBACK interactive` wraps each statement you type inside an open transaction in an implicit savepoint, so a typo does not abort your whole transaction.
- `%x` in the prompt prints `*` when you are inside an open transaction, and `!` when it is aborted: at a glance you can see that you left a `BEGIN` open, which is the leading cause of long-held locks.

Do not set `\set AUTOCOMMIT off` in your rc file. It makes every statement open a transaction that nothing closes, so a harmless `SELECT` leaves a session `idle in transaction` on a production database for hours. The inverse safety, a prompt that shows the host and database in a conspicuous way, is worth setting: you must know whether you are on staging or production before you press Enter. Many teams use per-environment service files with a distinct prompt.

## Pointing psql safely at a database you do not own

For a database you only intend to read:

```bash
PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=60000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=600000' \
  psql -h db.internal.example -U odoo -d mydb
```

Read-only default, a one-minute statement limit, a five-second limit on lock waits, and a ten-minute limit on idle open transactions. It is not a security boundary (the session can `SET` the option back), but it removes accidents. For a real boundary create a role with `pg_read_all_data` (PostgreSQL 14+) or `SELECT` grants on specific tables and connect as it.

## Backups: pg_dump and pg_restore

`pg_dump` makes a consistent snapshot of one database while it is in use (it runs in a REPEATABLE READ transaction, the same mechanism as [the previous chapters](transactions-and-isolation.md)). It does not block other users, though it adds read load.

| Format | Flag | Properties |
|---|---|---|
| plain SQL | `-Fp` (default) | a text file of SQL; restore with `psql -f`; no parallelism or selective restore |
| custom | `-Fc` | compressed, one file, `pg_restore` can list, select, and parallelize |
| directory | `-Fd` | one file per table; supports parallel dump (`-j`) |
| tar | `-Ft` | rarely useful |

The everyday choice is custom format:

```bash
pg_dump -h db.internal.example -U odoo -Fc -f mydb_2026-11-13.dump mydb
```

Inspect before trusting it:

```bash
pg_restore --list mydb_2026-11-13.dump | head -30
ls -l mydb_2026-11-13.dump
```

`pg_restore --list` prints the table of contents (tables, indexes, constraints, data); a dump that lists nothing, or is a few hundred bytes, is a failed one. The only real test of a backup is a restore.

Restore into a fresh database, never over a live one:

```bash
createdb -h db.internal.example -U odoo mydb_copy
pg_restore -h db.internal.example -U odoo -d mydb_copy --no-owner --no-privileges -j 4 mydb_2026-11-13.dump
```

- `--no-owner --no-privileges` ignore the ownership and `GRANT`s recorded in the dump, so everything is owned by the user running the restore. It avoids "role does not exist" errors when you restore on a machine without the original roles.
- `-j 4` restores with four parallel jobs (custom and directory formats only). It speeds up index builds substantially.
- Errors: `pg_restore` continues past errors by default and prints a count at the end. Read the messages, because "ignoring errors" can mean a missing extension (`unaccent`, `pg_trgm`) or a failed constraint. `--exit-on-error` stops at the first one.

For small databases or when you want to read the dump, plain SQL works: `pg_dump -Fp -f mydb.sql mydb`, restored with `psql -d mydb_copy -v ON_ERROR_STOP=1 -f mydb.sql`.

Compatibility rules: `pg_dump` must be the same or a newer major version than the server it dumps. A dump can be restored to the same or a newer server major version; restoring a dump from a newer server into an older one is not supported. Roles and tablespaces are cluster-wide, not in a per-database dump; `pg_dumpall --globals-only` captures them.

### Cloning a database on the same server

If no one is connected to the source, the fastest copy is a template:

```sql
CREATE DATABASE mydb_copy TEMPLATE mydb;
```

It fails with `source database "mydb" is being accessed by other users` while connections exist. Odoo's workers, cron, and any open sessions count. Disconnecting them is a decision for whoever owns the system, not a statement to run casually.

### The Odoo-specific part: the filestore

A PostgreSQL dump contains the database only. Attachments and binary fields stored with the default settings live as files in the **filestore**, a directory per database under the data directory (`data_dir`, e.g. `~/.local/share/Odoo/filestore/<dbname>` or `/var/lib/odoo/filestore/<dbname>`), and `ir_attachment.store_fname` names the file. A database restored without its filestore opens, but every attachment, report logo, and image gives a missing-file error. A complete backup is the dump plus the filestore directory, taken close together in time:

```bash
tar czf mydb_filestore_2026-11-13.tgz -C /var/lib/odoo/filestore mydb
```

and a complete restore puts the directory back under the new database's name (`filestore/mydb_copy`). Odoo's web database manager and its `db` command line (available from Odoo 16; check `odoo-bin db --help` on your version) produce a zip containing both `dump.sql` and the filestore, which is convenient and equivalent.

### A restored copy is a live clone: neutralize it

A copy of a production database contains scheduled actions, outgoing mail servers, payment provider credentials, webhooks, and integrations. Started as is, it can send real emails to real customers and process real payments. Before the first start of a copy, neutralize it. Odoo 16 and later ship a command for this:

```bash
odoo-bin neutralize -d mydb_copy
```

which disables the relevant scheduled actions, mail servers, and payment providers (the exact set depends on the installed modules). Otherwise do it by hand, always looking first:

```sql
SELECT id, cron_name, active FROM ir_cron WHERE active ORDER BY id;
SELECT id, name, active FROM ir_mail_server;
```

```sql
BEGIN;
UPDATE ir_cron SET active = false WHERE active;
UPDATE ir_mail_server SET active = false WHERE active;
COMMIT;
```

(The `cron_name` column and the other table names vary by version; use `\d ir_cron` first.) Also change `web.base.url` in `ir_config_parameter` so that links in emails and reports do not point at production, and reset anything that identifies the instance to external services. This is the same read-first, change-in-a-transaction discipline as in [INSERT, UPDATE, DELETE](writing-data.md), with one extra rule: do it on the copy, before anyone starts Odoo on it.

## Keeping the database healthy

MVCC leaves dead row versions behind (see [Transactions and isolation](transactions-and-isolation.md)); `VACUUM` reclaims them for reuse, `ANALYZE` refreshes planner statistics, and **autovacuum** does both automatically in the background. Usually you do nothing. You check:

```sql
SELECT relname, n_live_tup, n_dead_tup,
       round(100.0 * n_dead_tup / nullif(n_live_tup + n_dead_tup, 0), 1) AS dead_pct,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
```

```
  relname   | n_live_tup | n_dead_tup | dead_pct |       last_autovacuum        |       last_autoanalyze
------------+------------+------------+----------+------------------------------+------------------------------
 mail_message |    812344 |      30112 |      3.6 | 2026-11-13 02:14:55+00       | 2026-11-13 02:15:10+00
 bus_bus      |     12000 |      98000 |     89.1 | 2026-11-12 21:03:12+00       | 2026-11-12 21:03:13+00
(2 rows)
```

(Illustrative.) A high `dead_pct` with an old `last_autovacuum` means vacuum is not keeping up or is blocked by a long transaction. Run it by hand on one table: `VACUUM (ANALYZE, VERBOSE) mail_message;`. It does not block normal reads and writes.

`VACUUM FULL` rewrites the table into a new file to return space to the operating system. It takes an `ACCESS EXCLUSIVE` lock for the whole duration (the table is unusable), needs free disk space equal to the table, and is almost never the right call on a live system. Plain `VACUUM` makes space reusable, and `pg_repack` is the usual tool when real shrinking is needed without downtime.

Bulk operations leave stale statistics: after a big import, a mass update, or a restore, run `ANALYZE;` (restores do not carry statistics over). Sluggish first queries after a restore are very often this.

## Diagnostic queries worth keeping

Save these in a file (for example `diag.sql`) and run them with `\i`. All are read-only.

**What is running now** (excluding your own session), longest first:

```sql
SELECT pid, usename, application_name, state,
       now() - query_start AS running_for,
       wait_event_type, wait_event,
       left(query, 80) AS query
FROM pg_stat_activity
WHERE state <> 'idle' AND pid <> pg_backend_pid()
ORDER BY query_start;
```

**Sessions stuck in a transaction** (from the previous chapters):

```sql
SELECT pid, usename, now() - xact_start AS xact_age, state, left(query, 60) AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND state = 'idle in transaction'
ORDER BY xact_start;
```

**Who blocks whom:** the query using `pg_blocking_pids()` from [Locks](locks.md).

**Connections against the limit.** Each Odoo worker holds connections to the database, so the sum across all Odoo servers must stay below PostgreSQL's `max_connections` (default 100), minus the connections other tools need:

```sql
SELECT count(*) AS connections,
       current_setting('max_connections')::int AS max_connections,
       count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
FROM pg_stat_activity;
```

The Odoo option `db_maxconn` (default 64) is a per-process pool limit, not a global one; with several workers it multiplies. "FATAL: sorry, too many clients already" is this limit being exceeded.

**Database and table sizes:**

```sql
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database WHERE NOT datistemplate ORDER BY pg_database_size(datname) DESC;

SELECT relname,
       pg_size_pretty(pg_total_relation_size(oid)) AS total,
       pg_size_pretty(pg_relation_size(oid))       AS table_only,
       pg_size_pretty(pg_indexes_size(oid))        AS indexes
FROM pg_class
WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
ORDER BY pg_total_relation_size(oid) DESC
LIMIT 10;
```

**Cache hit ratio** (below about 99% on a database that should fit in memory means too little `shared_buffers` or an unusually scan-heavy workload):

```sql
SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2) AS hit_pct
FROM pg_stat_database WHERE datname = current_database();
```

**Unused and duplicate indexes:** see [Indexes and EXPLAIN](indexes-and-explain.md).

**Sequences approaching the integer limit.** Odoo ids are `int4`, so a sequence near 2.1 billion is a time bomb, usually on log-like tables:

```sql
SELECT schemaname, sequencename, last_value, max_value,
       round(100.0 * last_value / max_value, 1) AS pct_used
FROM pg_sequences
WHERE last_value IS NOT NULL
ORDER BY last_value DESC
LIMIT 5;
```

**Transaction-id age** (rarely a problem with working autovacuum, fatal if ignored for long):

```sql
SELECT datname, age(datfrozenxid) AS xid_age FROM pg_database ORDER BY 2 DESC;
```

Values approaching two billion need immediate attention, though normal systems stay in the low hundreds of millions.

**Slowest queries overall** need the `pg_stat_statements` extension, which must be in `shared_preload_libraries` (a restart) and created per database:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT calls,
       round(total_exec_time::numeric, 0) AS total_ms,
       round(mean_exec_time::numeric, 2)  AS mean_ms,
       rows,
       left(query, 80)                     AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

(Column names are `total_exec_time` and `mean_exec_time` from PostgreSQL 13; older servers call them `total_time` and `mean_time`.) The statements appear with parameters replaced by `$1`, `$2`, grouped by shape, so one slow ORM pattern called a million times surfaces at the top. `SELECT pg_stat_statements_reset();` clears the counters before an experiment.

### Server settings worth knowing

```sql
SHOW shared_buffers;
SHOW work_mem;
SHOW max_connections;
SHOW log_min_duration_statement;
```

Settings live in `postgresql.conf` and can be changed for the server with `ALTER SYSTEM SET name = value;` followed by `SELECT pg_reload_conf();` (many take effect on reload, a few need a restart; `SELECT name, pending_restart FROM pg_settings WHERE pending_restart;` shows which). For troubleshooting, three logging settings pay for themselves:

- `log_min_duration_statement = 500` logs every statement slower than 500 ms with its duration.
- `log_lock_waits = on` logs when a statement waits longer than `deadlock_timeout` for a lock, naming the blocker.
- `log_temp_files = 0` logs every query that spilled a sort or hash to disk, the cue to raise `work_mem` for that query.

Tuning memory and checkpoints for a production server is a topic of its own; start from a tool such as PGTune for the baseline and change one thing at a time. Odoo's own advice: keep `max_connections` consistent with workers, and give `shared_buffers` about a quarter of the memory of a dedicated database host.

## Roles and ownership

```sql
\du
```

```
                                   List of roles
 Role name |                         Attributes                         | Member of
-----------+------------------------------------------------------------+-----------
 odoo      | Create DB                                                  | {}
 postgres  | Superuser, Create role, Create DB, Replication, Bypass RLS | {}
```

Odoo's role needs `CREATEDB` for the database manager (creating, duplicating, restoring databases through the web UI or `odoo-bin db`), and does not need to be a superuser. Extensions that Odoo wants (`unaccent`, `pg_trgm`) need a superuser to create in older PostgreSQL versions; PostgreSQL 13 marks some as trusted so that a database owner may create them. After a restore with `--no-owner` all objects belong to the restoring role; to move ownership use `REASSIGN OWNED BY old_role TO new_role;` and `ALTER DATABASE mydb OWNER TO odoo;`.

## Cleaning up the lab

When you finish the exercises of this part, remove what you created:

```bash
dropdb handbook_lab
```

`dropdb` fails if anyone is connected, which in a lab is only your other psql windows. If you want to keep the lab but remove the heavy tables: `DROP TABLE loan_log, catalog, book_stock, notify_queue;` (each `IF EXISTS` if unsure).

## Pitfalls

- **Running a script without `ON_ERROR_STOP`.** After the first error psql carries on, and the rest of the file runs against a half-applied state. Always `-v ON_ERROR_STOP=1`, and `-1` for data changes.
- **An open `BEGIN` you forgot.** Locks held, vacuum blocked. Show the transaction state in the prompt (`%x`).
- **`AUTOCOMMIT off` in `.psqlrc`.** Turns every session into an idle-in-transaction session.
- **Connecting to production by habit.** Use distinct service names and prompts, and a read-only default for everything that is not a deliberate change.
- **Password on the command line.** Visible in process listings and shell history. Use `.pgpass` or a service file.
- **Dump without the filestore.** The restore opens but attachments and images are missing. Back up both and restore both.
- **Untested backups.** A backup is a guess until restored. Restore into a scratch database regularly and open it.
- **Starting a restored copy un-neutralized.** It sends production mail and runs production crons. Neutralize before the first start, and keep copies off networks that can reach real integrations.
- **Restoring over a live database.** Restore into a new name, check, then switch. `pg_restore --clean` against the wrong database drops production tables.
- **Version mismatch.** `pg_dump` older than the server refuses; a dump from a newer server does not load into an older one.
- **`VACUUM FULL` on a live table.** An exclusive lock for the duration. Plain `VACUUM` and autovacuum tuning are the right tools.
- **Skipping `ANALYZE` after a restore.** The planner has no statistics; first queries are slow.
- **Counting connections wrongly.** Workers times pool size, across all servers, must stay below `max_connections`, with room for cron, backup, and your own sessions.
- **`pg_terminate_backend` as a reflex.** It rolls back whatever the session was doing. Look at the session first.

## Try it

1. Create a `~/.psqlrc` with the settings from this chapter. Open psql, `BEGIN;`, and notice the prompt. Run a bad statement and notice the prompt again. Roll back.

2. Take a custom-format dump of `handbook_lab`, list its contents with `pg_restore --list`, restore it into `handbook_lab_copy` with `--no-owner`, and verify that the row counts of `books` and `loans` match in both databases. Drop the copy.

3. Write a `diag.sql` with the five queries you would run first when a user says "Odoo is slow": running statements, idle-in-transaction sessions, blockers, connection count, and the largest tables. Run it with `psql -f` against the lab.

4. Run a script that deliberately fails halfway, first without and then with `-v ON_ERROR_STOP=1 -1`, and compare the state of the database afterwards.

5. Describe, as a checklist, how you would produce a safe test copy of a production Odoo database from backups, including everything that must happen before the first start.

<details>
<summary>Solution</summary>

1. With the `%x` prompt, `handbook_lab=#` becomes `handbook_lab=*#` after `BEGIN;`, and `handbook_lab=!#` after an error inside the transaction (until `ROLLBACK`). With `ON_ERROR_ROLLBACK interactive` the `!` does not appear on errors you type interactively, because each statement is wrapped in a savepoint and the transaction survives; unset it temporarily if you want to see the aborted state.

2. 
```bash
pg_dump -Fc -f lab.dump handbook_lab
pg_restore --list lab.dump | head
createdb handbook_lab_copy
pg_restore -d handbook_lab_copy --no-owner lab.dump
psql -d handbook_lab -At -c "SELECT (SELECT count(*) FROM books), (SELECT count(*) FROM loans)"
psql -d handbook_lab_copy -At -c "SELECT (SELECT count(*) FROM books), (SELECT count(*) FROM loans)"
dropdb handbook_lab_copy
```
The two count lines should be identical, for example `6|7` on a pristine lab.

3. Put the queries of this chapter and the blocker query from the Locks chapter in the file, separated by `\echo '--- title ---'` lines so the output is readable, and run `psql -d handbook_lab -f diag.sql`.

4. Create `broken.sql` with three statements, the second invalid (for example `UPDATE books SET nosuchcolumn = 1;`) and the first and third valid updates. Without the options, the first and third apply and only the second fails. With `-v ON_ERROR_STOP=1 -1` the script stops at the error and the whole transaction rolls back: no statement leaves a trace.

5. 
- Take the dump (custom format) and a filestore archive at the same time.
- `createdb` a new name; `pg_restore --no-owner -j N` into it; `ANALYZE`.
- Copy the filestore under the new database name.
- Neutralize before starting: `odoo-bin neutralize -d newname`, or manually deactivate crons, mail servers, payment providers, webhooks; change `web.base.url`.
- Start Odoo against it on a different port with a configuration that has no outgoing mail, then log in and check a few records and an attachment.
- Never put the copy on a network path where it can reach live integrations.

</details>
