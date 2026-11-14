---
description: "Customer portal pages, public widgets, public OWL components and Odoo 20 interactions: the JavaScript and QWeb that run for visitors and portal users."
---

# Website and portal

The backend web client is not what visitors and portal users see. Their pages are rendered by a controller with QWeb, served with `web.assets_frontend`, and brought to life by a different set of JavaScript tools. This chapter covers the whole slice a developer touches: adding a section to the customer portal (controller, templates, access rules), attaching behaviour to the page with a public widget (Odoo 17 and 18) or an interaction (Odoo 20), mounting an OWL component on a public page, and calling back to the server.

Everything was read from the Odoo 18 `portal` and `web` addons and the Odoo 20 tree. The teaching module `library` gives its members a page listing their loans.

## What runs where

| Concern | Odoo 17 and 18 | Odoo 20 |
| --- | --- | --- |
| Page markup | QWeb templates (`portal.portal_layout`, `website.layout`) | same |
| Page logic | controller extending `CustomerPortal` | same |
| Behaviour on a page | `publicWidget.Widget` subclasses registered in `publicWidget.registry` | `Interaction` subclasses registered in `public.interactions` |
| OWL on a public page | `<owl-component name="...">` plus `public_components` registry | same element, mounted by an interaction |
| JSON calls | `rpc` from `@web/core/network/rpc`, route `type="json"` | same `rpc`, route `type="jsonrpc"` |
| Bundle | `web.assets_frontend` | `web.assets_frontend` |

Public code has no `env.services.orm` guarantee for anonymous users and no web client. Anything it needs from the server goes through a controller route, which is where access control belongs.

## The portal in one page

The portal is the set of pages under `/my` that a logged-in portal user sees. `CustomerPortal` in `addons/portal/controllers/portal.py` is the controller to extend. Its relevant members in 18:

- `_prepare_home_portal_values(self, counters)`: returns the values for the home page cards. `counters` is the list of badges to compute; the base returns `{}`.
- `/my/counters` (a JSON route) calls the same method for the lazily loaded badges, and caches the booleans in the session.
- `home()` renders `portal.portal_my_home`.
- `_document_check_access(model_name, document_id, access_token=None)`: loads a record the user may see, either through normal access or through a valid access token. It returns the record sudoed and raises `MissingError` or `AccessError`.
- `_get_page_view_values(...)`: adds chatter and pager values for a detail page.
- `pager(url, total, page=1, step=30, scope=5, url_args=None)`: module-level function producing the dict for the pager template.

## Step 1: access rights first

Portal users are in `base.group_portal`. Without an access rule and a record rule they see nothing, and the page raises `AccessError`. Write the security before the page.

`library/security/ir.model.access.csv` (one line more):

```
access_library_loan_portal,library.loan portal,model_library_loan,base.group_portal,1,0,0,0
```

`library/security/library_security.xml`:

```xml
<record id="library_loan_rule_portal" model="ir.rule">
    <field name="name">Loan: portal users see their own</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="domain_force">[('member_id.partner_id', '=', user.partner_id.id)]</field>
    <field name="groups" eval="[(4, ref('base.group_portal'))]"/>
</record>
```

Read access only, and only the member's own loans. Everything the controller does with `request.env` then goes through this rule. Do not reach for `sudo()` to make the page work; fix the rule.

## Step 2: the controller

