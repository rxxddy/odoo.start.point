---
description: "Company fields, rules, and the mistakes that leak data."
---

# Multi-company

In a multi-company database, one Odoo instance holds several companies and each user has a set of allowed companies and a current one. The framework gives you three tools: a `company_id` field convention, `check_company` consistency checks, and a global record rule per model. You need all three.

## The user's companies

The user has `company_id` (default company) and `company_ids` (allowed). The company switcher in the web client sends the selected set in the context as `allowed_company_ids`; the first id is the current company. In code:

```python
self.env.company      # current company
self.env.companies    # all selected companies (recordset)
self.env.user.company_ids   # all allowed, regardless of selection
```

Record rules use `company_ids` (the allowed set, from `_eval_context`), not the switcher selection. So a user can see records of a company they have unticked in the switcher; views filter by selection, rules by permission.

## The model pattern

```python
class LibraryBook(models.Model):
    _name = 'library.book'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    publisher_id = fields.Many2one(
        'res.partner', check_company=True)
```

```xml
<record id="library_book_comp_rule" model="ir.rule">
  <field name="name">Library book: multi-company</field>
  <field name="model_id" ref="model_library_book"/>
  <field name="domain_force">['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]</field>
</record>
```

The rule is global (no groups), so it ANDs with everything else and no group can open it up. That is the intended behaviour. `company_ids` here is the evaluation-context name for the user's allowed company ids.

`_check_company_auto = True` makes `create` and `write` call `_check_company()` (see `models.py`), which raises a `UserError` if a field marked `check_company=True` points to a record whose company is not compatible with the record's own. Without it the field attribute does nothing. The compatibility domain comes from `_check_company_domain`, which accepts records of the same company or without a company.

{% hint style="info" %}
Versions: 16, 17 and 18 all use `company_id`, `check_company` and `_check_company_auto`. Odoo 17 introduced the `company_ids` shorthand in domains of views; 18 adds `_check_company_domain` customisation hooks and the hierarchical branch concept, where records are visible from child companies. Check the branch behaviour in your build before assuming `child_of` semantics in rules.
{% endhint %}

## Shared records

`company_id = False` means shared across all companies. The standard rule includes `('company_id', '=', False)` for exactly that, which is why your records need either a company or an explicit decision to be shared. Making `company_id` required on a transactional model removes the ambiguity.

## Company-dependent fields

A field with `company_dependent=True` stores one value per company, in a JSONB column on the same table (since 18; earlier versions use `ir.property`). The value is read for `env.company`:

```python
loan_days = fields.Integer(company_dependent=True, default=14)
```

Write it as one company, read it as another and you get different values. In SQL, no plain column join works for it; use the ORM.

{% hint style="warning" %}
Versions: 16 and 17 store company-dependent values in `ir.property` rows; 18 moved them into the column itself. Raw SQL and migrations written for the old layout break.
{% endhint %}

## Sequences, journals and accounting

Anything that numbers records needs a company on the sequence (`ir.sequence.company_id`) or a per-company sequence code. Sharing one sequence across companies produces gaps and legal problems in accounting. Fiscal data (taxes, journals, accounts) is company-specific in the standard chart; your module should not mix these across companies.

## Pitfalls

- **Missing rule.** The field alone filters nothing. A model with `company_id` and no rule leaks every company's rows to every user.
- **Using `env.company` in a background job.** Crons run with the cron user and a default company, not the company of the record. Pass `with_company(record.company_id)`.
- **`with_company` and `sudo`.** `sudo()` doesn't switch company. Use `record.with_company(record.company_id)` before reading company-dependent values or creating accounting entries.
- **Search in the wrong set.** `search` through the UI is limited by rules only. If you need to restrict to the selected companies, add `('company_id', 'in', self.env.companies.ids)`.
- **Related fields across companies.** A many2one without `check_company` lets a Company A loan reference a Company B book. Rules will hide it from some users and the data becomes inconsistent.
- **Tests as admin.** Admin is usually in all companies. Create a second company and a user restricted to it, and assert that they can't read the other company's records.

## Try it

Count rows per company for a model to spot rows that are shared or orphaned (read-only):

```sql
SELECT company_id, count(*) FROM library_book GROUP BY company_id ORDER BY 1;
```
