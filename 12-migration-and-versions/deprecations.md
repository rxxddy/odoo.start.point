---
description: "Finding deprecated APIs before they are removed, a replacement table with the version of each deprecation, and the upgrade_code command that rewrites most of them."
---

# Deprecations

Odoo marks an API as deprecated, logs a warning for a release or two, then removes it. The cost of ignoring the warnings is paid at the next upgrade, all at once. Many deprecations in the source carry their version in the message (`Since 20.0, use ...`, `deprecated since 18.0`), so the source itself tells you how long you have.

## Surface the warnings

```bash
odoo-bin -d dev -u library --stop-after-init --log-level=warn 2>&1 | grep -iE "deprecat|since (1[6-9]|20)"
```

Run the test suite with warnings visible too: many deprecations are raised only when the code path executes. To turn them into failures in tests, run Python with `-W error::DeprecationWarning`.

## Replacement table

| Old | New | Deprecated or removed | Checked in |
| --- | --- | --- | --- |
| `attrs`, `states` in views | `invisible`, `readonly`, `required` expressions | removed in 17.0 | 17.0 view validation |
| `name_get()` | `display_name`, `_compute_display_name` | deprecated 17.0, removed 18.0 | 17.0 and 18.0 `models.py` |
| `_name_search` (old signature) | `_search_display_name(operator, value)` returning a domain | 18.0 | 18.0 `models.py` |
| `<tree>`, `view_mode` `tree` | `<list>`, `list` | 18.0 | 18.0 `ir_ui_view.py`, script `17.5-01-tree-to-list.py` |
| `ir.property` rows | company-dependent jsonb column | removed 18.0 | 18.0 has no `ir_property.py` |
| `check_access_rights`, `check_access_rule`, `_filter_access_rules` | `check_access`, `has_access`, `_filtered_access` | deprecated 18.0, removed 20 | 18.0 and 20 `models.py` |
| `@route(type='json')` | `@route(type='jsonrpc')` | deprecated alias since 19.0 | 20 `routing_map.py`, script `18.1-02` |
| `_sql_constraints = [...]` | `_name = models.Constraint(...)` | 19.0 | script `18.1-00-sql-constraint.py` |
| `self._cr`, `self._uid`, `self._context` | `self.env.cr`, `self.env.uid`, `self.env.context` | deprecated 19.0 | 20 `models.py`, script `18.5-00` |
| `request.cr`, `request.uid`, `request.context` | `request.env.cr`, `.uid`, `.context` | deprecated 19.0 | 20 `http/requestlib.py` |
| `ir.model.access` + `ir.rule` data | `ir.access` | 20 | script `19.4-00-ir-access.py` |
| `check_field_access_rights` | `check_field_access(field, operation)` | 20 | 20 `models.py` |
| `registry.clear_cache` | `transaction.invalidate_ormcache` | 20 | script `19.4-00` |
| `from odoo.tools import ormcache` | `from odoo.api import ormcache` | 20 | 20 `tools/__init__.py` |
| `type="base64"` in XML data | `type="bytes"` | 20 | 20 `tools/convert.py` |

A row marked "Checked in 20" was read in the Odoo 20 tree. Odoo 19 itself was not installed, so 19 entries rest on the deprecation messages and scripts.

## Let the scripts rewrite what they can

Odoo 18 and later include `odoo-bin upgrade_code`, which applies the scripts in `odoo/upgrade_code/` to the Python, XML, JS, CSS and CSV files of every addon on the addons path:

```bash
# list what would change, rewrite nothing
odoo-bin upgrade_code --addons-path=./my_addons --from 17.5 --dry-run

# apply one script
odoo-bin upgrade_code --addons-path=./my_addons --script tree-to-list

# apply every script from a version up to the current one
odoo-bin upgrade_code --addons-path=./my_addons --from 17.5
```

The options are `--script`, `--from`, `--to` (default: the running server's version), `--glob` to restrict files, `--dry-run` and `--addons-path`. The command exits with status 1 when it changed files, which is useful in CI. Read the diff: the docstring of the command says the scripts are "best-effort" and "not silver bullets". Commit the result on its own so the mechanical change is reviewable.

## Replace in an order that can be reviewed

1. Scripted XML and Python rewrites in one commit.
2. Hand-written API replacements in a second commit, with tests.
3. JavaScript last. A change of framework version is a rewrite, not a port, so keep it out of the mechanical commits.

## Writing code that is deprecated later

- Use the public ORM (`search`, `browse`, `write`, `_read_group`) and stay away from private helpers whose names start with `_` unless a chapter names them.
- Prefer registry entries and subclasses to `patch()` in JavaScript.
- Keep raw SQL in one method per model and build it with `SQL`.

## Pitfalls

- Silencing warnings in `odoo.conf` to quiet a noisy log removes the early signal.
- Overriding `name_get` on 18 or later does nothing, because the method no longer exists.
- Assuming `read_group` and `_read_group` are the same API: the web client uses `read_group`, Python code should use `_read_group`.
- Running `upgrade_code` without `--dry-run` on a dirty working tree mixes your edits with its rewrites.

## Try it

1. Run `odoo-bin upgrade_code --addons-path=... --from 17.5 --dry-run` on a copy of a 17.0 module and read the list.
2. Run it for real on a branch and diff.
3. Grep the result for `attrs=`, `states=` and `name_get` and fix what the scripts could not.

<details>

<summary>Solution notes</summary>

1. The dry run lists the files the scripts would rewrite, grouped by script.
2. Expect `<tree>` to `<list>` changes in XML, `view_mode` values, and `tree_view_ref` context keys.
3. `attrs` and `states` are not converted by a script in the 20 tree, so those are manual.

</details>
