---
description: Components, templates, state, props, hooks, slots and lifecycle in OWL 2, as shipped with Odoo 17 and 18.
---

# OWL fundamentals

OWL is the component framework of the web client. You write a class, an XML template and some hooks; the framework re-renders the component when reactive state changes. This chapter teaches OWL 2 as it ships in Odoo 18 (`owl.js` 2.8.4 in `addons/web/static/lib/owl`). Odoo 20 ships OWL 3, which changes props, state and refs; that is covered in the next chapter, and the differences are flagged here where they bite.

Everything in the examples uses imports that exist in the Odoo 18 source. The teaching module is `library`.

## Anatomy of a component

```javascript
/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class BookList extends Component {
    static template = "library.BookList";
    static props = {
        title: { type: String, optional: true },
        limit: { type: Number, optional: true },
    };
    static defaultProps = { limit: 10 };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ books: [], loading: true });
        onWillStart(async () => {
            this.state.books = await this.orm.searchRead(
                "library.book", [], ["name", "isbn"], { limit: this.props.limit }
            );
            this.state.loading = false;
        });
    }
}
```

```xml
<templates xml:space="preserve">
  <t t-name="library.BookList">
    <div class="o_library_book_list">
      <h4 t-if="props.title" t-out="props.title"/>
      <ul>
        <li t-foreach="state.books" t-as="book" t-key="book.id">
          <t t-out="book.name"/> <small class="text-muted" t-out="book.isbn"/>
        </li>
      </ul>
    </div>
  </t>
</templates>
```

Four things make a component: a class that extends `Component`, a `static template` naming a template, an optional `static props` description, and a `setup()` method. The template has the component as its rendering context: `props`, `state` (anything you assigned to `this`) and methods are reachable by name.

## `setup()`, not the constructor

Hooks only work while the component is being set up. They register themselves on "the component currently being built", and that pointer exists only during `setup()`.

```javascript
setup() {
    this.state = useState({ q: "" });         // fine
    const ref = useRef("input");              // fine
    onMounted(() => ref.el.focus());          // fine
}

async onClick() {
    const s = useState({});                   // throws: no current component
}
```

Never `await` before a hook call, and never make `setup` `async`. A hook after an `await` runs outside the setup window. Do asynchronous loading in `onWillStart` and keep `setup` synchronous.

## Templates

OWL templates are QWeb. A template file is a `<templates>` root with one `<t t-name="...">` per template, listed in the same bundle as the JavaScript. Template names are a single global namespace. Prefix them with the module name.

The directives you will use daily:

| Directive | Meaning |
| --- | --- |
| `t-if`, `t-elif`, `t-else` | conditionals |
| `t-foreach="items" t-as="item" t-key="item.id"` | loops. `t-key` is mandatory for lists that change; use a stable id, not the index |
| `t-out="expr"` | output, escaped unless the value is wrapped by `markup()` |
| `t-esc="expr"` | same as `t-out` for plain values. Works in 17/18, deprecated in 20 (console warning) |
| `t-att-name="expr"` | dynamic attribute. `false`/`null`/`undefined` omits the attribute |
| `t-attf-class="a #{expr} b"` | attribute with interpolation |
| `t-att-class="{ active: state.on, 'text-danger': state.err }"` | class object |
| `t-on-click="method"` | event handler. Also `t-on-input`, `t-on-keydown`, ... |
| `t-ref="name"` | element reference, read through `useRef("name")` |
| `t-set="x" t-value="expr"` | local variable inside the template |
| `t-call="other.template"` | include another template, sharing the current scope |
| `t-component="Comp"` | dynamic component (see below) |
| `t-props="obj"` | spread an object as props |
| `t-slot`, `t-call-slot` | slots (see below) |
| `t-model="state.q"` | two-way binding for inputs |

Expressions are a restricted JavaScript subset. You can call methods and use ternaries, `&&`, `||` and `!`, but you cannot declare functions or use `if` statements. The template compiler also rewrites some words: `and`, `or`, `not`, `lt`, `gt` are accepted as aliases for operators, which is why you may see `props.a and props.b` in core templates.

### Event handlers

```xml
<button t-on-click="save">Save</button>
<button t-on-click="() => this.remove(book.id)">Delete</button>
<form t-on-submit.prevent="onSubmit">...</form>
<div t-on-click.stop="noop">...</div>
```

A bare method name is bound to the component and receives the DOM event. An arrow function receives nothing unless you pass it. Modifiers `.prevent`, `.stop`, `.capture`, `.self`, `.synthetic` are available.

Handlers in a loop capture the loop variable, so the arrow form is the normal way to pass the row:

```xml
<li t-foreach="state.books" t-as="book" t-key="book.id">
    <a t-on-click="() => this.open(book.id)" t-out="book.name"/>
</li>
```

### Binding inputs

