---
description: create, write, unlink, copy; the batch signatures and where overrides go wrong.
---

# Overriding CRUD methods

Overriding `create`, `write`, `unlink` and `copy` is the usual way to hook business rules into the record lifecycle. It is also where the subtle bugs live: wrong signature, per-record logic that breaks on batches, side effects that run before validation.

## create

`create` receives a list of dictionaries (`create(self, vals_list: list[dict]) -> Self`). Decorate your override with `@api.model_create_multi` and treat the argument as a list.

```python
from odoo import api, models


class LibraryBook(models.Model):
    _inherit = 'library.book'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('isbn'):
                vals['isbn'] = self.env['ir.sequence'].next_by_code('library.book')
        books = super().create(vals_list)
        books._notify_new_books()
        return books
```

The decorator also lets legacy callers pass a single dictionary: it is wrapped into a list before your code runs.

Rules:

- Change values before `super()`, act on records after it. Records do not exist before `super()` returns.
- Return the recordset `super()` returned.
- Never loop `super().create([vals])` per item; you lose the batch insert.
- Values can contain context defaults, `False` for empty relational fields, and command tuples for x2many. Do not assume plain ids.

## write

```python
def write(self, vals):
    if vals.get('state') == 'lost':
        if self.loan_ids.filtered(lambda l: not l.returned):
            raise UserError(self.env._("Return open loans before marking a book lost."))
    old_shelf = {book.id: book.shelf for book in self}
    result = super().write(vals)
    if 'shelf' in vals:
        self.filtered(lambda b: old_shelf[b.id] != b.shelf)._reindex_shelf()
    return result
```

`write` runs on a recordset with one dictionary applied to every record. Read old values before `super()`; they are gone afterwards. It returns `True`.

{% hint style="info" %}
`self.env._()` for translation is available in Odoo 18. In 16 and 17 use `from odoo import _` and call `_("...")`.
{% endhint %}

## unlink

For cleanup, override `unlink`:

```python
def unlink(self):
    self.env['library.loan'].search([('book_id', 'in', self.ids)]).unlink()
    return super().unlink()
```

For validation, prefer `@api.ondelete`:

```python
@api.ondelete(at_uninstall=False)
def _unlink_except_on_loan(self):
    if any(book.state == 'on_loan' for book in self):
        raise UserError(self.env._("You cannot delete a book that is on loan."))
```

Methods marked `at_uninstall=False` are skipped when the module is being uninstalled. A `raise` in a plain `unlink` override can make the module impossible to uninstall because its own records cannot be deleted.

## copy and copy_data

Override `copy_data` to change what is copied, `copy` to react to the new record.

```python
def copy_data(self, default=None):
    default = dict(default or {})
    default.setdefault('isbn', False)
    return super().copy_data(default)
```

`copy_data` returns a list of dictionaries, one per record. If you only want to exclude a field, set `copy=False` on it instead of overriding anything.

## Conventions

- Always call `super()`. A missing call silently removes behaviour from every module loaded earlier.
- Context keys such as `tracking_disable`, `mail_notrack` and `mail_create_nolog` change the behaviour of the mail mixin further down the chain. Pass them with `with_context`, not through values.
- `_write` and `_create` are the low-level methods. They skip access checks and tracking; use them only for internal bookkeeping.

## Pitfalls

{% hint style="warning" %}
`self.ensure_one()` in `write` crashes on mass edits, imports and any save that touches several records. Loop or use `filtered`.
{% endhint %}

- Writing to `self` inside `write` recurses. Guard with a context key, or put the extra values into `vals` before `super()`.
- Side effects in `create` (HTTP calls, emails) run inside the transaction. A later error rolls back the data but not the action. Defer with `self.env.cr.postcommit.add(callback)` when it must happen only after commit.
- Validation belongs in `@api.constrains`, not in `write`: constraints also run on `create` and during import.
- Reading a stored computed field before `super().create()` returns nothing useful; it has not been computed.
- An override on `create` that returns early without calling `super()` for some vals breaks the order of the returned recordset relative to `vals_list`.

## Try it

On a throwaway database, in `odoo shell`, check that your override is batch-safe:

```python
books = env['library.book'].create([{'name': f'Book {i}'} for i in range(5)])
books.write({'shelf': 'A'})
```

Add a log line in each override. You should see one `create` call and one `write` call, not five.
