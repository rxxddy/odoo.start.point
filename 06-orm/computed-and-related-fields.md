---
description: "depends, stored vs not, inverse, search, and dependency pitfalls."
---

# Computed and related fields

A computed field's value comes from a Python method, not from user input. A related field is a computed field that follows a path through relations. Both depend on a correct dependency declaration: get `@api.depends` wrong and stored values go stale without any error.

## A minimal computed field

```python
class Loan(models.Model):
    _name = 'library.loan'
    _description = 'Loan'

    due_date = fields.Date()
    returned_on = fields.Date()
    days_late = fields.Integer(compute='_compute_days_late', store=True)

    @api.depends('due_date', 'returned_on')
    def _compute_days_late(self):
        today = fields.Date.context_today(self)
        for loan in self:
            end = loan.returned_on or today
            loan.days_late = max((end - loan.due_date).days, 0) if loan.due_date else 0
```

Rules the framework enforces:

- The method must assign the field on every record of `self`, including the cases where the result is "empty". Skipping a record raises on read.
- The method receives a recordset. Loop over it, or write the logic over the whole set.
- Do not call `write` or `create` on self inside a compute. Assign the attribute.

## Dependencies

`@api.depends` takes field names and dotted paths:

```python
@api.depends('line_ids.amount', 'partner_id.country_id')
def _compute_total(self): ...
```

For stored fields, a change of any listed field triggers recomputation at the next flush. For non-stored fields, it invalidates the cache.

Miss a dependency and the stored value stays wrong until something else touches the record. Typical causes:

- Reading a field in the method that is not in `depends`.
- Depending on `line_ids` when you read `line_ids.amount`. The first only reacts to adding or removing lines, not to amount changes.
- Using a field of another record found by `search` inside the method. The ORM cannot see that dependency at all.

`@api.depends_context('company', 'uid')` declares context keys that change the result of a non-stored compute, so the cache is keyed correctly.

## Stored versus non-stored

| | `store=False` (default) | `store=True` |
|---|---|---|
| Computed when | read, per cache miss | dependency changes, at flush |
| Searchable | only with `search=` | yes, as a column |
| Groupable | no | yes |
| Indexable | no | yes |
| Cost | on every uncached read | on writes of dependencies |

Store a field when you search, sort, or group on it, or when the computation is expensive and the dependencies change rarely. Keep it non-stored when the value depends on "now", the current user, or context, since a stored value would be stale the next day.

{% hint style="warning" %}
A stored field depending on `fields.Date.today()` never updates by itself. The ORM only recomputes on dependency changes. Compute it non-stored, or recompute it with a cron.
{% endhint %}

## precompute and compute_sudo

- `precompute=True` computes a stored field before the INSERT during `create`, so it exists in the first write and can carry `required=True` without a default. Dependencies must then be readable from the values being created.
- `compute_sudo` defaults to `True` for stored computed fields and related fields (confirmed in the 18 source: `attrs.get('compute_sudo', attrs.get('related_sudo', True))`). The method runs as superuser, so users who cannot read the dependencies still see the result. Set `compute_sudo=False` when the result must respect the caller's rights.

## inverse

An `inverse` method makes a computed field writable. It runs after `write` on the field and must push the value back into the real source fields.

```python
full_name = fields.Char(compute='_compute_full_name', inverse='_inverse_full_name')

def _inverse_full_name(self):
    for rec in self:
        first, _sep, last = (rec.full_name or '').partition(' ')
        rec.first_name, rec.last_name = first, last
```

Without `inverse`, writing a non-stored computed field has no lasting effect. For a stored computed field, the written value is kept until the next recomputation overwrites it, which is a confusing half-state; add an inverse or make the field readonly.

## search

A non-stored computed field is searchable only if you provide `search`. The chapter on search and domains shows the method shape: it receives `(operator, value)` and returns a domain over stored fields.

## Related fields

```python
author_country_id = fields.Many2one(related='author_id.country_id')
author_name = fields.Char(related='author_id.name', store=True)
```

A related field is a compute plus an inverse plus a search, generated from the path. Defaults from the 18 source and framework behaviour:

- `readonly=True` by default. Pass `readonly=False` to let a write go through to the target record.
- `store=False` by default. With `store=True` it is a real column that recomputes when the path changes.
- `copy=False` by default.
- `compute_sudo` is on, so the value shows even when the user cannot read the target model. Be careful when the path crosses into data the user should not see.
- Attributes such as `string`, `help`, `required` are taken from the target field unless overridden.

Writing a related field with `readonly=False` writes to the target record, possibly shared by many records. Writing `author_name` on one book renames the author for every book.

## Recursive dependencies

For hierarchies (`parent_id`, `child_ids`), set `recursive=True` on the field and depend on the parent path:

```python
@api.depends('parent_id.level')
def _compute_level(self): ...
level = fields.Integer(compute='_compute_level', store=True, recursive=True)
```

Without `recursive=True`, a dependency chain that returns to the same field raises a cycle error at setup.

## Performance

- Write computes over the whole recordset. A `search` per record inside the loop multiplies queries.
- For aggregates over children, use `_read_group` once for all of `self`, then assign:

```python
@api.depends('loan_ids.fine')
def _compute_total_fines(self):
    data = dict(self.env['library.loan']._read_group(
        [('member_id', 'in', self.ids)], ['member_id'], ['fine:sum']))
    for member in self:
        member.total_fines = data.get(member, 0.0)
```

- Stored fields with deep paths recompute on every change of any path element. Keep stored dependency chains short.
- A stored compute on a model with millions of rows makes module installation slow, since it fills the whole column. Plan for it, or add the field via a pre-install SQL column and a batch fill.

## Pitfalls

- Forgetting to assign the field on some branch: `ValueError: Compute method failed to assign ...`.
- Putting `@api.depends` on a method that is also used elsewhere with different dependencies. Keep compute methods single-purpose.
- Relying on `onchange` instead of compute. Onchange runs only in the form UI; API and import writes skip it. Business invariants belong in compute or constraints.
- Changing `store=True` to `False` later orphans a column that stays in the database, harmless but untidy; the reverse requires a migration to fill values.
- `depends` on a field of a model reachable only by a dotted path through a non-stored computed field. Dependency tracing works through stored and computed alike, but a cycle in that chain is hard to debug; read the setup log.

{% hint style="info" %}
**Versions.** `compute_sudo` defaulting to true for related fields and `precompute` are in 16 through 18. In 18, `company_dependent` fields are stored as jsonb on the model table, which affects raw SQL; check the field attribute in your version before writing SQL against it.
{% endhint %}

## Try it

Check how a standard field is wired, in a development shell:

```python
f = env['res.partner']._fields['display_name']
print(f.compute, f.store, f.depends)
g = env['res.partner']._fields['country_code']
print(g.related, g.store, g.readonly)
```
