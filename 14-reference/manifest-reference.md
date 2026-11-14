---
description: Every key accepted in __manifest__.py, with defaults.
---

# Manifest reference

`__manifest__.py` is a single Python dict literal. Odoo reads it with `ast.literal_eval`, not by importing the file, so it cannot contain expressions, function calls, or variables. Keys and defaults below come from `odoo/modules/module.py` in Odoo 18, where the defaults dict `_DEFAULT_MANIFEST` is defined.

## Minimal manifest

```python
{
    'name': 'Library',
    'version': '18.0.1.0.0',
    'summary': 'Books and loans',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/library_book_views.xml',
    ],
    'application': True,
    'installable': True,
}
```

## Keys and defaults

| Key | Default | Meaning |
|---|---|---|
| `name` | required | display name |
| `version` | `'1.0'` | module version. Odoo prefixes it with the series if it has fewer than 5 parts, so `1.0` becomes `18.0.1.0`; prefer the full `18.0.x.y.z` |
| `summary` | `''` | one-line description for the Apps list |
| `description` | `''` | long description (reStructuredText); `README.rst` is preferred in new modules |
| `author` | `'Odoo S.A.'` | set your own |
| `website` | `''` | URL shown in the Apps list |
| `category` | `'Uncategorized'` | Apps grouping |
| `license` | not defaulted in the list; Odoo warns when absent and assumes LGPL-3 | declare `LGPL-3` or another |
| `depends` | `[]` | modules that must be loaded first; controls load order and which XML IDs you may reference |
| `data` | `[]` | XML/CSV files loaded on install and update, in order |
| `demo` | `[]` | files loaded only on databases created with demo data |
| `assets` | `{}` | asset bundles: `{'web.assets_backend': ['library/static/src/**/*']}` |
| `external_dependencies` | `{}` | `{'python': ['requests'], 'bin': ['wkhtmltopdf']}`; install fails if missing |
| `application` | `False` | shows the module as an app in the Apps menu |
| `installable` | `True` | `False` hides the module from installation |
| `auto_install` | `False` | `True` or a list of modules: installs automatically when all its dependencies are installed (the "glue module" pattern) |
| `bootstrap` | `False` | for `web`-type modules loaded before the database |
| `web` | `False` | set by the web module family |
| `sequence` | `100` | ordering in the Apps list |
| `pre_init_hook` | `''` | name of a function in the module run before install |
| `post_init_hook` | `''` | function run after install |
| `uninstall_hook` | `''` | function run on uninstall |
| `post_load` | `''` | function called when the module's Python is loaded, before the registry is built (monkey-patching hook) |
| `countries` | `[]` | restricts auto-install suggestions to given country codes (localisations) |
| `cloc_exclude` | `[]` | globs excluded from the line-count tool |
| `images` | `[]` | website app store screenshots |
| `configurator_snippets`, `new_page_templates`, `images_preview_theme`, `live_test_url` | unset | website theme keys |
| `init_xml`, `update_xml`, `demo_xml`, `test` | `[]` | legacy keys, still in the defaults dict; do not use |

Fields such as `icon` and `addons_path` are computed (the icon from `static/description/icon.png`), not set in the manifest.

## Load order

Odoo loads modules by dependency graph. Within a module, `data` files load in listed order, so security files come first, then data, then views, then menus that refer to actions. An XML ID referenced before the file that defines it is loaded fails with `External ID not found`.

```python
'data': [
    'security/library_security.xml',
    'security/ir.model.access.csv',
    'data/sequences.xml',
    'views/library_book_views.xml',
    'views/library_menus.xml',
],
```

## Hooks

```python
# hooks.py
def post_init_hook(env):
    env['ir.config_parameter'].set_param('library.loan_days', '14')
```

```python
'post_init_hook': 'post_init_hook',
```

In Odoo 18 hooks receive `env`. In 16 they received `(cr, registry)`.

## Assets

```python
'assets': {
    'web.assets_backend': [
        'library/static/src/js/**/*',
        'library/static/src/xml/**/*.xml',
        'library/static/src/scss/library.scss',
    ],
    'web.assets_frontend': ['library/static/src/frontend/**/*'],
},
```

Globs are allowed. Files in a bundle but not matched by any rule are not served; adding a JS file does not require a manifest change if a glob covers it.

## Pitfalls

* **Non-literal values.** `'version': VERSION` or `'data': get_files()` fails to parse. Write literals.
* **Forgetting `depends`.** The module installs in a database that already has the other module, then fails in a clean one. Test installs on an empty database.
* **File listed but missing.** The update aborts with a file-not-found. Check paths in `data` after renaming views.
* **Data in `demo` that production needs.** Demo files are not loaded when demo data is disabled.
* **`auto_install` on a module with a heavy dependency set.** It silently adds the module to databases that happen to have all dependencies.
* **Version bumps.** Odoo does not use `version` for migrations as such; migration scripts in `migrations/<version>/` run when the stored version is lower than the manifest version. Forgetting to bump the version means pre/post migration scripts do not run.

{% hint style="info" %}
**Versions.** Hooks changed signature between 16 (`cr, registry`) and 17 onward (`env`). The `attrs`/`states` removal and `<list>` rename affect view files, not the manifest. Odoo 20 is not covered here.
{% endhint %}

## Try it

Read a module's manifest as Odoo does, from a shell, without touching data:

```python
from odoo.modules.module import get_manifest
m = get_manifest('sale')
print(m['version'], m['depends'], m['application'])
```
