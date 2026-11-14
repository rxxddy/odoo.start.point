---
description: How JavaScript, CSS and templates reach the browser, and how to debug it when they do not.
---

# Assets and bundles

Front-end files are not loaded because they exist. They are loaded because a manifest `assets` key (or an `ir.asset` record) lists them in a bundle. Forget this and your code is silently absent: no error, no warning, just nothing happening. This chapter covers how a bundle is assembled, every directive, SCSS and variables, lazy loading, caching, and a diagnosis procedure for the day your file does not show up.

Checked against the Odoo 18 source (`odoo/addons/base/models/ir_asset.py`, `assetsbundle.py`, `addons/web/__manifest__.py`) and the Odoo 20 tree. Differences are in the Versions section.

## Declaring assets

```python
# library/__manifest__.py
{
    "name": "Library",
    "version": "18.0.1.0.0",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "library/static/src/**/*",
            ("remove", "library/static/src/**/*.test.js"),
        ],
        "web.assets_frontend": [
            "library/static/src/website/**/*",
        ],
        "web.assets_tests": [
            "library/static/tests/tours/**/*",
        ],
    },
}
```

An entry is either a string (a path or glob, appended to the bundle) or a tuple `(directive, ...)`. A path starts with the addon name, not with a slash: `library/static/src/js/foo.js`. The path must point inside the `static` folder of an installed addon, which is why a typo gives no error beyond a log warning.

File types the bundler accepts: `js`, `css`, `scss`, `sass`, `less` and `xml` (templates). Anything else matching a glob is skipped. This is why `static/src/img/*.png` never needs listing: images are served directly by URL and are not part of a bundle.

## What a bundle is made of

A bundle is a list of files assembled in a fixed order, then compiled into one `.js` and one `.css` file stored as attachments. The assembly order, from `IrAsset._fill_asset_paths`:

1. `ir.asset` database records for the bundle whose `sequence` is below 16, in sequence order.
2. The `assets` entries of every installed addon's manifest, **addon by addon in dependency order** (topologically sorted), and entry by entry inside each manifest.
3. The remaining `ir.asset` records (sequence 16 and above).

So a module you write after `web` always sees the bundle as `web` left it, and can insert before, after, replace or remove a file of `web`. An addon that does not depend (directly or indirectly) on the one it patches may be processed before it, and its `before`/`after`/`replace` finds nothing.

`('include', 'other.bundle')` splices the whole other bundle at that point, and circular includes raise "Circular assets bundle declaration".

Globs expand alphabetically inside one entry. `**` is recursive. Order inside a glob matters only for SCSS (variables, mixins) and for non-module scripts; ES modules are ordered by their imports, not by file position.

## Directives

```python
"web.assets_backend": [
    "library/static/src/js/new_file.js",                                    # append (default)
    ("prepend", "library/static/src/scss/early.scss"),                      # start of this bundle
    ("before", "web/static/src/core/foo.js", "library/static/src/js/a.js"), # before the target
    ("after",  "web/static/src/core/foo.js", "library/static/src/js/b.js"), # after the target
    ("replace","web/static/src/core/foo.js", "library/static/src/js/foo.js"),
    ("remove", "web/static/src/core/foo.js"),
    ("include", "web._assets_helpers"),
]
```

Note the argument order of `before`, `after` and `replace`: **target first, new file second**. The `ir.asset` model uses the same logic with separate `target` and `path` fields.

Semantics worth knowing:

- `prepend` inserts at the beginning of the **current bundle as the bundle is being assembled**, not at the very top of the final list. If another addon later prepends, its file ends up in front of yours.
- `before`/`after`/`replace`/`remove` accept globs as the *new* path, and `remove` accepts a glob as its path. The *target* of `before`/`after`/`replace` must resolve to one existing file in the bundle at that moment; otherwise assembly raises `ValueError: File(s) <path> not found in bundle <bundle>`.
- If the target's extension is not an asset extension, the directive is silently ignored.
- `replace` and `remove` break when the target is renamed in a later version. For JavaScript, prefer a registry entry or `patch()`; for templates, `t-inherit`.
- `remove` applies to files **already in the bundle**. Removing something a later addon adds does nothing.

### External files

A path with a scheme or a host is passed through untouched, not aggregated into the bundle:

```python
"web.assets_frontend": [
    "https://cdn.example.com/lib/chart.min.js",
],
```