```xml
<input class="form-control" t-model="state.q" placeholder="Search"/>
<input t-model.trim="state.name"/>
<input type="number" t-model.number="state.qty"/>
<input t-model.lazy="state.note"/>
```

`t-model` updates `state.q` on every `input` event (on `change` with `.lazy`). It needs `state` to be reactive, otherwise nothing re-renders.

## State and reactivity

`useState(obj)` returns a reactive proxy around `obj`. Reading a key inside a render subscribes the component to it, and writing it later schedules a re-render of the components that read it.

```javascript
this.state = useState({ q: "", books: [], editing: null });
this.state.q = "dune";                // re-render
this.state.books.push({ id: 7 });     // re-render (arrays and nested objects are reactive)
this.state.editing = { id: 7 };       // re-render
```

Rules that explain most "my UI does not update" reports:

- **Only the proxy is reactive.** Keep the original object out of reach, and never destructure `state` at the top of a method: `let { q } = this.state; q = "x"` writes to a local variable.
- **Replacing the proxy**, as in `this.state = {...}`, discards reactivity. Assign to its keys.
- **Class instances and values set via `markRaw` are not proxied.** Wrap a big object (a chart instance, a library handle) in `markRaw(obj)` to avoid the cost and the surprises.
- **A key that was never present** is not tracked until written. Initialise every key you will read.
- **Renders are batched.** After `this.state.x = 1` the DOM is not updated yet; it updates on the next microtask. If you need the DOM after a change, do the work in an `onPatched` callback (or a `useEffect` that depends on the changed value).

### Sharing state between components

Use `reactive(obj, callback)` from `@odoo/owl` for state that lives outside a component, and `useState` on it inside each consumer:

```javascript
import { reactive, useState } from "@odoo/owl";

export const basket = reactive({ ids: [], add(id) { this.ids.push(id); } });

// in a component
this.basket = useState(basket);
```

For anything application-wide, a service is a better home (see the registries chapter).

## Props

Props come from the parent and are read-only from the child's point of view.

```javascript
static props = {
    title: { type: String, optional: true },
    book: { type: Object, shape: { id: Number, name: String } },
    onPick: { type: Function, optional: true },
    "*": true,                    // allow any other prop
};
static defaultProps = { title: "Books" };
```

- Types: `String`, `Number`, `Boolean`, `Object`, `Array`, `Function`, `Date`, a class, or a union `[String, Number]`. `{ type: Array, element: Object }` and `{ type: Object, shape: {...} }` validate contents.
- `optional: true` allows `undefined`. `defaultProps` fills in missing values *before* validation.
- `"*": true` accepts anything extra. Without it, an unknown prop is a validation error.
- Validation runs only in debug mode (the Odoo environment passes `dev: env.debug`) and in test mode. In production a wrong prop is silently accepted, so read the warnings in `?debug=1` while you develop.
- A component with no `static props` triggers the warning "Component 'X' does not have a static props description" (`warnIfNoStaticProps` is on outside test mode). Declare props even for components with none: `static props = {};`.

Callbacks are the only way a child tells its parent anything. Name them `onSomething`, and pass them in:

```xml
<BookRow t-foreach="state.books" t-as="book" t-key="book.id"
         book="book" onPick.bind="pick"/>
```

The `.bind` suffix on a prop binds the method to the parent component, so `this` is right when the child calls it. A prop name that is an attribute in an XML template must be a valid XML name; `onPick.bind` is the only place a dot is allowed.

## Children and dynamic components

Child components are registered in `static components` and used by name:

```javascript
import { BookRow } from "./book_row";

export class BookList extends Component {
    static template = "library.BookList";
    static components = { BookRow };
    static props = {};
}
```

When the component class is decided at runtime, use `t-component`:

```xml
<t t-component="state.editor" t-props="editorProps"/>
```

where `state.editor` holds a class. This is how the web client renders any field widget, any view and any action: it looks up the class in a registry and drops it into a `t-component`. Keep class references out of `useState` or wrap them with `markRaw`; a class is not meant to be proxied.

## Slots

Slots let the parent pass markup into the child.

```xml
<!-- child: library.Card -->
<t t-name="library.Card">
  <div class="card">
    <div class="card-header"><t t-slot="header"/></div>
    <div class="card-body"><t t-slot="default"/></div>
  </div>
</t>

<!-- parent -->
<Card>
  <t t-set-slot="header">Overdue loans</t>
  <p>Three books are late.</p>
</Card>
```

Content outside any `t-set-slot` becomes the `default` slot. A slot can receive values from the child:

```xml
<!-- child --> <t t-slot="row" book="book"/>
<!-- parent --> <t t-set-slot="row" t-slot-scope="s"><b t-out="s.book.name"/></t>
```

In the child class, declare `slots: { type: Object, optional: true }` in `static props` if you want validation to accept them. The core uses `t-call-slot` for the same purpose inside templates that are called with `t-call`.

