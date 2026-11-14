---
description: Testing controllers and the browser.
---

# HTTP and tour tests

`HttpCase` boots the real HTTP stack in the test process and, optionally, a headless Chrome. You use it to test controllers (status codes, redirects, access) and complete UI flows (tours). These tests are slower than model tests, so keep them for what the model layer cannot show.

## Testing controllers

```python
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestLibraryController(HttpCase):

    def test_loan_page_requires_login(self):
        res = self.url_open('/library/loan/1', allow_redirects=False)
        self.assertIn(res.status_code, (303, 401, 403, 404))

    def test_loan_page_as_user(self):
        self.authenticate('plain_emp', 'plain_emp')
        res = self.url_open('/library/loan/%d' % self.loan.id)
        self.assertEqual(res.status_code, 200)
```

`url_open(url, data=None, headers=None, timeout=...)` returns a `requests` response; if `data` is given it POSTs. `authenticate(login, password)` logs the test session in; password equals login for users you create with `password` set the same. The server runs in the same process and shares the test cursor, so records created in `setUp` are visible, and changes made by the request are visible to your assertions without committing.

For JSON routes, post with `self.make_jsonrpc_request(route, params)` where available, or `url_open` with a JSON body and header `Content-Type: application/json`.

{% hint style="info" %}
Versions: `HttpCase` warns when not `post_install` (verified in 18 `common.py`). `url_open` and `authenticate` exist in 16, 17 and 18; `make_jsonrpc_request` was added in 17.
{% endhint %}

Always include negative tests: an anonymous user, a user of another company, a user without the group. A controller that works for admin and leaks to the public passes a happy-path test.

## Tours

A tour is a scripted UI scenario written in JavaScript, registered in the `web_tour.tours` registry and run by the browser. In 18 the format is:

```javascript
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("library_loan_tour", {
    url: "/odoo/action-library.action_library_loan",
    steps: () => [
        { trigger: ".o_list_button_add", run: "click" },
        { trigger: ".o_field_widget[name=book_id] input", run: "edit Test Book" },
        { trigger: ".dropdown-item:contains('Test Book')", run: "click" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: ".o_form_saved" },
    ],
});
```

Declare the file in the manifest under `assets` with the bundle `web.assets_tests`, and run it from Python:

```python
def test_loan_tour(self):
    self.start_tour('/odoo', 'library_loan_tour', login='plain_emp')
```

`start_tour(url_path, tour_name, step_delay=None, **kwargs)` opens the page in headless Chrome and waits for the tour to finish; extra kwargs include `login`. A tour fails when a step's trigger is not found within the timeout, and the log prints the step and the page state.

{% hint style="warning" %}
Versions: the URL scheme changed. 16 and 17 use `/web#action=...`; 18 uses `/odoo/action-...` and `/odoo`. Tour step syntax also changed: 16 tours use `run: "click"` and old helpers such as `run: function (actions)`; 17 and 18 prefer string `run` actions. Tours written for 16 need review when ported.
{% endhint %}

## Writing stable tours

- Trigger on stable selectors: field names (`[name=book_id]`), `data-` attributes, and `o_*` classes that are part of the framework. Avoid CSS paths based on position.
- Wait for the right thing. A step that clicks and then reads must have a trigger that is only present after the previous action completed (`.o_form_saved`, a notification, a breadcrumb).
- Keep tours short: one flow, 10 to 25 steps. If it breaks you want to know which flow.
- Prepare the data in Python, in `setUp`. The tour should drive the UI, not set up the world through it.
- Remember demo vs no demo. Tours must pass without demo data.

## Debugging a tour

Run in a visible browser so that you can watch:

```python
def test_loan_tour_debug(self):
    self.start_tour('/odoo', 'library_loan_tour', login='plain_emp', watch=True)
```

`watch=True` opens a real browser window (needs a local Chrome and a display). Also `debug=True` pauses at the end for inspection in devtools. Never commit either flag. Alternatively, run the tour manually: open the URL with `?debug=assets,tests` (18) and use the tour menu in the debug toolbar to step through it.

## Pitfalls

- **Chrome not installed in CI.** Tours are skipped or fail with "Chrome headless not found". Install Chrome or Chromium on the runner, and fail loudly instead of skipping.
- **Flaky waits.** `sleep` in a tour is a smell. Replace it with a trigger on the state you await.
- **Tests leaking data across tours.** A tour that creates a record in the UI commits to the test cursor; the rollback at the end handles it, but a second tour in the same class sees the data. Use separate test methods and unique names.
- **Slow suites.** A HttpCase per page is expensive. Group steps into a single tour, test permissions with `url_open` instead.
- **Assets not rebuilt.** If you change tour JS and the test does not notice, clear the asset bundles (`ir.attachment` entries with `/web/assets/` URLs) or run with `--dev=assets` locally.

## Try it

Run a single HTTP test class and show the browser console log:

```bash
odoo-bin -d scratch -u library --test-tags /library:TestLibraryController --stop-after-init --log-level=test
```
