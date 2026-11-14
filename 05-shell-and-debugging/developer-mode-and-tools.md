---
description: "Debug mode, view editor, technical menu, and metadata inspection."
---

# Developer mode and tools

Developer mode exposes the metadata Odoo keeps about itself: models, fields, views, access rules, XML IDs. Most "why does this behave like that" questions are answered by one click there, faster than reading source.

## Turning it on

- URL: append `?debug=1` to the address. Use `?debug=assets` to serve unminified assets, useful when debugging JavaScript. `?debug=0` turns it off.
- Settings: Settings, Developer Tools, Activate the developer mode (with variants for assets).
- Keep it on while developing; do not leave it on for ordinary users, since it exposes technical menus and raw fields.

In recent versions a bug icon appears in the top bar when active. It opens the debug menu with the items for the current view.

## The debug menu on a form

Open any record with debug active and you get entries such as:

- **Edit View: Form** and the equivalent for list, search, kanban: opens the view's arch for editing. Edits are stored in the database as a customised view and are lost or conflict when the module is updated. Use it to experiment, then move the change to your module's XML.
- **View Fields**: the fields of the model with their types and technical names.
- **View Metadata**: the record's id, XML ID, creator and write date, and whether it is `noupdate`.
- **Manage Attachments**, **Set Defaults**, **Edit Action**, **View Access Rights**, **View Record Rules**.
- **Run Tour**, **Start Tour** and **Disable Tours** when working with tours.

Labels differ slightly by version.

## Technical menu

Settings, Technical (visible only in debug mode) contains the tables behind the system:

| Menu | Model | Typical use |
| --- | --- | --- |
| Models, Fields | `ir.model`, `ir.model.fields` | Find a field's technical name, type, stored or not |
| Views | `ir.ui.view` | See inherited views and their priority; the combined arch |
| Actions | `ir.actions.*` | Check domain, context, view mode of a menu entry |
| Scheduled Actions | `ir.cron` | Run now, change interval, see last call |
| Automation Rules | `base.automation` | Triggers on create and write |
| Server Actions | `ir.actions.server` | Code that menus and buttons run |
| Sequences | `ir.sequence` | Fix numbering |
| Parameters, System Parameters | `ir.config_parameter` | `web.base.url`, mail settings |
| Access Rights, Record Rules | `ir.model.access`, `ir.rule` | Why a user cannot see something |
| Outgoing Mail Servers, Emails | `ir.mail_server`, `mail.mail` | Stuck mail |
| Translations | `ir.translation` / `ir.model.fields.translate` storage | Wrong labels (storage changed in 16/17) |

## Finding out why a user cannot do something

1. Reproduce as the user: Settings, Users, pick the user, then Action, Impersonate (debug mode; in older versions log in with the user's credentials or use the shell with `env(user=...)`).
2. Check Access Rights for the model and the user's groups.
3. Check Record Rules for the model: a rule with a domain that excludes the record shows as "record does not exist" or an access error.
4. Check for a field with `groups=` that hides it in the view.

## Inspecting a view that does not do what you expect

The combined view is what the client receives. In debug mode, Edit View shows the source of the current view; the inheritance chain is under Settings, Technical, Views, with the "Inherited Views" tab. When your `xpath` does not apply you get an error at update time naming the view and the locator that failed.

From the shell you can see the final arch:

```python
>>> env['library.book'].get_view(view_type='form')['arch']
```

(`get_view` exists from 16; older versions use `fields_view_get`.)

## Metadata from the shell

```python
>>> rec = env['library.book'].browse(7)
>>> rec.get_metadata()
>>> rec.get_external_id()
```

Both are the same data as View Metadata.

## Developer shortcuts in the UI

- Hovering a field label in debug mode shows its technical name, type, and model.
- The list view's column selector and "Export" dialog show technical field names.
- Pressing the QWeb or "Inspect" tools shows which template rendered a block in a report; the "Edit Template" entry in a website or report context opens the QWeb source.

## Pitfalls

- **Editing views in the UI on a database that gets updated.** Your change is overwritten or conflicts after `-u`. Treat UI edits as scratch work.
- **`noupdate` data.** Records in `noupdate="1"` are not refreshed by module updates; View Metadata shows the flag when you wonder why your XML change did not arrive.
- **Debug assets in production.** `?debug=assets` is slower and not meant for users.
- **Changing system parameters casually.** `web.base.url` and mail parameters affect links in outgoing mail.
