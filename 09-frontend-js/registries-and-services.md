---
description: Registries as the extension mechanism of the web client, services as shared state, and the built-in services you will call every day.
---

# Registries and services

A registry is an ordered key-value store, and nearly every extension point of the web client is one. A service is a long-lived singleton started with the client, registered in the `services` registry. Together they are the reason you can add a field widget, a view, a menu entry or a global behaviour without touching Odoo's files. This chapter covers the registry API, the shapes of the entries you will register, how services are written and started, and the built-in services (`orm`, `action`, `dialog`, `notification`, `user`, `rpc`) with the exact signatures from the Odoo 18 source.

Odoo 20 is mid-way through replacing services with OWL 3 plugins. The service API described here still works there through a bridge; the last section says what changed.

## The registry API

```javascript
import { registry } from "@web/core/registry";

const systray = registry.category("systray");

systray.add("library.counter", { Component: LoanCounter }, { sequence: 25 });
systray.get("library.counter");            // the value, or throws KeyNotFoundError
systray.get("library.counter", null);      // default instead of throwing
systray.contains("library.counter");       // boolean
systray.getAll();                          // values, ordered by sequence
systray.getEntries();                      // [key, value] pairs, ordered by sequence
systray.remove("library.counter");
```

Behaviour that matters, from `addons/web/static/src/core/registry.js`:

- `add(key, value, { force, sequence })` returns the registry, so calls chain. If the key already exists and `force` is not true it **throws** `Cannot add "key" in this registry: it already exists`. With `force: true` it replaces the value.
- The default `sequence` is **50**. When you replace with `force` and give no sequence, the previous sequence is kept.
- `getAll()` and `getEntries()` sort by sequence (ascending). Equal sequences keep insertion order, which is module load order.
- `get(key)` without a second argument throws if missing; with a second argument (even `undefined`) it returns that instead.
- `category("a")` creates the sub-registry on first use, and `registry.category("a").category("b")` nests. Categories are plain strings with no declared list, so a typo creates a new, empty category and your entry is never read. Copy names from existing code.
- A registry is an event bus. Adding or removing triggers an `UPDATE` event with `{ operation, key, value }`, which the service starter listens to. You can too, with `addEventListener("UPDATE", ...)`.
- `addValidation(schema)` installs a schema for entries (in 18 an OWL 2 `validate` schema, checked in debug mode). Odoo uses it for `services` so that a malformed service fails with a message naming the key.

Register at module top level, never inside `setup()` or a function that can run twice. Registration is idempotent only if the key is unique; the second run throws.

## Keys and sequences

Key naming, because keys are global across all installed modules:

- Prefix with your module: `library.counter`, `library.book_search`. Core keys have no prefix and are short (`many2one`, `list`, `orm`), which is exactly why yours must not look like them.
- Do not overwrite another module's key with `force`. You may hide their entry and break the module. Register your own key and subclass the original (see the patching chapter for when replacement is justified).
- Use `sequence` to place yourself relative to others: lower comes first. Systray items from the core use 0, 1, 10 and so on (`burger_menu` is 0, `SwitchCompanyMenu` is 1).

## The categories and the shape of their entries

Registries do not validate the shape of an entry unless a schema is installed. The shape is whatever the code that reads the registry expects. The most useful categories in 18, with the shapes verified in the source:

| Category | Entry | Read by |
| --- | --- | --- |
| `systray` | `{ Component, props? }` | the navbar |
| `main_components` | `{ Component, props? }` | `MainComponentsContainer`, mounted once for the session |
| `actions` | an OWL component class, or a function `(env, action) => ...` | the action service, for `ir.actions.client` with a matching `tag` |
| `views` | a view definition object (`type`, `Controller`, `Renderer`, `Model`, `ArchParser`, ...) | the view service |
| `fields` | a field definition `{ component, supportedTypes, ... }` | views |
| `view_widgets` | `{ component, ... }` | `<widget name="..."/>` in view arch |
| `user_menuitems` | a **function** `(env) => item` | the user menu |
| `error_handlers` | a function `(env, error, originalError) => boolean` | the error service |
| `error_dialogs` | a dialog component keyed by Python exception name | RPC error handler |
| `error_notifications` | `{ title?, message?, type?, sticky? }` keyed by exception name | RPC error handler |
| `command_provider` | provider object for the command palette | command service |
| `debug` | functions that add items to the developer menu | debug menu |
| `lazy_components` | component classes, loaded after their bundle | `LazyComponent` |
| `public_components` | components mounted on website pages | public root |

