---
description: "Changing list, form and kanban views with js_class, subclassed controllers and renderers, and button templates, without patching the core."
---

# Customising views

Every list, form and kanban screen is assembled from a small set of replaceable parts: a controller, a renderer, a model, an arch parser, and a button template. They are bundled into a **view definition** stored in the `views` registry, and an individual view picks its definition with the `js_class` attribute. That is the supported way to change one screen without touching any other, and this chapter shows how it works and walks through four recipes: a list with an extra control panel button, a list that colours rows by a business rule, a form that confirms before a button runs, and a kanban card with extra classes.

Everything was read from the Odoo 18 source (`addons/web/static/src/views`). Odoo 20 differences are at the end.

## The view stack

When an action opens a view, the `View` component (`views/view.js`) does the following:

1. Loads the arch and field metadata from the server.
2. Reads the `js_class` attribute of the arch root, or falls back to the view type (`list`, `form`, `kanban`, ...). That string is the key looked up in the `views` registry.
3. If the key is not in the registry it first loads the lazy bundle `web.assets_backend_lazy` (this is how the graph and pivot views load on demand) and then looks again.
4. Calls the definition's `props(genericProps, view)` function to build the props for the controller. It parses the arch with `ArchParser`, and passes `Model`, `Renderer`, `buttonTemplate` and `archInfo` along.
5. Renders `Controller`, which renders `Renderer` inside a `Layout` with the control panel.

So a definition is a plain object:

```javascript
export const listView = {
    type: "list",
    Controller: ListController,
    Renderer: ListRenderer,
    ArchParser: ListArchParser,
    Model: RelationalModel,
    buttonTemplate: "web.ListView.Buttons",
    canOrderByCount: true,
    props: (genericProps, view) => { /* returns the controller props */ },
};
registry.category("views").add("list", listView);
```

Your override is the same object with some keys replaced:

```javascript
registry.category("views").add("library_loan_list", {
    ...listView,
    Controller: LoanListController,
});
```

The spread copies `props`, which reads `Renderer`, `Model` and `buttonTemplate` from the `view` argument (the definition object itself), so replacing a key on your copy is enough: the standard `props` function passes it on. For the kanban view the core comments that it does **not** pass `Compiler` automatically "in stable, for backward compat"; if you replace `Compiler` on a kanban definition, read `kanban_view.js` and pass it yourself in a custom `props`.

Select the definition per view, on the root tag:

```xml
<record id="view_loan_list" model="ir.ui.view">
    <field name="name">library.loan.list</field>
    <field name="model">library.loan</field>
    <field name="arch" type="xml">
        <list js_class="library_loan_list">
            <field name="book_id"/>
            <field name="member_id"/>
            <field name="due_date"/>
            <field name="state"/>
        </list>
    </field>
</record>
```

Two points:

- In Odoo 18 the list arch root tag is `<list>` and the view type is `list`. Earlier versions call it `<tree>`. A 17 arch must say `<tree js_class="...">`.
- `js_class` is the **registry key** and has nothing to do with a file name. If the key is not registered, the view falls back to loading the lazy bundle and then raises "Cannot find key" in the `views` registry. Check the console.

Only views that carry the attribute change. Everything else keeps using the stock definition, which is the point.

## What each part does

| Part | Class (list) | Customise it to |
| --- | --- | --- |
| `Controller` | `ListController` | add buttons and actions, hook into save, delete, open record, react to selection |
| `Renderer` | `ListRenderer` | change how rows and cells look: classes, cell content, column headers |
| `Model` | `RelationalModel` | change how data loads and saves (advanced) |
| `ArchParser` | `ListArchParser` | read extra arch attributes into `archInfo` |
| `buttonTemplate` | `web.ListView.Buttons` | change the buttons in the control panel |
| `Compiler` (form, kanban) | `FormCompiler`, `KanbanCompiler` | change how arch XML becomes a template |

The controller owns actions and the model; the renderer owns presentation. Put logic in the controller and keep the renderer to appearance.

## Recipe 1: an extra button in the list control panel