## Lifecycle

In order of occurrence:

| Hook | When | Typical use |
| --- | --- | --- |
| `setup()` | construction | register hooks, create state |
| `onWillStart(fn)` | before the first render, may be async | load data the first render needs |
| `onWillRender` / `onRendered` | before/after the template is evaluated | rare |
| `onMounted(fn)` | after the component is in the DOM | DOM libraries, focus, measure |
| `onWillUpdateProps(fn)` | before a re-render caused by new props, may be async | reload when a prop changes |
| `onWillPatch` / `onPatched` | around DOM updates | restore scroll positions |
| `onWillUnmount(fn)` | before removal | remove listeners, destroy library objects |
| `onWillDestroy(fn)` | after unmount, children included | last cleanup |
| `onError(fn)` | an error in a descendant | error boundary |

Parents render before children and mount after them: `onMounted` of a child fires before `onMounted` of its parent, and a parent waits for the `onWillStart` promises of all children to resolve before anything shows. A slow request in a deep child delays the whole screen; start non-essential loads in `onMounted` instead.

Reacting to a changed prop is the classic place to go wrong:

```javascript
setup() {
    this.state = useState({ lines: [] });
    onWillStart(() => this.load(this.props.loanId));
    onWillUpdateProps((next) => {
        if (next.loanId !== this.props.loanId) {
            return this.load(next.loanId);       // returning the promise delays the render
        }
    });
}
async load(id) {
    this.state.lines = await this.orm.searchRead(
        "library.loan.line", [["loan_id", "=", id]], ["book_id", "due_date"]
    );
}
```

Note that `onWillUpdateProps` receives the *next* props; `this.props` still holds the old ones.

## References and DOM work

```javascript
import { useRef, onMounted, useEffect } from "@odoo/owl";

setup() {
    this.input = useRef("search");           // <input t-ref="search"/>
    onMounted(() => this.input.el.focus());
}
```

`ref.el` is `null` until mount and while the element is not rendered (inside a false `t-if`). For code that must re-run when a dependency changes, use `useEffect`:

```javascript
useEffect(
    (el, open) => {
        if (open) el.focus();
        return () => { /* cleanup before the next run */ };
    },
    () => [this.input.el, this.state.open]
);
```

The second argument computes the dependency list. The effect runs after mount and after any patch where a dependency changed. An empty list `() => []` means once. Omitting the argument means "after every patch" (OWL uses `[NaN]`, which never equals itself).

Odoo provides ready-made hooks on top of these. The ones you will use, all in `@web/core/utils/hooks`: `useService`, `useBus`, `useAutofocus`, `useOwnedDialogs`, `useChildRef`, `useForwardRefToParent`, `useRefListener`. `useBus(bus, "EVENT", cb)` subscribes for the component lifetime. `useAutofocus({ refName: "search" })` focuses `t-ref="search"` on mount. Timing helpers in `@web/core/utils/timing`: `useDebounced(callback, delay)` and `debounce`.

Listeners on `window` or `document` go through `useExternalListener(window, "resize", cb)`, which removes them for you. Writing `window.addEventListener` in `setup` leaks the component.

## Error handling

An exception thrown while rendering or in a hook destroys the app unless some ancestor catches it:

```javascript
export class SafeBox extends Component {
    static template = xml`<t t-if="state.error">Could not display this.</t><t t-else="" t-slot="default"/>`;
    static props = { slots: Object };
    setup() {
        this.state = useState({ error: false });
        onError(() => { this.state.error = true; });
    }
}
```

`xml` is a tagged template from `@odoo/owl` that compiles a template string. It is handy for tiny inline templates and in tests; real modules put templates in files because only file templates can be inherited by other modules.

## Rendering HTML safely

`t-out` escapes. To render trusted HTML wrap it with `markup`:

```javascript
import { markup } from "@odoo/owl";
this.state.html = markup(htmlFromTheServer);   // only when the server sanitised it
```

Never mark user-provided text. A `html`-typed field value from the ORM is sanitised by the server for display purposes; anything else is not.

## Translating strings

Static strings in templates are extracted for translation automatically, and `data-tooltip` is registered as translatable by the web client. In JavaScript use `_t`:

```javascript
import { _t } from "@web/core/l10n/translation";
this.notification.add(_t("Book returned"), { type: "success" });
```

`_t` must be called with a literal string for the extraction to find it. For strings with values: `_t("%s is overdue", name)`. A top-level `const LABEL = _t("Hello")` runs before translations are loaded; use it inside functions, or build it lazily.

## A complete worked example

A debounced search box over `library.book`, with a loading state, using only what this chapter introduced.

