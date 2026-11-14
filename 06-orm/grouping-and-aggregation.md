---
description: read_group, _read_group, and aggregate queries.
---

# Grouping and aggregation

When you need counts, sums, or averages over many records, do it in PostgreSQL, not in a Python loop. Odoo 18 has two entry points: the public `read_group`, which serves the web client, and `_read_group`, the typed API you use in Python code.

## _read_group

Signature in the 18 source:

```python
_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None)
```

It returns a list of tuples: the group values first, then the aggregate values, in the order you asked for them. Many2one group values come back as recordsets, not `(id, name)` pairs.

```python
rows = self.env['library.loan']._read_group(
    domain=[('state', '=', 'late')],
    groupby=['member_id', 'due_date:month'],
    aggregates=['__count', 'fine:sum', 'book_id:count_distinct'],
    order='member_id',
)
for member, month, loans, fines, books in rows:
    ...
```

Rules from the source:

- A `groupby` item is `'field'` or `'field:granularity'`. Granularities for date and datetime are `day`, `week`, `month`, `quarter`, `year`; the source also defines number-style granularities (such as day of week) in `READ_GROUP_NUMBER_GRANULARITY`.
- An `aggregates` item is `'field:agg'` or the special `'__count'`. Aggregate functions are those of PostgreSQL, plus `count_distinct` and `recordset`.
- `recordset` as an aggregate returns the related records of each group as a recordset, handy when you need both the number and the records.
- `having` is a domain over the aggregates, for example `[('fine:sum', '>', 100)]`.
- With no `groupby`, PostgreSQL still returns one row, and so does this method, even on an empty set.
- When the domain is provably false, the method returns early without querying.

Access is checked through `check_access('read')` on the model, and the domain gets record rules like `search`.

### Typical patterns

Count per key into a dict:

```python
counts = {
    book: count
    for book, count in self.env['library.loan']._read_group(
        [('book_id', 'in', books.ids)], ['book_id'], ['__count'])
}
```

Total of one field with no grouping:

```python
[(total,)] = self.env['library.loan']._read_group(domain, [], ['fine:sum'])
```

Doing this over a stored computed field works. Over a non-stored field it fails, because the aggregate is computed by SQL.

## read_group

```python
read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True)
```

It returns a list of dicts and exists mainly for the web client's list, pivot, graph, and kanban views. The dicts contain the group values, `__domain` (the domain selecting that group), `__count` (named `<field>_count` in lazy single groupby mode), and the aggregated fields. With `lazy=True` only the first `groupby` level is evaluated, so drill-down is a second call using `__domain`.

Prefer `_read_group` in module code: it is typed, returns recordsets for relations, and supports `having`. Use `read_group` only when you need the web-client dict shape, for example to feed a custom view, or when the code must run on 16.

{% hint style="info" %}
**Versions.** `_read_group` exists in 16, 17, and 18, but the shape changed. In 16 it was a private helper returning dicts with the old `read_group` conventions. From 17 it is the tuple-based API with the `aggregates` list. Code written for 17 and 18 does not run on 16. In 18 the field attribute for the default aggregate is `aggregator`; `group_operator` is deprecated (a `DeprecationWarning` in the source), and in 16 and 17 `group_operator` is the name.
{% endhint %}

## Field-level aggregation

The `aggregator` attribute of a field sets what the web client uses when it totals that column, and what `read_group` uses for it when you list the field in `fields` without an explicit function:

```python
fine = fields.Monetary(aggregator='sum')
rating = fields.Float(aggregator='avg')
days_late = fields.Integer(aggregator=False)   # no total shown
```

Set it to a falsy value to stop a column from being summed in lists, which is right for rates, percentages, and ids.

## Grouping on related and computed fields

Group on stored fields. Related fields that are stored (`store=True`) group like normal columns. A Many2one path in `groupby` such as `'member_id.country_id'` is not supported; group on `member_id` and read the country in Python, or add a stored related field `member_country_id`.

Fields whose `groupable` description is false in `fields_get` cannot be grouped. Non-stored computed fields are the usual cause.

## group_expand and empty groups

Kanban stages show columns with no records. That is done with `group_expand` on the grouping field, a method name that returns the extra values:

```python
stage_id = fields.Many2one('library.stage', group_expand='_read_group_stage_ids')

@api.model
def _read_group_stage_ids(self, stages, domain):
    return stages.search([], order=stages._order)
```

It applies to `read_group` and the web client path, not to a plain `_read_group` call.

## In-memory grouping

For records already loaded, use `recordset.grouped('field')` or `grouped(lambda r: ...)`; it returns a dict of key to recordset and runs no SQL. Choose by size: SQL for scans over many rows, `grouped` when the set is already in memory.

## Pitfalls

{% hint style="warning" %}
`_read_group` returns tuples ordered by your `groupby` then `aggregates`. Unpacking in the wrong order gives no error when types are compatible, and wrong numbers.
{% endhint %}

- A group value for an empty Many2one is an empty recordset, not `False`. For dates, an empty value comes back as `False`.
- Date groups return the first day of the period as a date or datetime, not a label. Format it yourself.
- Datetime grouping uses the user's timezone from the context (`tz`). Running the same call in a cron with no `tz` groups on UTC and shifts rows near midnight.
- Lazy `read_group` with a list of `groupby` returns only the first level. Passing `lazy=False` returns all levels in one go but loses the `__domain` drill-down convenience.
- Do not loop over `read_group` results to build a `search` per group. The `__domain` is for one-off drill-downs.
- `__count` is the count of rows in the group, not distinct values. Use `field:count_distinct` for that.

## Try it

```python
rows = env['res.partner']._read_group(
    [('active', '=', True)], ['country_id'], ['__count'], order='__count desc', limit=5)
for country, count in rows:
    print(country.display_name or 'none', count)
```
