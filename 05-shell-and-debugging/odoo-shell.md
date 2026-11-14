---
description: "Starting it, the env object, committing, and using it as a lab."
---

# The Odoo shell

The shell loads the registry of one database and gives you an `env` in a Python prompt. It is the fastest way to test an ORM expression, reproduce a bug against real data, or run a one-off fix without writing a module. It is also the easiest way to damage a database, so this chapter spends as much time on transactions as on syntax.

## Starting it

```bash
./odoo-bin shell -d mydb -c /etc/odoo/odoo.conf
```

The shell reads the same configuration as the server: addons path, database host, credentials. Pass `-c` with the file the server uses, otherwise you land on defaults and get a confusing "module not found" or connection error.

```bash
# pick the interface (ipython, ptpython, bpython, python)
./odoo-bin shell -d mydb --shell-interface=ipython

# skip the http listener; the shell does not need it
./odoo-bin shell -d mydb --no-http

# run a script from stdin and exit
./odoo-bin shell -d mydb < fix_titles.py
```

`pip install ipython` is worth the ten seconds: tab completion on records and fields is what makes the shell pleasant. If the requested interface is missing, Odoo falls back to another one.

## What you get

| Name | Meaning |
| --- | --- |
| `env` | An `Environment` for the database, running as the superuser |
| `self` | The current user record, handy as a one-record recordset |
| `odoo` | The top-level `odoo` package |

```python
>>> env.user
res.users(1,)
>>> env['library.book'].search_count([])
42
>>> env.ref('base.main_company')
res.company(1,)
```

The superuser bypasses record rules and access rights. A query that returns records in the shell may return nothing for a real user. To see what a user sees:

```python
>>> user = env['res.users'].search([('login', '=', 'demo')])
>>> env_u = env(user=user.id)
>>> env_u['library.book'].search_count([])
```

For multi-company behaviour pass the companies explicitly:

```python
>>> Book = env['library.book'].with_context(allowed_company_ids=[1, 2])
>>> Book2 = env['library.book'].with_company(2)
```

## Transactions: nothing is saved until you commit

The shell keeps one transaction open. Writes are visible in your session and invisible to everyone else until you commit:

```python
>>> book = env['library.book'].browse(7)
>>> book.write({'name': 'Draft title'})
True
>>> env.cr.commit()     # now it is permanent
```

If you leave without committing, the transaction is rolled back. That is the safe default and why a shell experiment normally leaves nothing behind. Two consequences:

- A long session ended with Ctrl-D loses all its work. You learn this once.
- `env.cr.rollback()` discards everything since the last commit. Follow it with `env.invalidate_all()` (older versions: `env.clear()` or `invalidate_cache()`), otherwise cached records show values that no longer exist.

{% hint style="warning" %}
ORM writes run computes, constraints and `write` overrides. `env.cr.execute` does none of that and leaves the ORM cache stale. Prefer the ORM, and use SQL only when you have measured a need.
{% endhint %}

## Locks on a live database

Locking is by row. If your shell holds an uncommitted update and a user saves the same record, their request waits and may fail with a lock timeout or a concurrent update error. Keep experiments read-only, or commit quickly, when the instance is in use.

## Installing and upgrading

The shell inspects; the server entry point installs and updates:

```bash
./odoo-bin -d mydb -u library --stop-after-init
./odoo-bin -d mydb -i library_extra --stop-after-init
```

`-u` takes a comma-separated list. `-u all` updates everything and is slow; avoid it on production. The shell does not pick up edits to Python files, so restart it after changing code.

## The shell as a lab

```python
# What does this domain match?
>>> env['library.loan'].search([('state', '=', 'open')], limit=5).mapped('book_id.name')

# Field definitions
>>> env['library.book']._fields['isbn'].type
'char'

# Stored values
>>> env['library.book'].browse(7).read(['name', 'isbn'])

# XML ID of a record
>>> env['ir.model.data'].search([('model', '=', 'library.book'), ('res_id', '=', 7)]).complete_name
```

For the SQL behind a search see [Inspecting SQL](inspecting-sql.md). Any addon is importable: `from odoo.addons.library.models.library_book import LibraryBook`. A `ModuleNotFoundError` means the addons path of your config does not contain that addon.

## Pitfalls

- **Forgetting `-c`.** The shell connects with defaults and shows no addons.
- **Stale cache** after SQL or rollback. Call `env.invalidate_all()`.
- **Assuming a user's view.** The superuser sees everything; test with `env(user=...)`.
- **Committing in a loop.** One commit per record is slow and leaves a half-applied state if you stop. See [Safe bulk scripts](safe-bulk-scripts.md).
- **Mail side effects.** Tracked-field writes post messages and may queue emails. Use `with_context(tracking_disable=True)` for data repair, and make sure a copy of production cannot send mail.

## Try it

```bash
./odoo-bin shell -d mydb -c /etc/odoo/odoo.conf --no-http <<'PY'
print(env.user.login, env.company.name)
print(env['ir.module.module'].search_count([('state', '=', 'installed')]))
PY
```