```python
# library/controllers/portal.py
from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class LibraryPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "loan_count" in counters:
            Loan = request.env["library.loan"]
            values["loan_count"] = (
                Loan.search_count([]) if Loan.has_access("read") else 0
            )
        return values

    @http.route(
        ["/my/loans", "/my/loans/page/<int:page>"],
        type="http", auth="user", website=True,
    )
    def portal_my_loans(self, page=1, **kw):
        Loan = request.env["library.loan"]
        total = Loan.search_count([])
        pager = portal_pager(
            url="/my/loans", total=total, page=page, step=self._items_per_page,
        )
        loans = Loan.search(
            [], order="due_date desc", limit=self._items_per_page, offset=pager["offset"],
        )
        values = self._prepare_portal_layout_values()
        values.update({
            "loans": loans,
            "page_name": "loans",
            "pager": pager,
            "default_url": "/my/loans",
        })
        return request.render("library.portal_my_loans", values)

    @http.route("/my/loans/<int:loan_id>", type="http", auth="user", website=True)
    def portal_my_loan(self, loan_id, access_token=None, **kw):
        try:
            loan_sudo = self._document_check_access("library.loan", loan_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        values = {"loan": loan_sudo, "page_name": "loan"}
        return request.render("library.portal_my_loan", values)
```

Points to check in this code:

- `Loan.search_count([])` is not unsafe: the record rule above narrows the result to the user's own loans, because the call runs as the portal user. That is why the controller uses the plain environment.
- `has_access("read")` returns a boolean in 18. In 17 the equivalent is `check_access_rights("read", raise_exception=False)`. Counting without the check would raise for users who lack the ACL.
- `_items_per_page` is an attribute of `CustomerPortal` (80 in the 18 source); use it so your page matches the others, or define your own step.
- `portal_pager(...)` returns a dict with an `offset` key, ready for `search(offset=...)`.
- `_document_check_access` returns the record **sudoed**, so everything you render from `loan_sudo` bypasses record rules after the check. Render only fields you mean to show, and never pass `loan_sudo` to code that writes.
- `auth="user"` redirects anonymous visitors to the login page. Do not use `auth="public"` for private data.

Register the file in `controllers/__init__.py` (`from . import portal`) and in `library/__init__.py` (`from . import controllers`).

## Step 3: the templates

```xml
<odoo>
    <!-- 1. A card on /my -->
    <template id="portal_my_home_library" name="Library: loans card"
              inherit_id="portal.portal_my_home" customize_show="True" priority="30">
        <xpath expr="//div[hasclass('o_portal_docs')]" position="inside">
            <t t-call="portal.portal_docs_entry">
                <t t-set="title">Loans</t>
                <t t-set="url" t-value="'/my/loans'"/>
                <t t-set="text">Books you have borrowed</t>
                <t t-set="placeholder_count" t-value="'loan_count'"/>
            </t>
        </xpath>
    </template>

    <!-- 2. Breadcrumb entries -->
    <template id="portal_breadcrumbs_library" name="Library: breadcrumbs"
              inherit_id="portal.portal_breadcrumbs">
        <xpath expr="//ol[hasclass('o_portal_submenu')]" position="inside">
            <li t-if="page_name == 'loans'" class="breadcrumb-item active">Loans</li>
            <li t-if="page_name == 'loan'" class="breadcrumb-item">
                <a href="/my/loans">Loans</a>
            </li>
            <li t-if="page_name == 'loan'" class="breadcrumb-item active">
                <t t-out="loan.display_name"/>
            </li>
        </xpath>
    </template>

    <!-- 3. The list page -->
    <template id="portal_my_loans" name="Library: my loans">
        <t t-call="portal.portal_layout">
            <t t-set="breadcrumbs_searchbar" t-value="False"/>
            <t t-if="not loans">
                <p class="alert alert-info">You have no loans.</p>
            </t>
            <t t-else="">
                <t t-call="portal.portal_table">
                    <thead>
                        <tr>
                            <th>Book</th>
                            <th>Due</th>
                            <th class="text-end">State</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr t-foreach="loans" t-as="loan">
                            <td><a t-attf-href="/my/loans/#{loan.id}"><t t-out="loan.book_id.name"/></a></td>
                            <td><span t-field="loan.due_date"/></td>
                            <td class="text-end"><span t-field="loan.state"/></td>
                        </tr>
                    </tbody>
                </t>
            </t>
        </t>
    </template>

    <!-- 4. The detail page -->
    <template id="portal_my_loan" name="Library: my loan">
        <t t-call="portal.portal_layout">
            <div class="container pt-3 o_library_loan" t-att-data-loan-id="loan.id">
                <h2 t-out="loan.book_id.name"/>
                <p>Due on <span t-field="loan.due_date"/></p>
                <button t-if="loan.state == 'open'" type="button"
                        class="btn btn-primary o_library_extend">
                    Extend by 7 days
                </button>
            </div>
        </t>
    </template>
</odoo>
```

