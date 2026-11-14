---
description: "The four operations, batch behaviour, and the Command API."
---

# Create, read, write, unlink

The persistence methods are the supported way to change data through the ORM. They run access checks, record rules, constraints, computed field recomputation, and tracking. This chapter covers signatures, batch behaviour, and the command tuples used for relational fields. Overriding them is covered in a separate chapter.

## create

In Odoo 18 the signature is `create(self, vals_list)`, a batch method that takes a list of dicts and returns one recordset.

```python
books = self.env['library.book'].create([
    {'title': 'First', 'pages': 120},
    {'title': 'Second', 'pages': 340},
])
```

A single dict is still accepted and wrapped into a list. Pass a list in new code: one call with N dicts does batched INSERTs and one round of recomputation, where N calls repeat the overhead N times.

Missing values are filled from field defaults. Context keys `default_<field>` override model defaults, which is how actions prefill forms.

## Reading

Python code rarely calls `read()`. Attribute access fetches and caches values, and prefetching loads the same field for the other records of the recordset in one query.

```python
for book in books:
    print(book.title)     # one SELECT for all books, not one per book
```

`read(fields)` returns a list of dicts and is what RPC clients use. Many2one values come back as `(id, display_name)` pairs, x2many fields as lists of ids. When a search needs values immediately, use `search_read` (RPC style) or `search_fetch` (exists in the 18 source) to fetch named fields in the same query:

```python
rows = self.env['library.book'].search_fetch(
    [('pages', '>', 300)], ['title', 'pages'], limit=50)
```

## write

```python
books.write({'pages': 100})      # one UPDATE for the whole set
book.pages = 100                 # same, via the descriptor, singleton only
```

`write` applies the same values to all records and returns `True`. Values are converted by field type, constraints (`@api.constrains`) run once for the set, and dependent computed fields are marked for recomputation. Writing an unchanged value is not skipped for you; compare first if the extra UPDATE and `write_date` bump matter.

### The Command API

x2many fields are written with commands. In Odoo 18 `Command` is an `IntEnum` in `odoo.fields`, imported with `from odoo import Command`. The codes below are from the 18 source.

| Helper | Tuple | Effect |
|---|---|---|
| `Command.create(vals)` | `(0, 0, vals)` | create a record and link it |
| `Command.update(id, vals)` | `(1, id, vals)` | write on a linked record |
| `Command.delete(id)` | `(2, id, 0)` | unlink and delete the record |
| `Command.unlink(id)` | `(3, id, 0)` | remove the link, keep the record |
| `Command.link(id)` | `(4, id, 0)` | link an existing record |
| `Command.clear()` | `(5, 0, 0)` | remove all links |
| `Command.set(ids)` | `(6, 0, ids)` | replace all links with `ids` |

```python
member.write({
    'loan_ids': [
        Command.create({'book_id': book.id}),
        Command.update(old_loan.id, {'state': 'returned'}),
        Command.unlink(cancelled_loan.id),
    ],
})
```

Differences by field type:

- On a One2many, `unlink` detaches the child by clearing its inverse Many2one (the child is deleted if the inverse is required), while `delete` removes the child row.
- On a Many2many, `delete` removes the comodel record itself, not only the relation. Use `unlink` to detach and `delete` only when the target must go.
- `Command.set` on a One2many unlinks children missing from the list. Prefer explicit `link` and `unlink` when the intent is partial.

Use the named helpers. Raw tuples work and fill old code, but `(4, id)` versus `(4, id, 0)` makes readers stop; `Command.link(id)` does not.

## unlink

```python
books.unlink()
```

Before the DELETE the ORM checks access rights and record rules, then applies `ondelete` of every Many2one pointing at the records:

- `restrict`: refuse if referenced.
- `set null`: clear the reference (the default for optional Many2one).
- `cascade`: delete the referencing rows.

A `required` Many2one cannot use `set null`; state `ondelete` explicitly there. After `unlink`, any recordset still holding those ids raises `MissingError` on the next read; guard with `exists()`.

## copy

```python
new_book = book.copy({'title': book.title + ' (copy)'})
```

`copy(default)` duplicates a record and honours the `copy=` attribute of every field. One2many fields default to `copy=False`, so child lines are not duplicated unless the field says so. Fields under a unique constraint need an overriding value in `default`.

## Batching

- One `create` with 1000 dicts is far cheaper than 1000 `create` calls.
- One `write` with a shared dict beats a loop of per-record writes.
- Do not `search` inside a loop. Search once and use `grouped()` or `filtered()`.
- For very large changes, process in chunks of about 1000 ids. Call `cr.commit()` only in cron or script context, never inside a web request.

## Pitfalls

{% hint style="warning" %}
`write({'tag_ids': [1, 2, 3]})` is a bug. A plain list of ids is not a command list. Use `Command.set([1, 2, 3])`.
{% endhint %}

- An override of `create` must keep the batch signature (`@api.model_create_multi`, `vals_list`) or a list call breaks it. See the overriding chapter.
- Writing a non-stored computed field without `inverse` has no stored effect; the value is recomputed on the next read.
- A database integrity error aborts the whole transaction. Catching it inside a loop and continuing does not work unless you wrap the step in `with self.env.cr.savepoint():`.
- Do not assume `zip(vals_list, records)` alignment after an override that reorders or filters.
- Deleting a Many2many comodel record with `Command.delete` when you meant `Command.unlink` loses data for every other record linked to it.

{% hint style="info" %}
**Versions.** `Command` and `create` batching work the same in 16, 17, and 18. `search_fetch` is in the 18 source; I did not verify it in 16 or 17.
{% endhint %}

## Try it

Inspect the command tuples in a development shell:

```python
from odoo import Command
print(Command.link(5), Command.set([1, 2]), Command.clear())
```
