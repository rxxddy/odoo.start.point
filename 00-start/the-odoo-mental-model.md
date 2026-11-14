---
description: "One page that explains how Odoo fits together before you write anything."
---

# The Odoo mental model

Odoo looks like a pile of folders, XML files and decorators until you see the five moving parts and the one rule that connects them: almost everything you write is either a Python class that becomes a table, or a data record that is loaded into one. This page gives you the map. Later chapters fill in each region.

## The five moving parts

```
 Browser (web client, OWL/JS)
        |  HTTP: JSON-RPC (/web/dataset/call_kw), controllers, assets
        v
 +--------------------------------------------------------------+
 | Odoo server process (Python, one per worker)                 |
 |                                                              |
 |  HTTP layer (werkzeug) --> dispatch --> Environment (env)    |
 |                                            |                 |
 |  Registry (one per database)               v                 |
 |   - model classes, built from modules   ORM: recordsets,     |
 |   - fields, methods, inheritance chain  fields, domains,     |
 |   - view/ACL/rule caches                access checks        |
 +----------------------------|---------------------------------+
                              | SQL (psycopg2), one transaction per request
                              v
                        PostgreSQL
              tables, ir_model_data, ir_ui_view, ir_act_*, ir_rule ...
```

**PostgreSQL** holds everything: business data, and also the description of the application itself (views, actions, menus, access rights, translations). A database is an installation. Two databases on the same server can run different module sets.

**The server** is a Python process that serves HTTP, runs cron jobs and executes your code. It is stateless between requests apart from in-memory caches, which is why you can run several workers against one database. See [workers, cron and longpolling](../04-architecture/workers-cron-and-longpolling.md).

**The registry** is a per-database object built at startup. It loads the installed modules in dependency order, collects every class that declares `_name` or `_inherit`, merges them into one final class per model, and creates or updates the tables to match. After that, `env['library.book']` returns a recordset of the merged class. Details in [registry and model loading](../04-architecture/registry-and-model-loading.md).

**The ORM** is the only door to the data you should use. A recordset (`self`) is an ordered set of ids plus an environment (database cursor, user, context). Reading a field fetches from cache or SQL, writing goes through `write()`, and every call checks access rights and record rules for the environment's user. See [models and recordsets](../06-orm/models-and-recordsets.md).

**The web client** is a JavaScript application that knows nothing about your models. It asks the server for a view definition (`get_views`), then for data (`web_search_read`, `web_read`, `web_save`), and renders what comes back. A form you did not code in JS appears because an XML arch described it.

## A module is a unit of installation

A module is a directory with a `__manifest__.py` and a mix of Python, XML/CSV data and static assets:

```
library/
  __manifest__.py      # name, depends, data (ordered), assets
  models/              # Python classes -> tables, behaviour
  views/               # XML: ir.ui.view, ir.actions.*, ir.ui.menu
  security/            # groups, ir.model.access.csv, record rules
  data/                # reference or demo records
  report/              # QWeb templates and ir.actions.report
  wizard/              # TransientModel classes and their views
  static/              # JS, SCSS, images
  tests/
```

Installing a module does three things in order: loads its Python so the registry can build models, creates or alters the tables, then loads each file listed in `data` (and `demo` when enabled). Upgrading re-runs the data files, which is how an XML change reaches an existing database. See [anatomy of a module](../04-architecture/anatomy-of-a-module.md).

## Code and data are two halves of one feature

This is the idea beginners miss. A feature is spread over several kinds of artifact, and each is stored differently:

| Artifact | Written as | Stored in | Loaded when |
|---|---|---|---|
| Model, fields, methods | Python class | Python import; columns in the table | Registry build |
| View, action, menu, report | XML record | `ir_ui_view`, `ir_act_window`, `ir_ui_menu`, `ir_act_report_xml` | Install / upgrade |
| Access rights | CSV or XML record | `ir_model_access`, `ir_rule` | Install / upgrade |
| Reference data, demo data | XML/CSV record | The model's own table | Install / upgrade |
| Translations | `.po` files | `ir_translation` (16) / JSONB columns (17+) | Language load |

