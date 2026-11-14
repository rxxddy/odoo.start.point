---
description: Changing existing JavaScript and template behaviour with patch() and template inheritance, safely, and knowing when not to.
---

# Patching standard code

`patch(obj, extension)` from `@web/core/utils/patch` overrides properties of a class prototype or an object in place and returns a function that undoes the patch. It is the JavaScript counterpart of `_inherit` with a method override, with one difference that matters: a Python `_inherit` extends a model for every caller by design, while a JavaScript patch also changes every instance and every subclass of the target that does not override the patched method itself. That reach is why this chapter spends as much time on when not to patch as on how.

Verified against `addons/web/static/src/core/utils/patch.js` of Odoo 18 (identical in Odoo 20), and against the 16 and 17 branches for the signature change.

The Odoo 20 source tree ships its own web guidelines (`skills/odoo-web-guidelines/guidelines/javascript.md`). They say that patching is "strongly discouraged inside Odoo itself" and fine outside of it, because a patch makes the code harder to reason about and drifts from its target, and that a proper extension point is usually the better answer. For a module author this reads as a license with a condition: patching your database's behaviour from your own module is normal, but each patch should be small, guarded, and a candidate for replacement by a registry entry or a subclass.

## The mechanics

```javascript
/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.libraryFlag = true;
        this.libraryNotification = useService("notification");
    },

    async onWillSaveRecord(record) {
        const ok = await super.onWillSaveRecord(...arguments);
        if (ok === false) {
            return false;
        }
        // custom check; returning false cancels the save
        if (record.resModel === "library.loan" && !record.data.book_id) {
            this.libraryNotification.add("Pick a book first", { type: "danger" });
            return false;
        }
    },
});
```

What happens inside `patch`:

1. For each own property of the extension object it reads the current property descriptor on the target and keeps it.
2. It defines the new property on the target. On a class prototype it is made non-enumerable, like a normal method.
3. It rewires the extension object's prototype so that `super.method(...)` inside the extension reaches the previous implementation. That is how native `super` works in an object literal.
4. If you give only a getter or only a setter, the other half is taken from the ancestor so the property does not lose its pair.
5. It returns an `unpatch` function. Calling it restores the originals and re-applies any other patches that were stacked on the same target.

Consequences you can rely on:

- Patches stack. Two modules patching the same method both run, in module load order, each calling `super` for the one before it. If one forgets `super`, every earlier patch (and the original) is skipped.
- `super` works for methods, getters and setters, and for static members when you patch the class itself.
- A patch is global and immediate: it takes effect when the patching module loads, for existing and future instances.

## What to patch: prototype versus class

```javascript
patch(ListController.prototype, { ... });   // instance methods: what you want 95% of the time
patch(ListController, { ... });             // static members: props, components, template
```

For statics:

```javascript
import { patch } from "@web/core/utils/patch";
import { FormStatusIndicator } from "@web/views/form/form_status_indicator/form_status_indicator";

patch(FormStatusIndicator, {
    props: {
        ...FormStatusIndicator.props,
        libraryHint: { type: String, optional: true },
    },
});
```

In Odoo 18, `static props` of core components is an object (a map from prop name to type description), so you spread it and add keys. Passing a prop that the class does not declare is a validation error in debug mode, which is why adding a prop to a patched component needs this step.

Do not write `props: [...X.props, "name?"]`. That is the array form of older OWL code. In Odoo 18 core components use the object form, and mixing the two breaks validation.

## Where to find the thing to patch

1. Open the screen with `?debug=assets`. In the Sources tab find the class (`@web/views/form/form_controller`).
2. Read the methods that look like hooks: `onWillSaveRecord`, `beforeLeave`, `beforeExecuteActionButton`, `afterExecuteActionButton`, `onRecordSaved`, `onWillLoadRoot`. Core developers add hook methods where they expect customisation. Patch a hook before you patch a private method.
3. Confirm the method is looked up on the instance, not captured. Some code does `this.props.onSave = this.save.bind(this)` at setup; patching `save` later does nothing for those captures.

For example, the form controller of Odoo 18 documents `onWillSaveRecord` in a comment: "a callBack that will be executed before the record save if the record is valid. If it returns false, it will prevent the save." That is an invitation to patch (or, better, to subclass for one view).

## Safe patterns

### Always call `super`

```javascript
patch(FormController.prototype, {
    async deleteRecord() {
        // 1. do your pre-work
        const result = await super.deleteRecord(...arguments);
        // 2. do your post-work
        return result;
    },
});
```

