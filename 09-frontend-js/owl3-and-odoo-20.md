---
description: "What changes in the Odoo 20 web client with OWL 3, and how to port 17/18 frontend code."
---

# OWL 3 and the Odoo 20 web client

Odoo 20 replaces OWL 2 with OWL 3. Most of the vocabulary of the previous chapter survives (components, templates, slots, lifecycle hooks, registries) but the way you declare props, hold state, reference elements and write services changes. Code written for Odoo 18 does not run unchanged. This chapter lists what changed, shows the new idioms side by side with the old, and gives a porting procedure.

{% hint style="warning" %}
Everything here was read from the Odoo 20 source tree available to the author, whose bundled library reports `3.0.0-alpha.50` (`addons/web/static/lib/owl/owl.js`). The source contains `@todo owl3 migration` markers and a temporary compatibility layer, so details can still move between that tree and a release you install. Where something is marked temporary in the source, this chapter says so. Always re-check an API against your own checkout before relying on it.
{% endhint %}

## What you notice first

A component from the Odoo 20 core, `web/static/src/core/checkbox/checkbox.js`, trimmed:

```javascript
import { Component, signal, t, useProps } from "@odoo/owl";

export class CheckBox extends Component {
    static template = "web.CheckBox";
    props = useProps({
        value: t.boolean().optional(),
        disabled: t.boolean().optional(),
        onChange: t.function().optional(() => () => {}),
        slots: t.object().optional(),
    });

    rootRef = signal.ref();

    onChange(ev) {
        if (!this.props.disabled) {
            this.props.onChange(ev.target.checked);
        }
    }
}
```

```xml
<t t-name="web.CheckBox">
    <div class="o-checkbox form-check" t-ref="this.rootRef">
        <input type="checkbox" t-att-checked="this.props.value"
               t-att-disabled="this.props.disabled" t-on-change="this.onChange"/>
        <label class="form-check-label"><t t-call-slot="default"/></label>
    </div>
</t>
```

Compared with the 18 version of the same component, four things are different:

1. Props are declared **as a class field** with `useProps(...)` and a schema built from `t.*` types, not with `static props`.
2. Elements are referenced through a **signal**: `signal.ref()` in the class, `t-ref="this.rootRef"` in the template, and `this.rootRef()` to read the element.
3. Templates address component members with an explicit **`this.` prefix**: `this.props.value`, `this.onChange`.
4. There is no `useState` in sight: component state is a `proxy`, described below.

## Props

The old and new forms:

```javascript
// Odoo 17 / 18 (OWL 2)
static props = {
    title: { type: String, optional: true },
    limit: { type: Number, optional: true },
    onPick: { type: Function, optional: true },
};
static defaultProps = { limit: 10 };

// Odoo 20 (OWL 3)
props = useProps({
    title: t.string().optional(),
    limit: t.number().optional(10),
    onPick: t.function().optional(),
});
```

- Defaults move into `.optional(default)`. For a function-valued default the source passes a factory that returns the function (`t.function().optional(() => () => {})`), so the value is not shared.
- `static props` and `static defaultProps` are **errors** in Odoo 20: the compatibility layer throws `Component "X" defines a static "props" or "defaultProps", which Owl 3 ignores. Declare the props schema through "useProps" instead`. This is intentional, so a half-ported component fails at once instead of silently skipping validation.
- The type vocabulary, from the library's `types` export: `string`, `number`, `boolean`, `function`, `object`, `array`, `tuple`, `record`, `strictObject`, `any`, `literal`, `selection` (one of a list of values), `instanceOf`, `constructor`, `promise`, `ref`, `signal`, combined with `or([...])` and `and([...])`, plus `customValidator(type, fn)`. `t.object({...})` takes a shape.
- Some classes keep their schema as a separate constant so subclasses can reuse it, for example `static propsSchema = dialogProps` next to `props = useProps(this.constructor.propsSchema)` in `Dialog`. The source comments that this is a temporary measure, so do not build on that pattern.

A component with no props still declares them, as `props = useProps({})`.

## State: `proxy` instead of `useState`

```javascript
// OWL 2
import { useState } from "@odoo/owl";
this.state = useState({ q: "", rows: [] });

// OWL 3
import { proxy } from "@odoo/owl";
this.state = proxy({ q: "", rows: [] });
```

`proxy` is the reactive-object primitive; the Odoo 20 core uses it directly (`this.state = proxy({...})` in `autocomplete.js`, `barcode_dialog.js` and others) and `useState` is no longer exported by the library. Reactivity rules from the previous chapter carry over: write through the proxy, do not replace it, initialise every key.

OWL 3 adds other reactive primitives that the web client uses:

