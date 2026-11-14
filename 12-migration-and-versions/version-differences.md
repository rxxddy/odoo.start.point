---
description: "Changes that break module code between Odoo 16 and 20, with the version each one landed in and where it was verified."
---

# Version differences, 16 to 20

This page lists changes that break custom module code, grouped by the release that introduced them. Each item was checked in the source of at least one release: the 16.0 and 17.0 branches, the 18.0 source, and the Odoo 20 tree. Odoo 19 was not available as a full checkout. Items for 19 come from the deprecation markers and the `upgrade_code` scripts shipped in the 20 tree, and are labelled that way.

## Reading the `upgrade_code` version numbers

Odoo ships rewrite scripts in `odoo/upgrade_code/`, named `<version>-<name>.py`. The prefix is the master development version in which the change landed, not a release number. The branch listings show the mapping: the 18.0 branch contains only `17.5-*` scripts, the 19.0 branch contains `17.5` to `18.5`, and the 20 tree adds `19.1` to `20.0`. So `17.5` means "in Odoo 18", `18.x` means "in Odoo 19", `19.x` and `20.0` mean "in Odoo 20". The upgrade-a-module chapter shows how to run them.

## 16.0 to 17.0

**Views: `attrs` and `states` are removed.** The 17.0 view validation raises `Since 17.0, the "attrs" and "states" attributes are no longer used.` (`ir_ui_view.py`). `invisible`, `readonly`, `required` and `column_invisible` take expressions:

```xml
<!-- 16.0 -->
<field name="note" attrs="{'invisible': [('state', '=', 'done')], 'required': [('kind', '=', 'x')]}"/>
<button name="action_close" states="open,late"/>

<!-- 17.0 and later -->
<field name="note" invisible="state == 'done'" required="kind == 'x'"/>
<button name="action_close" invisible="state not in ('open', 'late')"/>
```

Conversion: `('a', '=', False)` becomes `not a`, `('a', 'in', [1, 2])` becomes `a in (1, 2)`, domain operators `|` and `&` become `or` and `and`. A field referenced in an expression must be present in the view; add it with `invisible="1"` if needed.

**`_read_group` gets its aggregate-based signature.** 16.0 has `_read_group(domain, fields, groupby, offset, limit, orderby, lazy)`. From 17.0 it is `_read_group(domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None)`, returning tuples (group values first, then aggregates such as `'__count'` or `'amount:sum'`). Many2one group keys are records. `read_group` remains for the web client.

**`name_get` is deprecated.** The 17.0 `name_get` emits `Since 17.0, deprecated method, read display_name instead`. `_compute_display_name` already exists in 16.0. `_name_search` changes signature in 17.0 (`name, domain, operator, limit, order` instead of `name, args, operator, limit, name_get_uid`).

**JavaScript.** The legacy widget layer leaves the backend client; custom JavaScript from 16 is a rewrite. See the frontend part.

## 17.0 to 18.0

**`<tree>` becomes `<list>`.** In 18.0 `ir.ui.view.type` has `list` and no `tree` (17.0 has `tree`), and the 18.0 branch ships the script `17.5-01-tree-to-list.py` to convert arches, `view_mode` values, xpaths and `tree_view_ref` context keys. Run it instead of editing by hand.

**`name_get` and `_name_search` are removed.** 18.0 has `_compute_display_name`, `_search_display_name(operator, value)` (returns a domain) and `name_search`. A module that overrides `name_get` loses the override silently.

```python
@api.depends("name", "isbn")
def _compute_display_name(self):
    for book in self:
        book.display_name = f"[{book.isbn}] {book.name}" if book.isbn else book.name
```

**Access check methods.** `check_access_rights`, `check_access_rule` and `_filter_access_rules` are deprecated since 18.0 in favour of `check_access(operation)`, `has_access(operation)` and `_filtered_access(operation)`.

**`ir.property` is gone.** `ir_property.py` exists on 16.0 and 17.0 and not on 18.0. Company-dependent fields are stored as a jsonb column on the model table (keys are company ids, defaults come from `ir.default`). SQL written against `ir_property` has to be rewritten.

**`SQL` objects.** `odoo.tools.SQL` exists from 17.0. Build queries with it rather than string formatting.

## 18.0 to 19.0 (from the 20 tree)