Return what the original returns. Callers that `await` the result expect it, and some check for `false`.

### Patch `setup` to add state or hooks

```javascript
import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.libraryState = useState({ checked: false });
        this.libraryOrm = useService("orm");
    },
});
```

A patched `setup` must call `super.setup(...arguments)` first or the base class never registers its own hooks, and then everything on the screen breaks in confusing ways. Hooks called here run inside the original setup window, so they work. Follow the same rules as in any `setup`: synchronous, no `await` before a hook.

### Guard by condition, not by absence

A patch applies to every form in the database. Restrict it to your model:

```javascript
patch(FormController.prototype, {
    async beforeExecuteActionButton(clickParams) {
        if (this.props.resModel === "library.loan" && clickParams.name === "action_return") {
            const confirmed = await this.libraryConfirm(); // a method you define, e.g. opening a ConfirmationDialog
            if (!confirmed) {
                return false;
            }
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});
```

Test the model, the view, or a context key first and fall through to `super` otherwise. A patch that changes behaviour for every model is almost always a bug waiting for another module to trip over.

### Patch a registry entry's value

Registry entries are often plain objects. Patch the value to change a widget definition in place:

```javascript
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const charField = registry.category("fields").get("char");
patch(charField, {
    displayName: "Text (library)",
});
```

Keep this for small tweaks. If you need a different component, register a new entry and select it with `widget="..."`, see the field widgets chapter.

## Patching templates

Markup changes use template inheritance, not `patch`. In an XML file in the same bundle as the JavaScript:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-inherit="web.FormStatusIndicator" t-inherit-mode="extension">
        <xpath expr="//div[hasclass('o_form_status_indicator_buttons')]" position="after">
            <span t-if="props.libraryHint" class="text-muted ms-2" t-out="props.libraryHint"/>
        </xpath>
    </t>
</templates>
```

- `t-inherit` names the template to extend, `t-inherit-mode="extension"` modifies it in place (every user of that template sees the change). The other mode, `primary`, creates a new template under a new `t-name` that inherits from the first and leaves the original alone; the core uses it for variants such as `web.CheckboxItem` built from `web.DropdownItem`.
- `xpath` takes `expr` and `position`: `inside` (default), `after`, `before`, `replace`, `attributes`, `move`. `hasclass('a', 'b')` is supported as in Python views. Elements can also be matched with attribute selectors such as `//button[@title='Full composer']`, as `portal` does when it removes the full-composer button from message composers.
- Inside an `attributes` position, children are `<attribute name="class" add="..." remove="..."/>` style entries, like in server views (check the existing core file you are patching for the exact form).
- The extended template must exist when the bundle loads, so list your XML after the target's addon (it follows from `depends`).

Templates are global names. An xpath that matches nothing raises an error at template compilation, which makes version drift visible. A rename of the target element in the next release is the usual cause.

## Replacing instead of patching: subclass and register

When the target is looked up in a registry, you do not need a patch at all. A subclass registered under a new key, selected only by the views that ask for it, changes one screen and nothing else:

```javascript
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";

class LoanFormController extends FormController {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
    }

    async onWillSaveRecord(record) {
        if (!record.data.book_id) {
            this.notification.add("Pick a book first", { type: "danger" });
            return false;
        }
        return super.onWillSaveRecord(...arguments);
    }
}

registry.category("views").add("library_loan_form", {
    ...formView,
    Controller: LoanFormController,
});
```

```xml
<form js_class="library_loan_form">...</form>
```

The class is subject to the usual caveats about internals, but the blast radius is one view. The customising views chapter works this out fully. Rule of thumb: **if the thing you want to change is reached through `js_class`, `widget` or an action tag, subclass. If it is not reached through any registry, patch.**

## When patching is the right tool

