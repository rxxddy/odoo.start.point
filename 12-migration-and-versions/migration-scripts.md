---
description: "Pre, post and end scripts that move data between module versions."
---

# Migration scripts

When a module changes in a way that existing rows cannot absorb (a renamed column, a split field, a changed selection key), you ship a migration script. Odoo runs it during `-u`, based on the version in the manifest.

## Where scripts live

```
library/
  migrations/
    18.0.1.1.0/
      pre-rename-isbn.py
      post-fill-shelf.py
      end-cleanup.py
```

The folder name is the module version the script migrates to. The loader docstring in `odoo/modules/migration.py` (18.0) states the rule: files start with `pre-`, `post-` or `end-`; `pre` runs before the module's models and data are loaded, `post` after, `end` after all modules of the run have loaded. The `0.0.0` folder runs on every update and `*` is not a valid folder name.

A script runs when the installed version is lower than the folder version and the new manifest version is greater or equal. Skipping versions is fine; all intermediate folders run in order.

## Shape

```python
def migrate(cr, version):
    # version is the previously installed version, or None on a fresh install
    if not version:
        return
    cr.execute("""
        UPDATE library_book SET isbn13 = isbn WHERE isbn13 IS NULL
    """)
```

Use `pre` when the ORM would otherwise fail at load: a column must be renamed before the new field definition makes Odoo create an empty one.

```python
# pre-rename-isbn.py
def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'library_book' AND column_name = 'isbn'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE library_book RENAME COLUMN isbn TO isbn13")
```

Use `post` for work that needs the new schema or the ORM:

```python
# post-fill-shelf.py
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    books = env['library.book'].search([('shelf_id', '=', False)])
    books.write({'shelf_id': env.ref('library.shelf_unsorted').id})
```

## Rules

- Make every script idempotent. Check the column or row before changing it; an update can be re-run after a failure.
- Prefer SQL in `pre`, ORM in `post`. In `pre` the registry for your module is not loaded.
- No commits inside a script. The loader owns the transaction; a half-committed script cannot be rolled back.
- Write set-based SQL. A Python loop over a million rows is the usual reason an upgrade takes a night.
- Log what you changed: `_logger.info("moved %s rows", cr.rowcount)`.

{% hint style="warning" %}
Mail, cron and automation records that react to writes will fire during a post script run through the ORM. Disable tracking with `with_context(tracking_disable=True, mail_notrack=True)`, or use SQL.
{% endhint %}

## Testing

Restore a copy of a real database at the old version, run `-u library`, and diff row counts and a few checksums. A fresh database never exercises migration code.

```bash
odoo-bin -d copy_old -u library --stop-after-init --log-level=info 2>&1 | grep -i migrat
```

## Pitfalls

- Forgetting to bump the manifest version, so the folder never runs.
- Writing the folder as `18.0.1.1` instead of the full five-segment version.
- Using `search` in a `pre` script on a model whose columns do not exist yet.
- Dropping a column in `pre` that a `post` script of the same step still reads.