```javascript
/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

export class BookSearch extends Component {
    static template = "library.BookSearch";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ q: "", rows: [], busy: false });
        this.search = useDebounced(this.runSearch, 300);
        onWillStart(() => this.runSearch());
    }

    onInput() {
        this.search();
    }

    async runSearch() {
        this.state.busy = true;
        const domain = this.state.q
            ? ["|", ["name", "ilike", this.state.q], ["isbn", "ilike", this.state.q]]
            : [];
        this.state.rows = await this.orm.searchRead(
            "library.book", domain, ["name", "isbn"], { limit: 20, order: "name" }
        );
        this.state.busy = false;
    }

    open(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "library.book",
            res_id: id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("library.book_search", BookSearch);
```

```xml
<templates xml:space="preserve">
  <t t-name="library.BookSearch">
    <div class="o_action p-3">
      <input class="form-control mb-3" placeholder="Title or ISBN"
             t-model="state.q" t-on-input="onInput"/>
      <div t-if="state.busy" class="text-muted">Searching...</div>
      <div class="list-group">
        <a t-foreach="state.rows" t-as="row" t-key="row.id"
           href="#" class="list-group-item list-group-item-action"
           t-on-click.prevent="() => this.open(row.id)">
          <t t-out="row.name"/>
          <small class="float-end text-muted" t-out="row.isbn"/>
        </a>
      </div>
    </div>
  </t>
</templates>
```

Registering it as `actions` entry `library.book_search` makes it a client action. Pair it with a menu:

```xml
<record id="action_book_search" model="ir.actions.client">
    <field name="name">Book search</field>
    <field name="tag">library.book_search</field>
</record>
<menuitem id="menu_book_search" name="Book search"
          parent="library.menu_root" action="action_book_search"/>
```

`tag` is the registry key. If the menu opens a blank screen, the key in the registry and the `tag` differ, and the console shows "Could not find client action".

## Pitfalls

{% hint style="warning" %}
Mutating props. OWL does not stop you, but the parent never learns about the change and its next render overwrites it. Copy a prop into state, or call a callback prop that asks the parent to change it.
{% endhint %}

- **`await` before a hook, or an `async setup`.** The hook has no current component and throws.
- **Missing `t-key`** in a `t-foreach` over changing data. OWL falls back to positions: input contents and focus jump to the wrong row after a reorder.
- **`t-key="row_index"`** has the same problem. Use the record id.
- **Destructuring `state`** loses reactivity.
- **Reusing a template name.** The last registered wins, silently. Always prefix: `library.BookList`.
- **Holding a service call across destruction.** Methods of `orm` and friends are wrapped by `useService`: if the component is destroyed while a request is pending, the returned promise never resolves. Code after the `await` simply does not run. Do not stash the wrapped service in a global.
- **Heavy `onWillStart` in many siblings.** They run in parallel but the screen waits for the slowest.
- **A `static props` that omits something you pass.** Silent in production, a loud error in debug mode, which is why you develop with debug on.
- **Forgetting `.bind` on a callback prop** passed to a child: `this` inside the callback is the child's, or undefined.
- **Putting a class instance in `useState`.** Proxying breaks private fields and identity checks. Use `markRaw`.
- **Writing to `state` in a template or getter.** Rendering must be pure. A write during a render triggers a render loop.
- **jQuery in the backend.** Not guaranteed to be loaded; use refs.

## Versions

{% hint style="info" %}
**16:** the client mixes OWL 1-style legacy widgets with OWL 2 code. Check what a file uses before copying: `static template` plus `useState` from `@odoo/owl` is the OWL 2 style used here.

**17 and 18:** OWL 2 only. 18 ships OWL 2.8.4. In 18 the `@odoo-module` header is optional under `static/src`.

**20:** OWL 3 (3.0.0-alpha.50 in the checked source). `static props` and `defaultProps` are rejected (`Component "X" defines a static "props" or "defaultProps", which Owl 3 ignores`), `useState` is gone in favour of `proxy`, `useRef` in favour of `signal.ref()`, and templates address members as `this.props.x`. Read the next chapter before porting.
{% endhint %}

## Try it

1. Build `BookSearch` above. Open it from the menu with `?debug=1`. Delete `static props` and read the warning. Add it back.
2. Remove `t-key` from the list, type a search that reorders results while one row is focused, and watch what happens. Put it back.
3. Change `useDebounced(this.runSearch, 300)` to call `this.runSearch` directly from `t-on-input` and watch the network tab while typing. Count requests.

<details>

<summary>Solution notes</summary>

1. Without `static props` the console shows a warning that the component has no props description; with it, there is no output. Passing a prop you did not declare produces a validation error unless `"*": true` is present.
2. Without `t-key`, rows are reused by position, so DOM state such as focus belongs to the position rather than the record. With a stable key the DOM node follows the record.
3. One request per keystroke versus one request per pause. `useDebounced` also cancels a pending call when the component unmounts.

</details>
