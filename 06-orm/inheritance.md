---
description: Classical, extension, and delegation, with the schema each produces.
---

# Inheritance

Odoo has three inheritance mechanisms, and they differ in one thing that matters: what ends up in PostgreSQL. Picking the wrong one is the usual source of "why is there a second table" and "why did my field not show up on the child".

## Extension: `_inherit` without `_name`

The most common form. You add fields and methods to an existing model. No new table, no new model; the registry builds one class from the original plus every extension, in module dependency order.

```python
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    library_card = fields.Char(index='btree_not_null')
    loan_ids = fields.One2many('library.loan', 'partner_id')
```

On module update, `library_card` becomes a column on `res_partner`. Every record of the model gets it, including partners created by other modules.

## Classical: `_inherit` plus a new `_name`

Copies the parent definition into a new model with its own table. The two share nothing at runtime: records of the parent do not appear in the child.

```python
class LibraryRareBook(models.Model):
    _name = 'library.rare.book'
    _inherit = 'library.book'
    _description = 'Rare book'

    insured_value = fields.Monetary(currency_field='currency_id')
```

Result: a table `library_rare_book` with all columns of `library_book` plus `insured_value`. Methods come through the Python class chain, so `super()` works as usual. Views, access rules and record rules are not copied: the new model needs its own.

You can inherit from several models at once, which is how mixins work:

```python
_inherit = ['library.book', 'mail.thread', 'mail.activity.mixin']
```

Mixins are abstract models (`models.AbstractModel`): no table of their own, only fields and methods that concrete models absorb. The fields of a mixin become columns on the table of the model that uses it.

## Delegation: `_inherits`

Composition, not copying. The child holds a required Many2one to the parent and exposes the parent's fields as if they were its own.

```python
class LibraryMember(models.Model):
    _name = 'library.member'
    _description = 'Library member'
    _inherits = {'res.partner': 'partner_id'}

    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    joined_on = fields.Date(default=fields.Date.today)
```

`member.name` reads `member.partner_id.name`. Creating a member with `name` in the values creates a partner first, then the member row pointing at it. Two tables, one join. This is how `res.users` relates to `res.partner`.

Rules worth knowing:

- Only fields are delegated. Methods of the parent are not reachable on the child.
- Writing a delegated field writes to the parent record, which may be shared by other children.
- Set `ondelete` on the link field explicitly. `restrict` protects a shared parent; `cascade` removes the child when the parent goes.
- Searching on a delegated field works and produces a join.
- Delegated fields are related fields (`inherited=True`); the value is stored once, on the parent.

## Which one

| You want | Use |
|---|---|
| New fields or behaviour on an existing model | extension (`_inherit` only) |
| Reusable behaviour (chatter, activities) | abstract mixin |
| A specialised variant with separate records and table | classical |
| A new record type that must also be a partner or product | delegation |

A fourth option, often missed: do not inherit. If the new model only needs a link to `res.partner`, a Many2one is simpler than any of the above.

## Method resolution order

Extensions are applied in load order, so `super()` in your override calls the version from the module loaded before yours. Declaring dependencies in `__manifest__.py` is therefore part of correctness, not just packaging: if module B must wrap module A's method, B must depend on A.

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _get_name(self):
        name = super()._get_name()
        return f'{name} ({self.library_card})' if self.library_card else name
```

## Pitfalls

{% hint style="warning" %}
Forgetting `_name` when you meant a classical inheritance modifies the parent for everybody. Forgetting `_inherit` when you meant an extension creates an unrelated model that merely shares the name.
{% endhint %}

- Classical inheritance copies `_sql_constraints` of the parent. Constraint names are keyed per table, but reusing a name with a different definition in the child is a silent override: check the update log.
- Redefining a field in an extension replaces only the attributes you pass. `name = fields.Char(string='Title')` on an existing Char keeps `required`, `translate` and the rest.
- Changing a field's type in an extension is not supported cleanly; the column conversion can lose data.
- With `_inherits`, creating a child creates a parent, so the parent's defaults and constraints run on child creation. A batch create produces one parent per child.
- Extend a mixin through `_inherit`; never copy its class into your module.

## Try it

Look at the schema each mechanism produced, read only, from `psql`:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('library_book', 'library_rare_book', 'library_member');
\d library_member
```

The `_inherits` model has a `partner_id` column and nothing for `name`; the classical model has every column of its parent.