Goal: a "Overdue report" button next to the standard buttons of `library.loan` lists. Clicking it opens the loans list filtered to open, past-due loans.

Controller, `library/static/src/loan_list/loan_list_controller.js`:

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

export class LoanListController extends ListController {
    setup() {
        super.setup(...arguments);
        this.libraryAction = useService("action");
    }

    onClickOverdue() {
        this.libraryAction.doAction({
            type: "ir.actions.act_window",
            name: "Overdue loans",
            res_model: "library.loan",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "open"], ["due_date", "<", new Date().toISOString().slice(0, 10)]],
        });
    }
}

registry.category("views").add("library_loan_list", {
    ...listView,
    Controller: LoanListController,
    buttonTemplate: "library.LoanListView.Buttons",
});
```

Button template, `library/static/src/loan_list/loan_list.xml`. It extends the standard buttons template as a new, separate template:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="library.LoanListView.Buttons" t-inherit="web.ListView.Buttons" t-inherit-mode="primary">
        <xpath expr="//div[hasclass('o_list_buttons')]" position="inside">
            <button t-if="!editedRecord" type="button" class="btn btn-secondary"
                    t-on-click="onClickOverdue">
                Overdue report
            </button>
        </xpath>
    </t>
</templates>
```

Why it is built this way:

- `t-inherit-mode="primary"` creates the new template `library.LoanListView.Buttons`, leaving `web.ListView.Buttons` alone. Other lists keep the standard buttons. With `extension` you would modify the standard template for every list.
- The buttons template is rendered with the controller as its context (`t-call="{{ props.buttonTemplate }}"` inside `web.ListView`), which is why `editedRecord` and `onClickOverdue` are visible by name.
- The standard buttons template holds the Save and Discard buttons for inline editing, wrapped in a div with class `o_list_buttons`. Adding inside that div keeps your button in the same toolbar.
- The date comparison uses `toISOString().slice(0, 10)`, which is UTC. For a domain on a `date` field that is fine for a report, but in a timezone far from UTC close to midnight it can be a day off. For exact "today", compute it server-side with a filter in the search view (`<filter name="overdue" domain="[('due_date', '&lt;', context_today().strftime('%Y-%m-%d'))]"/>`).

If the button should act on selected rows, read them from the model: `this.model.root.selection` is the list of selected records in 18 (the core builds its active ids from it with `this.model.root.selection.map((r) => r.resId)`).

## Recipe 2: colouring rows by a business rule

Decorations in the arch are the first tool and need no JavaScript:

```xml
<list decoration-danger="state == 'open' and overdue" decoration-muted="state == 'returned'">
```

`decoration-*` attributes take a Python-like expression over the fields in the view. Use them whenever the rule is a condition on fields already in the list (`overdue` could be a stored or computed boolean field).

When the rule needs computation that a decoration expression cannot express (dates compared to now, several records), override `getRowClass` in a renderer. The base method collects decoration classes and adds selection classes, so call it first:

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";

const { DateTime } = luxon;

export class LoanListRenderer extends ListRenderer {
    getRowClass(record) {
        let classes = super.getRowClass(record);
        const due = record.data.due_date;
        if (record.data.state === "open" && due && due < DateTime.now().startOf("day")) {
            classes += " o_library_overdue";
        }
        return classes;
    }
}