Two consequences follow. First, changing Python needs a server restart, changing XML needs a module upgrade (`-u library`), and changing both needs both. Second, every XML record gets an external id stored in `ir_model_data`, for example `library.book_form`. That row is how a later upgrade finds the record it created before and updates it instead of duplicating it. See [XML ids and references](../06-orm/xml-ids-and-references.md).

{% hint style="info" %}
Versions: translations of field values and view terms moved into JSONB columns in Odoo 16 for fields, and `ir_translation` was removed for most terms in 17. The mental model is the same: translations are data, not code.
{% endhint %}

## How the pieces point at each other

Follow one screen backwards:

1. A **menu** (`ir.ui.menu`) points to an **action** (`ir.actions.act_window`).
2. The action names a **model** (`res_model`) and the view types to offer (`list`, `form`, ...).
3. Each **view** (`ir.ui.view`) holds an XML arch whose `<field name="...">` tags must exist on that model.
4. When the user opens the screen, the **ORM** reads those fields, but only after the **security** layer has answered two questions: may this user's groups read this model (`ir.model.access`), and which rows may they see (`ir.rule`)?
5. A button in the form calls a **method** on the model by name (`type="object"`), or runs another action (`type="action"`).

If a link in this chain is wrong you get a precise failure: a missing field breaks view validation at install time, a missing access line gives an access error at first use, a missing menu group makes the menu simply vanish.

## What happens on a click

A user presses a button labelled "Return". Roughly:

1. The client sends a JSON-RPC call to `/web/dataset/call_kw/library.loan/action_return` with record ids and the context.
2. The HTTP layer authenticates the session, opens a cursor and builds an `Environment(cr, uid, context)`.
3. The dispatcher looks up the model in the registry, browses the ids, checks that the method is public (no leading underscore), and calls it.
4. Your method reads and writes through the ORM. Writes are flushed to SQL, computed fields are recomputed, constraints run.
5. On success the transaction commits. On any exception it rolls back entirely, so a request never leaves half a change behind.
6. The method returns `True`, a dict (an action to run next), or a value. The client renders the outcome.

The full path, including the `type="http"` controllers and report endpoints, is in [request lifecycle](../04-architecture/request-lifecycle.md).

## Inheritance is how you change what exists

You almost never edit the Odoo source. You extend it, in three forms:

- **Class inheritance** (`_inherit = 'res.partner'`) adds fields and overrides methods on an existing model. The registry merges your class into the chain.
- **View inheritance** (`inherit_id` plus `xpath`) patches another module's XML arch without copying it.
- **Data override** (a record with the same external id) replaces values on an existing record.

Because the result is one merged class per model, order matters: the `depends` list in your manifest decides who is applied first, and `super()` is how your override cooperates with the layers below. See [inheritance](../06-orm/inheritance.md).

## Pitfalls

- **Treating the database as the source of truth for views.** The Python and XML in the module are the source. Editing a view in the UI works until the next upgrade resets it.
- **Forgetting the load order of `data`.** Security files first, then views that reference groups, then menus that reference actions. An XML id used before it is defined fails at install.
- **Running code at import time that touches the database.** The registry does not exist yet. Do work inside methods.
- **Bypassing the ORM with raw SQL** for convenience. You lose access checks, cache invalidation and computed field triggers. Use it deliberately and flush first.
- **Assuming a restart picks up XML.** It does not. Upgrade the module.

## Try it

Read-only: list what the registry knows about one model and where its views come from.

```bash
psql -d mydb -c "select model, name from ir_model where model like 'library.%';"
psql -d mydb -c "select name, model, type, inherit_id from ir_ui_view where model = 'library.book';"
psql -d mydb -c "select module, name, res_id from ir_model_data where model = 'ir.ui.view' and module = 'library';"
```

The third query shows the external ids that tie your XML files to database rows. Next, see the [wizard and report blueprint](../13-blueprints/blueprint-wizard-and-report.md) for all the parts working together in one feature.
