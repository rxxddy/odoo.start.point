---
description: "Testing the frontend: tours that drive a real browser, hoot unit tests for components and fields, and how to run both locally and in CI."
---

# Tours and frontend tests

Frontend code fails in ways Python tests never see: a bundle that does not load, a selector that matches nothing, a widget that works in forms and crashes in lists. Two kinds of test cover this. A **tour** drives a real headless browser through a scenario against a real database. A **hoot unit test** mounts a component or a view against a mocked server in milliseconds.

Verified against the Odoo 18 source (`addons/web_tour`, `addons/web/static/tests`, `addons/web/tests/test_js.py`, `odoo/tests/common.py`).

## Which test for which question

| Question | Tool |
| --- | --- |
| Does the whole flow work through the real UI, server and database? | tour |
| Does my component render and react correctly in isolation? | hoot unit test |
| Does a field widget work in a form, a list, in readonly and edit mode? | hoot view test with `mountView` |
| Is my pure JavaScript logic right (an ISBN check digit)? | hoot unit test without any mount |
| Is the server rule enforced regardless of the UI? | Python test, not a JavaScript one |

Prefer many small unit tests and a handful of tours for the critical paths. Tours are slow (they start a browser and a server) and the first thing to become flaky.

## Tours

### Anatomy

A tour is an entry in the `web_tour.tours` registry: a name, a starting URL, and a function returning the steps. Put it in the `web.assets_tests` bundle so it is only loaded when tests run.

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_service/tour_utils";