Examples of the less obvious ones.

A user menu entry. Note it is a function that receives the environment and returns the item:

```javascript
import { registry } from "@web/core/registry";

function libraryHelpItem(env) {
    return {
        type: "item",
        id: "library_help",
        description: "Library handbook",
        callback: () => window.open("https://example.com/library-handbook", "_blank"),
        sequence: 35,
    };
}
registry.category("user_menuitems").add("library_help", libraryHelpItem);
```

A mapping from a Python exception to a friendly notification. The error handler looks at the `exceptionName` of the server error, which is the dotted Python class name:

```python
# library/models/library_loan.py
class LoanLimitError(UserError):
    pass
```

```javascript
registry.category("error_notifications").add("odoo.addons.library.models.library_loan.LoanLimitError", {
    title: "Loan limit reached",
    type: "warning",
    sticky: false,
});
```

If the server error has an `exceptionName` found in `error_notifications`, the client shows a notification instead of the error dialog, using `notif.message` or the server message. If it is found in `error_dialogs`, that dialog component is used. For ordinary `UserError` messages you do not need this, the default dialog already shows them.

An error handler of your own, for a client-side failure. Return `true` if you handled it, `false` to let the next handler try:

```javascript
registry.category("error_handlers").add("library.quietAbort", (env, error, originalError) => {
    if (originalError?.name === "AbortError") {
        return true;       // swallow: no dialog
    }
    return false;
}, { sequence: 5 });
```

## Writing a service

A service is a plain object with a `start` function and optional `dependencies` and `async`:

```javascript
import { registry } from "@web/core/registry";

export const bookService = {
    dependencies: ["orm", "notification"],
    async: ["titleOf"],
    start(env, { orm, notification }) {
        const cache = new Map();

        async function titleOf(id) {
            if (!cache.has(id)) {
                const [rec] = await orm.read("library.book", [id], ["name"]);
                cache.set(id, rec.name);
            }
            return cache.get(id);
        }

        function forget(id) {
            cache.delete(id);
        }

        return { titleOf, forget };
    },
};

registry.category("services").add("library.book", bookService);
```

Use it in a component with `useService("library.book")`, or outside components through `env.services["library.book"]`.

How the starter works (`addons/web/static/src/env.js`, `startServices`):

- It collects every entry of the `services` registry that is not started yet, then repeatedly starts those whose `dependencies` are all started. Services without dependencies start first and everything else follows in dependency order.
- A dependency name that is not registered (typo, module not installed) means the service **never starts**. The starter throws `Some services could not be started: <names>. Missing dependencies: <names>` and the web client does not come up. Read the console first.
- `start(env, deps)` may return a promise. The client waits for it before starting dependants and before mounting. A slow `start` delays the entire web client: no network calls in `start` unless they are essential.
- The value returned by `start` becomes `env.services[name]`. If you return nothing, the stored value is `null`.
- A service registered after startup is started on the `UPDATE` event once its dependencies exist, so lazy modules can add services.
- You cannot unregister: `remove` on the services registry is ignored by the starter.

### What `async` really does

The `async` list names methods that return promises and might outlive the component that called them. `useService` wraps **only the listed methods**:

```javascript
const service = useService("library.book");
await service.titleOf(3);          // listed in async: protected
service.forget(3);                 // not listed: called as is
```

A protected call checks the component state. If the component is **destroyed** by the time the promise resolves, the returned promise never settles, so the code after `await` simply does not run. This stops a closed dialog from updating a component that no longer exists, and the price is that you must not rely on `finally` blocks for cleanup in components. If the component is already destroyed when you call, the call is not made.

Rules of thumb:

- List every method that returns a promise.
- A service method that must run to completion regardless of the caller (saving data) should not rely on the component calling it surviving. Use it from the service itself, or call `env.services[name]` directly rather than `useService`.
- Methods not listed are never wrapped, so an unlisted async method does not get the destruction protection.

### State in services

A service is a singleton shared by every component. Keep per-component state in the component. Use a service for things that outlive a screen: a cache, a connection, a counter other components subscribe to.

To let components react to service changes, use a reactive object or an `EventBus`:

```javascript
import { EventBus, reactive } from "@odoo/owl";

start(env) {
    const state = reactive({ unread: 0 });
    const bus = new EventBus();
    return {
        state,
        bus,
        bump() { state.unread++; bus.trigger("CHANGED"); },
    };
}
```

```javascript
// component
this.stats = useState(useService("library.stats").state);   // re-render on change
useBus(useService("library.stats").bus, "CHANGED", () => this.refresh());
```

`useBus(bus, eventName, callback)` removes the listener when the component is destroyed.

## The built-in services you will use

### `orm`

Calls model methods over RPC. All methods return promises and are `async`-protected. Signatures from `orm_service.js` (18):

```javascript
const orm = useService("orm");

await orm.call("library.book", "action_archive", [[id]]);            // call(model, method, args, kwargs)
await orm.create("library.book", [{ name: "Dune" }]);                // returns the new ids
await orm.read("library.book", [id], ["name", "isbn"]);              // read(model, ids, fields)
await orm.search("library.book", [["state", "=", "available"]], { limit: 5 });  // ids
await orm.searchRead("library.book", domain, ["name"], { limit: 20, order: "name" });
await orm.searchCount("library.book", domain);
await orm.write("library.book", [id], { name: "Dune (2nd ed.)" });
await orm.unlink("library.book", [id]);
await orm.readGroup("library.book", domain, ["pages:sum"], ["author_id"]);
await orm.webSearchRead("library.book", domain, { specification: { name: {} }, limit: 20 });
await orm.webSave("library.book", [id], { name: "x" }, { specification: { name: {} } });
```

- Contexts are added for you from the user's context. Pass `{ context: {...} }` in `kwargs` to extend.
- `orm.silent.read(...)` makes the same call without triggering the global error dialog; use it for background refreshes where you handle errors yourself.
- `x2ManyCommands` in the same file builds one2many and many2many command tuples (`create`, `update`, `delete`, `unlink`, `link`, `clear`, `set`) for `write` and `create` values.
- Record rules and access rights apply to the calling user, as always. The ORM service cannot do `sudo`.

Prefer one call that returns what the screen needs over several small ones. A controller route (below) returning prepared data is often better than three `searchRead` calls.

### `rpc`

For your own controllers, import the function:

```javascript
import { rpc } from "@web/core/network/rpc";

const data = await rpc("/library/dashboard", { limit: 10 });
```

It posts JSON to the route and returns the parsed `result`. A server-side exception arrives as a rejected promise with an `RPCError` that carries `data.message`, `data.name` and `exceptionName`; connection loss gives `ConnectionLostError`. Use the `orm` service when you are calling model methods, and `rpc` for routes.

In 18, `rpc` is a module function and not a service (in 16 and 17 it is a service, `useService("rpc")`, which you will still see in older code).

### `action`

```javascript
const action = useService("action");

await action.doAction("library.action_loan");                 // xml id
await action.doAction(42);                                     // database id
await action.doAction({                                        // action dictionary
    type: "ir.actions.act_window",
    res_model: "library.loan",
    views: [[false, "list"], [false, "form"]],
    domain: [["state", "=", "open"]],
    context: { search_default_overdue: 1 },
    name: "Open loans",
});
```

Options (`ActionOptions` in the source): `additionalContext`, `clearBreadcrumbs`, `onClose` (callback when the action closes, for dialogs), `props` (extra props for client actions), `viewType`, `stackPosition` (`"replaceCurrentAction"` or `"replacePreviousAction"`), `index`. A `target: "new"` in the action opens it as a dialog. `{ type: "ir.actions.act_window_close" }` closes the current dialog.

