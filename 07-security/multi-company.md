---
description: "Several companies in one database: the environment's companies, the company_id pattern, check_company, company-dependent fields, and the sudo and cron traps."
---

# Multi-company

One Odoo database can serve several companies whose data must stay apart: their own invoices, stock, sequences, prices, while sharing users, products and partners where that is useful. Multi-company is not a switch you flip; it is a set of conventions that your models must follow.

Checked against `odoo/api.py`, `odoo/models.py`, `odoo/fields.py` and `odoo/addons/base/security/base_security.xml` (18).

## How the environment knows the company

The user belongs to one or more companies (`user.company_ids`) and has a main one (`user.company_id`). The web client has a **company switcher**; the companies ticked there are *enabled*. The client sends them in the context as `allowed_company_ids`, with the first id being the **current** company. Server code reads them from the environment:

```python
self.env.company      # the current company (a res.company record)
self.env.companies    # all enabled companies (a recordset)
self.env.user.company_ids   # all companies the user may switch to
```

From the 18 source (`api.py`):

- `env.company` returns the first id of `allowed_company_ids` from the context, or `user.company_id` when the context has none.
- For a non-superuser environment, if `allowed_company_ids` contains a company that is not among the user's own companies, reading `env.company` or `env.companies` raises `AccessError("Access to unauthorized or invalid companies.")`. A tampered context cannot pick companies the user does not have.
- **In `sudo()` mode the check is skipped**, and the docstring warns: "When in sudo mode, a user can access any company, even if not in his allowed companies." That is useful for inter-company transactions and dangerous everywhere else.

`with_company(company)` returns the recordset with a modified context so that `env.company` is the given company and `env.companies` includes it:

```python
invoice = self.with_company(other_company).create({...})
```

The docstring warns that using a company the current user is not allowed to use may raise `AccessError` unless the environment is sudoed. It returns `self` unchanged when `company` is empty.

## The model pattern

A model whose records belong to one company gets a `company_id` and a rule:

```python
class LibraryLoan(models.Model):
    _name = "library.loan"
    _description = "Loan"
    _check_company_auto = True

    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    member_id = fields.Many2one("library.member", check_company=True, required=True)
    book_id = fields.Many2one("library.book", check_company=True, required=True)
```

and in `security/library_security.xml` a **global** rule:

```xml
<record id="library_loan_rule_company" model="ir.rule">
    <field name="name">Library loan: multi-company</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="domain_force">['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]</field>
</record>
```

Three details are easy to get wrong:

- The default `lambda self: self.env.company` is the *current* company, not the user's main company. Records created while the switcher is on company B belong to B.
- The rule is **global** (no groups). A group rule would not restrict users outside the group; the record rules chapter explains why. This is the case where a global rule is exactly right.
- The rule uses `company_ids`, the *enabled* companies from the switcher, not all the user's companies. Records from companies the user has not ticked do not appear, which is what makes the switcher meaningful.

For shared data (a product visible to every company) allow an empty company: `('company_id', '=', False)` in the domain above, and leave `company_id` optional on the model. For a company hierarchy, the base `res.partner` rule uses `('company_id', 'parent_of', company_ids)` alongside the partner-share condition, so a company can see records of its parents.

## `check_company`: keeping relations consistent

A loan in company A that points at a book of company B is a data leak and a source of impossible accounting. Two switches prevent it:

- `_check_company_auto = True` on the model: on every `create` and `write` the ORM calls `_check_company()`.
- `check_company=True` on each relational field to verify.

`_check_company` verifies that the company of each related record is compatible with the company of the record: allowed are the same company or no company. The comodel's `_check_company_domain(companies)` is `[('company_id', 'in', company_ids + [False])]`, or `[('company_id', '=', False)]` when there are no companies. If a record fails the check you get `UserError: Incompatible companies on records:` with a line per offending field naming the company of each record. Records are checked with `active_test=False`, so archived records are judged too.

