---
description: "ir.model.data, env.ref, and stable identifiers."
---

# XML IDs and references

A database id changes between databases; an XML ID does not. Every reference from code, data files, views and migrations to a specific record should go through an XML ID. They live in the `ir.model.data` model, one row per identifier.

## Anatomy

An XML ID is `module.name`. The row in `ir_model_data` stores `module`, `name`, the target `model`, `res_id`, and a `noupdate` flag.

```xml
<odoo>
    <data noupdate="1">
        <record id="loan_type_default" model="library.loan.type">
            <field name="name">Standard</field>
        </record>
    </data>
</odoo>
```

This creates `library.loan_type_default` (the module prefix is added when you omit it, inside the module that owns the file). Inside the same module you can reference it as `loan_type_default`; from another module use the full form.

## Resolving in Python

```python
type_ = self.env.ref('library.loan_type_default')                  # record, raises if missing
type_ = self.env.ref('library.loan_type_default', raise_if_not_found=False)
```

`env.ref(xml_id, raise_if_not_found=True)` returns a recordset of the right model. It is cached for the transaction. For just the id, or when you do not want to build a record:

```python
res_id = self.env['ir.model.data']._xmlid_to_res_id('library.loan_type_default')
```

`_xmlid_to_res_id(xmlid, raise_if_not_found=False)` returns the id, or `0` when missing. And the other direction:

```python
book.get_external_id()          # {book.id: 'library.book_dune'} or '' per record
book.get_metadata()             # includes xmlid, noupdate, create/write info
```

`get_external_id()` on a recordset returns a dictionary keyed by id. It is a query per call, so do not use it in a loop over thousands of records.

## Access checks

`env.ref` does not check access rights on the result beyond what a later read does. If you need to verify, use `check_access` on the record. The model-level helper `ir.model.data.check_object_reference(module, xml_id, raise_on_access_error=False)` returns `(model, res_id)` after checking read access.

## In views and data files

```xml
<field name="partner_id" ref="base.main_partner"/>
<field name="category_ids" eval="[(6, 0, [ref('library.cat_fiction')])]"/>
<field name="groups_id" eval="[Command.link(ref('library.group_librarian'))]"/>
```

`ref="..."` sets a Many2one. `ref('...')` in `eval` returns the id. In 17 and 18 use `Command` objects in `eval`; the numeric tuple forms still work but are harder to read.

Actions, menus and views refer to each other by XML ID: `action="library.action_books"`, `parent="library.menu_root"`. A missing or mistyped ID fails the module update, which is how typos get caught.

## Creating XML IDs from code

Records you create in Python have no XML ID. When another module or a later upgrade must find them, create one:

```python
self.env['ir.model.data'].create({
    'module': 'library',
    'name': 'default_shelf',
    'model': 'library.shelf',
    'res_id': shelf.id,
    'noupdate': True,
})
```

Use this sparingly, in `post_init_hook` or migration scripts. For batch creation from data, `_load_records` is what the XML loader uses and it handles updates of existing IDs.

## noupdate

`noupdate="1"` means the record is created on install and left alone on module updates. Without it, every `-u` rewrites the record from the XML, discarding user changes. Use `noupdate` for data users are expected to edit (templates, sequences, default configuration) and plain records for technical data (views, actions, security groups).

To change a `noupdate` record deliberately, write a migration script or use a `<function>` in a data file. Editing the XML will not do it.

## Module uninstall and renaming

Uninstalling a module deletes the records for every XML ID it owns, which is how data cleans itself. Renaming an XML ID in a later version creates a new record and, after the old row is no longer in the data files, deletes the old one at the end of the update. If other records point to it, they break. Rename with a `pre-migration` script that updates `ir_model_data.name`, or keep the old ID.

## Pitfalls

{% hint style="warning" %}
`self.env.ref('module.name')` in the body of a method that runs during module loading, before that module's data is loaded, raises. Prefer lazy lookup or `raise_if_not_found=False`.
{% endhint %}

- Referencing an XML ID from a module that is not in your `depends`. It works on your database, fails on a clean install.
- Hardcoding database ids (`browse(3)`). They differ between staging and production.
- `ref` returns a recordset in the current environment. Calling it under `sudo()` and returning the record leaks the sudo flag to the caller.
- Two files declaring the same ID in the same module: the later one overwrites the earlier, silently.
- Using `noupdate` on a view or action and then wondering why a fix does not arrive on update.

## Try it

Read only, in `psql`:

```sql
SELECT module, name, model, res_id, noupdate
FROM ir_model_data
WHERE module = 'base' AND name LIKE 'group_%'
ORDER BY name LIMIT 10;
```

Then check one in the shell:

```python
env.ref('base.group_user')
env['ir.model.data']._xmlid_to_res_id('base.group_user')
```
