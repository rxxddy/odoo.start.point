---
description: "Naming, structure, and review checklists."
---

# Coding standards

Consistency is what lets a second developer open your module and find things. Odoo publishes its own guidelines; this chapter is the working subset, with the reasons and the review checklist we apply.

## Module layout

```
library/
  __init__.py
  __manifest__.py
  models/        # one file per model: library_book.py
  views/         # library_book_views.xml, library_menus.xml
  security/      # library_security.xml, ir.model.access.csv
  data/          # reference data, sequences, cron: noupdate where appropriate
  demo/          # demo data only
  wizard/        # transient models and their views
  controllers/
  report/
  static/        # src/js, src/xml, src/scss, description/icon.png
  tests/         # test_*.py, imported in tests/__init__.py
  i18n/          # .pot and translations
```

One model per file, named after the model with dots replaced by underscores. Add the import in `models/__init__.py`. Views for a model go in `<model>_views.xml`. Manifest data order: security first, then data, then views, then menus, then reports.

## Naming

- Model names: lowercase, dot-separated, module prefix: `library.book`. Table names follow by replacing dots.
- Python classes: CamelCase of the model, `LibraryBook`; inherit classes: `ResPartner`.
- Fields: snake_case. Many2one ends with `_id`, x2many with `_ids`. Booleans read as states: `is_overdue`, `active`. Avoid abbreviations.
- Methods: `_compute_<field>`, `_inverse_<field>`, `_search_<field>`, `_onchange_<field>`, `_check_<constraint>` (decorated with `@api.constrains`), `action_<verb>` for button handlers, `_default_<field>`.
- XML IDs: `<model>_view_<type>` (`library_book_view_form`), `<model>_action`, `menu_library_<name>`, `<model>_rule_<what>`, `group_library_<role>`. IDs are module-local, so no module prefix inside the module.
- Never name a custom field with an `x_` prefix in a module: that prefix is for fields created in the UI.

## Python style

- Follow PEP 8 with a line length of 120 (Odoo's linter settings); use `ruff` or `flake8` plus `pylint-odoo`.
- Import order: stdlib, third-party, `odoo`, `odoo.addons.*`, local. In this order, separated by blank lines.
- Recordset loops should not call `search` or `browse` for each row; prefetch, `mapped`, `filtered` and `read_group` (named `_read_group` in 17 and later) exist for this.
- Compute methods always assign the field on every record, including a default branch, or Odoo raises `ValueError: Compute method failed to assign`.
- `@api.depends` lists every field the compute reads, including dotted paths. A missing dependency is a stale-value bug that survives code review for months.
- Prefer `_sql_constraints` or database constraints for uniqueness, `@api.constrains` for logic that needs Python.
- Use `_()` around user-visible messages, with `%s` placeholders and lazy formatting: `_("Loan %s is overdue", loan.name)`.
- Don't catch `Exception` broadly; an ORM error in a transaction aborts it, and swallowing it hides the failure until a later query. Wrap risky blocks in `with self.env.cr.savepoint():`.

{% hint style="info" %}
Versions: `_sql_constraints` still works in 16 to 18; `models.Constraint` declarations replace it from 19, which is out of scope here. Likewise `read_group` is `_read_group` (private, tuple-returning) from 17 and public `read_group` remains for UI use.
{% endhint %}

## XML style

- Two-space indent, one attribute per line only when the line gets long.
- Always name the record id and set `string` or `name` on views.
- Use `<field name="arch" type="xml">` with `<list>` in 18 (the tag `<tree>` was renamed in 18 and the old name is deprecated). Inherit with `xpath` on `//field[@name='x']` and `position`, not on absolute positions.
- Don't use attribute `attrs` and `states` in 17 and later; they were removed in 17 in favour of `invisible`, `readonly`, `required` as Python-like expressions.

## JavaScript

Use ES modules (`import`/`export`) with `/** @odoo-module **/` in 16 and 17; 18 treats files under `static/src` as modules by default and the header is no longer needed. Components are OWL. Follow the Prettier config of the repository.

## Review checklist

1. Does the module install on an empty database and upgrade cleanly on a copy of production?
2. Does every new model have an ACL line, and a record rule where data is per company or per owner?
3. Are there raw SQL or `sudo()` calls? Is each one justified in a comment?
4. Do computes list full dependencies? Are expensive computes stored or indexed on purpose?
5. Are loops free of per-record queries?
6. Are user-visible strings translatable?
7. Are there tests for the new behaviour, including one run as a non-admin user?
8. Do views work for a user without every group? Are `groups` set on buttons and menus?
9. Did the change touch data in `data/` that needs `noupdate` or a migration script?
10. Is the manifest `version`, `depends` and `license` correct, and are all new files listed?

## Pitfalls

- **Reformatting unrelated code in a feature commit.** It hides the real change and creates merge conflicts. Format on its own commit.
- **Business logic in views or controllers.** Put it on the model so that RPC, cron, imports and tests share it.
- **Overriding `create` without `@api.model_create_multi`.** The method receives a list of dicts since 14; ignoring that breaks batch creation.
- **Calling `super()` conditionally.** Skipping it silently disables other modules' overrides.
- **Copy-pasting standard views.** Inherit instead; a copy does not receive upstream fixes.

## Try it

Add the linters to a copy of your module and see the baseline:

```bash
pip install ruff pylint-odoo
ruff check library/
pylint --load-plugins=pylint_odoo -d all -e odoolint library/
```
