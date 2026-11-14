---
description: "How custom code is organised and found."
---

# Project layout and addons path

Odoo finds modules by scanning directories listed in `addons_path`. Everything else about project layout follows from that one rule: a module is a directory with a manifest, directly inside one of the listed directories. This chapter covers how to structure repositories around it, how the scan resolves duplicates, and what breaks when the path is wrong.

## How the scan works

At startup (and when you click "Update Apps List") Odoo walks each directory in `addons_path`, one level deep. A subdirectory is a module if it contains `__manifest__.py` (older code used `__openerp__.py`; ignore it). The directory name is the technical module name and must be a valid Python identifier, because it becomes the package `odoo.addons.<name>`.

```
addons_path = /srv/odoo/18.0/odoo/addons,/srv/odoo/18.0/addons,/srv/custom/library,/srv/custom/third-party
```

Consequences:

- Modules are not found recursively. `/srv/custom/library/library/` is a module only if `/srv/custom/library` is in the path, and `/srv/custom` alone would not find it.
- **Order matters for duplicates.** If two directories contain a module with the same name, the first one in the path wins and the other is silently ignored. A fork of a standard module placed earlier than the core directory shadows the original; placed later, it is never loaded and you wonder why your change has no effect.
- Names are global across all directories. Two repositories that both ship `sale_extra` collide.
- The scan only decides what is available. What is loaded is decided by what is installed in the database, plus dependencies.

## Repository layout that scales

One repository per concern, each a directory of modules, none of them nested:

```
~/odoo/custom/
  library/               # a repository, added to addons_path
    library/             # a module (library.book, library.loan)
      __manifest__.py
      __init__.py
      models/ views/ security/ data/ static/ tests/
    library_portal/
    library_reports/
  third-party/
    some_oca_module/
```

Practical conventions:

- Prefix module names with a project or domain token (`library_`) so they sort together and cannot collide with standard or community names.
- One feature per module. A module with `depends` on half the system cannot be installed in a test database cheaply.
- A thin "glue" module per customer or deployment, last in the dependency chain, with settings and data that only matter there. Reusable logic stays in other modules.
- Keep dependencies as an acyclic graph that you can draw. Circular `depends` are rejected at load time with a clear message; indirect cycles through `auto_install` are harder to spot.

## Environment-specific paths

Keep paths out of the repository. The repository holds code; the config file on each machine holds `addons_path`. Using `--addons-path` on the command line overrides the config file, which is useful in CI:

```bash
odoo-bin -d ci --addons-path=odoo/addons,addons,$PWD --test-enable -i library --stop-after-init
```

Relative paths are resolved against the current working directory, not against the config file, so a relative `addons_path` in a config used from two directories behaves differently. Use absolute paths in long-lived configs.

## What else Odoo adds to the path

Odoo appends its own `odoo/addons` directory automatically in recent versions, and `base` is always available, but relying on it is fragile across versions and distributions. Listing both core directories explicitly is clearer and costs nothing.

On hosted platforms the platform assembles the path for you from the repository (every top-level module directory and submodule is scanned). See [Odoo.sh and deployment](odoo-sh-and-deployment.md).

## Python dependencies

A module declares pip dependencies with `external_dependencies` in its manifest:

```python
'external_dependencies': {'python': ['openpyxl'], 'bin': ['pdftotext']},
```

Odoo checks them at install time and refuses with an explicit error if one is missing. This only protects the machine where you install; a missing package on production after a deploy shows up as a failed upgrade. Keep a `requirements.txt` next to the modules and install it as part of every deploy.

## Pitfalls

{% hint style="warning" %}
A duplicate module name does not raise an error. The earlier path entry wins. If a change in your fork "does nothing", print the module's real location from a shell: `import odoo.addons.library; print(odoo.addons.library.__path__)`.
{% endhint %}

- **Module added but not listed.** The Apps list is cached in `ir.module.module`. After adding a directory, update the list (Apps menu in developer mode) or start with `-u base`. Merely restarting does not rescan for the web UI.
- **Directory name with a hyphen** (`library-portal`) is not importable. Rename the directory; the Git repository name can keep the hyphen.
- **Symlinks** work, but deployments that copy trees without following links lose them silently.
- **Stale `.pyc` or removed modules.** Deleting a directory of an installed module leaves the database record in state `installed`; the next start logs "module not found" and later updates can fail on its dependants. Uninstall first, then remove the code.
- **Nested addons directories.** Putting `custom/` inside `addons/` of the core checkout makes upgrades of the checkout destroy or conflict with your code.

## Try it

```bash
# which directories does this server scan?
odoo-bin shell -d dev <<'PY'
from odoo.modules import module
print(module.ad_paths)
PY
# where does a given module come from?
odoo-bin shell -d dev <<'PY'
print(env['ir.module.module'].search([('name', '=', 'library')]).mapped('state'))
import odoo.addons.library as m; print(m.__path__)
PY
```