registry.category("views").add("library_loan_list", {
    ...listView,
    Renderer: LoanListRenderer,
});
```

```scss
// library/static/src/loan_list/loan_list.scss
.o_list_renderer .o_data_row.o_library_overdue {
    --table-bg: var(--bs-danger-bg-subtle);
}
```

To combine recipes 1 and 2 in one view definition, put both keys in a single registration, since two registrations of `library_loan_list` would collide:

```javascript
registry.category("views").add("library_loan_list", {
    ...listView,
    Controller: LoanListController,
    Renderer: LoanListRenderer,
    buttonTemplate: "library.LoanListView.Buttons",
});
```

`record.data.due_date` is available only when `due_date` is in the list. If you do not want the column visible, add it with `column_invisible="1"`:

```xml
<field name="due_date" column_invisible="1"/>
```

Other renderer methods worth knowing in 18: `getCellClass(column, record)`, `getCellTitle(column, record)`, `getColumnClass(column)`, `isSortable(column)`, `canUseFormatter(column, record)`. Prefer overriding one of these small methods rather than copying a large template.

## Recipe 3: a form that confirms a button

Form buttons of `type="object"` or `type="action"` go through `beforeExecuteActionButton(clickParams)` in the controller. It saves the record first by default and returns whether it succeeded; returning `false` cancels the click. Wrap it to ask first:

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";

export class LoanFormController extends FormController {
    setup() {
        super.setup(...arguments);
        this.libraryNotification = useService("notification");
    }

    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "action_return") {
            const confirmed = await new Promise((resolve) => {
                this.dialogService.add(ConfirmationDialog, {
                    title: "Return this loan?",
                    body: "The book will be marked as available.",
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                    dismiss: () => resolve(false),
                });
            });
            if (!confirmed) {
                return false;
            }
        }
        return super.beforeExecuteActionButton(...arguments);
    }

    async onWillSaveRecord(record) {
        if (!record.data.book_id) {
            this.libraryNotification.add("Pick a book before saving.", { type: "danger" });
            return false;   // cancels the save
        }
    }
}

registry.category("views").add("library_loan_form", {
    ...formView,
    Controller: LoanFormController,
});
```

```xml
<form js_class="library_loan_form">
    <header>
        <button name="action_return" type="object" string="Return" class="btn-primary"/>
    </header>
    ...
</form>
```

Notes:

- `this.dialogService` exists on the form controller in 18 (the core uses it for the archive and delete confirmations). The controller has no notification property, so the example gets its own with `useService("notification")` in `setup`.
- `clickParams.name` is the `name` attribute of the button, so one controller can treat several buttons differently.
- The hook `onWillSaveRecord` is documented in the source: it runs "before the record save if the record is valid" and returning `false` prevents the save.
- Remember that confirmation in JavaScript protects users, not data. If a rule must hold, enforce it with a constraint or a state check in the Python method.

## Recipe 4: a kanban card with extra classes

The kanban card is the `KanbanRecord` component. The renderer lists it in `static components`, so you replace it by overriding that list on a renderer subclass, and then register the renderer:

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanRecord } from "@web/views/kanban/kanban_record";

class LoanKanbanRecord extends KanbanRecord {
    getRecordClasses() {
        let classes = super.getRecordClasses();
        if (this.props.record.data.state === "open") {
            classes += " o_library_open_loan";
        }
        return classes;
    }
}

class LoanKanbanRenderer extends KanbanRenderer {
    static components = { ...KanbanRenderer.components, KanbanRecord: LoanKanbanRecord };
}

registry.category("views").add("library_loan_kanban", {
    ...kanbanView,
    Renderer: LoanKanbanRenderer,
});
```

`getRecordClasses()` returns a string of classes in 18 (`classes.push(...)` then joined). Always call `super` and append to the string. The card template itself comes from the arch (`<templates><t t-name="card">`) and is compiled by the kanban compiler, so markup changes belong in the arch of the view.

## The arch parser: reading new attributes

To give your view its own arch attributes, parse them into `archInfo`:

```javascript
import { ListArchParser } from "@web/views/list/list_arch_parser";

class LoanListArchParser extends ListArchParser {
    parse(xmlDoc, models, modelName) {
        const archInfo = super.parse(...arguments);
        archInfo.libraryWarnDays = parseInt(xmlDoc.getAttribute("library_warn_days") || "0", 10);
        return archInfo;
    }
}