| Primitive | Use |
| --- | --- |
| `signal(value)` | a reactive cell; read by calling `sig()`, write with `sig.set(v)` or through helpers |
| `signal.ref()` | a reactive element reference (replaces `useRef`) |
| `signal.Array`, `signal.Map`, `signal.Object`, `signal.Set` | reactive collections |
| `computed(fn)` | derived value, recomputed when its inputs change |
| `effect(fn)` | side effect that re-runs when the signals it reads change |
| `untrack(fn)` | read signals without subscribing |
| `markRaw`, `toRaw` | opt out of, or unwrap, the proxy |

Which one to use in your own code: a plain `proxy` object for component state is the closest match to what you know and what most of the core does. Reach for `signal` when you need a value that several components or plugins share and depend on.

## Refs and listeners

```javascript
// OWL 2
this.input = useRef("search");           // <input t-ref="search"/>
onMounted(() => this.input.el.focus());

// OWL 3
this.input = signal.ref();               // <input t-ref="this.input"/>
onMounted(() => this.input().focus());
```

For global listeners, OWL 3 exports `useListener(target, eventName, handler, params)`, where `target` can be an element or a function returning one (it then wires itself with an effect). In the checked source `useExternalListener` is no longer part of the library exports.

`useEffect` still exists in the library. The Odoo compatibility layer wraps the old two-argument form as `useLayoutEffect(effect, computeDependencies)`, with the same semantics as the OWL 2 hook (runs after mount and after patches when a dependency changed).

## Templates: the `this.` prefix

In the Odoo 20 core, templates read members through `this`:

```xml
<!-- Odoo 18 -->
<button t-on-click="save" t-att-disabled="state.busy" t-out="props.label"/>

<!-- Odoo 20 core style -->
<button t-on-click="this.save" t-att-disabled="this.state.busy" t-out="this.props.label"/>
```

A template that still uses the bare form is what the compatibility layer exists for; new code should use `this.`. Other template changes visible in the compatibility notes:

- `t-portal` is renamed `t-custom-portal` and `t-model` is renamed `t-custom-model` while running OWL 2 style code on top of OWL 3. Native OWL 3 has its own `Portal` component and `t-model` backed by signals.
- `t-esc` still renders, but logs a deprecation warning: "t-esc has been deprecated in favor of t-out". Use `t-out` everywhere. In the Odoo 20 web addon `t-out` appears in 176 files and `t-esc` in 2.

## Services become plugins

OWL 3 introduces `Plugin`, `usePlugin`, `providePlugins` and `Resource`. The Odoo 20 core is mid-way through turning its services into plugins:

```javascript
// notification_container.js (Odoo 20, simplified)
import { Component, usePlugin } from "@odoo/owl";
import { NotificationPlugin } from "./notification_plugin";

export class NotificationContainer extends Component {
    notificationPlugin = usePlugin(NotificationPlugin);
    ...
}
```

```javascript
// registering a global plugin
import { Plugin } from "@odoo/owl";
import { services } from "@web/core/services";

export class LoanStatsPlugin extends Plugin {
    setup() { /* runs when the plugin starts */ }
}
services.add(LoanStatsPlugin);
```

`services` in `@web/core/services` is an OWL `Resource` that accepts `Plugin` subclasses (the validation is `t.constructor(Plugin)`). Everything added to it is started by the framework.

The old `registry.category("services")` still exists and still starts services in dependency order. The file `core/legacy_service_starter.js` is headed "temporary - to remove when all service are converted", and its schema validation still reads `{ start, dependencies?, async? }`. The ORM is the clearest example: the real implementation is the `ORM` plugin class in `core/orm_plugin.js`, and a small legacy entry keeps `useService("orm")` working:

```javascript
// end of orm_plugin.js
services.add(ORM);
registry.category("services").add("orm", {
    async: ["call", "create", "read", "searchRead", "unlink", "write", ...],
    start() { return Object.create(usePlugin(ORM)); },
});
```

What this means for module authors, for the source checked:

- **Existing `useService("orm")`, `useService("action")`, `useService("notification")` code keeps working** through the bridge. You do not have to port a module's service usage on day one.
- **A service you write with `registry.category("services")` still works.** Write new shared state as a `Plugin` if you target 20 only; keep the registry form if the module must also run on 18.
- Both worlds are expected to converge on plugins, so do not build large new code on the bridge.

`useService` itself still exists in `@web/core/utils/hooks` and wraps methods so that a call pending at component destruction is dropped, as before.

## The compatibility layer

`addons/web/static/src/owl2/owl3_compatibility_layer.js` patches OWL 3 so OWL 2 style code can run during migration. Its own header spells out the steps, and they double as a porting checklist:

1. Rename `t-portal` to `t-custom-portal` and `t-model` to `t-custom-model` in templates.
2. Load the layer immediately after OWL 3.
3. Replace `useEffect` with `useLayoutEffect`.
4. After the app builds, remove the shims one by one: portals, models, effects.

