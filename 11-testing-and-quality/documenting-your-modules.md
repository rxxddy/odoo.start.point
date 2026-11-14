---
description: What a future maintainer needs to find.
---

# Documenting your modules

The person who maintains your module in two years has the code, the database and whatever you left next to them. Good documentation answers the questions the code cannot: what is this for, what are the non-obvious decisions, and how do I know it works. Keep it short, keep it in the repository, and keep it where it will be updated with the code.

## The manifest is documentation

```python
{
    'name': 'Library',
    'summary': 'Book catalogue and loans',
    'description': """
Lets staff register books and lend them to members.
Overdue loans are flagged by a daily cron.
""",
    'category': 'Services/Library',
    'version': '18.0.1.0.0',
    'depends': ['base', 'mail'],
    'data': [...],
    'license': 'LGPL-3',
    'application': True,
}
```

`summary` is one line and shows in the Apps list. `description` in the manifest is legacy; Odoo prefers `static/description/index.html` for the Apps page, but a manifest `description` still works and is fine for internal modules. `depends` is documentation of coupling: keep it minimal and honest.

## README

One `README.md` (or `README.rst`, which the OCA tooling uses) at the module root, with these sections and no others unless needed:

1. **Purpose.** Two or three sentences: the business problem, who uses it.
2. **Configuration.** Settings, groups to assign, system parameters (`ir.config_parameter` keys), cron jobs and their schedule.
3. **Behaviour.** The rules that are not obvious from the UI: what makes a loan overdue, who can extend it, what happens on archive.
4. **Technical notes.** Models added or extended, hooks, known limitations, performance notes (stored computes, indexes).
5. **Upgrade notes.** What each version changed that an operator must know.

Write for a developer who has not seen the project. Put a model diagram in text if there are more than three models.

## Docstrings and comments

Docstrings on models describe the concept, not the code:

```python
class LibraryLoan(models.Model):
    """A book lent to one member.

    A loan is open until ``return_date`` is set. A book has at most one open
    loan, enforced by ``_check_single_open_loan``.
    """
    _name = 'library.loan'
    _description = 'Loan'
```

`_description` is mandatory in practice: it becomes the model's label in the UI and removes a log warning. Add `help=` to fields that users see; it becomes the tooltip and appears in `fields_get`, so it is user documentation for free.

Comments explain why:

```python
# Not an SQL constraint: archived loans must be allowed to overlap.
@api.constrains('book_id', 'return_date')
def _check_single_open_loan(self): ...
```

Do not comment what the next line plainly does. Do comment: workarounds (with a ticket or upstream issue reference), ordering requirements, odd performance choices, and security decisions such as why a `sudo()` is safe.

## In-app help

- **Field `help`** for tooltips.
- **Action `help`** for the empty-list message, which is the first thing a new user sees:

```xml
<field name="help" type="html">
  <p class="o_view_nocontent_smiling_face">Register your first book</p>
  <p>Books can be lent to members from here.</p>
</field>
```

- **Menu names and view titles** in the language of the user. Terms should match across menus, fields and messages.

## Data models and decisions

For modules over a few models, add a `docs/` folder with:

- `models.md`: the models, key fields, relations (a text diagram is enough).
- `decisions.md`: a log of choices, each with date, context and consequence ("Loans are not company-dependent because the library is shared"). A decision log is worth more than any amount of prose about what the code does.
- `runbook.md`: how to check health (a SQL query that shows stuck records), how to rerun a failed cron, how to restore a deleted record.

Link them from the README.

## Changelog

A `CHANGELOG.md` per module, newest first, one entry per manifest version bump, listing user-visible changes and any manual steps. It pairs with the migration scripts: if a version has a script, its changelog entry says what the script does.

```
## 18.0.1.2.0
- Overdue flag is now computed in the user timezone.
- Migration: renames loan.due to loan.due_date.
```

## Translations

User-facing strings use `_()` in Python and are extracted automatically from XML. Keep an `i18n/<module>.pot` up to date at release time (export from Settings, Translations with the module selected, or `odoo-bin --i18n-export`). Translators are readers of your documentation too: avoid concatenated sentences and strings that depend on context they cannot see.

## Pitfalls

- **README written once.** Docs that are not updated with the code lie. Make "docs updated" an item in the review checklist.
- **Documenting the obvious.** A paragraph per field wastes space; document the exceptions.
- **Client names and real data in examples.** Docs get shared and copied. Use neutral sample data.
- **Tooltips as essays.** A `help` text longer than three lines is a missing help page.
- **Orphan system parameters.** Every `ir.config_parameter` key your code reads must appear in the README with its default and effect.

## Try it

List the models in your module with no `_description`, which also generates the log warning:

```bash
grep -rn "_name = " library/models | while read l; do f=${l%%:*}; grep -L "_description" "$f"; done | sort -u
```
