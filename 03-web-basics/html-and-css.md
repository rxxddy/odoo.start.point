---
description: "Only the subset that matters for views, reports, and portals."
---

# HTML and CSS you need

You do not need to be a front-end designer to build Odoo modules, but you do need enough HTML and CSS to read a QWeb template, lay out a PDF report so it does not split a table row across pages, and make a portal page look like it belongs on the site. This chapter covers the subset that repeatedly shows up: document structure, the box model, selectors and specificity, flexbox, the Bootstrap grid and utilities that Odoo ships, and print CSS for the wkhtmltopdf engine behind PDF reports.

Everything here is plain web technology. Odoo specifics are limited to class names and behaviours I name explicitly; for anything version-sensitive there is a hint.

## HTML in five minutes

HTML is a tree of elements like XML, but with a forgiving parser and a fixed vocabulary.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Book card</title>
  <style>
    .card { border: 1px solid #ccc; padding: 12px; }
  </style>
</head>
<body>
  <article class="card">
    <h2>Dune</h2>
    <p>Published <time datetime="1965">1965</time>.</p>
    <ul>
      <li>Frank Herbert</li>
      <li>Science fiction</li>
    </ul>
  </article>
</body>
</html>
```

Save it as `card.html` and open it in a browser; it is the fastest way to try any snippet in this chapter.

Elements fall into two groups by default layout:

- **Block** elements (`div`, `p`, `h1`-`h6`, `ul`, `table`, `section`, `form`) start on a new line and stretch to the width of their container.
- **Inline** elements (`span`, `a`, `strong`, `em`, `img`, `code`) flow within a line of text. Width and height do not apply to a plain inline element.

The semantic elements you will meet in Odoo templates:

| Element | Use |
|---------|-----|
| `div`, `span` | Generic block and inline containers |
| `h1`...`h6` | Headings; one `h1` per page |
| `p`, `ul`, `ol`, `li` | Paragraphs and lists |
| `table`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td` | Tabular data. Reports are mostly tables |
| `a href` | Links |
| `img src alt` | Images; always provide `alt` |
| `form`, `input`, `label`, `button`, `select`, `textarea` | Forms on website and portal pages |
| `section`, `article`, `header`, `footer`, `nav` | Structure for portal and website pages |

Attributes worth knowing: `class` (a space-separated list of CSS classes), `id` (unique per page), `style` (inline CSS), `data-*` (custom data, read in JavaScript through `element.dataset`), and `aria-*` / `role` for accessibility.

### HTML versus XML

QWeb templates are XML files that produce HTML, so they must be well-formed XML even though the output is HTML. In templates:

- Every tag is closed. Write `<br/>`, `<img src="..." alt=""/>`, `<input type="text"/>`, never `<br>`.
- Attributes are always quoted and always have a value. Use `<input disabled="disabled"/>` instead of `<input disabled>`.
- Raw `<` and `&` in text must be escaped (see the XML chapter).

The browser sees the output of the template, so the output is HTML. But the file you author is XML.

## The box model

Every element is a rectangle with four layers, from the inside out: content, padding, border, margin.

```css
.box {
  width: 200px;
  padding: 10px;
  border: 2px solid #333;
  margin: 20px;
}
```

By default (`box-sizing: content-box`), `width: 200px` is the content width; the rendered box is 200 + 2*10 + 2*2 = 224px wide. With `box-sizing: border-box`, `width` includes padding and border and the box is 200px wide. Bootstrap, which Odoo uses, sets `border-box` globally, so inside Odoo pages widths behave the way you expect. In a standalone test file, add `* { box-sizing: border-box; }`.

Vertical margins between block siblings collapse: two stacked blocks with `margin-bottom: 20px` and `margin-top: 30px` are 30px apart, not 50px. Margins do not collapse inside flex containers.

Units you will use:

| Unit | Meaning | Where |
|------|---------|-------|
| `px` | CSS pixel | Screens |
| `rem` | Multiple of the root font size | Spacing and type in portal pages |
| `%` | Percentage of the parent | Widths |
| `mm`, `cm`, `pt` | Physical units | PDF reports |
| `vw`, `vh` | Percent of the viewport | Full-screen layouts; not useful in PDFs |

## Selectors, the cascade, and specificity

A rule is `selector { property: value; }`. Common selectors:

```css
p              /* all p elements */
.note          /* elements with class="note" */
#total         /* the element with id="total" */
table.items td /* td inside a table having class "items" */
ul > li        /* direct children only */
h2 + p         /* p right after an h2 */
a[href^="http"]/* attribute starts with */
li:first-child /* pseudo-classes */
li:nth-child(even)
p::first-line  /* pseudo-elements */
```

When several rules target one element and set the same property, the winner is chosen by:

1. Importance (`!important` wins; avoid it).
2. Specificity: inline `style` beats an id selector, which beats class/attribute/pseudo-class selectors, which beat element selectors. `#a .b` beats `.a .b .c`. Each level is counted separately; ten classes never beat one id.
3. Order: for equal specificity, the later rule wins.

```css
p { color: black; }          /* specificity 0,0,1 */
.note { color: gray; }       /* 0,1,0 wins over p */
article .note { color: red; }/* 0,1,1 wins over .note */
```

Inherited properties (`color`, `font-*`, `line-height`, `text-align`) flow down to children; box properties (`margin`, `padding`, `border`, `background`) do not.

In Odoo you almost never fight specificity by hand. Add your own class prefixed with your module (for example `o_library_card`) and write a selector one level more specific than the rule you override. If you reach for `!important`, you have usually picked the wrong selector.

## Flexbox

Flexbox lays children out along one axis. The container sets the rules:

```html
<style>
  .row-demo { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
  .row-demo > .grow { flex: 1 1 auto; }
</style>
<div class="row-demo">
  <span>Dune</span>
  <span class="grow">1965</span>
  <button>Open</button>
</div>
```

The properties that cover 90% of cases:

| Property | Where | Effect |
|----------|-------|--------|
| `display: flex` | container | Children become flex items |
| `flex-direction: row \| column` | container | Main axis; `row` is the default |
| `justify-content` | container | Distribution along the main axis (`flex-start`, `center`, `space-between`, `flex-end`) |
| `align-items` | container | Alignment across the cross axis (`stretch` default, `center`, `flex-start`) |
| `flex-wrap: wrap` | container | Allow items to wrap onto new lines |
| `gap` | container | Space between items |
| `flex: grow shrink basis` | item | `flex: 1` means "share leftover space equally" |
| `margin-left: auto` | item | Pushes the item (and followers) to the far end |

A common point of confusion: `justify-content` is main axis, `align-items` is cross axis. When you switch `flex-direction` to `column`, they swap geometric directions.

CSS Grid exists for two-dimensional layouts, but Odoo's own CSS and the Bootstrap grid do not require it, and PDF rendering does not support it at all (see below). Learn flexbox first.

## Bootstrap as Odoo uses it

Odoo's backend and website both build on Bootstrap. The website and the QWeb reports rely on its grid, spacing, and utility classes directly, so you write them in your templates.

{% hint style="info" %}
Versions: Odoo 16 and later use Bootstrap 5; Odoo 15 and earlier use Bootstrap 4. Several utility names changed between the two. Where it matters below, both are listed. Check your version's bundled Bootstrap before copying a snippet from the web, because the wrong generation silently does nothing.
{% endhint %}

### The grid

A row has 12 columns. Columns declare their span at a breakpoint and up.

```html
<div class="container">
  <div class="row">
    <div class="col-12 col-md-8">Main content</div>
    <div class="col-12 col-md-4">Sidebar</div>
  </div>
</div>
```

- `container` centres content with a maximum width (`container-fluid` uses the full width).
- `row` is a flex container with negative side margins that offset the column gutters.
- `col-N` takes N of 12 columns at all widths; `col-md-N` applies from the `md` breakpoint (768px) upward. Below that the column stacks to full width if `col-12` or nothing is set.
- The breakpoints are `sm` 576, `md` 768, `lg` 992, `xl` 1200, `xxl` 1400 (in Bootstrap 5).
- `col` alone shares remaining width equally; `col-auto` sizes to content.
- `offset-md-2` adds two columns of left space (same name in Bootstrap 4 and 5).
- Columns must be direct children of a `row`, and rows go inside a `container` or a column.

Bootstrap's grid is mobile-first: unprefixed rules apply everywhere, and each larger breakpoint overrides upward. Design the narrow layout first.

### Utility classes

Utilities are single-purpose classes. Learn these and you rarely need custom CSS:

```html
<!-- Spacing: m = margin, p = padding; t/b/s/e/x/y sides; 0-5 scale -->
<div class="mt-3 mb-2 px-4 py-2">...</div>

<!-- Flex helpers -->
<div class="d-flex justify-content-between align-items-center gap-2">
  <span class="fw-bold">Dune</span>
  <span class="text-muted">1965</span>
</div>

<!-- Text -->
<p class="text-center text-uppercase small">...</p>
<span class="text-end">right aligned in BS5</span>

<!-- Display and visibility -->
<div class="d-none d-md-block">Hidden on phones</div>

<!-- Tables -->
<table class="table table-sm table-bordered">...</table>
```

Names that differ between Bootstrap 4 and 5:

| Purpose | BS 4 (Odoo 15 and earlier) | BS 5 (Odoo 16+) |
|---------|----------------------------|-----------------|
| Margin left / right | `ml-2`, `mr-2` | `ms-2`, `me-2` |
| Padding left / right | `pl-2`, `pr-2` | `ps-2`, `pe-2` |
| Text align right / left | `text-right`, `text-left` | `text-end`, `text-start` |
| Float | `float-left` | `float-start` |
| Font weight | `font-weight-bold` | `fw-bold` |
| Gap between flex items | not available | `gap-2` |
| Badge colours | `badge badge-primary` | `badge text-bg-primary` or `badge bg-primary` |

If a spacing class has no visible effect, the generation mismatch is the first suspect.

### Colours and components in views

Contextual colour classes (`text-success`, `text-danger`, `bg-light`, `alert alert-warning`, `btn btn-primary`, `badge`) are the supported way to colour text and boxes. They follow the database's theme, which a custom hex colour does not.

Odoo's own widgets use classes beginning with `o_` (for example `o_form_view`, `o_list_view`). Treat these as internal: reading them in the browser inspector to find a hook is fine, but depending on one in module CSS ties you to a particular release. Prefer your own class on your own element.

## Where CSS lives in a module

CSS and SCSS files ship under `static/src` and are registered in the manifest `assets` key (assets are covered in the frontend part). For a quick edit in a QWeb template or a report you can use an inline `style` attribute, which also guarantees the rule reaches wkhtmltopdf. Inline styles have the highest specificity, so use them for report-only tweaks and keep reusable styles in a stylesheet.

## QWeb reports and wkhtmltopdf

A PDF report is not a page-sized screenshot. Odoo renders your QWeb template to HTML, then passes it to the wkhtmltopdf program, which uses an old fork of the WebKit engine to paginate it. That engine is years behind a modern browser, and it explains most report layout bugs.

What you can count on:

- Tables, floats, block layout, `position: absolute`, and fixed-width layouts work.
- Bootstrap's grid works in reports, because Odoo's report layouts load Bootstrap, but the engine's flexbox implementation is partial and prefixed. Rows and columns generally render; elaborate flex layouts (nested flex, `gap`, `flex-wrap` with many items) do not render reliably.
- CSS Grid does not work.
- CSS custom properties (`var(--x)`) do not work.
- `@media print` rules apply; wkhtmltopdf emulates print media by default.

Rule of thumb for reports: use tables for tabular content and Bootstrap rows of a few `col-N` columns for the header and totals; test in the real PDF, not in the browser preview.

{% hint style="warning" %}
The HTML preview of a report (the `?debug` or `report/html/...` route) is rendered by the browser with modern CSS. It looks right when the PDF does not. Always judge a layout from the PDF.
{% endhint %}

### Print CSS essentials

```css
/* Keep a table row together */
tr, .no-break { page-break-inside: avoid; }

/* Repeat the table header on every page */
thead { display: table-header-group; }
tfoot { display: table-footer-group; }

/* Force a page break before each section */
.new-page { page-break-before: always; }

/* Keep a heading with the content after it */
h2, h3 { page-break-after: avoid; }

/* Physical units for margins inside the page */
.signature { margin-top: 15mm; width: 60mm; border-top: 1px solid #000; }
```

`page-break-inside: avoid` on a `div` containing a long table is ignored when the table is longer than a page; apply it to rows or to small blocks, not to large containers. In PDF reports, page breaks inside tables are the most common source of ugly output: a total row orphaned alone at the top of a new page. Wrapping the totals in a block with `page-break-inside: avoid` and placing it after the table helps.

An example report fragment for a library loan sheet:

```xml
<template id="report_loan_sheet_document">
    <t t-call="web.external_layout">
        <div class="page">
            <h2>Loan <span t-field="o.name"/></h2>
            <div class="row mb-3">
                <div class="col-6">
                    <strong>Member</strong>
                    <div t-field="o.member_id"/>
                </div>
                <div class="col-6 text-end">
                    <strong>Date out</strong>
                    <div t-field="o.date_out"/>
                </div>
            </div>
            <table class="table table-sm">
                <thead>
                    <tr><th>Book</th><th class="text-end">Copies</th></tr>
                </thead>
                <tbody>
                    <tr t-foreach="o.line_ids" t-as="line" style="page-break-inside: avoid;">
                        <td><span t-field="line.book_id"/></td>
                        <td class="text-end"><span t-field="line.copies"/></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </t>
</template>
```

The `t-call`, `t-foreach`, and `t-field` directives are explained in the QWeb and PDF reports chapters. For layout, note: `div.page` is the content wrapper, the `row`/`col-6` pair is plain Bootstrap, and the row-level `style` attribute keeps each line unbroken. `text-end` is the Bootstrap 5 name; use `text-right` in versions with Bootstrap 4.

### Fonts, colours, images in PDFs

- Fonts must be installed on the machine that runs wkhtmltopdf, or loaded from a path it can read. A missing font silently falls back to a default and changes the layout. Stick to the fonts the report layout already uses unless you control the server.
- Background colours on table cells and rows normally print; background images are less reliable. Check the actual PDF.
- Images: give an explicit `width` or `max-width`. An unconstrained image taller than a page breaks pagination. Use `t-att-src` with `image_data_uri(...)` for binary fields in reports, and always include `alt`.
- Wide tables: wkhtmltopdf will not shrink content to fit; a table wider than the page is cut off. Set `table-layout: fixed`, give column widths in `%`, and use `word-wrap: break-word`.

## Portal and website pages

Portal and website templates render inside Odoo's website layout, which already loads Bootstrap, so the grid and utilities work as in any Bootstrap page. The structure you will write most often:

```xml
<template id="portal_my_loans" name="My loans">
    <t t-call="portal.portal_layout">
        <div class="o_portal_my_loans">
            <t t-if="not loans">
                <p class="alert alert-info">No loans yet.</p>
            </t>
            <div t-else="" class="table-responsive">
                <table class="table table-hover">
                    <tbody>
                        <tr t-foreach="loans" t-as="loan">
                            <td><a t-attf-href="/my/loans/#{loan.id}" t-out="loan.name"/></td>
                            <td class="text-end"><span t-field="loan.date_out"/></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </t>
</template>
```

A few points that apply regardless of version:

- Wrap wide tables in `table-responsive` so phones can scroll them sideways.
- A portal page is viewed on a phone more often than you expect. Test at 375px wide with the browser's responsive mode.
- Forms posted to Odoo controllers need a CSRF token; the controller chapter covers it. In a form the hidden input is `<input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>`.
- Link and button text should be real text, not images, so translations pick them up.
- Avoid `id` attributes derived from record ids unless you need them; duplicated ids make anchors and label `for=` links misbehave.

## Debugging CSS

1. Right-click the element, Inspect. The Styles pane lists the winning rules and the crossed-out losers.
2. The Computed tab shows the final value of every property, which ends most "why is my padding ignored" questions.
3. Toggle a rule off with its checkbox to see which one is responsible.
4. For reports, produce the PDF and view it; the browser preview misleads. Download a sample PDF, then change one thing at a time.
5. To see the HTML wkhtmltopdf received, open the report's HTML route in the browser with developer mode, and inspect what Odoo produced.

## Pitfalls

- **Treating the browser preview as the PDF.** Different engines. Final judgement is always from the PDF.
- **Flexbox and grid in reports.** Partial or absent in wkhtmltopdf. Use tables and Bootstrap rows of simple columns.
- **Bootstrap generation mismatch.** `ml-2` on Odoo 16+ does nothing; `ms-2` on Odoo 15 does nothing.
- **`position: fixed` footers in reports** repeat in unpredictable ways. Use the layout's footer facility.
- **Row-breaking.** Without `page-break-inside: avoid`, a single row may split between two pages.
- **Overriding with `!important`.** It wins today and makes the next override impossible. Write a more specific selector.
- **Depending on Odoo's internal `o_` classes.** They change between releases; add your own class.
- **Unclosed tags in templates.** `<br>` is valid HTML and a fatal XML error in a QWeb file.
- **Units.** Pixels in a PDF depend on the engine's DPI assumptions. Use `mm` and `pt` for anything that must be sized physically.
- **Big images.** A 4000px photo inside a report makes the PDF huge and slow to generate. Resize in code.

## Try it

**1. Box model.** An element has `width: 300px; padding: 20px; border: 5px solid;`. How wide is it on screen with `content-box`, and with `border-box`?

<details>
<summary>Solution</summary>

`content-box`: 300 + 2*20 + 2*5 = 350px. `border-box`: 300px, because the width includes padding and border and the content shrinks to 250px.
</details>

**2. Header row.** Write HTML using Bootstrap utilities (no custom CSS) for a row where the title "Loans" is left and a button "New" is right, vertically centred.

<details>
<summary>Solution</summary>

```html
<div class="d-flex justify-content-between align-items-center">
  <h2 class="mb-0">Loans</h2>
  <a class="btn btn-primary" href="/my/loans/new">New</a>
</div>
```

`d-flex` makes it a flex container, `justify-content-between` pushes the two items to opposite ends, `align-items-center` centres them across the cross axis, `mb-0` removes the heading's default bottom margin so the centring looks right.
</details>

**3. Responsive columns.** Make a two-column layout (8/4) that stacks on phones. Then change it so the sidebar is hidden on phones.

<details>
<summary>Solution</summary>

```html
<div class="row">
  <div class="col-12 col-md-8">Main</div>
  <div class="col-12 col-md-4 d-none d-md-block">Sidebar</div>
</div>
```

Below `md` both columns are `col-12`; `d-none d-md-block` hides the sidebar until `md` and then displays it as a block.
</details>

**4. Report table.** Write CSS that repeats a table header on every page, never splits a row, and keeps a `div.totals` block together.

<details>
<summary>Solution</summary>

```css
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
.totals { page-break-inside: avoid; }
```

Test it with a table of 100 rows in a real PDF. The `thead` rule is what makes the header repeat; some engines already do it by default, wkhtmltopdf is more reliable when you state it.
</details>

**5. Specificity.** Given `.note { color: gray }`, `p.note { color: blue }`, `#x { color: red }`, and `<p id="x" class="note" style="color: green">`, what colour is the text, and what if the inline style is removed?

<details>
<summary>Solution</summary>

Green: the inline style beats everything without `!important`. Without it, red: the id selector (specificity 1,0,0 in id, class, element order) outranks `p.note` (0,1,1) and `.note` (0,1,0).
</details>
