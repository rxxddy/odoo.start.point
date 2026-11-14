---
description: "ir.rule domains, global vs group rules, and what the ORM does with them."
---

# Record rules

ACLs say whether a user may touch a model at all. Record rules (`ir.rule`) narrow that to specific rows. A rule is a domain plus a set of operations, optionally restricted to groups.

## Defining a rule

```xml
<record id="library_loan_rule_own" model="ir.rule">
  <field name="name">Library loan: own loans</field>
  <field name="model_id" ref="model_library_loan"/>
  <field name="domain_force">[('borrower_id.user_ids', 'in', [user.id])]</field>
  <field name="groups" eval="[(4, ref('library.group_library_user'))]"/>
  <field name="perm_read" eval="True"/>
  <field name="perm_write" eval="True"/>
  <field name="perm_create" eval="True"/>
  <field name="perm_unlink" eval="False"/>
</record>

<record id="library_loan_rule_manager" model="ir.rule">
  <field name="name">Library loan: managers see all</field>
  <field name="model_id" ref="model_library_loan"/>
  <field name="domain_force">[(1, '=', 1)]</field>
  <field name="groups" eval="[(4, ref('library.group_library_manager'))]"/>
</record>
```

The domain is evaluated with a small context (see `_eval_context` in `ir_rule.py`): `user`, `time`, `company_id`, `company_ids`. In 18 `user` is the current user record (not sudo'd), so `user.id`, `user.partner_id.id` and `user.company_ids.ids` work. Anything else, like `uid`, fails.

By default a rule applies to all four operations. Unticking `perm_*` makes it skip that operation.

## Global versus group rules

This is the part people get wrong. Rules on a model split into two sets for the current user:

- **Global rules** (no groups): all of them are AND-ed. Every global rule must pass.
- **Group rules** (with groups): only those whose groups the user belongs to apply, and they are OR-ed. One passing is enough.

The final domain is `AND(global_domains + [OR(group_domains)])`. If the user matches no group rules but there are group rules for the model, the OR part is empty and, by the code in `_compute_domain`, only the global rules remain. Read `_compute_domain` in `odoo/addons/base/models/ir_rule.py` once; it is short.

Practical consequences:

- To **widen** access for managers, add a group rule with a permissive domain, as above. It ORs with the employee rule.
- To **restrict** everyone (multi-company, archived data), use a global rule. It cannot be bypassed by adding another group.
- A group rule never relaxes a global rule.

## Operations and their semantics

| Operation | What the rule does |
|---|---|
| read, search | Domain is appended to the SQL query. Non-matching rows silently disappear. |
| write, unlink | Selected records are checked; if any fails, an `AccessError` names the failing rule. |
| create | The new values are checked against the domain after creation; failing rolls the create back. |

Because `read` filters silently, a user report like "my record disappeared" is usually a rule, not a bug in the view. `_get_failing` is what builds the readable `AccessError` message for write and unlink.

## Parents and `any`

In 18, a rule on a child model can express the parent condition with the `any` operator:

```python
[('loan_id', 'any', [('borrower_id.user_ids', 'in', [user.id])])]
```

This turns into a subquery and is safer than `loan_id.borrower_id.user_ids`, whose multi-hop path behaves differently with archived or inaccessible parents. For many2one and one2many fields, `any` is applied with the record rules of the comodel as well, unless you use `any!`.

{% hint style="info" %}
Versions: `any` and `not any` exist from 17 on, and 18 uses them internally for rule inheritance and `_check_company` (the ORM was seen to wrap parent rules in `'any'` in `_compute_domain`). In 16, write explicit `in` subdomains with `search`, or use dotted paths.
{% endhint %}

## Rules and performance

A rule domain is added to every query on the model. A path like `borrower_id.user_ids` becomes a join or subquery on every list view. Rules are cached per user, model and operation in the registry; changes to `ir.rule` clear the cache, which is why editing rules on a busy production database stalls briefly.

Keep rule domains indexable: compare on stored many2one or company columns, and avoid non-stored fields (these can't be searched anyway).

## Pitfalls

{% hint style="warning" %}
`sudo()` ignores record rules entirely. If you sudo to read data and then return it, you have effectively removed the rule.
{% endhint %}

- **Using a global rule for one group.** It will restrict every user, including admins who are not in the group. Superuser only is exempt.
- **No `groups` and an open domain.** `[(1, '=', 1)]` globally is a no-op, but a leftover global rule with a real domain, copied from a demo, blocks everyone.
- **Rules on `res.partner` and `res.users`.** Almost every model joins these. A tight partner rule changes behaviour across the entire system, and breaks `name_get` on related fields with `AccessError` or `False` display names.
- **XML `noupdate`.** Rules are data. If you tune a rule in the UI and then update the module, it reverts unless the record has `noupdate="1"`.
- **Testing.** Rule bugs only show when you run as the right user. Use `with_user` in tests, never `sudo` or admin.

## Try it

List the rules that apply to a model, with their groups:

```sql
SELECT r.name, r.domain_force, r.global, r.perm_read, r.perm_write,
       (SELECT string_agg(g.name, ', ') FROM rule_group_rel rg
        JOIN res_groups g ON g.id = rg.group_id WHERE rg.rule_group_id = r.id) AS groups
FROM ir_rule r JOIN ir_model m ON m.id = r.model_id
WHERE m.model = 'library.loan';
```
