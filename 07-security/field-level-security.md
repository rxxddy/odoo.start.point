---
description: "Field groups and hiding data properly."
---

# Field-level security

Some fields are more sensitive than the record around them: a cost price on a product, a salary on an employee, a private note on a loan. Odoo handles this with the `groups` attribute on the field definition, which the ORM enforces, as opposed to `groups` on a view element, which only hides it.

## The `groups` attribute

```python
class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Book'

    name = fields.Char(required=True)
    purchase_price = fields.Monetary(
        groups='library.group_library_manager',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one('res.currency')
```

A user outside the group:

- cannot `read` the field: `read(['purchase_price'])` raises `AccessError`, and a bare `read()` or `browse().purchase_price` access follows the same rule;
- cannot `write` it;
- does not see it in `fields_get()`, so the web client never renders it;
- cannot use it in search domains or `group_by`.

`groups` takes a comma-separated string of XML IDs. A leading `!` negates: `groups='!base.group_portal'`. Several IDs are OR-ed.

## What the ORM does with `read()` and `search_read`

When the web client calls `web_read` or `read` with an explicit field list, forbidden fields are dropped from the view of that user because `fields_get` never advertised them. When your own code asks for them, you get an error, not an empty value:

```python
book.with_user(employee).purchase_price   # AccessError
```

That is the correct behaviour, and also the source of most field-groups bugs: some other code path (a compute, a report, a mail template) touches the field as the current user.

## Computed fields over restricted fields

```python
margin = fields.Monetary(compute='_compute_margin', groups='library.group_library_manager')

@api.depends('price', 'purchase_price')
def _compute_margin(self):
    for book in self:
        book.margin = book.price - book.purchase_price
```

The compute reads `purchase_price`. If margin is non-stored and has the same `groups`, only managers evaluate it and everything works. If you store it, the recompute runs in the context of whoever triggered it, and a normal user editing `price` would hit an `AccessError` on `purchase_price`. Stored computes run with sudo semantics in the ORM's recompute flow, which is what you want; just keep the field's own `groups` on it so that users cannot read the result.

## Hiding in views vs. protecting

```xml
<field name="purchase_price" groups="library.group_library_manager"/>
```

On a view element, `groups` removes the node from the architecture when the view is rendered for that user. It does not prevent RPC access, and it does not hide the data when the field is also on the model without groups. Do both: put `groups` on the model field, and the view will simply follow because the field disappears from `fields_get`.

If a field is on the model with `groups` and you place it in a view without matching `groups`, Odoo 18 strips the node for unauthorised users; it does not fail. Be explicit anyway, so that the view is readable.

## Related patterns

- **Separate model for secrets.** If the data really must be sealed, a side model with its own ACL and rules is stronger than a field group, because you can audit and restrict it independently (`library.book.cost`, many2one back to the book).
- **`invisible` is not security.** `invisible="1"` and `column_invisible` change rendering only. The data is still sent to the browser.
- **Export and reports.** Field groups apply to exports and to QWeb reports as long as they are rendered with the user's environment. A report that runs `sudo()` shows everything.

## Pitfalls

{% hint style="warning" %}
Defaults, `onchange` and `related` fields can leak a restricted field: `related='book_id.purchase_price'` on another model, without `groups`, hands the value to anyone who can read that model. A related field inherits the target's restrictions only if you repeat them.
{% endhint %}

- **Related and delegated fields.** `_inherits` and `related` copy values; repeat `groups` on the copy.
- **Mail tracking.** `tracking=True` on a restricted field writes its old and new values into chatter messages that any follower can read. Don't track it, or accept that history is visible.
- **`name_search` and `display_name`.** If `_rec_name` points at a restricted field, users outside the group see broken names.
- **Code run by cron.** Cron jobs run as the user in `ir.cron`, usually the superuser. Code that checks `groups` there behaves differently than during an interactive test.
- **Upgrade changes.** Adding `groups` to an existing field breaks custom views, reports and automated actions that used it as a plain user. Search the code base for the field name before releasing.

{% hint style="info" %}
Versions: `groups` on fields behaves the same in 16, 17 and 18. Stricter checks in views at load time (a field in a view the user can't read) come from the arch validation in newer versions; test your views as a restricted user on your target.
{% endhint %}

## Try it

In a test or shell you own, compare what two users see:

```python
Book = env['library.book']
manager = env.ref('base.user_admin')
employee = env['res.users'].search([('groups_id', 'not in', env.ref('library.group_library_manager').ids), ('share', '=', False)], limit=1)
print('purchase_price' in Book.with_user(manager).fields_get())
print('purchase_price' in Book.with_user(employee).fields_get())
```
