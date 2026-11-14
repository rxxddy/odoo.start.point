---
description: "ir.rule in depth: the exact domain the ORM builds, global versus group rules, the five patterns you will actually write, how failures are reported, and how to test rules."
---

# Record rules

ACLs say whether a user may touch a model at all. Record rules (`ir.rule`) narrow that to specific rows. A rule is a domain, a set of operations it applies to, and optionally a set of groups.

Checked against `odoo/addons/base/models/ir_rule.py`, `odoo/models.py` and `odoo/osv/expression.py` of Odoo 18, and the Odoo 20 tree where noted.

## The fields

| Field | Meaning |
| --- | --- |
| `name` | label |
| `model_id` | the model the rule restricts (rules on `ir.rule` itself are forbidden) |
| `domain_force` | the domain, as a Python expression string |
| `groups` | groups the rule is scoped to; **empty means a global rule** |
| `perm_read`, `perm_write`, `perm_create`, `perm_unlink` | which operations it applies to (all default to true) |
| `active` | switch it off without deleting it |

`global` is a computed field: true when `groups` is empty.

## Defining rules

```xml
<odoo>
    <data noupdate="1">

        <!-- group rule: a library user sees only their own loans -->
        <record id="library_loan_rule_own" model="ir.rule">
            <field name="name">Library loan: own loans</field>
            <field name="model_id" ref="model_library_loan"/>
            <field name="domain_force">[('member_id.user_id', '=', user.id)]</field>
            <field name="groups" eval="[(4, ref('library.group_library_user'))]"/>
            <field name="perm_unlink" eval="False"/>
        </record>

        <!-- group rule: managers see everything; ORed with the rule above -->
        <record id="library_loan_rule_manager" model="ir.rule">
            <field name="name">Library loan: managers see all</field>
            <field name="model_id" ref="model_library_loan"/>
            <field name="domain_force">[(1, '=', 1)]</field>
            <field name="groups" eval="[(4, ref('library.group_library_manager'))]"/>
        </record>

        <!-- global rule: nobody sees loans of other companies -->
        <record id="library_loan_rule_company" model="ir.rule">
            <field name="name">Library loan: multi-company</field>
            <field name="model_id" ref="model_library_loan"/>
            <field name="domain_force">['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]</field>
        </record>

    </data>
</odoo>
```

`noupdate="1"` matters: rules are data, and without it a module update resets any rule you tuned in the UI.

## The evaluation context

`domain_force` is evaluated by `safe_eval` with exactly these names (from `_eval_context`):

| Name | Value |
| --- | --- |
| `user` | the current user record, taken with an **empty context** so evaluation does not depend on the request context |
| `time` | the Python `time` module |
| `company_ids` | the ids of the companies currently **enabled** in the company switcher (`env.companies.ids`) |
| `company_id` | the id of the current company (`env.company.id`) |

Everything else is undefined. `uid` does not exist; use `user.id`. The domain can use any field path of the model, any attribute path on `user` (`user.partner_id.id`, `user.commercial_partner_id.id`, `user.company_ids.ids`), and `time.strftime(...)` for date comparisons.

`company_ids` is not "all companies the user may use", it is those the user has ticked in the switcher: "These companies are filtered and trusted", says the source comment. The domain cache is keyed on the context key `allowed_company_ids` for this reason.

A rule's domain is validated when it is saved (`_check_domain` compiles it against the model with `safe_eval` and the expression parser), so a typo in a field name is rejected at install time with `Invalid domain: ...`.

## How the final domain is built

For one model and one operation, `_compute_domain` does this, in order:

1. For each parent model in `_inherits`, compute that parent's domain recursively and add `(parent_field, 'any', parent_domain)` as a **global** domain. Delegation inheritance therefore inherits the restrictions of the parent.
2. `_get_rules` fetches the active rules for the model whose `perm_<operation>` is true and that are either global or belong to a group the user is in. In superuser mode it returns nothing.
3. Each rule's domain is evaluated and normalised. A rule without groups goes to the global list; a rule with groups the user belongs to goes to the group list.
4. **If there are no applicable group domains, the result is `AND(global_domains)`.** Otherwise it is `AND(global_domains + [OR(group_domains)])`.

