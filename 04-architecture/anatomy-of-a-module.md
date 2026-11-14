---
description: Manifest, folders, load order, and what each file is for.
---

# Anatomy of a module

A module is a Python package plus a manifest and a set of data files. The manifest tells Odoo what to load and in which order; the folders are convention, except for the few names the framework treats specially. Knowing which parts are convention and which are contract saves you from cargo-culting a layout that does not matter and ignoring one that does.

## The smallest useful module

```
library/
  __init__.py
  __manifest__.py
  models/
    __init__.py
    book.py
  security/
    ir.model.access.csv
  views/
    book_views.xml
```

```python
# __manifest__.py
{
    'name': 'Library',
    'version': '18.0.1.0.0',
    'summary': 'Books and loans',
    'category': 'Services/Library',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/book_views.xml',
    ],
    'application': True,
    'installable': True,
}
```

```python
# __init__.py
from . import models
```

```python
# models/__init__.py
from . import book
```

```python
# models/book.py
from odoo import fields, models


class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Library Book'

    name = fields.Char(required=True)
    isbn = fields.Char(copy=False)
```

Every Python file must be imported from an `__init__.py` chain starting at the module root. A model file that is not imported is simply not part of the registry; there is no error.

## Manifest keys

| Key | Purpose |
|---|---|
| `name` | Display name. Required. |
| `version` | Convention: `<series>.<major>.<minor>.<patch>`, e.g. `18.0.1.0.0`. If you give a short version, Odoo prefixes the series. Migration scripts are selected by comparing this. |
| `summary`, `description`, `category`, `author`, `website`, `license` | Metadata. A missing `license` logs a warning and defaults to LGPL-3. |
| `depends` | Modules that must be loaded first. Defaults to `['base']`. This is the only thing that decides load order. |
| `data` | Files loaded at install and at every update, in the listed order. |
| `demo` | Files loaded only when demo data is enabled. |
| `assets` | JS, SCSS, and XML bundles (from 16; earlier versions used QWeb templates in `data`). |
| `application` | Shows the module as an app in the Apps list. |
| `installable` | `False` hides it from installation. |
| `auto_install` | `True`, or a list of modules: installed automatically once all dependencies are installed. |
| `external_dependencies` | Python packages and binaries checked at install. |
| `pre_init_hook`, `post_init_hook`, `uninstall_hook`, `post_load` | Python hooks, names of functions in the module's `__init__.py`. |

{% hint style="info" %}
Versions: hook signatures changed. In 16, `pre_init_hook` and `post_init_hook` receive `(cr, registry)`; from 17 they receive `env`. A module that supports both needs a compatibility shim or separate branches. Check the `odoo/modules/loading.py` of your branch.
{% endhint %}

## Standard folders

Only some names mean something to the framework. The rest are convention.

| Folder | Role |
|---|---|
| `models/` | Python models. Convention. |
| `views/` | XML views, actions, menus. Convention; files are loaded because they are in `data`. |
| `security/` | `ir.model.access.csv` and record rule XML. Convention, but `ir.model.access.csv` is the expected name of the ACL file. |
| `data/` | Records with `noupdate` data, sequences, cron jobs, mail templates. |
| `demo/` | Demo data listed under `demo`. |
| `wizard/` (or `wizards/`) | Transient models. Convention. |
| `report/` | QWeb report templates and report models. |
| `controllers/` | HTTP controllers. Convention; imported from `__init__.py`. |
| `static/` | Served to the browser as `/library/static/...`. **This name is contract.** `static/description/icon.png` is the app icon and `index.html` the Apps page description. |
| `static/src/` | Frontend sources, referenced in `assets`. |
| `i18n/` | `.po` and `.pot` translation files, loaded by language code. **Contract.** |
| `tests/` | Test classes. Test discovery imports `tests/__init__.py`. **Contract.** |
| `migrations/` | Upgrade scripts. **Contract**, see below. |

## Load order inside a module

1. Dependencies are loaded first, recursively. Order among independent dependencies is not specified; do not rely on it.
2. The module's Python package is imported, which defines the model classes.
3. The registry is built for the models (see [Registry and model loading](registry-and-model-loading.md)).
4. On install or update, the `data` files are processed in the order listed, then `demo` files if demo is enabled.
5. Hooks run: `pre_init_hook` before data on install, `post_init_hook` after.

Within `data`, order is yours to get right. Security CSV first, so that views and menus that reference groups do not fail; views before the menus and actions that reference them; data records before anything that points at them by XML id.

```python
'data': [
    'security/library_security.xml',     # groups
    'security/ir.model.access.csv',      # ACLs reference groups and models
    'data/library_sequence.xml',
    'views/book_views.xml',              # views and actions
    'views/menus.xml',                   # menus reference actions
],
```

## XML IDs and noupdate

Records created from data files get an XML ID `module.name` stored in `ir.model.data`. On update, Odoo matches records by that ID and overwrites them, unless the record sits in a `noupdate="1"` block. `noupdate` is for data that users are expected to edit (mail templates, sequences). If you change a `noupdate` record in code and update the module, nothing happens on databases that already have it. That is the single most common "my data change is not applied" report.

## Migrations

```
library/migrations/18.0.1.1.0/pre-migrate.py
library/migrations/18.0.1.1.0/post-migrate.py
```

A script runs when the installed version is lower than the folder version and the manifest version is equal or higher. `pre-` runs before the module's data and schema are updated, `post-` after. Each script defines `migrate(cr, version)`. Forgetting to bump the manifest `version` means the script never runs.

## Pitfalls

- **Missing `depends`.** A module works on your database because another module happened to load first, then fails on a clean install with "model or field not found" or an XML ID error. Test installs on an empty database with only your dependencies.
- **Wrong order in `data`.** A view referencing a group defined in a later file raises `ValueError: External ID not found`.
- **File not listed in `data`.** The file exists, is never loaded, and nothing complains.
- **Tab or space style in CSV.** `ir.model.access.csv` must have the exact header and one blank-free line per rule; a stray empty column makes the whole file fail.
- **Models with no access rule.** In 16 and later a model with no ACL logs a warning at load and is unreachable for non-superusers. Add the ACL in the same change as the model.
- **Renaming a module directory.** XML IDs, `ir_model_data` rows, and installed state all carry the old name. Rename through a migration, not just the folder.

## Try it

```bash
odoo-bin scaffold library_demo /tmp/addons     # compare its output with the layout above
psql -d dev -c "select module, name, noupdate from ir_model_data where module='library' limit 10;"
```