- The behaviour is hard-wired in a core class with no registry in front of it (the navbar, the control panel, the list renderer's cell logic when you need it for all lists).
- You are fixing a bug in a standard component for your database until the fix lands upstream.
- You are extending a class from another module that defines no registry (many `mail` models in the Discuss code).

In each case keep the patch in its own file named after what it does (`patch_form_controller.js`), small, guarded by condition, and commented with the reason and the version it was written for.

## Testing a patch

Patches are global, so tests must be able to remove them. The test helper `patchWithCleanup(obj, patchValue)` (in `@web/../tests/web_test_helpers` in Odoo 18) applies a patch for one test and restores it afterwards; use it when a test needs different behaviour of a core class. Your own production patch is tested by running the screen it touches, either in a unit test or in a tour (see the tests chapter).

## Version drift: why patches break

Patching internals ties you to the internals of that release. A concrete example from the two trees checked, `FormController` and `ListController`:

| Method | Odoo 18 | Odoo 20 |
| --- | --- | --- |
| `FormController.beforeLeave` | `async beforeLeave()` | `async beforeLeave({ forceLeave } = {})` |
| `ListController.openRecord` | `async openRecord(record, force = false)` | `async openRecord(record, { force, newWindow } = { force: false })` |
| `ListController.onDeleteSelectedRecords` | `async onDeleteSelectedRecords()` | `onDeleteSelectedRecords()` (no longer async) |

A patch of `openRecord` that does `super.openRecord(record, true)` works on 18 and silently passes the wrong argument shape on 20, where the second parameter is an options object. Patches that forward `...arguments` are tolerant to such changes; patches that rebuild the argument list are not.

Defensive habits:

- Forward `...arguments` unless you must change an argument.
- Do not rely on private names (`_foo`, `onXInternal`) or on the order of calls inside a method.
- After every upgrade, grep your `patch(` calls and diff the target methods against the new branch. The migration chapter has a checklist.
- Keep a short comment per patch: target, why, version. It saves an afternoon later.

## Pitfalls

{% hint style="warning" %}
Patching runs when its module loads. The module must be in a bundle that loads the patched module first, and it must import the target; the import is what guarantees order.
{% endhint %}

- **Patching an arrow-function property.** Fields assigned in the constructor or in `setup` (`this.handler = () => {...}`) live on the instance, so a prototype patch does not see them. Patch the method that creates them, or the code that calls them.
- **A method captured by `bind` at setup time.** Already-bound copies keep the old function for components created before the patch loaded; for new ones it is fine.
- **Forgetting `super` in `setup`.** The base hooks never register. The screen renders empty or throws on first use.
- **Not returning the value of `super`.** Callers waiting on a result get `undefined`.
- **Two modules patching the same method, one omitting `super`.** Order-dependent bugs that appear only when both modules are installed.
- **A patch for everyone.** Without a model or view guard it changes unrelated screens.
- **Patching a static `props` with the array form.** Core components in 18 use the object form.
- **Patch name argument from 16.** `patch(obj, "name", {...})` throws in 17 and later. See Versions.
- **`this._super(...)` from 16.** There is no `_super` in 17 and later: use `super`.
- **Patching to avoid registering an entry.** If the target is looked up in a registry, register a subclass.
- **Patching what you can configure.** Many behaviours are controlled by a context key, an arch attribute (`options`, `class`, `js_class`) or a field option. Look before you patch.

## Versions

{% hint style="info" %}
**16:** the signature is `patch(obj, patchName, patchValue, options)`. The name must be a string and must be unique for that object, otherwise it throws. Calling the original is done with `this._super(...)`, because the patch is not an object with a prototype chain.

**17 and 18:** `patch(objToPatch, extension)`. Passing a string as the second argument throws `Patch "<name>": Second argument is not the patch name anymore, it should be the object containing the patched properties`. Call the original with `super.method(...)`.

**20:** same `patch` implementation and semantics. Patch targets themselves moved: signatures differ (table above), and components use `props = useProps(...)` instead of `static props`, so patching a component's props schema has to follow the OWL 3 form described in the previous chapter.
{% endhint %}

## Try it

1. Patch `FormController.prototype.setup` to `console.log("form", this.props.resModel)`, reload with `?debug=assets`, open a form, and confirm the log. Remove the patch afterwards.
2. Patch `onWillSaveRecord` so a `library.loan` cannot be saved without a book. Confirm other models still save.
3. Add a second patch in another file that also overrides `onWillSaveRecord` but forgets `super`. Install both and see which behaviour wins and why.
4. Extend the `web.FormStatusIndicator` template with a hint after the buttons, using `hasclass`.

<details>

<summary>Solution notes</summary>

1. The log shows the model for every form you open, which also shows how global the patch is. Delete the file or keep the `unpatch` function in a variable if you want to remove it at runtime.
2. The model guard (`record.resModel === "library.loan"`) keeps other models unaffected, and returning `false` from `onWillSaveRecord` cancels the save.
3. The patch that loads last wins when it does not call `super`: the earlier patch and the original are never reached. Load order follows manifest and module dependency order, which is why a forgotten `super` makes behaviour depend on which modules are installed.
4. The xpath `//div[hasclass('o_form_status_indicator_buttons')]` with `position="after"` inserts the span right after the buttons container. If the class were renamed in a later version, template compilation would fail loudly.

</details>
