---
description: "Writing field widgets and view widgets for Odoo 17 and 18 forms, lists and kanbans, with complete working examples."
---

# Custom field widgets

A field widget is an OWL component that displays and edits one field of a record, registered in the `fields` registry and selected from a view with `widget="name"`. A view widget is the same idea without a field behind it, registered in `view_widgets` and placed with `<widget name="..."/>`. This chapter shows how the web client finds a widget, what it hands your component, how to read and write values correctly, and builds three complete widgets: an editable ISBN field with validation, a read-only "days overdue" badge that pulls an extra field, and a view widget.

All behaviour was read from the Odoo 18 source (`addons/web/static/src/views/fields`, `views/widgets`, `model/relational_model`). The OWL 3 form used by Odoo 20 is shown at the end.

## How a widget is found

When a form, list or kanban arch is parsed, each `<field>` node goes through `Field.parseFieldNode`. The resolution of the widget class is `getFieldFromRegistry(fieldType, widget, viewType, jsClass)`:

1. If the node has `widget="foo"`, look for `foo` in the `fields` registry, trying these keys in order: `<jsClass>.foo` (only if the view has a `js_class`), `<viewType>.foo` (for example `list.foo`, `form.foo`, `kanban.foo`), then plain `foo`. The first that exists wins. If none exists you get a console warning `Missing widget: foo for field of type char` and a fallback.
2. Otherwise look up the field's **type** the same way (`char`, `many2one`, ...), falling back to a generic `DefaultField`.

This lookup order is the reason the core registers `many2one` and `list.many2one` separately, and it gives you a clean way to ship one widget with a different implementation for lists: register `library_isbn` and `list.library_isbn`.

The parser also collects, per field node: `options` (the dictionary from the `options="{...}"` attribute, evaluated), `attrs` (every other non-dynamic attribute such as `placeholder`, `password`), `context`, `domain`, `string`, `help`, `decoration-*`, and the `invisible`, `readonly`, `required`, `column_invisible` expressions. Your widget never parses arch. It receives these through `extractProps`.

## The anatomy of a widget

Two objects: the component and the definition.

```javascript
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class MyField extends Component {
    static template = "library.MyField";
    static props = {
        ...standardFieldProps,       // id, name, readonly, record
        strict: { type: Boolean, optional: true },
    };
}

export const myField = {
    component: MyField,
    displayName: "My field",                  // label in the Studio-like editors
    supportedTypes: ["char"],                 // field types it can be used on
    supportedOptions: [ ... ],                // documented options (optional)
    extractProps(fieldInfo, dynamicInfo) {    // arch -> component props
        return { strict: Boolean(fieldInfo.options.strict) };
    },
};

registry.category("fields").add("my_field", myField);
```

The keys of the definition, from the registry validation schema in `field.js`:

| Key | Purpose |
| --- | --- |
| `component` | the OWL component class (mandatory) |
| `displayName` | human-readable name |
| `supportedTypes` | field types the widget works on |
| `supportedOptions`, `supportedAttributes` | descriptions of options/attributes, used by editors; each is `{ label, name, type, default?, help?, choices? }` |
| `extractProps(fieldInfo, dynamicInfo)` | turns arch information into extra props |
| `isEmpty(record, fieldName)` | custom emptiness for the "empty field" styling |
| `isValid(record, fieldName, fieldInfo)` | replaces the validity test used for the red outline (visual only, does not block saving) |
| `fieldDependencies` | extra fields the widget needs loaded (array, or function of the field node) |
| `relatedFields`, `useSubView` | for x2many-like widgets that need subview fields |
| `additionalClasses` | CSS classes added to the field wrapper |
| `listViewWidth` | default column width in lists (number, `[min, max]`, or function) |
| `label` | set `false` to suppress the label |

`fieldInfo` is the parsed node: `{ name, type, widget, options, attrs, string, context, decorations, ... }`. `dynamicInfo` holds what depends on the current record: `readonly`, `required`, `context`, and a `domain()` function. Always take `readonly` from `dynamicInfo` when you need it in props: the final readonly state of the widget is `readonly || !record.isInEdition`, which `Field` computes for you.

## What your component receives

