---
description: "The web client, its three JavaScript worlds, how it boots, and the toolbox for reading it."
---

# Frontend overview

Odoo ships three different JavaScript worlds, and most confusion comes from mixing them. A snippet that works in the backend does nothing on a public page, and a tutorial for one version can crash another.

Everything below was checked against the Odoo 18 source and, where noted, against Odoo 20. Version differences are called out in the Versions section at the end.

## The three worlds

| World | Where it runs | Stack | Entry bundle |
| --- | --- | --- | --- |
| Backend web client | `/odoo` (18, 20) or `/web` (16, 17) after login | OWL, ES modules, registries, services | `web.assets_web` (includes `web.assets_backend`) |
| Website and portal | public pages, `/my`, e-commerce | `publicWidget` (jQuery era), OWL for newer parts, `public_components` | `web.assets_frontend` |
| Tours and tests | any of the above | `web_tour`, hoot unit tests (QUnit in older code) | `web.assets_tests`, `web.assets_unit_tests` |

Two more bundles you will meet: `web.report_assets_common` (what PDF reports load, see the reports chapter in part 08) and `web.assets_backend_lazy` (graph and pivot views, loaded on demand).

List the bundles of the version you run instead of trusting a table:

```bash
grep -nE "^\s+'web\.[a-z_]+': \[" addons/web/__manifest__.py
```

In 18 this prints `web.assets_backend`, `web.assets_backend_lazy`, `web.assets_web`, `web.assets_frontend`, `web.assets_frontend_lazy`, `web.report_assets_common`, `web.assets_tests`, `web.assets_unit_tests`, the private `web._assets_*` helper bundles, and a few more.

The rule of thumb: ask where the code will execute. If a logged-in employee sees it, it is the backend client. If an anonymous visitor or a portal user sees it on a QWeb page, it is the website world. If the code only exists to drive a browser through a scenario, it is a tour.

## How the backend client starts

Understanding the boot sequence explains most "my code is not running" problems.

1. The browser requests `/odoo` (18) or `/web` (16, 17). The controller in `addons/web/controllers/home.py` renders the `web.webclient_bootstrap` QWeb template. That template emits the `<script>` and `<link>` tags for the `web.assets_web` bundle and a small inline `odoo` global with the session info.
2. The bundle loads. Each `.js` file is a module registered with a tiny loader (`addons/web/static/src/module_loader.js`). The loader keeps `odoo.loader.modules` (a `Map` of started modules), `odoo.loader.factories` (modules defined but not yet started) and `odoo.loader.failed`. A module starts once all its dependencies have started.
3. `main.js` calls `startWebClient(WebClient)`, which waits for the DOM and calls `mountComponent`. That builds the `env`, **starts every service in the `services` registry in dependency order**, loads templates, and mounts the `WebClient` OWL component on `document.body`.
4. The web client loads the menus (`/web/webclient/load_menus/<hash>`), reads the URL, and asks the `action` service to open the matching action. The action's `type` and `view_type` select entries from the `actions` and `views` registries.

Two consequences:

- **Registries are filled at module load time**, step 2, before services start in step 3. That is why every `registry.category(...).add(...)` sits at the top level of a file and not inside a function.
- **If a module throws while loading, the module and everything depending on it silently never exists**, and the loader prints one console error naming the failed module. Always open the browser console after you add JavaScript. Look for "The following modules failed to load because of an error".

The loader itself is plain code you can inspect in the console:

```javascript
// any backend page
odoo.loader.modules.size                 // started modules
[...odoo.loader.failed]                  // names of modules that threw
[...odoo.loader.jobs]                    // modules waiting for a missing dependency
odoo.loader.modules.get("@web/core/registry")
```

`jobs` is the most useful: a module listed there is waiting for a dependency that no bundle provides, which usually means a typo in an import path or a file that is not in any bundle.

## Module names

Every file under an addon's `static/src` (and `static/tests`) becomes an ES module whose name is derived from its path:

| File | Module name |
| --- | --- |
| `web/static/src/core/registry.js` | `@web/core/registry` |
| `library/static/src/book_list/book_list.js` | `@library/book_list/book_list` |
| `library/static/src/components/card.js` | `@library/components/card` |

The pattern is `@<addon>/<path under static/src without extension>`. Relative imports (`./card`) work inside one addon; across addons always use the `@addon/...` form so a file move in your module does not break someone else's import.

## The `@odoo-module` header

Older code starts with this comment:

```javascript
/** @odoo-module **/
```

The transpiler (`odoo/tools/js_transpiler.py`) turns files that are "Odoo modules" into loader definitions. In 16 and 17 a file is an Odoo module only if the header is present. **In 18 and 20 every file under `<addon>/static/src` and `<addon>/static/tests` is transpiled as a module whether or not the header is there**; the header only matters for files outside those folders, and `/** @odoo-module ignore **/` opts a file out.

Keep writing the header. It costs one line, it makes the module work on 16 and 17 as well, and it tells readers that the file is an ES module.

## Registries, services, components

