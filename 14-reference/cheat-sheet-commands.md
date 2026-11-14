---
description: Shell, odoo-bin, psql, and git on one page.
---

# Command cheat sheet

Commands are grouped by whether they read or change data. Read-only ones come first.

## odoo-bin

| Goal | Command |
|---|---|
| Start server | `odoo-bin -c odoo.conf` |
| Install module | `odoo-bin -d DB -i library --stop-after-init` |
| Update module | `odoo-bin -d DB -u library --stop-after-init` |
| Update everything | `odoo-bin -d DB -u all --stop-after-init` |
| Run tests | `odoo-bin -d DB -u library --test-tags /library --stop-after-init` |
| Test one class | `--test-tags /library:TestLoan` |
| Dev helpers | `--dev=xml,reload` |
| Shell | `odoo-bin shell -d DB --no-http` |
| Log level | `--log-level=warn` or `--log-handler=odoo.sql_db:DEBUG` |
| Scaffold | `odoo-bin scaffold library ./addons` |

Test tags: `/module`, `:Class`, `.method`, `at_install`, `post_install`, `-tag` to exclude.

{% hint style="danger" %}
`-u all` and `odoo-bin shell` with writes change data. Run them on a copy first.
{% endhint %}

## psql (read-only first)

```bash
psql -d DB -c "SELECT name, state, latest_version FROM ir_module_module WHERE state='installed'"
psql -d DB -c "SELECT pid, state, query_start, left(query, 80) FROM pg_stat_activity WHERE datname = 'DB'"
psql -d DB -c "SELECT pg_size_pretty(pg_database_size('DB'))"
psql -d DB -c "\d library_book"
```

Changing commands:

```bash
createdb -T source_db copy_db            # copy a database (no connections on source)
pg_dump -Fc -f backup.dump DB
pg_restore -d NEWDB backup.dump
dropdb copy_db
```

## Useful queries

```sql
SELECT module, name, res_id FROM ir_model_data WHERE model = 'ir.ui.view' AND module = 'library';
SELECT key, value FROM ir_config_parameter ORDER BY key;
SELECT id, login, active FROM res_users ORDER BY id;
```

## Shell session

```python
env['library.book'].search_count([])
env.ref('base.user_admin')
env.cr.rollback()    # discard
env.cr.commit()      # keep: deliberate only
```

## git

```bash
git log --oneline -20
git diff 17.0..18.0 --stat -- my_addons/library
git grep -nE "attrs=|<tree" -- '*.xml'
git switch -c 18.0-port
git cherry-pick <sha>
```

## Shell

```bash
grep -rn "def _compute_display_name" odoo/models.py
ls addons | head
tail -f odoo.log | grep -E "ERROR|WARNING"
```

## Pitfalls

- `-u` without `--stop-after-init` leaves a server running after the update.
- `createdb -T` fails while someone is connected to the template.
- `--dev=all` on a shared server reloads code on every save; keep it local.
- Forgetting the database filter `-d`, which makes Odoo scan every database.