Details behind it:

- `portal.portal_docs_entry` takes `title`, `url`, `text`, `icon`, `placeholder_count`, `count`, `show_count` and `config_card` (read from the template). A card with `placeholder_count` stays hidden until the lazily fetched `/my/counters` result says the count is non-zero, which is why `_prepare_home_portal_values` must answer to the key you pass.
- `portal.portal_table` wraps whatever you put inside in a `<table>`, plus the pager when `pager` is in the values.
- `t-field` renders a field with its formatting and widget rules (dates, selections), which is better than `t-out` for model values. It needs a record and a field.
- `page_name` drives breadcrumbs and menu highlighting. Set it in the controller.
- The home page template is inherited with `customize_show="True"` so an administrator can switch the card on and off from the website editor.
- The `xpath` selectors reuse classes from the portal templates (`o_portal_docs`, `o_portal_submenu`). Check them in the branch you target; they are the part most likely to move.

## Step 4: put the files in the right bundles

Portal pages use `web.assets_frontend` for scripts and styles. Backend code does not belong there.

```python
"assets": {
    "web.assets_frontend": [
        "library/static/src/portal/**/*",
    ],
},
"data": [
    "security/ir.model.access.csv",
    "security/library_security.xml",
    "views/portal_templates.xml",
],
"depends": ["portal", "library_base"],
```

## Behaviour on the page: public widgets (Odoo 17 and 18)

A `publicWidget` attaches to the elements matching its `selector` when the page loads, and gives you jQuery-style helpers (`this.$el`, `events`), a lifecycle, and automatic cleanup. This is the legacy-style API that portal and website still use in 18.

```javascript
/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.LibraryLoanExtend = publicWidget.Widget.extend({
    selector: ".o_library_loan",
    events: {
        "click .o_library_extend": "_onExtendClick",
    },

    start() {
        this.loanId = parseInt(this.el.dataset.loanId, 10);
        return this._super(...arguments);
    },

    async _onExtendClick(ev) {
        const button = ev.currentTarget;
        button.disabled = true;
        try {
            const result = await rpc(`/my/loans/${this.loanId}/extend`, { days: 7 });
            this.el.querySelector("p").textContent = `Due on ${result.due_date}`;
        } catch (error) {
            button.disabled = false;
            throw error;
        }
    },
});
```

The pieces, from `addons/web/static/src/legacy/js/public/public_widget.js`:

