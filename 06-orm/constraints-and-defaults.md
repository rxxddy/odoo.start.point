---
description: "Python and SQL constraints, defaults, and onchange."
---

# Constraints, defaults, and onchange

Three mechanisms keep data valid and convenient: constraints reject bad data, defaults fill in values on creation, onchange methods update a form while the user types. They run at different moments and enforce different guarantees, and only constraints are guarantees.

## SQL constraints

Declared on the model, enforced by PostgreSQL, so they hold for every writer: ORM, import, raw SQL, other tools.

```python
class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Book'

    name = fields.Char(required=True)
    isbn = fields.Char()
    pages = fields.Integer()

    _sql_constraints = [
        ('isbn_unique', 'UNIQUE(isbn)', 'The ISBN must be unique.'),
        ('pages_positive', 'CHECK(pages >= 0)', 'Pages cannot be negative.'),
    ]
```

Each tuple is `(name, definition, message)`. The constraint is created at module update as `<table>_<name>`. The message is shown when PostgreSQL reports a violation.

Limits: the definition is a single static expression. It cannot call Python, cannot see other tables except through a subquery-free `CHECK`, and a `UNIQUE` on a nullable column allows many NULLs. For a partial or conditional unique, create a unique index in `init()`.

{% hint style="info" %}
Versions: `_sql_constraints` is the form in 16, 17 and 18. Adding a constraint to a table that already holds violating rows fails with a warning in the log and the constraint is simply not created. The module update still succeeds.
{% endhint %}

## Python constraints

```python
from odoo import api, models
from odoo.exceptions import ValidationError


@api.constrains('isbn')
def _check_isbn(self):
    for book in self:
        if book.isbn and len(book.isbn.replace('-', '')) not in (10, 13):
            raise ValidationError(self.env._("ISBN %s is not valid.", book.isbn))
```

`@api.constrains` triggers after `create` and after `write` on the listed fields, once per call, on the affected records. Points that matter:

- It is triggered only by the fields you name. Constraints on a related path, `'loan_ids.date_due'`, are not triggered by changes on the other model in older versions; do not rely on dotted names and name local fields.
- It runs after the write, inside the transaction. Raising rolls everything back.
- A constraint on a field not present in `vals` does not run on `write`, so an unchanged invalid record is not re-validated.
- It is not a security measure; code that uses `sudo()` or raw SQL bypasses nothing, but code that writes with SQL skips it entirely.

Python constraints are for rules SQL cannot express. If `CHECK` can say it, use SQL: it holds for imports and SQL scripts too.

## Defaults

```python
state = fields.Selection([('draft', 'Draft'), ('active', 'Active')], default='draft')
date = fields.Date(default=fields.Date.context_today)
user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
```

A default is a constant or a callable taking the recordset. Never write `default=fields.Date.today()` with parentheses: it is evaluated at import and every record gets the date the server started. A lambda or `fields.Date.today` (no call) is evaluated on each create.

Defaults apply on `create` for fields absent from `vals`, and in `default_get` for forms. Resolution order, highest first:

1. Values in `vals`.
2. Context keys `default_<field>`.
3. User defaults set by `ir.default`.
4. Field `default`.

`ir.default` is how Settings configure defaults, and per-company defaults for company-dependent fields use the same table. It is why changing a Python default in code does not change a value an administrator already set.

## onchange

```python
@api.onchange('book_id')
def _onchange_book_id(self):
    if self.book_id:
        self.due_days = self.book_id.default_loan_days
```

`@api.onchange` runs only in the form view, on a virtual record, when the user changes the field. It does nothing on `create`, `write`, import or API calls. Use it for convenience only.

When the value should always follow another field, use a computed field with `store=True, readonly=False`. It runs everywhere, is recomputed when the dependency changes, and the user can still override it:

```python
due_days = fields.Integer(compute='_compute_due_days', store=True, readonly=False)

@api.depends('book_id')
def _compute_due_days(self):
    for loan in self:
        loan.due_days = loan.book_id.default_loan_days or 14
```

Onchange can also return a warning:

```python
return {'warning': {'title': self.env._("Careful"), 'message': self.env._("Rare book.")}}
```

## Company consistency

For models with several `company_id`-bound relations, set `_check_company_auto = True` and `check_company=True` on the relational fields. The ORM then validates on write that records belong to compatible companies.

## Pitfalls

{% hint style="warning" %}
A constraint that reads many records per record (`search` inside the loop) turns an import of ten thousand rows into ten thousand searches. Group the work: one `read_group` or one search with `in`.
{% endhint %}

- `required=True` on a field is a NOT NULL column, but only for stored fields that are not set in the view as `required` by a `states`-like condition. A view-level `required` is client-side only.
- Raising in a constraint with a plain `Exception` produces an internal error dialog; use `ValidationError` (or `UserError`) for messages meant for people.
- A default that depends on `self.env.company` evaluated in a cron or in sudo uses the company of the environment, not of the user in the form.
- Defaults on `create` do not apply to `write`. Setting a field to `False` later does not restore the default.

## Try it

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conrelid = 'library_book'::regclass;
```

Each `_sql_constraints` entry appears as `library_book_<name>`.
