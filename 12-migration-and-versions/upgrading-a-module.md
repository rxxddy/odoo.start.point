---
description: Port a custom module to a new Odoo version.
---

# Upgrading a module

You have a custom module that works on one version and must load on the next. This page is the order of work that avoids rediscovering errors one at a time. The reference for what changed is [Version differences](version-differences.md).

## Work on a branch per version

Create a branch named after the target (`18.0`), not a long-lived feature branch. Bump the manifest `version` to `18.0.1.0.0`; the first two segments are the Odoo series and Odoo checks them when it computes the module version.

## The sequence

1. Start a throw-away database with only your module's dependencies, then install your module with `-i library --stop-after-init`. Read the first traceback; fix; repeat. Do not fix everything by grepping first, the real loader order shows what matters.
2. Fix XML first. View validation fails before Python is imported for most issues. Convert `attrs`/`states` to expressions, `tree` to `list`, replace removed XML ids.
3. Fix Python: removed or renamed methods (`name_get`, `name_search`, `read_group` calls), changed signatures, `check_access_rights`.
4. Fix data files: `noupdate` records that reference renamed ids, removed groups, changed `selection` keys.
5. Rewrite JavaScript. Legacy widgets are not portable; treat each as a new OWL component.
6. Run the tests: `-u library --test-tags /library --stop-after-init`.
7. Only then write migration scripts for existing databases (see [Migration scripts](migration-scripts.md)).

```bash
odoo-bin -d lib_18 -i library --stop-after-init --log-level=warn 2>&1 | tee install.log
grep -nE "WARNING|ERROR|Deprecat" install.log
```

## Find removed standard ids

The most common XML failure is a reference to a standard view or group that was renamed. Check the target source read-only:

```bash
grep -rn 'id="view_partner_form"' odoo/addons/base/views/ addons/*/views/
```

If an `inherit_id` target moved, the traceback names the `ref` that failed. Replace it with the new xml id, and if the anchor element (`//field[@name='x']`) disappeared, re-anchor on a stable sibling.

## Keep one codebase when you must

If you maintain two series, do not sprinkle `if version` in Python. Keep one branch per series and cherry-pick fixes. The XML syntax differences make a shared branch unreadable.

{% hint style="warning" %}
A module that installs cleanly on an empty database can still fail on upgrade of a real one: new required fields without defaults, changed constraints, and renamed selection keys only show on existing rows.
{% endhint %}

## Pitfalls

- Bumping only the manifest. Odoo then runs the module's pre/post scripts for versions you never wrote.
- Leaving `external_dependencies` unchanged when the target needs a newer Python library.
- Adding a stored computed field on a large table without checking recompute time; it recomputes on update.
- Overriding `create` with the old single-vals signature and breaking batch creation.

## Try it

Run your test suite once with the old branch on the old version, record the pass count, then compare after the port. A lower count is a regression, not a "removed test".