Three ideas cover almost everything in the backend client.

**Components** are OWL classes with an XML template. Pages, field widgets, list renderers, dialogs and systray buttons are all components.

**Registries** are ordered key-value stores. Nothing in the client hard-codes "the list of field widgets" or "the list of view types"; it looks them up in a registry, so you extend the client by adding an entry. The categories actually used by the 18 `web` addon, from most to least populated:

| Category | What lives there |
| --- | --- |
| `fields` | field widgets (`char`, `many2one`, your custom ones) |
| `services` | singletons started with the client (`orm`, `action`, `dialog`, ...) |
| `formatters`, `parsers` | text conversions for field values |
| `views` | view types (`list`, `form`, `kanban`, your own) |
| `view_widgets` | widgets used with `<widget name="..."/>` in views |
| `main_components` | components mounted once next to the web client (notification container, dialog container) |
| `actions` | client actions (`tag` values of `ir.actions.client`) |
| `systray` | items in the top right bar |
| `debug` | entries of the developer menu |
| `command_provider` | command palette sources |
| `user_menuitems` | entries in the user menu |
| `public_components` | OWL components for website pages |

Print the real list for your build:

```javascript
odoo.loader.modules.get("@web/core/registry").registry.category("services").getEntries().map(([k]) => k)
```

**Services** hold shared state and do shared work. The built-in ones in 18 include `orm`, `action`, `dialog`, `notification`, `user` (a plain module in 18, not a registry service), `hotkey`, `ui`, `view`, `field`, `name`, `menu`, `command`, `popover`, `title`, `http`, `localization`, `company`, `currency`, `effect`, `file_upload`, `datetime_picker`, `sortable`, `tooltip`. A component asks for one with `useService("orm")`.

The next chapters cover each in depth: OWL in "OWL fundamentals", registries and services in their own chapter, and the three ways to change existing behaviour (registry entry, subclass, patch).

## Choosing the right extension technique

Work down this list and stop at the first that fits:

1. **Add a new entry to a registry.** A new field widget, a new client action, a new systray item. Zero coupling with existing code. This is the only technique that survives every upgrade intact.
2. **Subclass and register a replacement.** For example, extend `ListRenderer`, then register a new view type `library_list` that uses it, and select it with `js_class="library_list"` on the `<list>` tag of one view. Only the views that opt in change.
3. **`patch()` an existing class.** This changes behaviour for everyone, everywhere, which is what you want only when the existing class has no registry hook and you really need the global change. See the patching chapter.
4. **Template inheritance** (`t-inherit`, `t-inherit-mode="extension"`) for markup changes only.
5. **Replacing a file through the manifest** (`("replace", ...)`). Last resort, breaks on renames.

The order is not about elegance. It is about blast radius: number 2 changes one view; number 3 changes every form in the database, including those from modules you never read.

## A module with a frontend: the file layout

This is the layout this book uses for every teaching module. Names are the conventional ones; nothing forces them except the globs in your manifest.

```
library/
  __manifest__.py
  static/
    src/
      js/                     # or one folder per feature
        book_counter.js
      xml/
        book_counter.xml
      scss/
        library.scss
    tests/
      tours/
        library_tour.js
      unit/
        book_counter.test.js
```

And the manifest part that makes it load:

```python
"assets": {
    "web.assets_backend": [
        "library/static/src/**/*",
        ("remove", "library/static/src/**/*.test.js"),
    ],
    "web.assets_tests": [
        "library/static/tests/tours/**/*",
    ],
},
```

The `remove` line keeps unit-test files out of the production backend bundle. The assets chapter explains globs and directives in detail.

## A first end-to-end change

Show the number of open loans in the systray. This is a complete, working extension (18 and 20; see Versions for 16/17).

`library/static/src/systray/loan_counter.js`:

```javascript
/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LoanCounter extends Component {
    static template = "library.LoanCounter";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ open: 0 });
        onWillStart(() => this.refresh());
    }

    async refresh() {
        this.state.open = await this.orm.searchCount("library.loan", [
            ["state", "=", "open"],
        ]);
    }

    openLoans() {
        this.action.doAction("library.action_loan");
    }
}

registry.category("systray").add(
    "library.LoanCounter",
    { Component: LoanCounter },
    { sequence: 25 }
);
```

`library/static/src/systray/loan_counter.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="library.LoanCounter">
        <div class="o_nav_entry">
            <button class="btn btn-link" t-on-click="openLoans">
                Loans: <t t-out="state.open"/>
            </button>
        </div>
    </t>
</templates>
```

Add both files to `web.assets_backend`, update the module, hard-reload. If nothing appears, the order of checks is: browser console for a failed module, then `odoo.loader.modules.has("@library/systray/loan_counter")`, then `registry.category("systray").getEntries()`.

`library.action_loan` is the xml id of a window action in the teaching module. `doAction` accepts an xml id string, a numeric id, or an action dictionary.

## Reading the real implementation

You will spend more time reading Odoo's JavaScript than writing yours. Three techniques, in the order you should try them.