- **`@route(type='json')` becomes `type='jsonrpc'`.** The 20 router logs `Since 19.0, @route(type='json') is a deprecated alias to @route(type='jsonrpc')`. Script `18.1-02-route-jsonrpc.py` replaces it in controllers.
- **`_sql_constraints` become `models.Constraint` attributes.** Script `18.1-00-sql-constraint.py` rewrites `_sql_constraints = [(name, definition, message)]` into `_name = models.Constraint(definition, message)`.
- **`self._cr`, `self._uid`, `self._context` are deprecated** (`Deprecated since 19.0, use self.env.cr directly`). Script `18.5-00-deprecated-properties.py` rewrites them to `.env.cr`, `.env.uid`, `.env.context`. `request.cr`, `request.uid` and `request.context` carry the same deprecation in the HTTP layer.
- Search view date filters and domain dynamic dates have rewrite scripts (`18.5-00-domain-dynamic-dates.py`).

## 19.0 to 20.0 (from the 20 tree)

- **ACLs and record rules become `ir.access`.** Script `19.4-00-ir-access.py` converts `ir.model.access` and `ir.rule` data. The combining rule changes: permissions are OR-ed, restrictions AND-ed, no permission means no access. See the security chapters.
- **Groups use privileges.** `res.groups.privilege_id` replaces `category_id`; `user_ids` replaces `users`; the user's groups are `group_ids`/`all_group_ids` instead of `groups_id`.
- **OWL 3.** `static props` becomes `useProps`, `useState` becomes `proxy`, refs are signals, templates use `this.`. Script `owl3-migration.py` rewrites part of it. See the OWL 3 chapter.
- **`type="base64"` in XML data files becomes `type="bytes"`** (`Since 20.0, use type=bytes instead of type=base64` in `tools/convert.py`; script `19.3-00-base64-in-xml.py`).
- **`registry.clear_cache` becomes `transaction.invalidate_ormcache`** (script `19.4-00-ormcache-on-transaction.py`), and `ormcache` is imported from `odoo.api` (`Since 20.0 import ormcache from odoo.api`).
- **The deprecated access methods are gone.** `check_access_rights`, `check_access_rule`, `_filter_access_rules` and `check_field_access_rights` no longer exist in the 20 `orm/models.py`; `check_access`, `has_access`, `_filtered_access` and `check_field_access(field, operation)` remain. `_check_access` is deprecated in favour of `Model._access_domain` (`Since 20.0, use Model._access_domain instead`) and `_check_field_access` in favour of `check_field_access()`.
- **`Query` and `SQL`.** `Query` methods accept only `SQL` arguments in 20 (several `Since 20.0` warnings in `orm/query.py`), and `tools.sql` helpers are renamed (`escape_like_value`).
- **`concat()` and `union()`** warn when called with one iterable or on an empty recordset.
- **`_rec_names_search` is a tuple** (script `19.5-00-tuple-rec_names_search.py`), icons move from FontAwesome markup to Material Symbols (`19.5-00-material-symbols-icons.py`), and search date filters lose per-view month and year attributes (`20.0-00-search-date-filters.py`).

## Summary table

| Topic | 16.0 | 17.0 | 18.0 | 19.0 | 20 |
| --- | --- | --- | --- | --- | --- |
| Field visibility in views | `attrs`, `states` | expressions | expressions | expressions | expressions |
| List view tag | `tree` | `tree` | `list` | `list` | `list` |
| `_read_group` signature | old | aggregates | aggregates | aggregates | aggregates |
| `name_get` | yes | deprecated | removed | removed | removed |
| `_search_display_name` | no | no | yes | yes | yes |
| Company-dependent storage | `ir.property` | `ir.property` | jsonb column | jsonb | jsonb |
| Access check | `check_access_rights` | `check_access_rights` | `check_access` (old names deprecated) | `check_access` | `check_access`; old names removed |
| Route type for JSON | `json` | `json` | `json` | `jsonrpc` (`json` alias) | `jsonrpc` |
| Constraints | `_sql_constraints` | `_sql_constraints` | `_sql_constraints` | `models.Constraint` | `models.Constraint` |
| ACL and rules | `ir.model.access` + `ir.rule` | same | same | same | `ir.access` |
| Frontend | OWL 2 + legacy | OWL 2 | OWL 2 | OWL 2 | OWL 3 |

Cells for 19 are inferred from the deprecation markers and script prefixes and were not run on a 19 install.

## Pitfalls

- Fixing the XML and forgetting the Python. The views load, the first button click fails on a removed method.
- Overriding `name_get` on 18 or later. The method is gone and the override does nothing.
- Running upgrade scripts blindly. They are best-effort rewrites; review the diff.
- Treating a deprecation warning as optional. Each `Since X` marker above is a removal waiting for the next release.

## Try it

Search your module for what the next version will break:

```bash
grep -rnE "attrs=|states=|<tree|name_get|_sql_constraints|type=.json|\._cr\b|\._uid\b|\._context\b|ir\.model\.access|ir\.rule" my_addons --include=*.xml --include=*.py --include=*.csv
```

Every hit is a line to review before you bump the version in the manifest.