External assets add a render-blocking request and a runtime dependency on a third party. For anything that must keep working offline (the reason this book exists) vendor the file under `static/lib/` and list it as a normal path.

## Bundles that matter

From `addons/web/__manifest__.py` (18):

| Bundle | Purpose |
| --- | --- |
| `web.assets_backend` | the internal web client: core, views, fields, services of every installed app |
| `web.assets_backend_lazy` | graph and pivot views and other heavy parts, loaded on demand |
| `web.assets_web` | entry bundle of the backend: includes `web.assets_backend`, then `main.js` and `start.js` |
| `web.assets_frontend` | website, portal, e-commerce, public pages |
| `web.assets_frontend_lazy` | lazily loaded public code |
| `web.report_assets_common`, `web.report_assets_pdf` | what wkhtmltopdf loads when rendering reports |
| `web.assets_tests` | tours; loaded only when tests are enabled |
| `web.assets_unit_tests`, `web.assets_unit_tests_setup` | hoot unit tests and their runner |
| `web.assets_web_dark`, `web.assets_backend_lazy_dark` | dark mode variants of the above |
| `web._assets_primary_variables`, `web._assets_secondary_variables` | SCSS variable layers, see below |
| `web._assets_helpers`, `web._assets_backend_helpers`, `web._assets_frontend_helpers` | mixins and functions shared by SCSS files |
| `web._assets_core` | module loader, OWL, luxon and everything under `core/` |

Where a file goes decides who sees it. Code for logged-in staff goes into `web.assets_backend`. Code for the public website goes into `web.assets_frontend`. A report stylesheet goes into `web.report_assets_common`. Putting a backend file in the frontend bundle fails with missing dependencies: `@web/views/...` does not exist there.

## SCSS, variables and themes

Stylesheets in a bundle are compiled to one CSS file with the SCSS compiler. Two bundles are included first in every compilation: the helpers (functions and mixins, `web._assets_helpers`) and the variables, so your file can use Bootstrap variables and the Odoo palette without importing them.

To change a variable you do not write a new rule. You add a file to the variables bundle, which is processed before everything else:

```python
"web._assets_primary_variables": [
    "library/static/src/scss/primary_variables.scss",
],
```

```scss
// library/static/src/scss/primary_variables.scss
$o-library-accent: #5b7fa6 !default;
```

`mail` and `portal` do exactly this (`mail/static/src/**/primary_variables.scss`, `portal/static/src/scss/primary_variables.scss`). The core bundle also picks up any file named `*.variables.scss` under `web/static/src`. Use `!default` so another module can still override your value.

Variants by file suffix:

- Files ending in `.dark.scss` are excluded from the normal backend bundle (`('remove', 'web/static/src/**/*.dark.scss')`) and included in the dark bundles. Put dark mode overrides there.
- RTL stylesheets are generated automatically by flipping the compiled CSS. You do not write them. Use logical properties (`margin-inline-start`) and avoid hand-rolled direction hacks.

In templates and JavaScript, use Bootstrap utility classes instead of new CSS wherever you can. Every selector you add is a global selector. Prefix your own: `.o_library_book_list`.

## Loading code on demand

Some code is only needed on one screen. Put it in a separate bundle and load it when needed. The web client offers helpers in `@web/core/assets`:

```javascript
import { loadBundle, loadJS, loadCSS } from "@web/core/assets";

await loadBundle("library.assets_chart");              // js and css of a bundle
await loadJS("/library/static/lib/chart/chart.min.js"); // one script
await loadCSS("/library/static/src/scss/print.css");    // one stylesheet
```

`loadBundle` calls `/web/bundle/<name>` to get the list of files and loads them. Results are cached: a second call returns the same promise. A failed load is retried, with a delay.

Define the bundle in the manifest under your own name. Keep it to two dot-separated parts, `addon.name`, like every core bundle:

```python
"assets": {
    "library.assets_chart": [
        "library/static/lib/chart/chart.min.js",
        "library/static/src/chart/**/*",
    ],
},
```

For a whole component, `LazyComponent` loads a bundle and then looks the class up in the `lazy_components` registry:

```xml
<LazyComponent bundle="'library.assets_chart'" Component="'library.Chart'" props="chartProps"/>
```

```javascript
registry.category("lazy_components").add("library.Chart", Chart);
```

The core uses the same pattern for heavy things: the graph and pivot views sit in `web.assets_backend_lazy`.