**1. Debug assets in the browser.** Add `?debug=assets` to any backend URL. Odoo stops bundling and minifying; every module is served as its own file, and the Sources tab of the developer tools shows `@web/...` paths with readable code. Set breakpoints there. (`?debug=1` gives the developer menu and some tooling; `assets` additionally serves unbundled files and regenerates the bundle when a source file changes.) A `tests` value adds the test bundle and enables tours to run from the debug menu.

**2. grep a checkout.** Keep a checkout of the branch you run. Searching beats browsing:

```bash
grep -rn "registry.category(\"fields\").add(\"many2one\"" addons/web/static/src
grep -rn "static template = \"web.ListRenderer\"" addons/web/static/src
```

For the XML half of a component, search by template name, which is global (`t-name="web.ListRenderer"`).

**3. Ask the running client.** In the console, with debug on:

```javascript
const { registry } = odoo.loader.modules.get("@web/core/registry");
registry.category("views").getEntries().map(([k]) => k);     // view types
registry.category("fields").get("many2one");                 // the widget definition
```

## Debug modes at a glance

| URL parameter | Effect |
| --- | --- |
| `?debug=1` | developer menu, technical names in tooltips, view editing tools |
| `?debug=assets` | everything of `1` plus unbundled, unminified assets, regenerated on change |
| `?debug=tests` | everything of `1` plus the test bundle for tours |
| `?debug=0` | leave debug mode |

They combine: `?debug=assets,tests`. Debug state lives in the URL and is also kept in the session cookie for the rendered pages that need it, so a plain link without the parameter drops it.

## Pitfalls

{% hint style="warning" %}
Old tutorials use `odoo.define("module.name", function (require) {...})`. It still exists in the loader (`odoo.define = loader.define.bind(loader)`) and runs in 16 and in some website code, but backend code in 17 and later is written as ES modules. Do not mix: a legacy `require("web.core")` returns nothing useful in a modern backend.
{% endhint %}

- **Looking for a global to reach services.** There is none you should use. Inside components use `useService`; outside them use `env.services`.
- **Writing jQuery in backend components.** It is not guaranteed to be loaded by the modern client. Use OWL refs and plain DOM APIs.
- **Putting a backend file in `web.assets_frontend`** (or the reverse). The module `@web/views/...` does not exist on a public page, and the module is added to `odoo.loader.jobs` forever.
- **Forgetting the template file.** A component whose template is not in any bundle fails at mount with "Missing template", not at load time. Templates and scripts live in the same `assets` list.
- **Editing a file and expecting a change without `debug=assets`.** The compiled bundle is cached under a hash; you are running the old copy.
- **Adding a registry entry inside `setup()`.** It runs once per component instance; the second instance throws "Cannot add key ... already in registry".
- **Naming a template or registry key without your module prefix.** Both are global namespaces. `t-name="LoanCounter"` can collide with someone else's; `library.LoanCounter` cannot.
- **Trusting `console.log` ordering across modules.** Module start order follows dependencies, not file names.

## Versions

{% hint style="info" %}
**16:** OWL 2 and the legacy widget system coexist. Fields and views have separate legacy and OWL registries (`legacy_registries`), and a `/** @odoo-module **/` header is required for a file to be an ES module. The backend URL is `/web`, and there is no `web.assets_web` bundle (the client loads `web.assets_backend` directly).

**17:** the legacy layer is gone from the backend. `web.assets_web` exists and includes `web.assets_backend`. The URL is still `/web`. The header is still required.

**18:** URLs are `/odoo/...` (the `/web` route still works). Files under `static/src` and `static/tests` are transpiled without the header.

**20:** ships OWL 3 (`3.0.0-alpha.50` in the source checked), where 18 ships OWL 2.8.4. The web client keeps the same registries and services, but some hook signatures changed. For example `useAutofocus` takes a `ref` instead of a `refName`, and `useBus` names its arguments `target, type, listener`. The registry validation in 20 uses `assertType` from OWL instead of `validate`. Treat any 18 snippet as a starting point and run it on a 20 database before trusting it. The chapters that follow mark each known difference.
{% endhint %}

## Try it

1. Open any backend page with `?debug=assets`. In the Sources tab find `web/static/src/core/registry.js` and read the `add` method. Note what happens when the key already exists.
2. In the console run `odoo.loader.modules.get("@web/core/registry").registry.category("systray").getEntries()` and compare with the icons in the top bar.
3. Build the systray counter above. Then break it on purpose by misspelling the import `@web/core/utils/hooks` and read what `odoo.loader.jobs` and the console say.

<details>

<summary>Solution notes</summary>

1. `add(key, value, { force, sequence })` throws if the key is already present and `force` is not set, and keeps the previous sequence when you replace with `force`.
2. The entries come back ordered by `sequence`; the default sequence is 50, which is why items you add without one land after the built-in ones that use lower numbers.
3. A wrong import path leaves your module in `odoo.loader.jobs`, and the console reports that the module is waiting for an unknown dependency. A syntax error instead puts it in `odoo.loader.failed`.

</details>
