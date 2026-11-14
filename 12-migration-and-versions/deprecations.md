---
description: How to find and replace deprecated APIs before they are removed.
---

# Deprecations

Odoo deprecates an API for one or two series, logs a warning, then removes it. The cost of ignoring warnings is paid in one go at the next upgrade. This page is a method plus a table of replacements verified on 18.0.

## Surface the warnings

```bash
odoo-bin -d dev -u library --stop-after-init --log-level=warn 2>&1 | grep -iE "deprecat"
python -W error::DeprecationWarning -c "import odoo"
```

Run your test suite with warnings visible; many deprecations are only logged when the code path executes.

## Replacements

| Old | New | From |
|---|---|---|
| `attrs`, `states` in views | `invisible=` / `readonly=` / `required=` expressions | 17.0 |
| `<tree>` | `<list>` | 17.0 |
| `name_get()` | `_compute_display_name` | 17.0 |
| `name_search()` | `_search_display_name()` | 17.0 |
| `read_group()` in code | `_read_group()` | 17.0 |
| `check_access_rights` / `check_access_rule` | `check_access()` / `has_access()` | 18.0 |
| Raw SQL with `%` formatting | `odoo.tools.SQL` | 17.0 and later |
| `self._cr`, `self._uid`, `self._context` | `self.env.cr`, `self.env.uid`, `self.env.context` | long-standing |
| `@api.multi`, `@api.one` | remove | removed before 16.0 |

Check any entry before relying on it:

```bash
grep -n "def _search_display_name\|def _read_group" odoo/models.py
```

## Replace in an order that is reviewable

1. XML mechanical changes in one commit (`tree` to `list`, `attrs` to expressions).
2. Python API replacements in a second commit, with tests.
3. JavaScript last; it is a rewrite, so keep it out of the mechanical commits.

A single giant commit hides which change broke a view.

## Writing code that does not become deprecated

- Use the public ORM: `search`, `browse`, `write`, `_read_group` for aggregation. Avoid private helpers that start with `_` unless the book names them.
- Do not subclass internal web controllers or JS classes when a registry hook exists.
- Keep SQL isolated in one method per model so a later `SQL` migration is local.

{% hint style="info" %}
A deprecation notice is not a promise of a date. Odoo's own modules are the best predictor: if standard code has stopped using an API, remove it from yours.
{% endhint %}

## Pitfalls

- Suppressing warnings in `odoo.conf` to quiet a noisy log. You lose the early signal.
- Replacing `name_get` by overriding `display_name` as a plain field; it is computed, override the compute.
- Treating `read_group` from the web client (still supported) and from your Python code (deprecated) as the same thing.
- Assuming a removed method raises. Some removals silently skip a hook, so the feature stops working without an error.

## Try it

```bash
grep -rnE "name_get|name_search|check_access_rights|read_group\(|self\._cr" my_addons --include=*.py
```