registry.category("web_tour.tours").add("library_loan_tour", {
    url: "/odoo",
    steps: () => [
        ...stepUtils.goToAppSteps("library.menu_root", "Open the Library app"),
        {
            content: "Create a loan",
            trigger: ".o_list_button_add",
            run: "click",
        },
        {
            content: "Pick a book",
            trigger: ".o_field_widget[name=book_id] input",
            run: "edit Dune",
        },
        {
            content: "Choose it in the dropdown",
            trigger: ".o-autocomplete--dropdown-item > a:contains('Dune')",
            run: "click",
        },
        {
            content: "Save",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "The loan is saved and open",
            trigger: ".o_field_widget[name=state]:contains('Open')",
        },
    ],
});
```

Registry validation in `tour_service.js` defines the shape: a tour has `steps` (a function), and optionally `name`, `url` and `wait_for`. A step has `trigger` (mandatory string) and optional `content`, `run`, `isActive`, `timeout`, `tooltipPosition`, `expectUnloadPage`, `id`, `debugHelp`, and in debug mode `pause` and `break`.

### How a step runs

For each step the engine:

1. waits until `trigger` matches a visible, enabled element (default timeout 10000 ms; the schema accepts 0 to 60000 through `timeout`). It re-checks on DOM mutations;
2. then performs `run` on that element;
3. moves to the next step.

A step **without `run`** only waits for the trigger: it is an assertion that the element exists. In the 18 source an action is performed only when `run` is a string or a function. Do not write `run: "click"` on assertion steps, and do not omit it on steps that must click.

Triggers are CSS selectors extended by the hoot query engine, so you can use `:contains(text)`, `:visible`, `:hidden`, `:has(...)`, `:not(:has(...))` and `:iframe` among others. A selector ending in `:hidden` or `:visible` overrides the default "must be visible".

### The `run` vocabulary

`run` is a string, a chain joined with `&&`, or a function.

| String | Effect |
| --- | --- |
| `click` | click the element |
| `dblclick` | double click |
| `edit text` | focus and type text (replaces content) |
| `fill text` | set the value of an input and fire events |
| `clear` | empty the input |
| `check`, `uncheck` | toggle a checkbox |
| `select value`, `selectByIndex n`, `selectByLabel text` | choose in a `<select>` |
| `press Enter` | key press |
| `hover` | hover |
| `range n` | set a range input |
| `editor text` | type into an HTML editor |
| `goToUrl /path` | navigate |

Examples: `run: "edit 42"`, `run: "click && edit hello"`. The engine splits on `&&` and parses each part as `action argument`. A function receives the helpers object and runs with `this.anchor` bound to the element:

```javascript
{
    trigger: ".o_field_widget[name=due_date] input",
    run: function (helpers) {
        helpers.edit("2030-01-01");
    },
},
```

The helper methods are `check`, `clear`, `click`, `dblclick`, `edit`, `editor`, `fill`, `hover`, `range`, `press`, `select`, `selectByIndex`, `selectByLabel`, `uncheck` and `goToUrl`, as defined in `tour_helpers.js`.

### Reusable steps

`@web_tour/tour_service/tour_utils` exports `stepUtils` with ready-made steps: `goToAppSteps(menuXmlid, description)` opens an app from the home menu, `saveForm()` and `discardForm()`, `statusbarButtonsSteps(text, description, trigger)`, `autoExpandMoreButtons()`, `waitIframeIsReady()`, `goToUrl(url)`. Use them. They handle the community and enterprise differences (`isActive: ["community"]` and `["enterprise"]`) that you would otherwise copy wrongly.

Make your own helpers the same way, as functions returning arrays of steps, and spread them:

```javascript
function createLoan(bookName) {
    return [
        { trigger: ".o_list_button_add", run: "click" },
        { trigger: ".o_field_widget[name=book_id] input", run: `edit ${bookName}` },
        { trigger: `.o-autocomplete--dropdown-item > a:contains('${bookName}')`, run: "click" },
        stepUtils.saveForm(),
    ];
}
```

### Conditional steps

`isActive` skips a step when its condition is false. It accepts keywords (`"community"`, `"enterprise"`, `"mobile"`, `"desktop"`) and arrays of selectors that must all match. A skipped step is simply passed over:

```javascript
{
    isActive: [".o_dialog .modal-footer"],
    trigger: ".modal-footer .btn-primary",
    run: "click",
},
```

Use it for optional UI (a confirmation dialog that appears only sometimes) instead of sleeps.

### Writing robust triggers

- Anchor on stable hooks: `name="..."` attributes (`.o_field_widget[name=book_id]`), `data-menu-xmlid`, `data-hotkey`, `t-ref`-based class names you control. Avoid positional selectors (`:nth-child`) and text that is translated.
- Make steps wait for the result of the previous action. After saving, add a step that waits for something that appears only once the save completed. Never rely on time.
- One action per step, with a `content` that says what and why. It becomes the failure message and, in manual mode, the tooltip.
- Tours run with demo or test data of your module. Create what the tour needs in `setUp` of the Python test or in the tour's initial steps, never rely on whatever exists in the database.

### Running a tour from Python

The tour is launched by a Python `HttpCase`:

```python
# library/tests/test_tours.py
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestLibraryTours(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["library.book"].create({"name": "Dune", "isbn": "9780306406157"})

    def test_loan_tour(self):
        self.start_tour("/odoo", "library_loan_tour", login="admin")
```

`start_tour(url_path, tour_name, step_delay=None, **kwargs)` is implemented in `odoo/tests/common.py`: it builds `odoo.startTour(tour_name, options)`, waits for `odoo.isTourReady(tour_name)`, and runs `browser_js` with the success signal `tour succeeded` and a default timeout of 60 seconds. Useful keyword arguments:

| Argument | Meaning |
| --- | --- |
| `login="admin"` | authenticate as that user before loading the page |
| `step_delay=500` | milliseconds between steps, for watching |
| `watch=True` | show the browser window (needs a local Chrome, not headless) |
| `debug=True` | open the browser debugger |
| `timeout=120` | override the 60 s limit for long tours |

Tags matter:

- `post_install` runs the test after all modules are installed, so the web client with all its bundles exists. `-at_install` prevents it from also running right after your module installs, when the full UI is not ready.
- Select the tour from the command line with a test tag:

```bash
./odoo-bin -d test_library -i library --test-enable --test-tags /library:TestLibraryTours --stop-after-init
```

Tag syntax is `[-][tag][/module][:class][.method]`, so `/library:TestLibraryTours.test_loan_tour` selects one test.
The `-i`/`-u` run needs a database where demo data exists if your tour uses it; create the data in the test itself to avoid the dependency.

### Debugging a failing tour

1. Read the failure message: it names the step `content` and the trigger that was never found, and prints the DOM at that point.
2. Reproduce interactively. Log in, open the starting URL with `?debug=tests` (it adds the test bundle) and start the tour from the console with `odoo.startTour("library_loan_tour", { mode: "manual" })`, (the `tests` debug mode makes the `web.assets_tests` bundle load: the bootstrap template checks `'tests' in debug`). In manual mode the tour shows a pointer and tooltips and waits for you to do each step.
3. Run with `watch=True, step_delay=500` locally to see it happen.
4. Check whether the selector matches at all in the browser console: `document.querySelector(".o_field_widget[name=book_id] input")`.
5. If a step passes locally and fails in CI, the cause is usually timing (the previous action had not finished) or data (the record does not exist). Add a waiting step, create the data in `setUp`.

The engine also has a check for non-deterministic steps, enabled with the environment variable `ODOO_TOUR_DELAY_TO_CHECK_UNDETERMINISMS` (seconds). With it set above zero, `start_tour` adds that many seconds to the timeout and runs the tour in a mode that checks for non-deterministic steps (the web_tour tests include `check_undeterminisms.test.js`). Use it on tours that fail intermittently.

### Tours for the website and portal

The same registry is used on public pages. The bundle is the same (`web.assets_tests`), the URL is a public or portal path, and the test passes the login:

```python
self.start_tour("/my/loans", "library_portal_tour", login="portal_user")
```

```javascript
registry.category("web_tour.tours").add("library_portal_tour", {
    url: "/my/loans",
    steps: () => [
        { trigger: "a:contains('Dune')", run: "click" },
        { trigger: ".o_library_extend", run: "click" },
        { trigger: "p:contains('Due on')" },
    ],
});
```

## Hoot unit tests

Hoot is Odoo's own test framework for JavaScript, living in `addons/web/static/lib/hoot` and `hoot-dom`. Tests are files ending in `.test.js`; each declares `test("name", async () => {...})` and uses `expect` from `@odoo/hoot`. They run in a browser against a **mock server**, so no database is needed.

### Where files go and how they are picked up

The runner bundle is `web.assets_unit_tests`. It includes the framework (`web.assets_unit_tests_setup`, which itself includes `web.assets_backend` and `web.assets_backend_lazy`, so your module's production code is already loaded) and then the test files you list:

```python
"assets": {
    "web.assets_backend": [
        "library/static/src/**/*",
        ("remove", "library/static/src/**/*.test.js"),
    ],
    "web.assets_unit_tests": [
        "library/static/src/**/*.test.js",
        "library/static/tests/**/*.test.js",
    ],
},
```

The `remove` line is important if tests live under `static/src`: without it they ship in the production bundle. The core addons keep tests in `static/tests` and list them in `web.assets_unit_tests`, as `mail` and `web_tour` do.

### Running them

In the browser: open `/web/tests` on a running server (you need to be logged in). The page lists suites and runs them. Add `?debug=assets` to read the source, filter with the search box or `?id=<hash>` URLs, and use `?headless` to run without the UI. From the command line the Python class `WebSuite.test_unit_desktop` in `addons/web/tests/test_js.py` opens `/web/tests?headless&loglevel=2&preset=desktop...` in headless Chrome and waits for `[HOOT] Test suite succeeded`:

```bash
./odoo-bin -d test_library -i web,library --test-enable --test-tags /web:WebSuite.test_unit_desktop --stop-after-init
```

That runs every unit test of every installed module. Use the browser while developing; use the command line in CI.

### A pure-logic test

The ISBN functions of the widgets chapter, tested with no DOM. `library/static/tests/isbn.test.js`:

```javascript
import { describe, expect, test } from "@odoo/hoot";
import { formatIsbn, isValidIsbn, normalizeIsbn } from "@library/fields/isbn";

describe("isbn helpers", () => {
    test("accepts valid ISBN-13 and ISBN-10", () => {
        expect(isValidIsbn("9780306406157")).toBe(true);
        expect(isValidIsbn("0-306-40615-2")).toBe(true);
        expect(isValidIsbn("080442957X")).toBe(true);
    });

    test("rejects wrong check digits and garbage", () => {
        expect(isValidIsbn("9780306406158")).toBe(false);
        expect(isValidIsbn("0306406153")).toBe(false);
        expect(isValidIsbn("abc")).toBe(false);
        expect(isValidIsbn("")).toBe(false);
    });

    test("normalises and formats", () => {
        expect(normalizeIsbn(" 978-0-306 40615-7 ")).toBe("9780306406157");
        expect(formatIsbn("9780306406157")).toBe("978-0-30640-615-7");
    });
});
```

The module path `@library/fields/isbn` follows the rule from the overview chapter: `@addon/path under static/src`, without extension. The same assertions were run in plain Node against the function bodies while writing this book, with the results noted in the widgets chapter.

### A field view test

This mirrors how the core tests its own widgets (`views/fields/char_field.test.js`): declare a model class for the mock server, register it, mount a view, interact, assert.

```javascript
import { expect, test } from "@odoo/hoot";
import {
    clickSave,
    defineModels,
    fields,
    fieldInput,
    models,
    mountView,
} from "@web/../tests/web_test_helpers";

class LibraryBook extends models.Model {
    _name = "library.book";

    name = fields.Char();
    isbn = fields.Char();

    _records = [{ id: 1, name: "Dune", isbn: "9780306406157" }];
    _views = {
        form: /* xml */ `
            <form>
                <field name="name"/>
                <field name="isbn" widget="library_isbn"/>
            </form>
        `,
    };
}

defineModels([LibraryBook]);

test("isbn widget shows the formatted value", async () => {
    await mountView({ type: "form", resModel: "library.book", resId: 1 });
    expect(".o_field_widget[name=isbn] input").toHaveValue("978-0-30640-615-7");
});

test("an invalid ISBN marks the field invalid", async () => {
    await mountView({ type: "form", resModel: "library.book", resId: 1 });
    await fieldInput("isbn").edit("9780306406158");
    expect(".o_field_widget[name=isbn]").toHaveClass("o_field_invalid");
});

test("a valid ISBN is stored without hyphens", async () => {
    await mountView({ type: "form", resModel: "library.book", resId: 1 });
    await fieldInput("isbn").edit("0-306-40615-2");
    await clickSave();
    expect(LibraryBook._records[0].isbn).toBe("0306406152");
});
```

What the helpers do, from `web_test_helpers.js` and `_framework`:

- `models.Model` plus `fields.*` declare a model the mock server serves. `_records` are the rows, `_views` the arch for each view type the test mounts.
- `defineModels([...])` registers the classes for the tests of the file (it uses `before` hooks, so call it at top level).
- `mountView({ type, resModel, resId?, arch? })` mounts a real view with the real controller, renderer and widgets against the mock server, and returns when it is ready.
- `fieldInput(name)` gives access to the input of a field (`.edit(value)`, `.clear()`), `clickSave()` clicks the save button, `contains(selector)` finds elements and offers actions, `onRpc(route|method, handler)` intercepts server calls, `patchWithCleanup(obj, patch)` applies a patch that is removed after the test.
- `expect(selector)` returns assertions with DOM-aware matchers: `toHaveCount`, `toHaveValue`, `toHaveText`, `toHaveClass`, `toHaveAttribute`, `toBeEnabled`, and the usual `toBe`, `toEqual`.

The test file imports your widget module indirectly: `web.assets_unit_tests_setup` includes `web.assets_backend`, which lists your `static/src/**/*`, so `library_isbn` is registered when the test runs.

### Testing a component directly

For a component that is not a view, mount it with `mountWithCleanup`:

```javascript
import { expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { LoanCounter } from "@library/systray/loan_counter";

test("shows the open loans count", async () => {
    await mountWithCleanup(LoanCounter);
    expect("button").toHaveText(/Loans:/);
});
```

Declare `library.loan` with `defineModels` and some `_records` before mounting a component that calls the ORM, since the mock server only knows the models you define. A component that calls a custom controller route needs `onRpc("/library/dashboard", () => ({ ... }))` registered first.

### Mocking and time

- `onRpc` handlers receive `{ args, kwargs, model, method, route }` and return the response. The core uses the form `onRpc("web_save", ({ args }) => { expect(args[1].name).toBe(false); })` to assert what the client sends.
- Hoot controls time. Use its mocked clock helpers from `@odoo/hoot-mock` (`animationFrame`, `runAllTimers`, `Deferred`) instead of real `setTimeout` waits, so tests run instantly and deterministically.
- Reset global state between tests with `patchWithCleanup`; avoid mutating registries or services directly. If you must register something, do it inside the test and rely on cleanup.

### Old QUnit tests

Odoo 17 and the legacy folders of 18 contain QUnit tests (`/web/tests/legacy`, `web.qunit_suite_tests`). In 18 the QUnit suites are being ported to hoot, and the manifest comments say the legacy paths are to be removed "when all legacy tests are ported". Write new tests in hoot. If you maintain a 16 or 17 module, its tests are QUnit with `QUnit.test` and the legacy helpers; the shape differs, the ideas do not.

## Continuous integration checklist

1. Python tests, with `post_install` tours: `./odoo-bin -d ci -i library --test-enable --test-tags /library --stop-after-init`.
2. The web suite when you change shared code: `--test-tags /web:WebSuite.test_unit_desktop` (long) or `/library` hoot tests through your own tagged Python class.
3. A tour must create its own data, must wait on results rather than time, and must pass three times in a row before you merge it.
4. Fail the build on JavaScript console errors: the browser runner already treats an uncaught error as a failure, so do not silence it.
5. Keep screenshots and logs. On failure the runner prints the console log and a DOM snapshot; keep those artefacts.

A Python class that runs only your module's hoot tests is a good idea. The core's `HOOTCommon` base class in `addons/web/tests/test_js.py` shows the pattern: tagged `post_install`, `-at_install`, calling `browser_js` on `/web/tests?...` with a filter and waiting for the `[HOOT] Test suite succeeded` log line.

## Odoo 20

The tour registry and `start_tour` carry over. Two cautions for 20:

- The tours and tests use the same step and run vocabulary, but the component code under test changes (props with `useProps`, `signal.ref()`, `this.` in templates). Tests that mount your components do not change, selectors in tours rarely do. Tests that **patch** internals (`patchWithCleanup(FormController.prototype, ...)`) must follow the method signatures of 20.
- Route type `jsonrpc` replaces `json` in controllers called by tours, and `onRpc` handlers still intercept by route or method.

## Pitfalls

{% hint style="warning" %}
Tours that depend on database contents you did not create are the most common cause of "works on my machine". Create what you need, in the test.
{% endhint %}

- **Sleeping.** A fixed delay is either too short (flaky) or too long (slow). Wait for a trigger.
- **Triggers on translated text** break when the test user's language changes. Prefer `name`, `data-*` and class hooks.
- **Missing `post_install`.** The tour starts before the UI bundles exist and fails with obscure errors.
- **Test files in the production bundle.** Add the `remove` entry and list them in `web.assets_unit_tests`.
- **Forgetting `login=`.** The tour runs as an anonymous user and stops at the login page.
- **`run: "click"` on an assertion step.** It clicks something you only meant to check.
- **Missing `run` on an action step.** In 18 nothing happens: the step passes as soon as the element exists.
- **Duplicated tour names.** The registry throws at load, and every later tour disappears.
- **Mounting a component without declaring the models it queries.** The mock server raises an error; declare models and records.
- **Leaving `only` or `debug` calls in tests.** The core has a check (`test_check_suite`) that fails the build when `only()` or `debug()` is left in a loaded test file.
- **Asserting right after an action without awaiting it.** Hoot helpers are async; `await` them.
- **UI tests as the only protection for a business rule.** Add a Python test for the rule too.

## Versions

{% hint style="info" %}
**16:** tours live in the `web_tour` addon with an older step vocabulary, tests are QUnit. A tour or test written here needs rewriting for 17 and 18.

**17:** `web_tour` has the `tour_service` directory and steps use functional `run: (actions) => ...` forms; QUnit remains the main unit test runner. Check the vocabulary of your branch before copying 18 steps.

**18:** the engine and vocabulary of this chapter (`run` strings, `isActive`, `stepUtils`); hoot is the test framework for new unit tests, QUnit remains for legacy code. `start_tour(url_path, tour_name, step_delay=None, **kwargs)`.

**20:** same tour API; route `type="jsonrpc"`; components under test use OWL 3 idioms.
{% endhint %}

## Try it

1. Add the loan tour above, write the Python test, and run it with the `--test-tags` line. Make it fail on purpose by changing a trigger and read the message.
2. Write the three ISBN hoot tests, run `/web/tests` in the browser and filter on `isbn`.
3. Add the widget view tests. Watch the invalid class test fail if you remove the `throw` from `parse`.
4. Run the tour with `watch=True, step_delay=500` on a machine with Chrome.

<details>

<summary>Solution notes</summary>

1. The failure message names the step's `content` and the trigger; with a wrong trigger the tour waits up to the step timeout (default 10 s) and then fails.
2. The three tests appear under the `@library` module in the runner list and pass; the same assertions were run in Node on the function bodies.
3. Without the `throw`, `parse` returns a value for the invalid ISBN, the field is not marked invalid, and the second test fails because `o_field_invalid` is absent.
4. A visible Chrome window opens and each step runs 500 ms apart. If the tour starts but nothing is displayed, Chrome is not installed or headless mode is forced.

</details>