`check_company=True` has a second effect: it generates a default **domain** for the field (`_description_domain` in `fields.py`), so the many2one dropdown offers only compatible records. When the model has `company_id` the domain reads, in effect: if the record has a company, offer comodel records whose company is that one or empty; if it has none, offer only records without a company. With `company_ids` it uses that field the same way; if the model has neither, the framework logs a warning that it could not generate the company-dependent domain. Your own `domain=` on the field is appended to it.

The check is skipped for fields that are not marked, so a missing `check_company=True` is a silent hole: the domain is also missing and the form lets users pick wrong records.

## Company-dependent fields

Some values differ per company on the same record: a product's cost price, a partner's receivable account. `company_dependent=True` stores one value per company:

```python
class LibraryBook(models.Model):
    _inherit = "library.book"

    replacement_cost = fields.Float(company_dependent=True)
    shelf_account_id = fields.Many2one("account.account", company_dependent=True, check_company=True)
```

In the Odoo 18 source:

- The value is stored in the model's own table as a **jsonb dictionary keyed by company id**, not in a separate table. (Older versions used `ir.property` rows, which is why old tutorials describe them differently.) Defaults for companies without a value come from `ir.default`.
- It is read and written for `env.company`, the current company. Switching company changes what the same record shows.
- Allowed types are `char`, `float`, `boolean`, `integer`, `text`, `many2one`, `date`, `datetime`, `selection`, `html`. A company-dependent field **cannot be `required`** and **cannot be translated**; Odoo warns at definition.
- With `check_company=True` on a company-dependent field, the check uses the **currently active company** instead of the record's company, and the generated domain uses the first enabled company.
- A model with company-dependent fields should have a `company_id` or `company_ids` field, or the framework logs "Skipping a company check ... the model doesn't have a `company_id`".

Because of the jsonb storage, a SQL query on such a field needs the key: `replacement_cost->>'1'` for company 1. When you read in SQL, remember this and that the value for a company without an entry is null, not the default.

## Where multi-company breaks

**`sudo()`.** It ignores record rules, so a `sudo().search([])` returns all companies' records mixed together, and `env.company` skips its sanity check. The `sudo` docstring in 18 spells it out: "could cause data access to cross the boundaries of record rules, possibly mixing records that are meant to be isolated (e.g. records from different companies)", and "methods which select one record among many - for example getting the default company, or selecting a Bill of Materials" can behave unintuitively. In a multi-company database every `sudo()` in a search is a bug report waiting to happen. Add the company explicitly when you must elevate:

```python
loans = self.env["library.loan"].sudo().search([
    ("company_id", "in", self.env.companies.ids),
    ("state", "=", "open"),
])
```

**Cron jobs and server actions.** They run as the user configured on the job (often the superuser, `base.user_root`), so `env.company` is the superuser's main company and rules do not apply. A cron that processes "all open loans" will process every company with whatever company context the first record happens to give. Loop over companies explicitly:

```python
@api.model
def _cron_send_reminders(self):
    for company in self.env["res.company"].search([]):
        loans = self.with_company(company).search([
            ("company_id", "=", company.id),
            ("state", "=", "open"),
        ])
        loans._send_reminders()
```

**Sequences.** An `ir.sequence` has its own `company_id`. If the sequence has no company, all companies share one numbering. Use `company_id` on the sequence and search it with the right `with_company`, or invoices of different companies will interleave. See the sequences chapter in the ORM part.

**Reports and emails.** Reports render with the company of the record; templates should read `object.company_id`, not `user.company_id`, for letterheads and legal data.

**Default values.** `default=lambda self: self.env.company` evaluates at creation, in the creator's current company. Imports and automated creation under sudo take the superuser's. Pass `company_id` explicitly in automated creation.

**Unique constraints.** An SQL `UNIQUE (name)` is global across companies. If names only need to be unique per company use `UNIQUE (company_id, name)`; remember null `company_id` values are distinct in PostgreSQL unique constraints.

**Domains in actions.** Do not filter by company in an action `domain` for isolation; use the rule. The rule applies everywhere (list, kanban, search, RPC), a domain only in that action.

## Testing

Create two companies and a user belonging to both, and test with the switcher in each state:

```python
@tagged("post_install", "-at_install")
class TestLoanCompanies(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Company B"})
        cls.user = cls.env["res.users"].create({
            "name": "Multi", "login": "multi",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id, cls.company_b.id])],
            "groups_id": [(6, 0, [cls.env.ref("library.group_library_user").id])],
        })
        Loan = cls.env["library.loan"]
        cls.loan_b = Loan.with_company(cls.company_b).create({
            "company_id": cls.company_b.id,
            "member_id": cls.env["library.member"].create({"name": "M", "company_id": cls.company_b.id}).id,
            "book_id": cls.env["library.book"].create({"name": "Dune", "company_id": cls.company_b.id}).id,
        })

    def test_only_enabled_companies_are_visible(self):
        Loan = self.env["library.loan"].with_user(self.user)
        only_a = Loan.with_context(allowed_company_ids=[self.company_a.id]).search([])
        both = Loan.with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id]
        ).search([])
        self.assertNotIn(self.loan_b, only_a)
        self.assertIn(self.loan_b, both)

    def test_incompatible_company_is_rejected(self):
        book_a = self.env["library.book"].create({"name": "A", "company_id": self.company_a.id})
        with self.assertRaises(UserError):
            self.loan_b.write({"book_id": book_a.id})
```

The first test exercises the global rule through `allowed_company_ids`, exactly as the web client sends it. The second exercises `_check_company`. Also test a user who tries `allowed_company_ids` with a company they do not own: reading `env.company` raises `AccessError`.

## Odoo 20

The mechanisms above (`env.company`, `env.companies`, `with_company`, `check_company`) exist unchanged in the Odoo 20 tree. The group layout for `base.group_multi_company` follows the new privilege structure, which affects only the group XML you write, not the ORM behaviour.

## Pitfalls

{% hint style="warning" %}
`sudo()` plus `search` in a multi-company database mixes companies. Add the company condition explicitly, or avoid elevation.
{% endhint %}

- **A group rule for companies.** It does not restrict users outside the group. Companies need a global rule.
- **Forgetting `check_company=True`.** No consistency check and no filtered dropdown; wrong-company records can be linked.
- **`company_id` without `index=True`.** The rule domain is on every query.
- **Defaulting `company_id` to `user.company_id`.** Use `env.company`: records follow the switcher.
- **Crons that ignore companies.** They run as the superuser. Loop over companies and use `with_company`.
- **Company-dependent fields in SQL.** They are jsonb keyed by company id in 18; old `ir.property` queries do not apply.
- **A company-dependent field marked `required`.** Not supported; Odoo warns.
- **Shared sequences** across companies by leaving the sequence company empty.
- **`env.company` on a tampered context.** Raises `AccessError` for normal users; sudo skips the check.
- **Unique constraints without the company.** Global uniqueness blocks legitimate duplicates across companies.

## Versions

{% hint style="info" %}
**16 and 17:** company-dependent fields are stored as `ir.property` rows; `company_ids` rule context and `check_company` exist. Verify the storage claim on your branch before writing SQL against these fields.

**18:** company-dependent fields are jsonb columns on the model table, with defaults from `ir.default`. `check_company` and `_check_company_auto` as above.

**20:** same environment API.
{% endhint %}

## Try it

1. Create two companies and a user in both. Open the switcher with only A ticked, then both. Count `library.loan` records.
2. In a shell, as that user, set `allowed_company_ids` to a company the user does not own and read `env.company`. Then repeat with `sudo()`.
3. Add `replacement_cost` as company-dependent, set it in A and in B for one book, and read it in each company. Then inspect the column in SQL: `SELECT replacement_cost FROM library_book WHERE id = ...`.

<details>

<summary>Solution notes</summary>

1. With only A ticked the rule hides B's loans; with both ticked they appear.
2. The non-sudo access raises `AccessError: Access to unauthorized or invalid companies.`; with `sudo()` it returns the company.
3. The value follows the current company, and the column holds a JSON object such as `{"1": 12.5, "2": 14.0}`.

</details>
