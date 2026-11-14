---
description: Every field type, its attributes, and when to choose it.
---

# Fields reference

Choosing the right field type and attributes decides the column type, the index, the UI widget, and how the field behaves in search, grouping, and export. This chapter lists the types in the Odoo 18 `odoo/fields.py` and the attributes that matter in daily work.

## Basic types

| Type | Column | Notes |
|---|---|---|
| `Boolean` | `bool` | Never `NULL` semantics; unset reads `False`. |
| `Integer` | `int4` | `aggregator` defaults to sum. |
| `Float` | `numeric` | `digits=(total, decimals)` or a `decimal.precision` name. |
| `Monetary` | `numeric` | Needs `currency_field` (default `currency_id`) on the model. |
| `Char` | `varchar` | `size`, `translate`, `trim`. |
| `Text` | `text` | Multi-line, `translate` supported. |
| `Html` | `text` | Sanitised on write unless `sanitize=False`. |
| `Date` / `Datetime` | `date` / `timestamp` | Datetime is stored in UTC and shown in the user's timezone. |
| `Binary` / `Image` | attachment or `bytea` | `attachment=True` by default; stored as `ir.attachment`. |
| `Selection` | `varchar` | List of `(value, label)` pairs, or a method name. |
| `Json` | `jsonb` | Opaque to search except via `=` on the whole value. |
| `Properties` | `jsonb` | User-defined fields, defined on a parent record. |
| `Reference` | `varchar` | Value is `"model,id"`. |

Relational types: `Many2one` (FK column), `One2many` (inverse of a Many2one, no column), `Many2many` (relation table), `Many2oneReference` (id column plus a model field).

```python
class Book(models.Model):
    _name = 'library.book'
    _description = 'Book'

    title = fields.Char(required=True, index='trigram', translate=True)
    isbn = fields.Char(copy=False)
    pages = fields.Integer()
    price = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one('res.currency')
    state = fields.Selection(
        [('draft', 'Draft'), ('available', 'Available'), ('lost', 'Lost')],
        default='draft', required=True)
    author_id = fields.Many2one('res.partner', ondelete='restrict', index=True)
    tag_ids = fields.Many2many('library.tag')
    loan_ids = fields.One2many('library.loan', 'book_id')
```

## Attributes that apply to every field

From the `Field` class in the 18 source:

- `string`, `help`: label and tooltip.
- `required`, `readonly`: `readonly` is a UI and write-through rule on the field definition, not a database constraint. Server code can still write it.
- `default`: a value or a callable `lambda self: ...`.
- `store`: `False` for non-stored computed or related fields.
- `index`: see below.
- `copy`: whether `copy()` duplicates the value. `True` by default for simple fields, `False` for One2many, computed, and related fields.
- `groups`: comma-separated group XML ids. Users outside the groups cannot read or write the field, and it disappears from the form view. This is field-level access, not record-level.
- `compute`, `inverse`, `search`, `related`, `compute_sudo`, `precompute`, `recursive`: see the computed fields chapter.
- `aggregator`: how `read_group` aggregates the field (`sum`, `avg`, `max`, `min`, `count_distinct`, and others PostgreSQL allows).
- `group_expand`: name of a method that adds empty groups to grouped views, used by kanban stages.
- `prefetch`: set `False` for heavy fields you do not want fetched along with their siblings.
- `company_dependent`: the value is stored per company, in a jsonb column in 18.
- `tracking`: from `mail.thread`; see the mail chapter.

{% hint style="info" %}
**Versions.** In 18 the aggregation attribute is `aggregator`; passing `group_operator` still works but emits a `DeprecationWarning` and is mapped to `aggregator` (confirmed in the 18 source). In 16 and 17 the name is `group_operator`.
{% endhint %}

## Index values

`index` accepts a string, not only `True`. The 18 source maps `index=True` to `'btree_not_null'` (btree that skips NULL rows). Other values are `'btree'`, and `'trigram'` for `ilike` search on Char and Text.

Index what you filter or sort on: foreign keys you search through, state fields with selective values, and Char fields searched with `ilike`. Do not index everything; every index slows writes and costs disk.

## Selection

```python
state = fields.Selection([...], default='draft')
```

When a module extends a selection with `selection_add`, it must say what happens to existing rows if that module is uninstalled:

```python
state = fields.Selection(selection_add=[('archived', 'Archived')],
                         ondelete={'archived': 'set default'})
```

The 18 source requires an `ondelete` policy for added values on required fields and rejects policies that are invalid for the field. A dynamic list is a method name string: `selection='_get_states'`.

## Many2one

Key attributes: `comodel_name`, `domain`, `context`, `ondelete`, `check_company`, `auto_join`.

- `ondelete`: `set null` (default for optional), `restrict`, `cascade`. Required fields must not use `set null`.
- `domain` on the field is a UI filter plus a default for search; it is not enforced on write. Enforce with a constraint.
- `check_company=True` validates that the target belongs to the same company, using a `_check_company` pass on write.

## One2many and Many2many

- `One2many(comodel, inverse_name)`: the inverse Many2one must exist. No column. Writes go through commands.
- `Many2many(comodel, relation, column1, column2)`: the relation table name is derived from the two model names if omitted. When two Many2many fields on the same pair of models need separate storage, name `relation` explicitly or they share one table.
- Neither can be sorted in SQL.

## Monetary and Float

`Monetary` rounds by the currency's rounding on write. Reading it as `Float` elsewhere loses that rounding. `Float(digits=...)` rounds on write by the precision; use `float_compare`, `float_is_zero`, and `float_round` from `odoo.tools` to compare. Never compare floats with `==`.

## Date and Datetime

`Date.today()`, `Date.context_today(record)`, `Datetime.now()` and `Datetime.to_datetime()` are the safe helpers. `Datetime.now()` is naive UTC. `Date.context_today(record)` gives the date in the user's timezone, which differs from `Date.today()` near midnight.

## Choosing: quick rules

- Status with a fixed set of values: `Selection`, not `Char`.
- Reference to another record: `Many2one`, not an integer.
- Free structured data per record that users define: `Properties`, not Json.
- Long text indexed for search: `Char` with `index='trigram'`.
- Money: `Monetary`, never `Float`.

## Pitfalls

{% hint style="warning" %}
Changing a field's type on an existing database does not migrate data automatically for all type pairs. Changing `Integer` to `Float` works; `Char` to `Many2one` does not. Write a migration script.
{% endhint %}

- `required=True` on a field with existing NULL rows breaks module update. Add a default or a pre-migration.
- `readonly=True` does not stop `write()` from Python. Use access rights or `groups` to block writes.
- A One2many without a matching Many2one raises at registry load.
- `default=fields.Date.today()` with parentheses evaluates once at import. Pass the callable: `default=fields.Date.today`.
- `translate=True` on Char changes the column to jsonb in 16 and later; raw SQL against it must use the language key.
- A `Many2many` shared relation table between two fields causes each to show the other's links.

## Try it

List the attributes a field carries on a development shell:

```python
f = env['res.partner']._fields['name']
print(f.type, f.required, f.index, f.translate)
print(env['res.partner'].fields_get(['name'], attributes=['type', 'string', 'required']))
```