A library that is not an ES module (a UMD build such as chart.js) attaches itself to `window`. Load it with `loadJS` before use and read it from `window`, for example `window.Chart`. Do not list it in `web.assets_backend`: it loads on every page for every user.

## Data-driven assets: `ir.asset`

The same directives exist as database records, which is useful for hotfixes on a database you cannot redeploy, for per-website assets, and for toggling a file on and off without changing code. The model `ir.asset` has the fields `name`, `bundle`, `directive`, `path`, `target`, `active` and `sequence` (default 16).

```xml
<record id="library_hide_old_banner" model="ir.asset">
    <field name="name">Remove old banner script</field>
    <field name="bundle">web.assets_frontend</field>
    <field name="directive">remove</field>
    <field name="path">library/static/src/website/old_banner.js</field>
</record>
```

Creating or writing an `ir.asset` clears the assets cache. Records with a sequence below 16 are applied before manifests, the rest after. Prefer the manifest for anything that ships with your module; `ir.asset` is for runtime control.

## Caching, regeneration and debugging

Compilation is expensive, so the result is stored as attachments with the version hash in the URL (`/web/assets/<hash>/web.assets_web.min.js`). In normal mode:

- The bundle is generated once per cache key (bundle plus parameters such as website) and then reused until the cache is cleared or the hash changes.
- Changing a source file does **not** change the bundle. You are still running the old compiled copy.
- Installing or updating a module, or the "Regenerate Assets Bundles" entry of the debug menu, rebuilds it.

With `?debug=assets` in the URL, Odoo serves files unminified and, when a source file changes, regenerates the bundle. The server-side comment in `ir_qweb.py` says it plainly: with `debug=assets` the assets are regenerated when a composing file has been modified, otherwise they are generated once and cached.

Server flags matter too:

```bash
# 18: dev features are all, reload, qweb, xml (there is no "assets" feature)
./odoo-bin -d dev --dev=reload,qweb,xml
```

- `xml` stops the assets path list from being cached, so edits to the `assets` key and new files are picked up without a restart for the asset lookup. (It also reads views from source files instead of the database.)
- `reload` restarts the server when Python files change.
- `qweb` logs the compiled XML when a QWeb error occurs.

A common mistake is writing `--dev=assets`. That is not a server option in 18 or 20. The browser's `?debug=assets` is what unminifies and regenerates bundles.

### Where bundles live

Compiled bundles are rows in `ir_attachment` whose URL starts with `/web/assets/` (the URL format is `/web/assets/<unique>/<filename>`). When a bundle seems stale in a way `?debug=assets` does not fix, look:

```sql
-- read-only
SELECT id, name, url, write_date
FROM ir_attachment
WHERE url LIKE '/web/assets/%'
ORDER BY write_date DESC
LIMIT 20;
```

To force a rebuild you can delete those rows. This is safe: they are regenerated on the next request. It is a data change on the database, so run the SELECT first, take a backup on production, and expect the next page load to be slow while bundles rebuild:

```sql
DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';
```

From an Odoo shell, delete the attachments and clear the assets cache with `env.registry.clear_cache("assets")`, or simply click "Regenerate Assets Bundles" in the debug menu. (`ir.asset.create` and `write` call `clear_cache("assets")` themselves.)

## The "my file is not loaded" procedure

Work through these in order. Each step cuts the problem in half.

1. **Is the module installed and updated?** Manifests are read at registry load. Edit `__manifest__.py`, restart (or use `--dev=reload`), then `-u library`.
2. **Is the path valid?** The path starts with the addon name. In the Odoo log look for `IrAsset: the path "..." did not resolve to anything`. A wrong glob logs exactly that line.
3. **Is it in the right bundle?** Backend code in `web.assets_backend`, public code in `web.assets_frontend`.
4. **Is the extension supported?** Only `js`, `css`, `scss`, `sass`, `less`, `xml`.
5. **Is the browser really loading the new bundle?** Load the page with `?debug=assets`, open the Sources tab and find `library/static/src/...`. If it is there, the problem is in your code, not in the bundle.
6. **Did the module throw while loading?** Open the console. Look for "The following modules failed to load because of an error" and inspect `odoo.loader.failed` and `odoo.loader.jobs`. A missing dependency puts a module in `jobs` forever.
7. **Is the template in the bundle?** A component whose XML was never listed fails at mount with a missing template error, not at load time.
8. **Was another addon's `remove` or `replace` applied after yours?** Print what the server resolved:

```python
# Odoo shell
paths = env["ir.asset"]._get_asset_paths("web.assets_backend", {})
for path, addon, bundle in paths:
    if addon == "library":
        print(path)
```

`_get_asset_paths(bundle, assets_params)` returns tuples of `(path, addon, bundle)`. The signature is the one in 18; `assets_params` is `{}` unless a module such as `website` overrides `_get_asset_params`.

## A realistic manifest

A module with a backend UI, a public page, a lazily loaded chart library, tour tests, unit tests and a report stylesheet:

```python
"assets": {
    "web._assets_primary_variables": [
        "library/static/src/scss/primary_variables.scss",
    ],
    "web.assets_backend": [
        "library/static/src/backend/**/*",
        ("remove", "library/static/src/backend/**/*.test.js"),
    ],
    "web.assets_frontend": [
        "library/static/src/public/**/*",
    ],
    "library.assets_chart": [
        "library/static/lib/chart/chart.min.js",
        "library/static/src/chart/**/*",
    ],
    "web.report_assets_common": [
        "library/static/src/report/report.scss",
    ],
    "web.assets_tests": [
        "library/static/tests/tours/**/*",
    ],
    "web.assets_unit_tests": [
        "library/static/src/**/*.test.js",
    ],
},
```

## Pitfalls

- **A file under `static/src` that matches no glob is never served**, and nothing reports it. Search the Sources tab, not the file system.
- **A backend file in `web.assets_frontend`** fails with missing dependencies. A frontend file in the backend runs on every page for every employee.
- **`("before", new, target)` with the arguments swapped.** The target is the second element.
- **A target that is not in the bundle yet.** Your addon is processed before the addon that adds the target, usually a missing `depends`.
- **Importing a module from a bundle not loaded on that page** fails at load time and lists your module in `odoo.loader.jobs`.
- **Changing the manifest without restarting the server.** The `assets` key is read when the registry loads.
- **Vendoring a library into `web.assets_backend`** and shipping megabytes to every user. Make it a lazy bundle.
- **SCSS that relies on file order.** Put variables in the variable bundle, mixins in helpers, and rules in the normal bundle.
- **`--dev=assets`.** It does nothing. Use `?debug=assets` in the browser.
- **A bundle name with three parts** (`library.assets.chart`). The compiled-bundle URL parser (`_parse_bundle_name`) requires exactly two dot-separated parts, so keep your own bundle names to `addon.name`.
- **Deleting attachments to fix a bundle and forgetting the cache.** After a database edit, restart or clear the registry caches too.

## Versions

{% hint style="info" %}
**16:** no `web.assets_web` bundle; the client loads `web.assets_backend` directly. Templates are listed in the same `assets` key as JavaScript (there is no separate `qweb` key). The `@odoo-module` header is required.

**17:** `web.assets_web` exists and includes `web.assets_backend`.

**18:** the lazy bundles and dark variants shown above exist. The server accepts `--dev=all,reload,qweb,xml` (`all` stands for `reload,qweb,xml`).

**20:** `--dev` accepts `access`, `qweb`, `reload`, `replica` and `xml`, and `all` expands to `access,qweb,reload,xml`. The bundle list adds icon font bundles (`web.material_symbols_*`, `web.odoo_ui_icons`, `web.icons_fonts`) and drops the jQuery helper bundle `web._assets_jquery` that 18 has. The directives and the assembly order are the same as in 18.
{% endhint %}

## Try it

1. Create a file `library/static/src/hello.js` that logs a line, list it in `web.assets_backend`, update the module, and find it in the Sources tab with `?debug=assets`.
2. Mistype the path on purpose and find the warning in the server log.
3. Add `("before", "web/static/src/main.js", "library/static/src/early.js")` and check, with the Odoo shell snippet above, where your file landed.
4. Run the read-only SQL on `ir_attachment` and note how many compiled bundles exist.

<details>

<summary>Solution notes</summary>

1. The path in the Sources tab is `library/static/src/hello.js`. In a normal (non-debug) page you would see only the minified bundle.
2. The log line is `IrAsset: the path "library/static/src/helo.js" did not resolve to anything.`, at WARNING level.
3. Printing `_get_asset_paths("web.assets_web", {})` shows your file immediately before `web/static/src/main.js`. Use `web.assets_web`, since `main.js` belongs to that bundle and not to `web.assets_backend`.
4. One `.js` and one `.css` per bundle and per language direction, plus lazy and report bundles.

</details>