Other methods: `switchView(viewType, props)`, `restore(jsId)` for breadcrumbs, and `doActionButton(params)` which handles `<button type="action">`.

### `notification`

```javascript
const notification = useService("notification");
const close = notification.add("Book returned", { type: "success" });
notification.add("Could not reach the server", {
    title: "Warning",
    type: "danger",
    sticky: true,
    autocloseDelay: 8000,
    buttons: [{ name: "Retry", primary: true, onClick: () => this.retry() }],
});
```

Types are `warning` (default), `danger`, `success`, `info`. A non-sticky notification closes after `autocloseDelay` (default 4000 ms). `add` returns a function that closes it.

### `dialog`

```javascript
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const dialog = useService("dialog");
dialog.add(ConfirmationDialog, {
    title: "Return all books?",
    body: "This cannot be undone.",
    confirm: () => this.returnAll(),
    cancel: () => {},
});
```

`dialog.add(Component, props, options)` mounts the component in a dialog and returns a function that closes it. The component receives a `close` prop it can call. Dialogs opened this way share the lifetime of the dialog stack, not of the opening component. For a dialog tied to a component, use the `useOwnedDialogs` hook from `@web/core/utils/hooks`, which closes them when the component is destroyed.

### `user`

In 18, `user` is **a module export, not a registry service**:

```javascript
import { user } from "@web/core/user";

user.userId;            // numeric id
user.name;
user.isAdmin;           // boolean
user.isInternalUser;    // boolean
user.partnerId;
user.lang;              // JS locale, e.g. "en-US"
user.tz;
user.context;           // copy of the user context, with uid
await user.hasGroup("library.group_librarian");
await user.checkAccessRight("library.book", "write", [id]);
```

`hasGroup` and `checkAccessRight` call the server once per distinct argument and cache the answer. `checkAccessRight(model, operation, ids)` takes an operation such as `"read"` or `"write"` and calls `has_access` on the model. Hiding a button for users without a group is a convenience; the server must still enforce it.

In 16 and 17 `user` is a service (`useService("user")`) backed by `session` and `user_context`. The property names also differ (for example the id is `userId` here, `uid` in `session`).

### Others

- `ui`: `ui.block()` and `ui.unblock()` to freeze the screen during a long call, `ui.isSmall` for mobile layouts, `ui.bus` for resize events.
- `hotkey`: `hotkey.add("alt+shift+l", callback, options)` returns a remove function. In components prefer the `useHotkey` hook in `@web/core/hotkeys/hotkey_hook`.
- `title`, `menu`, `command`, `effect` (rainbow man), `popover`, `field`, `name` (display names for many2one values), `http`, `localization`, `company`, `currency`, `view`. When in doubt, read the file named `<service>_service.js` in `addons/web/static/src/core` or `webclient`. Each is short.

## Putting it together: a service, a component and a client action

A "recent books" service that caches the last five opened books, plus a systray dropdown that shows them.

```javascript
/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { reactive } from "@odoo/owl";

export const recentBooksService = {
    dependencies: ["orm"],
    async: ["touch"],
    start(env, { orm }) {
        const state = reactive({ ids: [], names: {} });
        return {
            state,
            async touch(id) {
                if (!(id in state.names)) {
                    const [rec] = await orm.read("library.book", [id], ["name"]);
                    state.names[id] = rec.name;
                }
                state.ids = [id, ...state.ids.filter((i) => i !== id)].slice(0, 5);
            },
        };
    },
};
registry.category("services").add("library.recent_books", recentBooksService);

export class RecentBooks extends Component {
    static template = "library.RecentBooks";
    static props = {};
    setup() {
        this.recent = useState(useService("library.recent_books").state);
        this.action = useService("action");
    }
    open(id) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "library.book",
            res_id: id, views: [[false, "form"]],
        });
    }
}
registry.category("systray").add("library.RecentBooks", { Component: RecentBooks }, { sequence: 30 });
```

```xml
<t t-name="library.RecentBooks">
  <div class="o_nav_entry">
    <span t-foreach="recent.ids" t-as="id" t-key="id" class="me-2">
      <a href="#" t-on-click.prevent="() => this.open(id)" t-out="recent.names[id]"/>
    </span>
  </div>
</t>
```

