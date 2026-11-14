---
description: "XML and CSV data, noupdate, and load order."
---

# Data files

Data files are how a module ships records: views, menus, security rules, demo content, configuration. They are declared in the manifest, loaded in order at install and update, and tracked through `ir.model.data` so a second load updates instead of duplicating. Most upgrade bugs trace back to misunderstanding this loop.

## Manifest keys

```python
{
    "name": "Library",
    "version": "18.0.1.0.0",
    "depends": ["base", "mail"],
    "data": [
        "security/library_security.xml",
        "security/ir.model.access.csv",
        "views/library_book_views.xml",
        "views/library_menus.xml",
        "data/library_sequence.xml",
    ],
    "demo": ["demo/library_demo.xml"],
}
```

Files in `data` load on install and on every update. Files in `demo` load only when the database was created with demo data. Order inside the list is the load order: a file may only reference XML IDs defined earlier (or in a dependency). Security groups go first, because access rules and views reference them; menus go after the actions they point to.

## XML records

```xml
<odoo>
  <record id="book_dune" model="library.book">
    <field name="name">Dune</field>
    <field name="author_id" ref="author_herbert"/>
    <field name="pages" eval="412"/>
    <field name="tag_ids" eval="[(6, 0, [ref('tag_scifi')])]"/>
  </record>
</odoo>
```

- `ref="module.xmlid"` resolves a many2one; the module prefix is optional inside the same module.
- `eval` runs a Python expression with `ref()`, `time`, `datetime`, `timedelta` and a few helpers in scope. Use it for numbers, booleans, and x2many commands.
- `type="xml"` or `type="html"` on a field stores a literal markup fragment, used for QWeb arch and HTML fields.
- Shortcuts exist: `<menuitem>`, `<template>`, `<report>`-style elements are sugar that generate `ir.ui.menu`, `ir.ui.view`, and (in older versions) report actions. They are covered in their own chapters.

### How the XML ID works

Every `<record id="x">` creates an `ir.model.data` row `(module, name, model, res_id)`. On the next load the loader looks that row up: found means write to the existing record, missing means create. Renaming an `id` therefore creates a second record and orphans the old one; the old row is cleaned up only if the loader sees it is no longer declared (and it is not under `noupdate`).

## noupdate

```xml
<odoo noupdate="1">
  <record id="seq_loan" model="ir.sequence">
    <field name="name">Loan</field>
    <field name="code">library.loan</field>
    <field name="prefix">LN/</field>
  </record>
</odoo>
```

With `noupdate="1"`, the record is created on install and never touched again by module updates. Use it for data the customer is expected to edit: sequences, mail templates they customize, default configuration. Do not use it for views or security rules you expect to change; an edited XML would silently not apply.

A single record can opt in with `<record noupdate="1">` inside a normal `<odoo>` block. The flag lives on the `ir.model.data` row (`noupdate` column), which means it is set when the record is first created. Changing the attribute in XML later does not change existing rows in a stable way; if you need to force a reload of a `noupdate` record, write the record from a migration script or set the `ir.model.data.noupdate` flag to false first.

{% hint style="warning" %}
A common production surprise: you fix a mail template or a record rule in XML, deploy, update the module, and nothing changes. The record is `noupdate`. Check with `select module, name, noupdate from ir_model_data where name = 'your_xmlid';`.
{% endhint %}

## Updating and deleting from data files

```xml
<!-- change one field on a record owned by another module -->
<record id="base.main_company" model="res.company" forcecreate="0">
  <field name="street">Example Street 1</field>
</record>

<!-- remove a record -->
<delete model="ir.ui.view" search="[('name', '=', 'library.book.legacy')]"/>
<delete model="library.tag" id="tag_obsolete"/>
```

Writing onto another module's XML ID works, but if that record is `noupdate` the write is skipped on updates. `forcecreate="0"` tells the loader not to recreate the record if it was deleted by the user.

## CSV files

The file name is the model name; the first row is the header.

```
id,name,code
tag_scifi,Science fiction,SF
tag_history,History,HI
```

- Many2one columns use `field_id` for the XML ID or `field_id:id`; to match by name use `field_id/name`... but prefer XML IDs, names are not unique.
- The special file `ir.model.access.csv` uses columns `id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink`. `model_id:id` is `model_library_book`, the XML ID Odoo generates for each model (`model_` plus the dotted name with underscores).
- CSV records are updated by XML ID too. There is no `noupdate` attribute in CSV; the loader treats those rows as normal updatable data, except `ir.model.access.csv` entries, which are updated on every upgrade.

## Load order and dependencies

1. Modules load in dependency order, then alphabetically.
2. Within a module: `data` files in manifest order, then `demo`.
3. After all files, the module's `post_init_hook` runs on install only.

If file B needs a record from file A, put A first. If two modules each need the other's data, the design is wrong; move the shared piece into a base module.

## Pitfalls

- Referencing an XML ID from a module not in `depends` works on your machine, because that module happens to be installed, and fails on a clean database.
- Forgetting a new file in the manifest: the file is simply not loaded, with no warning.
- Putting demo records in `data`: they ship to production.
- Using `noupdate` on `ir.ui.view` and then wondering why a fix does not apply.
- Copying a record with its XML ID from a dump: two records cannot share one ID, the loader reports a duplicate key on `ir_model_data`.

## Versions

{% hint style="info" %}
The `<report>` shortcut tag was removed years ago; define `ir.actions.report` records instead (see the PDF reports chapter). Since 17 the loader also validates view architecture earlier, so a bad view in a data file fails at update time rather than at first open.
{% endhint %}

## Try it

Run the update and read what the loader did:

```bash
odoo-bin -d dev_db -u library --stop-after-init --log-level=info 2>&1 | grep -i "library"
```

Then list what you own and which of it is frozen:

```sql
select name, model, noupdate from ir_model_data where module = 'library' order by model;
```
