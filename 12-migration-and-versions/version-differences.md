---
description: "The changes that break code, by version."
---

# Version differences, 16 to 20

This page lists what actually breaks when a custom module written for 16.0 is loaded on 17.0 and 18.0. It comes from diffing real 16.0 modules against their 18.0 upgrades, and the Odoo 18 items were checked against the 18.0 source. Odoo 19 and 20 are not covered until they can be verified.

## 16.0 to 17.0

### Views: `attrs` and `states` are gone

In 16.0 you wrote `attrs="{'invisible': [('state', '=', 'done')]}"`. From 17.0 the attributes `invisible`, `readonly`, `required` and `column_invisible` take a Python expression evaluated in the client.

```xml
<!-- 16.0 -->
<field name="note" attrs="{'invisible': [('state', '=', 'done')], 'required': [('kind', '=', 'x')]}"/>
<button name="action_close" states="open,late"/>

<!-- 17.0 and later -->
<field name="note" invisible="state == 'done'" required="kind == 'x'"/>
<button name="action_close" invisible="state not in ('open', 'late')"/>
```

Conversion rules that matter: `('a', '=', False)` becomes `not a`; `('a', 'in', [1, 2])` becomes `a in (1, 2)`; the domain-level `|` and `&` become `or` and `and`; `states="x"` becomes `invisible="state not in ('x')"`. Dotted paths work only on fields that are present in the view, so add the field as `invisible="1"` if you reference it.

{% hint style="danger" %}
On 17.0 and later a view that still has `attrs` fails validation at install time. On 16.0 the opposite is true, so one branch cannot serve both.
{% endhint %}

### Views: `<tree>` becomes `<list>`

The root tag of list views is `<list>` from 17.0 (`<tree>` is still accepted as an alias in 17.0 and 18.0, but new code uses `list`). The action `view_mode` value is `list` in 18.0; `tree` no longer works in `view_mode` strings. Search the codebase for `view_mode` and `view_type` values together with the XML.

### `name_get` and `name_search`

`name_get()` was deprecated in 17.0. The display name is now the stored-less computed field `display_name`, and you override `_compute_display_name`:

```python
@api.depends('name', 'isbn')
def _compute_display_name(self):
    for book in self:
        book.display_name = f"[{book.isbn}] {book.name}" if book.isbn else book.name
```

`name_search` was replaced by `_search_display_name(self, operator, value)`, which returns a domain instead of a list of tuples. Both new hooks are present in the 18.0 `models.py`.

### Other 17.0 changes

- `@api.model_create_multi` is the expected signature for `create`; single-record `create(vals)` overrides still work but receive lists internally.
- JavaScript: legacy widgets (`web.Widget`, `AbstractField`, `FormController` classic classes) were removed in favour of OWL components registered in registries. Any custom JS from 16.0 is a rewrite, not a port.
- `ir.ui.view` `type="qweb"` templates: `t-esc` still works; `t-out` is preferred.

## 17.0 to 18.0

### `read_group` and `_read_group`

`_read_group(domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None)` is the new private API. It returns a list of tuples, one value per `groupby` item then one per aggregate, and the aggregates are strings such as `'amount:sum'` or `'__count'`.

```python
rows = self.env['library.loan']._read_group(
    [('state', '=', 'open')],
    groupby=['member_id'],
    aggregates=['__count', 'fee:sum'],
)
for member, count, fee in rows:   # member is a recordset
    ...
```

`read_group` still exists for the web client, but calling it from Python code is deprecated. Group keys are records, not `(id, name)` pairs; code that did `row['member_id'][0]` breaks.

### Search domains and `search_count`

Domain leaves with `False` or `None` operators are normalised more strictly. Parent/child leaves that relied on `child_of` with an empty list now return no records instead of raising.

### Access and `check_access`

`check_access_rights` and `check_access_rule` are replaced by `check_access(operation)` and `has_access(operation)` on recordsets. The older methods remain as thin wrappers and emit warnings.

### Other 18.0 items seen in real upgrades

- `<field name="active_id"/>` style `context` keys in actions: use `active_ids` explicitly.
- `@api.depends` on `display_name` needs the dependencies listed on `_compute_display_name`.
- `Query` and `SQL` objects: raw `self.env.cr.execute("..." % ...)` string composition is flagged; use `SQL("... %s", value)` from `odoo.tools`.
- The accounting `account.invoice` leftovers (`account.move.type`, `invoice_line_ids` conventions) changed again; test any report or mail template that reads them.

## Pitfalls

- Fixing the XML and forgetting the Python. The views install, the first button click fails on a removed method.
- Mixing `tree` and `list` in `view_mode` across actions, which leaves some menus opening blank.
- Trusting deprecation warnings. Run the test suite with `--log-level=warn` and grep for `DeprecationWarning` before and after.

## Versions

| Topic | 16.0 | 17.0 | 18.0 |
|---|---|---|---|
| Field visibility | `attrs`, `states` | expressions | expressions |
| List view tag | `tree` | `list` (alias ok) | `list` |
| Display name | `name_get` | `_compute_display_name` | `_compute_display_name` |
| Name search | `name_search` | `_search_display_name` | `_search_display_name` |
| Grouping API | `read_group` | `_read_group` introduced | `_read_group` with aggregates strings |

## Try it

```bash
grep -rnE "attrs=|states=|<tree|name_get|read_group\(" my_addons --include=*.xml --include=*.py
```

Every hit is a line to review before you bump the version in the manifest.
