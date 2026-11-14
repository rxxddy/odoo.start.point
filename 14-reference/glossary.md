---
description: Terms used in the book.
---

# Glossary

**Action.** A record telling the client what to open: a window action (`ir.actions.act_window`), a report, a server action, or a URL.

**Addon / module.** A directory with a `__manifest__.py` that adds models, views, data or code. Used interchangeably in this book.

**Addons path.** The list of directories Odoo scans for modules, set by `addons_path`.

**Aggregate.** In `_read_group`, a string like `'fee:sum'` or `'__count'` computed per group.

**Batch (create).** A call to `create` with a list of value dicts, handled by `@api.model_create_multi`.

**Chatter.** The message and activity panel from `mail.thread`.

**Command.** A tuple-like helper (`Command.create`, `Command.link`, and others) used to write x2many fields.

**Computed field.** A field filled by a method listed in `compute=`; stored only if `store=True`.

**Context.** A dictionary carried on the environment: language, time zone, defaults, and feature flags like `tracking_disable`.

**Cursor (`cr`).** The database connection wrapper for the current transaction.

**Domain.** A list of conditions in prefix notation used to filter records.

**Environment (`env`).** The bundle of cursor, user, context and registry through which all ORM calls go.

**External ID (xml id).** A stable name `module.name` stored in `ir.model.data` that points to a record.

**Filestore.** The directory holding attachment files; a database dump does not include it.

**Group.** A set of users with access rights, defined in `res.groups`.

**Inheritance, classical.** `_inherit = 'model'` without `_name`: extend a model in place.

**Inheritance, delegation.** `_inherits` with a Many2one: a model exposes the fields of another through a link.

**Inheritance, prototype.** `_inherit` with a new `_name`: copy a model into a new one.

**Manifest.** The `__manifest__.py` file declaring name, version, dependencies and data files.

**Migration script.** A `pre-`, `post-` or `end-` Python file in a module's `migrations/<version>` folder, run on update.

**Model.** A Python class mapped to a table and registered by `_name`; abstract models have no table, transient ones are temporary.

**noupdate.** A flag on data that stops the file from overwriting user changes on later updates.

**ORM.** The layer mapping models and fields to PostgreSQL tables.

**OWL.** Odoo's JavaScript component framework used in the web client since 16.0.

**Record rule.** A domain-based row-level access restriction on a model.

**Recordset.** An ordered set of records of one model; the unit of all ORM operations.

**Registry.** The loaded set of models for one database.

**Sequence.** An `ir.sequence` record generating numbered references.

**`sudo()`.** Returns a recordset that bypasses access rights and record rules.

**Transient model.** A model for wizards, with rows purged periodically.

**View.** An `ir.ui.view` record with an XML `arch` describing a form, list, search, kanban or other layout. The list view tag was `tree` until 16.0.

**Wizard.** A form on a transient model that collects input and then performs an action.

## Pitfalls

- Using "module" for a Python package and "addon" for a deliverable in the same project; pick one in your own docs.
- Confusing the xml id (`module.name`) with the database id, which differs between databases.