- `selector` is a CSS selector; one widget instance is created for each match.
- `events` maps `"event selector"` to a method name, with jQuery-style delegation inside `this.$el`.
- Lifecycle: `init(parent, options)` first, then `willStart()` (may return a promise, nothing is displayed before it resolves), then `start()` (the element is ready; return the parent's promise by calling `this._super`), and `destroy()` when the page unloads or the website editor takes over.
- `this._super(...arguments)` calls the overridden method. It is required in `start` so the base class can finish.
- Registered widgets are looked up through `publicWidget.registry`; the key is only a unique name.
- Selectors are matched when the page loads. Elements injected later (a modal, an AJAX fragment) are not matched automatically, so prefer server-rendered pages.

The matching JSON route, with `type="json"` in 18. It needs `from odoo import _, fields, http`, and `action_extend` is a method of the teaching model `library.loan` (it adds the days to `due_date`):

```python
@http.route("/my/loans/<int:loan_id>/extend", type="json", auth="user", website=True)
def portal_extend_loan(self, loan_id, days=7, **kw):
    try:
        loan_sudo = self._document_check_access("library.loan", loan_id)
    except (AccessError, MissingError):
        raise AccessError(_("You cannot extend this loan."))
    loan_sudo.action_extend(days=int(days))
    return {"due_date": fields.Date.to_string(loan_sudo.due_date)}
```

Do the check on the server every time. The button being hidden in the template is not a security measure.

## Behaviour on the page: interactions (Odoo 20)

Odoo 20 replaces `publicWidget` with `Interaction` classes (`web/static/src/public/interaction.js`), registered in `public.interactions`. The Odoo 20 core ports its portal pages to them (`account/static/src/interactions/...`). The same widget, as an interaction:

```javascript
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

export class LibraryLoanExtend extends Interaction {
    static selector = ".o_library_loan";
    dynamicContent = {
        ".o_library_extend": { "t-on-click": this.onExtendClick },
    };

    setup() {
        this.loanId = parseInt(this.el.dataset.loanId, 10);
    }

    async onExtendClick(ev) {
        const button = ev.currentTarget;
        button.disabled = true;
        try {
            const result = await this.waitFor(
                rpc(`/my/loans/${this.loanId}/extend`, { days: 7 })
            );
            this.el.querySelector("p").textContent = `Due on ${result.due_date}`;
        } catch (error) {
            button.disabled = false;
            throw error;
        }
    }
}

registry.category("public.interactions").add("library.loan_extend", LibraryLoanExtend);
```

What the base class documents in the source:

- `static selector` picks the elements; `selectorHas` and `selectorNotHas` refine it. One instance per element, with `this.el` and `this.env`/`this.services`.
- The constructor is not overridden; use `setup()` (sync initialisation), `willStart()` (async, awaited before dynamic content applies), `start()` (equivalent of OWL's `mounted`, handlers attached), and `destroy()` for cleanup. It is not necessary to call `super` in these unless you inherit from a concrete subclass.
- `dynamicContent` is an object `{ selector: { directive: handler } }` with directives `t-on-*` (with `.prevent`, `.stop`, `.capture`, `.once`, `.noUpdate`), `t-att-*`, `t-out` and `t-component`. Special selectors are `_root`, `_body`, `_document`, `_window`. The framework re-applies the dynamic content after each handler, so state-driven classes and attributes need no manual DOM code.
- Helpers: `waitFor(promise)` (ignores a result that arrives after the interaction was destroyed), `addListener`, `debounced`, `throttled`, `locked` (one run at a time, optionally with a loading animation), `setSafeInterval`, `waitForTimeout`, `insert`, `removeChildren`, `registerCleanup`, `mountComponent`.
- Interactions must clean up after themselves: they are destroyed when someone switches the website to edit mode.
- The source states plainly that it "is not owl": the syntax resembles OWL templates but differs.

For a port from `publicWidget`: `selector` stays; `events` become entries of `dynamicContent`; `start()` becomes `setup()` or `start()`; `this._super` disappears; wrap asynchronous calls in `this.waitFor`.

## An OWL component on a public page

For richer UI on a public page, use OWL in a controlled way: register a component and place a custom element in the template.

```javascript
/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

class LoanCountdown extends Component {
    static template = "library.LoanCountdown";
    static props = { due: String };
    setup() {
        const ms = new Date(this.props.due) - Date.now();
        this.state = useState({ days: Math.ceil(ms / 86400000) });
    }
}

registry.category("public_components").add("library.loan_countdown", LoanCountdown);
```

```xml
<owl-component name="library.loan_countdown" t-att-props="json.dumps({'due': str(loan.due_date)})"/>
```

In 18 the `public_component_service` mounts each `owl-component[name]` element it finds, parsing the element's `props` attribute as JSON and creating a separate OWL app per element (`addons/web/static/src/public/public_component_service.js`). The component class comes from the `public_components` registry. In 20 a `PublicComponentInteraction` with selector `owl-component[name]` does the same through `this.mountComponent`.

The portal's own signature form uses exactly this shape: `<owl-component name="portal.signature_form" t-att-props="json.dumps(signature_form_props)"/>`. Build the dictionary in the controller and serialise it in the template as shown. A public OWL component gets the public environment: services like `orm` that need a session user are not safe to assume. Fetch data through your own routes.

## Styling

Frontend styles go into `web.assets_frontend` as SCSS and can use Bootstrap utilities and the portal's CSS variables. Prefix your classes (`o_library_...`). To change colours globally for the portal, override variables in `web._assets_primary_variables`, as described in the assets chapter.

## Testing the portal

Python controller tests use `HttpCase` with `self.authenticate("portal_user", "portal_user")` and `self.url_open("/my/loans")`; they check status codes, redirects for anonymous users, and that a portal user cannot read another member's loan (`/my/loans/<other id>` redirects to `/my`). A tour (see the next chapter) drives the real page, including the widget click, with `self.start_tour("/my/loans", "library_portal_tour", login="portal_user")`.

Write the access test first. It is the one that catches the expensive mistakes.

## Pitfalls

- **No access rule for `base.group_portal`.** The portal page raises `AccessError` or shows nothing. Write ACL and record rule first.
- **`sudo()` to "fix" a portal page.** It exposes other members' records. Fix the rule instead.
- **Rendering a sudoed record into a writing code path.** `_document_check_access` returns the record with elevated rights; keep it read-only.
- **`auth="public"` for private pages.** Use `auth="user"`.
- **A JSON route without server-side checks.** The UI is not a boundary.
- **Backend code in `web.assets_frontend`, or the other way round.** The module does not exist on that page.
- **Widget or interaction selector that matches nothing.** Check the class in the rendered HTML (with `?debug=assets`), not in the template source.
- **`type="json"` on 20.** It is a deprecated alias of `jsonrpc` since 19; write `jsonrpc` when you target 20 only.
- **`publicWidget` on 20 for new code.** Core is moving to interactions. Existing widgets may keep working for now; confirm in your build.
- **Assuming the `orm` service works for visitors.** Public pages have no logged-in user; use routes.
- **Heavy JavaScript on every public page.** `web.assets_frontend` is downloaded by every visitor. Use lazy bundles (`loadBundle`) for rarely needed code.
- **Hard-coded URLs.** Use `t-attf-href` or `url_for`-style helpers so website and language prefixes keep working.
- **Counters without a matching key.** A card with `placeholder_count="loan_count"` stays hidden if `_prepare_home_portal_values` does not return `loan_count` when asked.

## Versions

{% hint style="info" %}
**16:** `publicWidget` is the only tool. The portal controller API and the `rpc` helper were not verified on 16 for this chapter; check `_prepare_home_portal_values` and the JSON call helper on your branch.

**17:** `publicWidget`; the portal helpers above exist. `check_access_rights` is the way to test access.

**18:** `publicWidget`, `has_access`, `rpc` import, `type="json"`. Public OWL components via `owl-component`.

**20:** `Interaction` classes in `public.interactions`; routes use `type="jsonrpc"` (`json` is a deprecated alias with a warning).
{% endhint %}

## Try it

1. Create the ACL, rule, controller and templates above. Log in as a portal user whose partner owns two loans and check `/my/loans`.
2. Log in as a second portal user and request the first user's loan id directly at `/my/loans/<id>`. What happens?
3. Add the widget, open the loan page, click the button, and read the network tab.
4. Write a `HttpCase` test that asserts step 2.

<details>

<summary>Solution notes</summary>

1. The list shows only the user's loans, and the home card appears once `/my/counters` reports a non-zero `loan_count`.
2. `_document_check_access` raises `AccessError` for a record the user cannot read without a token, and the controller redirects to `/my`. If you see the other user's data, the record rule is missing or has the wrong domain.
3. One JSON request to `/my/loans/<id>/extend`; the date text updates without a page reload.
4. `self.authenticate("portal_b", "portal_b")`, `response = self.url_open("/my/loans/%d" % loan_a.id)`, then assert the final URL ends with `/my` (follow redirects) or the status is 302.

</details>
