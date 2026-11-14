---
description: "Modeling workflows with a state field and guarded transitions."
---

# State machines

Most business documents (a loan, an order, a request) move through a fixed set of states. A state machine makes that explicit: a selection field, a table of allowed transitions, and one method per transition. Done well, nobody can reach an invalid state by clicking, by RPC, or by import.

## The shape

```python
class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Book loan'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, readonly=True, copy=False, tracking=True, index=True)

    _TRANSITIONS = {
        'draft': {'active', 'cancelled'},
        'active': {'returned', 'cancelled'},
        'returned': set(),
        'cancelled': {'draft'},
    }

    def _transition(self, new_state):
        for rec in self:
            if new_state not in self._TRANSITIONS[rec.state]:
                raise UserError(_("A loan cannot go from %(a)s to %(b)s.",
                                  a=rec.state, b=new_state))
        self.write({'state': new_state})
```

`readonly=True` on the field hides editing in the form, but does not stop `write()` from RPC. The guard lives in the model.

## One method per transition

```python
def action_confirm(self):
    self._transition('active')
    self._reserve_copy()

def action_return(self):
    self._transition('returned')
```

Buttons call these methods. Business effects (reserving, notifying, accounting) go in the action method, after the state check, so they run only for a valid transition. Name them `action_*` for user-triggered and `_do_*` for internal ones.

## Batch safety

`self` is a recordset. Validate every record before changing any, as `_transition` does: raising halfway through a loop is fine inside one transaction, but validating first gives one clear error and avoids partial side effects such as an email already queued for the first three records.

```python
def action_confirm(self):
    to_confirm = self.filtered(lambda l: l.state == 'draft')   # skip silently, or raise: decide
    to_confirm._transition('active')
```

Decide deliberately between "skip records not in the right state" and "refuse the whole batch". Skipping suits server actions on lists; refusing suits API calls where the caller needs to know.

## Guarding writes outside the actions

Someone will write `state` directly: a server action, an import, another module. To enforce transitions regardless of the entry point, check in `write`:

```python
def write(self, vals):
    if 'state' in vals:
        for rec in self:
            if vals['state'] != rec.state and vals['state'] not in self._TRANSITIONS[rec.state]:
                raise UserError(_("Invalid transition."))
    return super().write(vals)
```

This is stricter, and it also blocks legitimate data fixes by administrators. Keep a context key (`self.with_context(force_state=True)`) as an escape hatch that is documented, logged, and used only in migrations.

## Locks and fields that freeze

Once a document leaves draft, usually some fields must stop changing. Express it once:

```python
LOCKED_FIELDS = {'book_id', 'partner_id'}

def write(self, vals):
    if LOCKED_FIELDS & vals.keys() and any(r.state != 'draft' for r in self):
        raise UserError(_("These fields can only change in draft."))
    return super().write(vals)
```

In views use `invisible`/`readonly` with `state` conditions for the user experience, and keep the model check as the real rule.

## Concurrency on transitions

Two users pressing Confirm on the same record: both read `draft`, both pass the check. The second write usually fails with a serialization error and is retried by the framework, and the retry then sees `active` and raises a clean error. When the transition has side effects outside the record (stock, sequences), lock the row first with `SELECT ... FOR UPDATE` (see [Concurrency](concurrency.md)).

## Pitfalls

- **Transitions scattered across the code.** If three modules write `state` freely, the table above is fiction. Centralize in one `_transition`.
- **Computed or related state.** A state derived from other fields cannot be set; keep a stored selection for workflow, and compute flags beside it.
- **Cancel that destroys history.** Cancel to a state, do not unlink, if anything referenced the record. Provide a reset to draft only if the business really allows it.
- **Inheriting and adding states.** Use `selection_add` with `ondelete={'new_state': 'set default'}` (required, or uninstalling the module breaks existing rows).
- **Business logic in the view.** Attrs that hide a button are not security.

{% hint style="info" %}
Versions: in 17 and 18, `attrs` and `states` on view elements are replaced by direct `invisible`, `readonly` and `required` expressions. In 16 you still write `attrs="{'invisible': [('state', '!=', 'draft')]}"`. `selection_add` with `ondelete` behaves the same in 16 to 18.
{% endhint %}

## Try it

Read-only: count records per state to find impossible ones before adding a guard.

```sql
SELECT state, count(*) FROM library_loan GROUP BY state ORDER BY 2 DESC;
```