The result is cached per user, `su` flag, model, operation and the context values from `_compute_domain_keys` (just `allowed_company_ids`), and the cache is cleared whenever a rule is created, written or deleted.

Step 4 is the sentence to remember. Consider a model whose only rules are group rules: "library users see their own loans" and "managers see all". A user who belongs to neither group, but whose ACL lets them in through some third group, has **no applicable group rules**. The OR part disappears and nothing restricts them: they see every loan. Group rules narrow nothing for people outside their groups. To restrict everyone, you need a global rule.

Practical consequences:

- To **widen** access for a group, add a group rule with a permissive domain; it is ORed with the others.
- To **restrict** everyone (companies, archived data, tenant isolation), use a global rule. Another group's rule cannot widen past it.
- A global rule is ANDed with the OR of the group rules, so combining the two is the normal pattern: global rules draw the outer fence, group rules open specific gates inside it.
- A group rule can never override a global rule.

## Operations

| Operation | What the rule does |
| --- | --- |
| `read`, and `search` | The domain is added to the SQL query. Non-matching rows silently disappear. `search_count` and `read_group` obey the same domain. |
| `write`, `unlink` | The selected records are checked; if any is not matched by the domain, an `AccessError` names the failing rule. |
| `create` | The new records are checked **after** they are created (`records.check_access('create')` at the end of `create`). If a record does not satisfy the domain, the creation fails and rolls back. |

Because reads filter silently, "my record disappeared" is most often a rule. And because `create` checks after the fact, a rule like `[('state', '=', 'draft')]` with `perm_create` makes it impossible to create a record in any other state, which is easy to forget when a wizard creates in `confirmed`.

The check on write and unlink is `filtered_domain` over the records, run as superuser: `forbidden := self - self.sudo().filtered_domain(domain)`.

## Reading the failure message

`_get_failing` builds the explanation: it re-evaluates the rules **with `active_test` disabled** on the failing records, so a record that is archived is judged on its fields, not hidden. It returns every failing global rule and, if the group rules as a whole fail, all of them. Then `_make_access_error` produces the message. Users without the technical-features group (`base.group_no_one`, effective only in debug mode) and portal or public users get the generic text ("Uh-oh! Looks like you have stumbled upon some top-secret records. Sorry, <user> doesn't have 'write' access to: ..."), which names the user, the operation and the model but not the records or rules. Internal users in debug mode also see the first records and the failing rules. When a failing rule's domain mentions `company_id`, the message adds a multi-company hint and, if it can tell, the company to switch to.

Odoo also logs at INFO level: `Access Denied by record rules for operation: write on record ids: [...], uid: ..., model: ...`. When a user reports "access error", that log line tells you which model and operation.

## Patterns that cover most needs

**Own records.**

```python
[('create_uid', '=', user.id)]
[('user_id', '=', user.id)]
```

**Through a parent, with `any`** (Odoo 17 and 18; also `not any`):

```python
[('loan_id', 'any', [('member_id.user_id', '=', user.id)])]
```

`any` turns into a subquery. It evaluates the sub-domain **with the comodel's own record rules applied**, so if the user cannot see the parent loans at all, the child rows disappear too, which is usually what you want and sometimes a surprise. The 18 `expression.py` knows only `any` and `not any`. In the Odoo 20 tree there is also an internal `any!` that skips the comodel rules; it is listed as an internal operator, so do not use it in rule XML.

**Company isolation.** The shape used by the core for shared master data:

```python
['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]
```

and for hierarchies of companies, `('company_id', 'parent_of', company_ids)`, as the base `res.partner` rule does.

**Portal users' own documents.** The core rule for partners available to portal and public groups reads `[('id', 'child_of', user.commercial_partner_id.id)]` with write, create and unlink disabled. Your portal rules follow the same pattern: group `base.group_portal`, `perm_read` only, the domain anchored on the user's partner:

```xml
<record id="library_loan_rule_portal" model="ir.rule">
    <field name="name">Library loan: portal sees own</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="domain_force">[('member_id.partner_id', '=', user.partner_id.id)]</field>
    <field name="groups" eval="[(4, ref('base.group_portal'))]"/>
    <field name="perm_write" eval="False"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>
```

**Hide archived or finished rows from non-managers.** A group rule can not do this (see step 4), a global rule can, with an exception built into the domain only if you have a way to identify managers in the domain. Usually the better tool is a default `active_test` filter in the action, not a rule.

**Time-based.**

```python
[('date', '>=', time.strftime('%Y-%m-01'))]
```

`time.strftime` is evaluated each time the rule is computed. The domain cache key does not include the date, so a long-running worker can keep a stale month until the cache is cleared. Avoid time in rules for anything that must roll over exactly.

## Performance

A rule domain is appended to every query on the model by every user in its scope. Dotted paths such as `member_id.user_id` become joins or subqueries on **every** list, search and read, and a rule on `res.partner` or `res.users` touches almost everything because most models join those. Keep rule domains:

- indexable: compare stored columns (many2one ids, company, `create_uid`);
- shallow: one hop where possible, `any` over deep dotted paths;
- not dependent on non-stored computed fields, which cannot be searched anyway and will fail at save.

Look at the SQL the rule produces with `env.cr` logging (see the shell chapters) before shipping a rule on a table with millions of rows. Editing a rule clears the registry cache, so changing rules on a busy production database causes a short stall.

## `sudo()` and rules

`sudo()` ignores record rules entirely, because `_get_rules` returns an empty set when `env.su` is true. A `sudo().search(...)` returns rows the rules were meant to hide. If you must elevate, do it narrowly and check access first as the real user, as in the security model chapter.

`with_user(user)` returns an environment in which rules apply for that user, which is what tests need.

## Testing rules

Rule bugs appear only when you run as the right user. A minimal test:

```python
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoanRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("library.group_library_user")
        cls.user_a = cls.env["res.users"].create({
            "name": "Member A", "login": "member_a",
            "groups_id": [(6, 0, [group_user.id])],
        })
        cls.user_b = cls.env["res.users"].create({
            "name": "Member B", "login": "member_b",
            "groups_id": [(6, 0, [group_user.id])],
        })
        cls.loan_a = cls.env["library.loan"].create({
            "member_id": cls._member_for(cls.user_a).id,
            "book_id": cls.env["library.book"].create({"name": "Dune"}).id,
        })

    @classmethod
    def _member_for(cls, user):
        return cls.env["library.member"].create({"name": user.name, "user_id": user.id})

    def test_user_sees_only_own_loans(self):
        loans = self.env["library.loan"].with_user(self.user_a).search([])
        self.assertEqual(loans, self.loan_a)
        self.assertFalse(self.env["library.loan"].with_user(self.user_b).search([]))

    def test_other_user_cannot_write(self):
        with self.assertRaises(AccessError):
            self.loan_a.with_user(self.user_b).write({"state": "returned"})
```

Notes: use `with_user` and never `sudo` or the default admin in the assertions. `groups_id` is the 18 field name (`group_ids` in 20). Assert both directions, that allowed users see what they should and that others do not. Test the unlisted-group case too: a user in neither group.

## Inspecting rules in a database

```sql
-- read-only: the rules of a model, with their groups
SELECT r.id, r.name, r.domain_force, r.global,
       r.perm_read, r.perm_write, r.perm_create, r.perm_unlink,
       (SELECT string_agg(g.name->>'en_US', ', ')
          FROM rule_group_rel rg
          JOIN res_groups g ON g.id = rg.group_id
         WHERE rg.rule_group_id = r.id) AS groups
FROM ir_rule r
JOIN ir_model m ON m.id = r.model_id
WHERE m.model = 'library.loan' AND r.active
ORDER BY r.global DESC, r.id;
```

In 18, `res_groups.name` is a translatable column stored as jsonb, hence `->>'en_US'`. In an Odoo shell the effective domain for a user is one call:

```python
env["ir.rule"].with_user(user)._compute_domain("library.loan", "read")
```

It returns the normalised domain the ORM will append, or an empty list when nothing restricts the user.

