---
description: QWeb directives, t-call, t-set, and escaping.
---

# QWeb templates

QWeb is Odoo's XML template engine. The same directive language renders website pages, PDF reports, emails (in part), and, with a JavaScript implementation, the OWL components of the web client. This chapter is about the server side, where templates are `ir.ui.view` records of type `qweb` evaluated by Python.

## Defining a template

```xml
<template id="book_card" name="Book card">
  <div class="card">
    <h3 t-out="book.name"/>
    <p t-if="book.author_id">By <span t-field="book.author_id"/></p>
    <p t-else="">Anonymous</p>
    <ul>
      <li t-foreach="book.loan_ids" t-as="loan">
        <t t-out="loan_index + 1"/>. <t t-out="loan.borrower_id.name"/>
        <t t-if="loan_last"> (latest)</t>
      </li>
    </ul>
  </div>
</template>
```

`<template>` is shorthand for an `ir.ui.view` with `type="qweb"`; `id` becomes the XML ID.

## Directives you use daily

- `t-out="expr"`: output an escaped value (the successor of `t-esc`/`t-raw`). `False` and `None` render as empty. Markup objects are not escaped again.
- `t-field="record.field"`: render a field using its formatting (dates, monetary values, many2one names). Accepts `t-options='{"widget": "monetary"}'`. Only works on records, not plain values.
- `t-if`, `t-elif`, `t-else`: conditions. Python expressions.
- `t-foreach` / `t-as`: loops. Helpers `x_index`, `x_first`, `x_last`, `x_size`, `x_even`, `x_odd` are available per alias.
- `t-set` / `t-value`: assign a variable; `t-set` with a body captures markup. Variables are scoped to the enclosing element.
- `t-att-name="expr"`, `t-attf-name="text #{expr}"`, `t-att="dict"`: dynamic attributes.
- `t-call="module.template"`: include another template; the body of `t-call` becomes `0` (the "slot"), output with `<t t-out="0"/>`.
- `t-set-slot`, `t-slot` and `t-inherit`: used for newer slot mechanisms and inheritance; stick to `t-call` plus `t-out="0"` unless you know why.

```xml
<template id="layout_box">
  <div class="box"><t t-out="0"/></div>
</template>
<template id="book_page">
  <t t-call="library.layout_box">
    <t t-set="title">Books</t>
    <p t-out="title"/>
  </t>
</template>
```

## Evaluation context

In website and report templates the context includes `request`, `user_id`, `res_company`, `website`, `json`, `time`, `datetime`, `len`, `abs`, `min`, `max`, and the values passed by the caller. Rendering from Python:

```python
html = self.env["ir.qweb"]._render("library.book_card", {"book": book})
```

This returns `Markup`. Pass only trusted values in as markup; everything else is escaped.

## Escaping and safety

QWeb escapes on output by default, so `t-out` of user text is safe in HTML. The unsafe cases are building markup yourself in Python and passing it as a plain string (it will be escaped and look broken) or wrapping untrusted text in `Markup()` (it will be injected). Use `Markup.format()` or `markupsafe.escape` when composing.

Templates run in a restricted evaluator: no imports, no `__` attribute access, no arbitrary builtins. Computation belongs in the model; the template displays.

## Inheritance

QWeb views inherit like other views, with xpath, covered in the next chapter on view inheritance:

```xml
<template id="book_card_extra" inherit_id="library.book_card">
  <xpath expr="//h3" position="after"><small t-out="book.isbn"/></xpath>
</template>
```

For website pages, `customize_show="True"` and `active="False"` make optional templates togglable from the editor.

## Pitfalls

- `t-esc` and `t-raw` are deprecated in favour of `t-out` (the Odoo 18 `ir_qweb.py` documents both as "Deprecated, please use `t-out`" and still compiles them). `t-raw` in particular was an XSS source; replace it.
- A `t-foreach` over a recordset inside another over the same alias: inner variables shadow the outer.
- `t-field` on a related path that is empty returns blank; on a `False` boolean it prints nothing useful. Use `t-out` with your own text.
- Queries inside templates: each `loan.borrower_id.name` can hit the database. Prefetch in the model, pass a prepared structure.
- Forgetting that `t-set` inside a loop does not leak outside; use an accumulator on the model side.

## Versions

{% hint style="info" %}
`t-raw` and `t-esc` are deprecated in favour of `t-out`; Odoo 18 still accepts both (verified in `ir_qweb.py`), so old templates keep rendering, but write new ones with `t-out`. Report templates since 17 render through `ir.qweb` with `web.external_layout`, and 18 relies on the OWL-compatible attribute handling for `t-att`.
{% endhint %}

## Try it

Render a template from the shell of a development database:

```python
print(env["ir.qweb"]._render("library.book_card", {"book": env["library.book"].search([], limit=1)}))
```