The layer also provides OWL 2 names on top of OWL 3: `useEnv`, `useSubEnv` (via a plugin that holds the environment), `onWillRender`, `useComponent`, `status` (returns `"new"`, `"mounted"` or `"destroyed"`), and the aliases `owl.config`, `owl.plugin` and `owl.props`. A helper module `@web/owl2/utils` re-exports `useLayoutEffect`, `useEnv` and `useSubEnv` and a deprecated `render(component, deep)`.

Treat the layer as scaffolding for Odoo's own migration. For a module you write today, port to the OWL 3 idioms and import from `@odoo/owl` directly.

## Porting a component: before and after

The `BookSearch` component of the previous chapter, ported.

Before (Odoo 18):

```javascript
export class BookSearch extends Component {
    static template = "library.BookSearch";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ q: "", rows: [], busy: false });
        this.search = useDebounced(this.runSearch, 300);
        this.input = useRef("q");
        onMounted(() => this.input.el.focus());
        onWillStart(() => this.runSearch());
    }
    // ...
}
```

After (Odoo 20):

```javascript
import { Component, onMounted, onWillStart, proxy, signal, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

export class BookSearch extends Component {
    static template = "library.BookSearch";
    props = useProps({});

    input = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ q: "", rows: [], busy: false });
        this.search = useDebounced(this.runSearch, 300);
        onMounted(() => this.input().focus());
        onWillStart(() => this.runSearch());
    }
    // runSearch unchanged
}
```

```xml
<t t-name="library.BookSearch">
    <div class="o_action p-3">
        <input class="form-control mb-3" t-ref="this.input"
               t-model="this.state.q" t-on-input="this.onInput"/>
        <div t-if="this.state.busy" class="text-muted">Searching...</div>
        <a t-foreach="this.state.rows" t-as="row" t-key="row.id" href="#"
           t-on-click.prevent="() => this.open(row.id)" t-out="row.name"/>
    </div>
</t>
```

A porting procedure that works in practice:

1. Replace `static props`/`defaultProps` with `props = useProps({...})`, moving defaults into `.optional(default)`.
2. Replace `useState` with `proxy`.
3. Replace `useRef("name")` with a `signal.ref()` field, `ref.el` with `ref()`, and `t-ref="name"` with `t-ref="this.field"`.
4. Prefix template members with `this.`.
5. Change `t-esc` to `t-out`.
6. Load in a browser with debug on and read every console warning. A wrong prop schema and a leftover `static props` both name the component.

## Writing for 18 and 20 at the same time

If one module must run on both versions, you cannot share component code: `static props` throws on 20 and `useProps` does not exist on 18. Options, in order of preference (a manifest is a literal dictionary, not executable code, so it cannot choose files by version):

1. **Two branches** of the module, one per major version, as Odoo itself maintains them. Cleanest.
2. Write only logic that is independent of OWL (plain functions, `rpc` calls) in shared files and keep components per version.

What you should not do is feature-detect inside one component class; the base class constructor of Odoo 20 refuses `static props` outright.

## Pitfalls

- **Leaving `static props` on a 20 component.** The constructor throws at first mount. Search for it with `grep -rn "static props\|static defaultProps" static/src` before running.
- **Importing `useState`, `useRef`, `useExternalListener` or `useComponent` from `@odoo/owl` on 20.** They are absent from the library exports. `useComponent` and `useEnv` exist only through the compatibility layer, so importing them from `@odoo/owl` works at runtime only while the layer is loaded.
- **Forgetting to call a signal.** `this.input.focus()` on a `signal.ref()` fails because `this.input` is the signal, not the element. Call it: `this.input().focus()`.
- **Mixing `this.`-less templates with new components.** It works under the compatibility layer, not as a convention. Pick one style per file.
- **Building on the bridge.** The `registry.category("services")` path and `useService("orm")` are marked temporary in the source.
- **Copy-pasting from 18 documentation.** Tutorials, forum answers and older versions of this book describe the OWL 2 API. When something fails on 20, the first suspect is the props and state primitives.

## Try it

1. In an Odoo 20 checkout, run `grep -rn "static props" addons/web/static/src | head` and `grep -rn "useProps(" addons/web/static/src | head`. Read what remains, and why.
2. Port the systray `LoanCounter` of the overview chapter to 20. Run it and read the console.
3. Add `static props = {}` to your ported component and find the exact error text.

<details>

<summary>Solution notes</summary>

1. The checked tree has no `static props` left in `web/static/src`; components declare `props = useProps(...)`, and `Dialog` keeps a `propsSchema` constant with a comment calling it temporary.
2. The port is `props = useProps({})`, `this.state = proxy({ open: 0 })`, and `this.` prefixes in the template. `useService("orm")` and `useService("action")` continue to work.
3. `Component "LoanCounter" defines a static "props" or "defaultProps", which Owl 3 ignores. Declare the props schema through "useProps" instead, e.g. "props = useProps({ someProp: t.string().optional(defaultValue) })".`

</details>