registry.category("views").add("library_loan_list", {
    ...listView,
    ArchParser: LoanListArchParser,
});
```

```xml
<list js_class="library_loan_list" library_warn_days="3">
```

The renderer and controller receive `archInfo` as a prop, so `this.props.archInfo.libraryWarnDays` is available. Server-side arch validation in Odoo 18 checks known attributes of known tags against RNG schemas; an unknown attribute on a standard tag may be rejected when the view is saved. If it is, put the setting in `options` or in the `context` of the action instead.

## Layout slots and where markup goes

The list view template `web.ListView` fills slots of the `Layout` component: `control-panel-create-button`, `layout-buttons`, `control-panel-always-buttons`, `layout-actions`, `control-panel-navigation-additional`, among others. The buttons template you replaced above is what the `layout-buttons` slot calls. For changes that fit a slot, the button template is the smaller intervention. For deeper structural changes, extend the template with `t-inherit` (see the patching chapter) rather than copy it.

## Sharing code across views

A recurring need is "all list views of module X should behave like this". Do not patch `ListController` for it. Define the definition once and select it explicitly with `js_class` on each arch that wants it. Where many views need the same behaviour, make the shared part a mixin-style base class and give each view its own small subclass registered under its own key.

## Odoo 20 notes

In the Odoo 20 source the view definition objects keep their shape (`type`, `Controller`, `Renderer`, `ArchParser`, `Model`, `buttonTemplate`, `props`). What changes is the component code underneath:

- Controllers declare `props = useProps({...})` with OWL 3 types instead of `static props`.
- Templates address members with `this.`.
- Some method signatures changed. Examples from the two trees: `ListController.openRecord(record, force)` becomes `openRecord(record, { force, newWindow })`, and `FormController.beforeLeave()` becomes `beforeLeave({ forceLeave })`. Re-read each method you override.
- The 20 list view definition does not carry the `limit: 80` key that 18 has.

The registry key, the `js_class` attribute and the subclass-and-spread technique carry over. Treat each override as something to re-verify after a major upgrade.

## Pitfalls

- **Registering the same key twice.** The second `add` throws on load. Build one definition per `js_class` and put all keys in it.
- **`js_class` typo.** The view loads the lazy bundle, then fails looking the key up.
- **Using `<tree>` in 18.** The arch root is `<list>` in 18.
- **Overriding a method and not calling `super`.** You lose selection classes, decorations or saving behaviour of the base.
- **Using `extension` instead of `primary` for a buttons template.** The standard list buttons change for every list in the database.
- **Reading a field that is not in the arch.** `record.data.due_date` is undefined unless the field is in the view; add it with `column_invisible="1"`.
- **Relying on private members** (`_something`) of controllers or models. Prefer documented hook methods (`onWillSaveRecord`, `beforeExecuteActionButton`, `afterExecuteActionButton`, `getRowClass`).
- **Logic in the renderer.** Actions belong to the controller; the renderer re-renders often and should stay pure.
- **Client-side checks as business rules.** The server must enforce them.

## Versions

{% hint style="info" %}
**16:** views are mixed legacy and OWL. The OWL view stack exists for list, form, kanban and others, but legacy views still appear. Arch root is `<tree>`.

**17:** the OWL view stack is the only one. Arch root is `<tree>`.

**18:** arch root is `<list>`; the registry shapes above apply.

**20:** same registry model, OWL 3 component code.
{% endhint %}

## Try it

1. Implement recipe 1. Open `library.loan` through an action. Check the button appears on lists using `js_class` and not on others.
2. Add recipe 2's renderer to the same definition. Create a loan with a past due date and confirm the row class.
3. Replace `t-inherit-mode="primary"` with `extension` in the buttons template, restart, and look at a different model's list. Revert it.
4. Misspell `js_class` in the arch and read the console.

<details>

<summary>Solution notes</summary>

1. The button only exists where the arch has `js_class="library_loan_list"`, because only that definition points at the new button template.
2. The row gets the class from `getRowClass`; with `?debug=1` you can inspect the `tr` and find `o_library_overdue`.
3. With `extension`, the standard template `web.ListView.Buttons` is modified, so every list view in the database shows the button (and `onClickOverdue` does not exist on other controllers, so the click throws).
4. The `views` registry reports that the key cannot be found, after the lazy bundle has been requested.

</details>
