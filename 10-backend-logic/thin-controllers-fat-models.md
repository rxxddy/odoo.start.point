---
description: Where business logic belongs and why.
---

# Thin controllers, fat models

Business rules live in models. Controllers, wizards, cron entries and server actions only translate an input into a model call. The reason is reuse and testability: a rule in a model works from the UI, from RPC, from a cron, from an import and from a test with one call. A rule in a controller works from one URL.

## What goes where

| Layer | Responsibility |
| --- | --- |
| Controller | Parse request, authenticate, call one model method, shape the response |
| Wizard (`TransientModel`) | Collect user input, call the model method on the active records |
| Cron / server action | Select records, call the model method |
| Model | Validate, compute, change state, enforce invariants, create side effects |

## An example

Thick controller, which is hard to test and impossible to reuse:

```python
@http.route('/library/borrow', type='json', auth='user')
def borrow(self, book_id, days):
    book = request.env['library.book'].browse(book_id)
    if book.available_copies < 1:
        return {'error': 'no copies'}
    loan = request.env['library.loan'].create({
        'book_id': book.id, 'due_date': date.today() + timedelta(days=days)})
    book.available_copies -= 1
    return {'loan': loan.id}
```

The same rule in the model:

```python
class LibraryBook(models.Model):
    _inherit = 'library.book'

    def borrow(self, partner, days=14):
        self.ensure_one()
        if self.available_copies < 1:
            raise UserError(_("No copies available."))
        loan = self.env['library.loan'].create({
            'book_id': self.id,
            'partner_id': partner.id,
            'due_date': fields.Date.today() + timedelta(days=days),
        })
        return loan
```

and the controller shrinks to authentication, a call and a response:

```python
@http.route('/library/borrow', type='json', auth='user')
def borrow(self, book_id, days=14):
    book = request.env['library.book'].browse(book_id)
    loan = book.borrow(request.env.user.partner_id, days)
    return {'loan': loan.id}
```

`UserError` becomes a proper error response, so the controller does not need its own error encoding.

## Respect existing hooks

Standard models already have extension points: `create`, `write`, `_compute_*`, `_onchange_*`, `_prepare_*_vals`, `_action_*`, `_post`. Prefer them over new parallel paths. If standard code builds values through `_prepare_invoice_vals()`, override that and your change applies on every route into the flow. If you instead write a new method that creates the invoice directly, you bypass every other module that extended the hook.

## Trace the impact before changing a standard flow

A change that looks local often is not. Before overriding or bypassing a standard method:

1. Find all callers: `grep -rn "_action_confirm" addons/ odoo/addons/` in the source of every installed module, including enterprise and your own.
2. Find all overrides of the method and read their order. With `super()` chains, your code runs inside theirs and the reverse.
3. Check which stored computes and constraints depend on the fields you write. A write to one field can trigger a recomputation chain across models.
4. Check which automated actions, mail templates, followers and server actions are bound to the model. They fire on your write too.
5. Run the standard test tags for the affected apps (`--test-tags`), not only your own.

This is the butterfly effect: a one-line change in `write` of a core model runs for every record of every flow. Narrow your override with a condition on `vals` and on the context so unrelated paths are not slowed or altered.

## Batch-safe code

Methods get recordsets. Write for `self` of any size, not for one record:

```python
# Wrong: N queries, and breaks on empty or multi recordsets
def _compute_overdue(self):
    for loan in self:
        loan.overdue = self.env['library.fine'].search_count([('loan_id', '=', loan.id)]) > 0

# Right: one grouped query
def _compute_overdue(self):
    groups = self.env['library.fine']._read_group(
        [('loan_id', 'in', self.ids)], ['loan_id'], ['__count'])
    counts = {loan.id: count for loan, count in groups}
    for loan in self:
        loan.overdue = counts.get(loan.id, 0) > 0
```

Use `ensure_one()` only on methods that are single-record by nature, and say so in the name or docstring.

## Pitfalls

- **Logic in `@api.onchange`.** It does not run on RPC or import. Rules go in `create`/`write`/constraints; onchange is only UX.
- **`sudo()` in controllers.** It removes access rules for everything downstream. Call `sudo()` on the narrowest expression, and re-check rights by hand.
- **Helpers on the controller class.** Anything another entry point might need belongs on a model.
- **God models.** "Fat" means rules sit with their data, not that one model does everything. Split by responsibility with a helper model or mixin.

{% hint style="info" %}
Versions: `_read_group` with `['__count']` aggregates and a list return is the 17 and 18 signature. In 16 use `read_group` or the older `_read_group` form with `lazy` and dict results.
{% endhint %}

## Try it

Find every override of a standard method you plan to touch:

```bash
grep -rn "def _action_confirm" /path/to/odoo/addons /path/to/custom-addons --include=*.py
```