## Odoo 20: `ir.access`

In the Odoo 20 tree a record rule is an `ir.access` row: `model_id`, `group_id`, `operation` (a subset of `crud`) and `domain`. The three rules of this chapter become:

```csv
id,name,model_id,group_id/id,operation,domain
library_loan_own,Library loan: own loans,library.loan,group_library_user,cru,"[('member_id.user_id', '=', user.id)]"
library_loan_manager,Library loan: managers see all,library.loan,group_library_manager,crud,
library_loan_company,Library loan: multi-company,library.loan,,crud,"['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]"
```

The first two have a group, so they are permissions and are OR-ed; the third has none, so it is a restriction and is AND-ed. The effect is `OR(own, all) & company`. Two behaviours differ from 18:

- With no applicable permission the result is the empty set, not "no restriction". The surprise described under "How the final domain is built" is gone.
- A permission without a domain grants every record. A user who is in a group with `r` and no domain and in another group with `r` and a narrowing domain gets everything. Give each group's permission its own domain.

The evaluation context, `_get_failed_accesses` (the 20 name of `_get_failing`) and the error text are otherwise the same idea as in 18.

## Pitfalls

{% hint style="warning" %}
A model with only group rules is unrestricted for users outside those groups. Restrict everyone with a global rule.
{% endhint %}

- **A global rule meant for one group.** It restricts every user of the model, including managers. Only the superuser is exempt.
- **A leftover global rule with a real domain**, copied from a demo, blocks everyone silently.
- **Rules on `res.partner` and `res.users`.** Nearly every model joins them, so a tight rule changes behaviour system-wide and can make `display_name` fail or show empty for related records.
- **`noupdate` missing.** Tuned rules revert on the next module update.
- **`create` rule that rejects your own creates.** The check runs after creation against the final values.
- **Time in domains.** Cached, so it does not roll over exactly at midnight.
- **Testing as admin.** The administrator is in many groups and passes most group rules; use plain users with `with_user`.
- **Using `any!`.** It is an internal operator in the 20 tree and does not exist in 18.
- **Assuming read rules apply to `sudo` background jobs.** They do not; check what runs as superuser (crons, server actions with a configured user).
- **Tuning rules in production by hand.** Every change clears the registry cache. Keep rules in code.

## Versions

{% hint style="info" %}
**16:** the `any` operator does not exist (it is absent from the 16 `expression.py`); use dotted paths or `in` with a sub-search. The rule context has the same names.

**17 and 18:** `any` and `not any` are available (present in the 17 `expression.py`). 18 applies parent rules for `_inherits` through `any` in `_compute_domain`.

**20:** `ir.rule` and `ir.model.access` no longer exist as separate models. Both are `ir.access` records (`odoo/addons/base/models/ir_access.py`): a record with a group is a permission, a record without one is a restriction, and the final domain is `OR(permissions) & AND(restrictions)`. A rule written for 18 has to be converted, and the semantics of group rules change (no permission means no access). See "Odoo 20: `ir.access`" below. The ORM code was also moved to `odoo/orm/`.
{% endhint %}

## Try it

1. Create the three rules above for `library.loan`. As a plain user in the library user group, run `search_count([])`. Then remove the user from the group, give them read access to the model through some other group, and repeat. What changed, and why?
2. Remove the global company rule, keep the two group rules, and repeat with a user in neither group.
3. Print `_compute_domain` for the same user before and after.
4. Write the second test of the testing section and make it fail by adding `perm_write=False` to the wrong rule.

<details>

<summary>Solution notes</summary>

1. In the group the user sees only their own loans (and only those passing the global company rule). Outside it, no group rule applies, so only the global company domain remains: the user sees every loan of their companies.
2. With only group rules, a user in neither group sees every loan the ACL lets them reach. This is the case step 4 describes.
3. The first domain is `AND(global, OR(group domains))`; after the change it is the global domain alone.
4. The write attempt by another user raises `AccessError` only while the owner rule applies to write; changing the wrong flag turns the test into a pass on the wrong rule, which is why testing each operation separately matters.

</details>
