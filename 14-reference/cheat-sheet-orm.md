---
description: Compact tables for daily use.
---

# ORM cheat sheet

Written for Odoo 18.0. Version marks are given where 16.0 or 17.0 differ.

## Search and read

| Goal | Code |
|---|---|
| Search | `env['library.book'].search(domain, limit=80, order='name')` |
| Count | `search_count(domain)` |
| Browse by id | `browse([1, 2])` |
| Read to dicts | `records.read(['name', 'isbn'])` or `search_read(domain, fields)` |
| Exists | `record.exists()` |
| External id | `env.ref('library.group_library_manager')` |
| Aggregate | `_read_group(domain, ['member_id'], ['__count', 'fee:sum'])` |

`read_group` is the web client API; in code on 17.0 and later use `_read_group`.

## Domains

```python
[('state', '=', 'open'), ('date_due', '<', fields.Date.today())]   # AND
['|', ('state', '=', 'open'), ('member_id', '=', False)]            # OR
[('book_id.name', 'ilike', 'odoo')]                                  # path
[('id', 'in', ids)]
```

Prefix operators: `&` (default), `|`, `!`. Both operands follow the operator.

## Write

| Goal | Code |
|---|---|
| Create | `create([{...}, {...}])` |
| Update | `records.write({'state': 'done'})` |
| Delete | `records.unlink()` |
| Copy | `record.copy({'name': 'x'})` |

### x2many commands

| Command | Meaning |
|---|---|
| `Command.create(vals)` | new record |
| `Command.update(id, vals)` | write on linked record |
| `Command.delete(id)` | delete record |
| `Command.unlink(id)` | remove link only |
| `Command.link(id)` | add link |
| `Command.clear()` | remove all links |
| `Command.set(ids)` | replace links |

`from odoo import Command`. The numeric tuples `(0, 0, vals)` still work.

## Recordset operations

```python
books.mapped('name')                 # list of values
books.mapped('loan_ids')             # recordset
books.filtered(lambda b: b.active)
books.sorted('name', reverse=True)
books | other, books & other, books - other
books.ids, len(books), bool(books)
```

## Environment

```python
self.env.user, self.env.company, self.env.companies
self.env.context.get('lang')
self.with_context(tracking_disable=True)
self.with_company(company)
self.sudo()
self.with_user(user)
```

`sudo()` skips access rules and record rules, not constraints. Use it narrowly.

## Field options

| Option | Effect |
|---|---|
| `required`, `readonly`, `index`, `copy` | usual |
| `compute`, `store`, `depends` | computed, stored if `store=True` |
| `inverse`, `search` | write and search on computed fields |
| `related='a.b'` | computed path, not stored by default |
| `ondelete='cascade' / 'restrict' / 'set null'` | on Many2one |
| `tracking=True` | chatter log, needs `mail.thread` |

## Decorators

`@api.depends('a', 'b.c')`, `@api.constrains('a')`, `@api.onchange('a')`, `@api.model`, `@api.model_create_multi`, `@api.ondelete(at_uninstall=False)`.

## Pitfalls

- `search` without `limit` on a large table inside a loop.
- `write` inside a loop; build one dict per target value and write once on the recordset.
- Comparing recordsets to ids: `rec == 5` is False; use `rec.id == 5`.
- Relying on `name_get`; on 17.0+ it is `display_name`.