In `props`:

- `record`: the record datapoint.
- `name`: the field name. Never hard-code it; the same widget serves many fields.
- `readonly`: true when the widget must not edit. It already accounts for view readonly attributes and for the record not being in edition.
- `id`: the DOM id to put on your input so the label focuses it.
- plus whatever `extractProps` returned.

On `record` you will use:

| Member | Meaning |
| --- | --- |
| `record.data[name]` | the current value (formats below) |
| `record.fields[name]` | field metadata from the server: `type`, `string`, `size`, `trim`, `translate`, `required`, `selection`, `relation`, ... |
| `record.update(changes, { save })` | change one or more fields; `save: true` writes to the database immediately |
| `record.isInEdition` | whether the record is editable right now |
| `record.isNew`, `record.resId`, `record.resModel` | identity |
| `record.setInvalidField(name)` | mark the field invalid (red) |
| `record.isFieldInvalid(name)` | read it back |
| `record.model.bus` | event bus of the model |

Value formats in `record.data`:

| Field type | JavaScript value |
| --- | --- |
| `char`, `text`, `html` | string (`false` when empty for some types, normalise with `|| ""`) |
| `integer`, `float`, `monetary` | number |
| `boolean` | boolean |
| `date`, `datetime` | `luxon.DateTime`, or `false` when empty |
| `selection` | the key string, or `false` |
| `many2one` | `[id, display_name]` pair, or `false` |
| `one2many`, `many2many` | a static list object (not an array of ids) |

Write with the same shapes. To set a many2one pass `[id, display_name]` or `false`; incomplete pairs are completed from the server. Never mutate `record.data` directly: `record.update` runs onchange, dirty tracking and validation.

## Reading luxon dates

`luxon` is a global in the web client:

```javascript
const { DateTime } = luxon;
const due = this.props.record.data.due_date;      // DateTime or false
const days = due ? Math.floor(DateTime.now().startOf("day").diff(due.startOf("day"), "days").days) : 0;
```

## Example 1: an editable ISBN field

Requirement: a char field that accepts ISBN-10 or ISBN-13 with or without hyphens, rejects invalid check digits (red outline, record cannot be saved), and stores the digits only.

The validation logic is a plain module, so it can be tested alone. `library/static/src/fields/isbn.js`:

```javascript
/** @odoo-module **/

export function normalizeIsbn(raw) {
    return (raw || "").replace(/[\s-]/g, "").toUpperCase();
}

export function isValidIsbn(raw) {
    const s = normalizeIsbn(raw);
    if (/^\d{9}[\dX]$/.test(s)) {
        let sum = 0;
        for (let i = 0; i < 10; i++) {
            sum += (s[i] === "X" ? 10 : Number(s[i])) * (10 - i);
        }
        return sum % 11 === 0;
    }
    if (/^\d{13}$/.test(s)) {
        let sum = 0;
        for (let i = 0; i < 13; i++) {
            sum += Number(s[i]) * (i % 2 ? 3 : 1);
        }
        return sum % 10 === 0;
    }
    return false;
}

export function formatIsbn(raw) {
    const s = normalizeIsbn(raw);
    if (s.length === 13) {
        return `${s.slice(0, 3)}-${s.slice(3, 4)}-${s.slice(4, 9)}-${s.slice(9, 12)}-${s.slice(12)}`;
    }
    return s;
}
```

The three functions were run against known values: `9780306406157`, `0-306-40615-2` and `080442957X` are valid; the same numbers with a changed last digit, `abc` and the empty string are not; `formatIsbn("9780306406157")` returns `978-0-30640-615-7`.

The component, `library/static/src/fields/isbn_field.js`:

```javascript
/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useInputField } from "@web/views/fields/input_field_hook";
import { formatIsbn, isValidIsbn, normalizeIsbn } from "./isbn";

export class IsbnField extends Component {
    static template = "library.IsbnField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
    };

    setup() {
        useInputField({
            getValue: () => formatIsbn(this.props.record.data[this.props.name]),
            parse: (value) => this.parse(value),
        });
    }

    get formattedValue() {
        return formatIsbn(this.props.record.data[this.props.name]);
    }

    parse(value) {
        if (!value.trim()) {
            return false;
        }
        if (!isValidIsbn(value)) {
            throw new Error("Invalid ISBN");   // marks the field invalid
        }
        return normalizeIsbn(value);
    }
}

export const isbnField = {
    component: IsbnField,
    displayName: _t("ISBN"),
    supportedTypes: ["char"],
    extractProps: ({ attrs }) => ({
        placeholder: attrs.placeholder,
    }),
    isEmpty: (record, fieldName) => !record.data[fieldName],
};

registry.category("fields").add("library_isbn", isbnField);
```

`library/static/src/fields/isbn_field.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="library.IsbnField">
        <t t-if="props.readonly">
            <span class="o_library_isbn font-monospace" t-out="formattedValue"/>
        </t>
        <t t-else="">
            <input class="o_input font-monospace" type="text"
                   t-att-id="props.id"
                   t-att-placeholder="props.placeholder"
                   t-ref="input"/>
        </t>
    </t>
</templates>
```

Use it in a view:

```xml
<field name="isbn" widget="library_isbn" placeholder="978-0-..."/>
```

What each piece does:

- `useInputField` is the hook the core uses for text inputs. It looks for a `t-ref="input"` element, writes `getValue()` into it unless the user is typing or the field is invalid, listens to `input`, `change` and `keydown`, and on commit calls `parse` and then `record.update`. It also protects what the user is typing from being overwritten by an onchange that arrives meanwhile. That is why you do not write your own `t-on-change`.
- `parse` **throws** to say "this text is invalid". The hook catches it and calls `record.setInvalidField(name)`, which gives the red outline and blocks saving with the usual "Invalid fields" message. Return the value to store otherwise. Returning `false` empties a char field.
- `getValue` formats for display; the stored value is the normalised digits. The same value goes through `formatIsbn` in readonly mode, which is the only place where display and storage differ.
- `isEmpty` makes an empty field show the usual "empty" styling in readonly forms.

On the server, enforce the same rule, because the widget is not security. A Python constraint using the same check digit rules belongs on `library.book` (`@api.constrains("isbn")`), see the constraints chapter.

## Example 2: a read-only "days overdue" widget using an extra field

A widget on the `state` field of `library.loan` that shows a badge and, for open loans, how many days past `due_date` they are. It needs `due_date`, a field that may not be in the view, so it declares it as a dependency.

```javascript
/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const { DateTime } = luxon;

export class LoanStateField extends Component {
    static template = "library.LoanStateField";
    static props = { ...standardFieldProps };

    get state() {
        return this.props.record.data[this.props.name];
    }

    get daysOverdue() {
        const due = this.props.record.data.due_date;
        if (this.state !== "open" || !due) {
            return 0;
        }
        const days = DateTime.now().startOf("day").diff(due.startOf("day"), "days").days;
        return Math.max(0, Math.floor(days));
    }

    get badgeClass() {
        if (this.daysOverdue > 0) {
            return "text-bg-danger";
        }
        return { open: "text-bg-info", returned: "text-bg-success" }[this.state] || "text-bg-secondary";
    }

    get label() {
        const selection = this.props.record.fields[this.props.name].selection || [];
        const found = selection.find(([key]) => key === this.state);
        return found ? found[1] : "";
    }
}

export const loanStateField = {
    component: LoanStateField,
    displayName: _t("Loan state"),
    supportedTypes: ["selection"],
    fieldDependencies: [{ name: "due_date", type: "date" }],
};

registry.category("fields").add("library_loan_state", loanStateField);
// same widget in lists
registry.category("fields").add("list.library_loan_state", loanStateField);
```

```xml
<t t-name="library.LoanStateField">
    <span class="badge rounded-pill" t-att-class="badgeClass">
        <t t-out="label"/>
        <t t-if="daysOverdue" t-out="' (' + daysOverdue + ' d late)'"/>
    </span>
</t>
```

```xml
<field name="state" widget="library_loan_state"/>
```

`fieldDependencies` makes the model request `due_date` along with the fields of the view, even if the view does not show it. Without it `record.data.due_date` is `undefined` when the arch lacks the field. For the dependency to be useful the field must exist on the model; if it does not, loading the view fails with an unknown field error that names it.