Anything that opens a book calls `useService("library.recent_books").touch(id)`, and every systray instance updates because they read the same reactive state.

## Odoo 20: services and plugins

In the Odoo 20 source the web client moves services to OWL 3 plugins, but keeps the registry as a bridge. Verified in the tree available at the time of writing:

- `registry.category("services")` still exists. Its validation schema is now written with OWL 3 types, but still expects `{ start, dependencies?, async? }`. The file `core/legacy_service_starter.js` is marked "temporary - to remove when all service are converted".
- Global plugins register through `services.add(PluginClass)` from `@web/core/services`, where `services` is an OWL `Resource` accepting `Plugin` subclasses.
- The ORM is now `class ORM extends Plugin` in `core/orm_plugin.js`, and `useService("orm")` keeps working through a registry entry that returns `usePlugin(ORM)`. A comment in the source says that entry is temporary.
- `useService` still exists, and in 20 returns a `proxy` of the service when it is not already reactive.
- Hook argument names differ in places (`useAutofocus({ ref })`, `useBus(target, type, listener)`). Check the signature before copying a 18 call.

So: service code you write for 18 keeps working on 20 for now, but the documented direction is plugins, and the next major version may drop the bridge. The OWL 3 chapter shows the plugin form.

## Pitfalls

- **A dependency on a service that does not exist.** Startup stops with a message naming it. Check spelling and that the providing module is in your `depends`.
- **Per-screen state in a service.** It is a singleton and every component sees it.
- **A slow or failing `start`.** The whole client waits for it; avoid network calls, or guard them.
- **`registry.add` on an existing key without `force`.** Throws on load, and the module (and everything depending on it) never starts.
- **`force: true` on a core key** to "replace" behaviour. You remove the original for everyone; subclass and register under your own key where the consumer allows it.
- **Wrong category name.** No error, no effect.
- **Forgetting `async`.** Calls from a destroyed component are not blocked, and their results land on dead state.
- **Relying on `finally` after a protected call.** If the component is destroyed the promise never resolves and the block never runs.
- **Treating `hasGroup` as security.** It hides UI; the server enforces access.
- **Importing `rpc` as a service on 18.** It is a function: `import { rpc } from "@web/core/network/rpc"`.
- **Copying `useService("user")` from 16.** In 18 import `user` from `@web/core/user`.

## Versions

{% hint style="info" %}
**16:** legacy and OWL registries coexist. `rpc_service.js` and `user_service.js` exist, so `useService("rpc")` and `useService("user")` work. Services and the registry API are otherwise as described.

**17:** the legacy layer is gone from the backend. `rpc` is still a service (`core/network/rpc_service.js` exists in 17.0) and so is `user` (`core/user_service.js`).

**18:** `rpc` is imported from `@web/core/network/rpc` and `user` from `@web/core/user`. The service list of this chapter is the 18 list.

**20:** services are being replaced by plugins. `useService` and the services registry keep working through a bridge.
{% endhint %}

## Try it

1. In the console, list services: `odoo.loader.modules.get("@web/core/registry").registry.category("services").getEntries().map(([k]) => k)`.
2. Add the `library.recent_books` service and the systray component above. Open two books and watch the systray update.
3. Rename the dependency `"orm"` to `"ormm"` and read the startup error.
4. In the systray component, call `useService("library.recent_books")` without listing `touch` in `async`, open a dialog that calls it, close the dialog quickly, and compare with the `async` version.

<details>

<summary>Solution notes</summary>

1. The list contains `orm`, `action`, `dialog`, `notification`, `hotkey`, `ui` and the rest of the 18 services; `user` is absent because it is a module.
2. Both items read the same reactive `state`, so they re-render together.
3. The client fails to start, with `Some services could not be started: library.book. Missing dependencies: ormm` in the console.
4. With `async: ["touch"]` the call from a destroyed component never resolves, so there is no write to dead state. Without the entry the promise resolves normally and code after `await` runs, even though the component is gone.

</details>
