---
description: "Designing business rules that survive imports, RPC, crons and other modules."
---

# Business logic design

A business rule is only a rule if it holds on every path: the form, an import, an RPC call, a cron and another module's code. This chapter is about deciding where each kind of rule lives, how to change standard flows without breaking others, and how to keep logic predictable when many modules overlap.

## Choose the right enforcement point

| Kind of rule | Where |
| --- | --- |
| Value must be unique or non-null | SQL constraint |
| Condition across fields of a record | `@api.constrains` |
| Derived value | `@api.depends` compute, stored if searched or grouped |
| Default value | field `default` or `default_get` |
| Workflow step | action method with a state guard (see [State machines](state-machines.md)) |
| UX hint while typing | `@api.onchange` and view attributes only |
| Access | record rules and groups, not Python `if` |

The common mistake is putting a real rule into an onchange or a view attribute. Both are skipped by RPC and imports.

## Keep rules in one place

If a rule is needed in two places, there is a missing method. Extract it onto the model with a name that states the rule (`_check_can_borrow`, `_get_due_date`). Callers then agree by construction. Avoid copying a condition into a domain, a constraint and a button; derive the domain from the method or a stored flag.

## Change standard flows with care

Standard flows are chains of methods that dozens of modules extend. Three rules:

1. **Extend, do not replace.** Override and call `super()`. Rewriting a method body copies a snapshot of the standard code that rots at the next upgrade and drops other modules' changes.
2. **Prefer the narrowest hook.** A `_prepare_*_vals` method, a single compute, or a `_get_*` helper changes one thing. Overriding `create` or `write` of a core model changes everything and costs on every call.
3. **Trace before you touch.** Before editing a flow, list its callers, overrides, dependent computes, constraints, automated actions and mail templates. Check what writing a field on this model triggers elsewhere. The cost of one grep is small against a regression discovered in accounting two weeks later.

```python
# Narrow: one decision, one hook, composable with other modules
def _prepare_invoice_vals(self):
    vals = super()._prepare_invoice_vals()
    if self.library_account_id:
        vals['partner_bank_id'] = self.library_account_id.bank_id.id
    return vals
```

## Side effects deserve names and switches

Side effects (emails, messages, record creation in other models, external calls) are where flows surprise people. Isolate them in methods, so they can be overridden or skipped, and honor the standard context keys for silencing them: `tracking_disable`, `mail_notrack`, `mail_create_nolog`, `mail_auto_subscribe_no_notify`. Imports and migrations then do not spam users.

## Design for recordsets and volume

Code must not assume one record or small data. Write for the recordset, group queries, and precompute lookups outside the loop. Where you must loop, avoid searching or browsing inside it. Process large volumes in chunks and flush or invalidate between chunks (see [Transactions in practice](transactions-in-practice.md)).

## Make logic idempotent

A rule that runs twice should leave the same result as running once: recomputing a total, applying a transition only when the state allows it, creating a child only if absent. This is what lets crons resume, retries be safe and migrations be repeated. Where it cannot be pure (sending a message), record that it happened in a field or table and check it first.

## Configuration over code

When a threshold or option varies by company, store it as a field on `res.company` or a `res.config.settings` parameter, not as a literal. Keep the literal out of the code and give it a default that matches the old behavior, so existing databases do not change on upgrade.

## Pitfalls

- **Onchange as validation.** Silent on RPC. Add a constraint.
- **Overriding `create` with a loop over `vals_list`.** Use `@api.model_create_multi` and handle the list; one-by-one defeats batching.
- **Calling `sudo()` to make an error disappear.** An access error is information; fix the rule or narrow the elevation.
- **Hidden coupling through context.** A context key that changes behavior three calls away is hard to find. Document it where it is read and where it is set.
- **Reimplementing standard computations.** If a standard field has the number, use it.
- **Tests that only test the happy path of the form.** Test the method with a recordset of mixed states, and through RPC.

{% hint style="info" %}
Versions: `@api.model_create_multi` is standard from 12 onward. Attribute names for view conditions changed between 16 (`attrs`) and 17/18 (`invisible`, `readonly` expressions), but the rule of keeping real validation in the model is the same in all.
{% endhint %}

## Try it

Before changing a standard method, list its overrides across all installed code:

```bash
grep -rn "def _prepare_invoice_vals" /path/to/odoo /path/to/custom-addons --include=*.py
```

Read each override and write down what it expects from `super()`. That list is your impact map.