Since the widget has no input, it works unchanged in readonly and edit mode. Add `readonly` handling only if you add editing.

## Example 3: a view widget

A view widget is not tied to a field. It is useful for banners, buttons and ribbons placed in a form. It gets `record` and `readonly` (`standardWidgetProps`) and `extractProps` receives the node's attributes.

```javascript
/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class OverdueBanner extends Component {
    static template = "library.OverdueBanner";
    static props = { ...standardWidgetProps, text: { type: String, optional: true } };

    get overdue() {
        const { state, due_date } = this.props.record.data;
        return state === "open" && due_date && due_date < luxon.DateTime.now();
    }
}

export const overdueBanner = {
    component: OverdueBanner,
    fieldDependencies: [
        { name: "state", type: "selection" },
        { name: "due_date", type: "date" },
    ],
    extractProps: ({ attrs }) => ({ text: attrs.text }),
};

registry.category("view_widgets").add("library_overdue_banner", overdueBanner);
```

```xml
<t t-name="library.OverdueBanner">
    <div t-if="overdue" class="alert alert-danger mb-0" role="alert">
        <t t-out="props.text or 'This loan is overdue.'"/>
    </div>
</t>
```

```xml
<widget name="library_overdue_banner" text="Return reminder sent after 14 days"/>
```

The core ribbon (`web_ribbon`) is the model to read: its `extractProps` maps the `title`, `bg_color` and `tooltip` attributes onto props, and it lists them in `supportedAttributes`.

## Extending an existing widget

If you want most of the behaviour of a core widget, subclass the component and spread the definition:

```javascript
import { CharField, charField } from "@web/views/fields/char/char_field";

class UpperCharField extends CharField {
    parse(value) {
        return super.parse(value).toUpperCase();
    }
}

registry.category("fields").add("library_upper_char", {
    ...charField,
    component: UpperCharField,
    displayName: "Uppercase text",
});
```

The definition object is plain data, so spreading it carries over `supportedTypes`, `extractProps` and the rest. The template is inherited with the class: `UpperCharField` still uses `web.CharField`. Give it your own template (`static template = "library.UpperCharField"`, with `t-inherit="web.CharField" t-inherit-mode="primary"`) only if markup must change.

## Reacting to other fields

A widget can read any field that is loaded in the view or in `fieldDependencies`. It re-renders when `record.data` changes, including after an onchange. To change another field in response to an edit, call `record.update` with several keys at once:

```javascript
await this.props.record.update({
    [this.props.name]: value,
    title_hint: computeHint(value),
});
```

One call produces one onchange round trip, whereas two calls produce two.

For autosaving widgets (toggles, ratings), pass `{ save: true }`. The core toggle does it by default and exposes an `autosave` option:

```javascript
await this.props.record.update({ [this.props.name]: newValue }, { save: this.props.autosave });
```

Autosave on a new, invalid or dirty record can surprise the user with a half-saved form, so make it optional as the core does.

## Formatting and parsing outside widgets

Read-only display of values in lists, kanban and other places uses two registries, `formatters` and `parsers`, keyed by field type, plus helpers in `@web/views/fields/formatters` such as `formatChar`, `formatInteger`. You rarely need to touch them. When you need the same formatting in a widget and elsewhere, factor it into a plain function as the ISBN example does, then call it from both.

## Supported options and Studio

`supportedOptions` and `supportedAttributes` do not change runtime behaviour. They document what the widget accepts and let the view editors present controls. Provide them for widgets you hand to others:

```javascript
supportedOptions: [
    {
        label: _t("Strict check digit"),
        name: "strict",
        type: "boolean",
        default: true,
        help: _t("Reject numbers whose check digit is wrong."),
    },
],
```

## Debugging a widget

- `?debug=1`, hover a field label: the tooltip lists the widget (and its `displayName`) when the node has a `widget` attribute. If the entry is missing or shows the default, your key did not match.
- Console warning `Missing widget: library_isbn for field of type char`: the registry key does not exist. Either the module with the registration is not in the bundle (see the assets chapter) or the key is misspelled.
- Registry validation errors in debug mode (`component`, `supportedTypes`, `extractProps` types) appear when the module loads, with the key name.
- Check what the widget receives: add `console.log(this.props)` in `setup`. `extractProps` is the place for missing props.
- If the value does not update after typing, you probably wrote your own change handling instead of using `useInputField`, or you mutated `record.data` directly.

## Odoo 20 form of the same widget

OWL 3 changes how props and refs are declared (see the OWL 3 chapter). The field definition object, the registry, `extractProps`, `fieldDependencies` and `useInputField` stay. In the Odoo 20 source:

- `standardFieldProps` is an object of OWL 3 types: `{ id: t.string().optional(), name: t.string(), readonly: t.boolean().optional(), record: t.object() }`.
- Components declare `props = useProps({ ...standardFieldProps, placeholder: t.string().optional() })`.
- The input ref is `input = signal.ref()`, templates use `t-ref="this.input"`, and the hook is called as `useInputField({ ref: this.input, getValue, parse })`.
- Templates address members as `this.props.readonly`, `this.formattedValue`.
- `charField.supportedTypes` is `["char", "text"]` there.

A port of `IsbnField` therefore changes the props declaration, the ref, the template prefixes, and nothing in `isbn.js` or in the definition object.

## Pitfalls

{% hint style="warning" %}
Widgets run in lists, forms, kanban and dialogs, with and without edit mode. Test each context you register for. A widget that assumes `record.isInEdition` crashes in a list cell.
{% endhint %}

- **Hard-coding the field name.** Use `this.props.name`.
- **Mutating `record.data`.** Use `record.update`, or onchange, dirty state and saving break.
- **Writing a many2one as a number.** Use `[id, display_name]` or `false`.
- **Treating dates as strings.** They are luxon `DateTime`s; compare with `<`, `diff`, `toISODate()`.
- **Forgetting `fieldDependencies`.** The extra field is `undefined` when the arch does not contain it.
- **Not throwing in `parse` for invalid input.** Returning something odd stores it; throwing marks the field invalid.
- **Returning a value without trimming or normalising** and then comparing in constraints. Normalise once, in `parse`.
- **Own change handlers instead of `useInputField`.** An onchange response can overwrite what the user is typing.
- **Registering only `fields` and forgetting list rendering.** If the list needs a different look, add `list.<name>`.
- **Keys without a prefix.** `isbn` could clash with another module; use `library_isbn`.
- **Skipping the server check.** A widget is a convenience, never validation.
- **Missing template in the bundle.** The widget fails at mount; the template is a separate file in the same bundle.

## Versions

{% hint style="info" %}
**16:** widgets are legacy classes (`AbstractField` subclasses registered in `field_registry`) or OWL components registered in the OWL field registry, depending on the field. The definition objects above are the 17+ model.

**17 and 18:** the OWL field registry model described here, with `static props` and `useState`.

**20:** same registry and definition keys, with OWL 3 props, refs and template prefixes.
{% endhint %}

## Try it

1. Add the ISBN field to `library.book`'s form with `widget="library_isbn"`. Type `9780306406158` and tab out. Then type `978-0-306-40615-7`.
2. Add `isValid` to the definition so a value that is non-empty but not a valid ISBN is outlined red, and check whether it also blocks saving.
3. Register the same definition under `list.library_isbn` with a different component that renders only the formatted text.
4. Build the loan state widget, then change `due_date` in the form and watch the badge update.

<details>

<summary>Solution notes</summary>

1. The first value is rejected: the field turns red and saving shows the invalid fields message. The second is stored as `9780306406157` and displayed as `978-0-30640-615-7`.
2. `isValid: (record, name) => !record.data[name] || isValidIsbn(record.data[name])` changes only the red outline: `fieldVisualFeedback` uses it instead of `record.isFieldInvalid`. It does not block saving, which is why the real check stays in `parse` (invalid field) and in the Python constraint.
3. The lookup for a list cell tries `list.library_isbn` before `library_isbn`, so the list uses the second component and the form the first, with no change to the arch.
4. `daysOverdue` is a getter reading `record.data`, so it recomputes after the onchange or edit that changes `due_date`.

</details>
