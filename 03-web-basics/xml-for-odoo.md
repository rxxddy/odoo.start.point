---
description: "Syntax, escaping, and the parts of XML Odoo files rely on."
---

# XML for Odoo

Almost everything an Odoo module ships besides Python and JavaScript is XML: views, menus, security groups, report templates, email templates, demo data. A single stray `&` or an unclosed tag stops module installation with a parser error that points at a line you did not write. This chapter teaches XML as a language, then shows exactly how Odoo reads a data file, so that the errors become predictable and the `eval`, `ref`, and `noupdate` attributes stop looking like magic.

## What XML is

XML is a tree of elements. Every document has exactly one root element, every element is closed, and the text between tags is data. There is no built-in meaning for any tag name: `<record>` means something only because Odoo's loader says so.

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="book_dune" model="library.book">
        <field name="name">Dune</field>
        <field name="year">1965</field>
    </record>
</odoo>
```

The pieces:

- **Declaration** `<?xml version="1.0" encoding="utf-8"?>`: optional, but Odoo files always carry it. It must be the very first thing in the file, with no blank line or space before it. If you declare an encoding, the file must actually be saved in that encoding. Use UTF-8 everywhere.
- **Element**: `<field name="year">1965</field>` has a start tag, text content, and an end tag. An element with no content can be self-closing: `<field name="year"/>`.
- **Attribute**: `name="year"`. Values are always quoted, with double or single quotes. `<field name=year>` is invalid, and so is an attribute without a value (`<button disabled>` is HTML, not XML).
- **Text**: everything between tags, including whitespace and newlines.
- **Comment**: `<!-- ... -->`. A comment cannot contain `--` and cannot nest.
- **Root**: one element wraps everything. In Odoo data files it is `<odoo>`.

### Well-formed

A document is well-formed if tags are properly nested and closed, attribute values are quoted, there is exactly one root, and special characters are escaped. A parser rejects everything else outright; XML has no "best effort" mode, unlike HTML.

```xml
<!-- Not well-formed: wrong nesting -->
<b><i>text</b></i>

<!-- Not well-formed: unclosed -->
<field name="year">1965

<!-- Not well-formed: two roots -->
<odoo/><odoo/>
```

Tag names are case-sensitive: `<Field>` and `<field>` are different elements, and the end tag must match the start tag exactly.

{% hint style="info" %}
Well-formed and valid are two different checks. Well-formed means the syntax is right. Valid means the document also follows a schema. Odoo validates view architectures against a RelaxNG schema shipped with the `base` addon, so a view can be well-formed XML and still be rejected at load time for an unknown tag or attribute.
{% endhint %}

## Escaping

Five characters are special. Two of them are always dangerous in text and attributes.

| Character | Write it as | Notes |
|-----------|-------------|-------|
| `<` | `&lt;` | Always escape in text and attribute values |
| `&` | `&amp;` | Always escape. The most common cause of load failures |
| `>` | `&gt;` | Legal raw in text, but escape it for consistency |
| `"` | `&quot;` | Required inside a double-quoted attribute |
| `'` | `&apos;` | Required inside a single-quoted attribute |

The place this bites in Odoo is domains and Python expressions that live in attributes:

```xml
<!-- Broken: raw '<' inside an attribute -->
<field name="domain">[('year', '<', 2000)]</field>   <!-- text content: also broken -->

<!-- Correct -->
<field name="domain">[('year', '&lt;', 2000)]</field>
```

The symptom is `lxml.etree.XMLSyntaxError: StartTag: invalid element name` (for a `<`) or `xmlParseEntityRef: no name` (for an `&`). The line number it reports is usually right.

The same applies to view attributes in Odoo 17 and later, where visibility is a Python-like expression:

```xml
<field name="year" invisible="year &lt; 1000 and state != 'done'"/>
```

Python's `and`/`or` need no escaping. The operators `<`, `<=`, and a bitwise `&` do.

Escaping works through numeric references too: `&#60;` is `<` and `&#x20AC;` is the euro sign. You rarely need them, because UTF-8 lets you type the character directly.

### CDATA

A CDATA section says "everything until `]]>` is literal text":

```xml
<field name="code"><![CDATA[
for rec in records:
    if rec.year < 2000 and rec.copies > 1:
        rec.flag = True
]]></field>
```

This is the readable way to embed Python or SQL that contains many `<` and `&`. Two limits: CDATA cannot contain the sequence `]]>`, and it works only in text content, never in attribute values. Odoo's server action `code` field is the typical user.

## Attributes versus text

Both carry data, with one practical difference: attribute values are normalised by the parser. Newlines and tabs inside an attribute value become spaces, so a multi-line `domain` or `invisible` expression still works, but a multi-line attribute can never carry meaningful line breaks. Put anything that needs newlines (Python code, HTML, an email body) in element text.

Text keeps whitespace as written. In Odoo most field loaders strip surrounding whitespace for simple types (`Char`, `Integer`), but not inside HTML or text content you intend to be exact. Do not rely on indentation inside text you care about; for `Text` and `Html` fields keep the content flush with the tag if the exact bytes matter.

## Namespaces

A namespace prefixes tag names so that vocabularies do not collide: `<svg:rect>` versus `<html:rect>`. A prefix is bound to a URI with `xmlns:prefix="..."`, and a default namespace with plain `xmlns="..."` applies to every unprefixed element below it.

Odoo data files and views use **no namespaces**. Elements like `<record>`, `<field>`, `<t>` and attributes like `t-if` and `t-foreach` are plain names; the `t-` prefix is a naming convention, not an XML namespace. The places you meet namespaces:

- **Inline SVG** in a QWeb template: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">...</svg>`. Without `xmlns`, the browser treats the contents as unknown HTML elements.
- **Reading other people's XML** with Python: `{http://example.org/ns}tag` is how a namespaced tag looks in ElementTree and lxml.
- **Electronic invoice formats and SOAP**: heavy namespace use. In Python you write explicit namespace maps.

```python
from lxml import etree

doc = etree.fromstring(b'<a xmlns="urn:x" xmlns:p="urn:y"><p:b/><c/></a>')
print([el.tag for el in doc.iter()])
# ['{urn:x}a', '{urn:y}b', '{urn:x}c']
print(doc.findall('{urn:y}b'))
print(doc.xpath('//x:c', namespaces={'x': 'urn:x'}))
```

Note `xpath('//c')` would find nothing: unprefixed names in XPath mean "no namespace", not "the default namespace". This is the reason people think XPath on invoice XML is broken.

## How Odoo parses a data file

Files listed in the manifest `data` or `demo` keys with the extension `.xml` go to Odoo's XML loader (`odoo/tools/convert.py`), which builds a tree with lxml and walks it element by element. It does not execute the file as a whole; it interprets each top-level element as a command.

```text
manifest 'data': ['views/book_views.xml']
   |
   v
lxml parses the file -> tree
   |
   v
for each child of <odoo> (or of <data>):
     <record>   -> create or update a database row
     <template> -> create a QWeb view row (ir.ui.view)
     <menuitem> -> create menu rows (ir.ui.menu)
     <function> -> call a model method
     <delete>   -> remove records by id or search
```

### Root and noupdate

The root element is `<odoo>`. Older files wrap their content as `<odoo><data>...</data></odoo>`, and older still, `<openerp><data>`. All forms load; the inner `<data>` is optional and only matters when you need `noupdate`:

```xml
<odoo>
    <data noupdate="1">
        <record id="seq_loan" model="ir.sequence">
            <field name="name">Loan</field>
            <field name="code">library.loan</field>
        </record>
    </data>
    <record id="book_dune" model="library.book">...</record>
</odoo>
```

`noupdate="1"` means: create the record when the module is first installed, but never overwrite it on later module updates (`-u library`). It exists for records the user is expected to edit, such as sequences, email templates, and default configuration. Records without it are overwritten from the file on every update, so a manual edit in the UI is lost. Both the `<odoo noupdate="1">` and `<data noupdate="1">` forms work. Records are marked per record in `ir.model.data`, and the flag is only applied when the record is created or updated by the loader.

### The record element

```xml
<record id="loan_demo_1" model="library.loan">
    <field name="book_id" ref="book_dune"/>
    <field name="member_id" ref="base.partner_demo"/>
    <field name="date_out" eval="(datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')"/>
    <field name="copies" eval="1"/>
    <field name="note">Reserved by phone.</field>
</record>
```

- **`model`**: the technical model name. If it does not exist at load time (the module that defines it is not in `depends`), loading fails.
- **`id`**: the XML ID suffix. Odoo stores it as `<module>.<id>` in `ir.model.data`. Without a dot, the module name is prefixed automatically. With a dot (`other_module.some_id`), you refer to or overwrite a record from another module. IDs must be unique per module.
- **`<field name="x">text</field>`**: the text is the field value. For `Char`, `Text`, `Selection` it is used as a string. For `Integer`, `Float`, `Boolean` Odoo converts the string, but it is cleaner to use `eval`.
- **`ref="xml_id"`**: resolves an XML ID to a database ID. Use it for `Many2one`.
- **`eval="python expr"`**: evaluates a Python expression and uses the result.
- **`search="[domain]"`**: finds the record(s) by domain, used for rare cases when no XML ID exists.
- **`type="xml"`** or **`type="html"`**: the element's children are the value, serialised back to a string. This is how a view's `arch` is stored.
- **`file="path"` with `type="base64"`**: reads a file relative to the module and stores it base64-encoded, as for an image.

### `eval` in detail

`eval` is a Python expression, not a statement, evaluated with a restricted set of names in scope. The set includes `ref` (a function returning a database ID from an XML ID), `time`, `datetime`, `timedelta`, `relativedelta`, and a few more. Treat anything beyond `ref`, `datetime`, `timedelta`, and `time` as unavailable until you have checked your version's `convert.py`.

```xml
<!-- Boolean, integer, float: eval keeps the type -->
<field name="active" eval="False"/>
<field name="copies" eval="3"/>
<field name="price" eval="12.5"/>

<!-- A Many2one as an id -->
<field name="member_id" eval="ref('base.partner_demo')"/>

<!-- Many2many and One2many: list of command tuples -->
<field name="tag_ids" eval="[(6, 0, [ref('tag_fiction'), ref('tag_classic')])]"/>
<field name="line_ids" eval="[(0, 0, {'name': 'Line 1', 'qty': 2})]"/>
```

The command tuples are `(0, 0, vals)` create, `(1, id, vals)` update, `(2, id)` delete, `(3, id)` unlink, `(4, id)` link, `(5,)` unlink all, and `(6, 0, ids)` replace. In Python code you can also use `Command.create(...)`; in XML data the tuples are the portable form.

A frequent mistake is putting a bare number or word without `eval`: `<field name="active">False</field>` stores a string, and whether the loader converts it to a boolean depends on the version. Use `eval="False"` and the question never arises.

`ref` as an attribute versus `ref()` in `eval` is the same lookup. Prefer the attribute; use the function when you build a list or dictionary.

### Dates and times in data

Fixed dates are plain text in ISO format: `<field name="date_out">2025-03-01</field>` and `2025-03-01 14:30:00` for datetimes. For demo data that should always look recent, compute from `datetime`:

```xml
<field name="date_out" eval="(DateTime.today() - relativedelta(days=2)).strftime('%Y-%m-%d')"/>
```

`DateTime` and `relativedelta` are available in the eval context in standard data files. If you are not sure in your version, `datetime.now()` and `timedelta` are the safe pair.

### Views as records

A view is a record of `ir.ui.view` whose `arch` field contains the view XML:

```xml
<record id="library_book_view_form" model="ir.ui.view">
    <field name="name">library.book.form</field>
    <field name="model">library.book</field>
    <field name="arch" type="xml">
        <form string="Book">
            <sheet>
                <group>
                    <field name="name"/>
                    <field name="year"/>
                </group>
            </sheet>
        </form>
    </field>
</record>
```

`type="xml"` is what tells the loader to serialise the child elements into the `arch` text. When the view is read, the server parses `arch` again, validates it against the schema, and applies inheritance. Form, list, and search structure are covered in the data and views part; here the point is that the file you write is a record wrapper around an XML document, so two parsers are involved: the file parser at install time and the view parser at read time.

### Template shortcut

QWeb templates have shorthand: `<template>` is expanded to an `ir.ui.view` record with `type="qweb"`.

```xml
<template id="report_book_card">
    <t t-call="web.html_container">
        <t t-foreach="docs" t-as="o">
            <div class="page">
                <h2 t-out="o.name"/>
            </div>
        </t>
    </t>
</template>
```

Attributes of `<template>` include `id`, `name`, `inherit_id`, `priority`, `active`, `customize_show`, and `t-name`-less operation: the id becomes the template's name. The body of `<template>` is the template content, so any `<`, `&` in expressions needs escaping exactly as above: `t-if="o.year &lt; 2000"`.

{% hint style="info" %}
Versions: `t-esc` and `t-raw` were the output directives up to 14. From 15 onward `t-out` is the output directive and `t-esc`/`t-raw` are deprecated aliases that still work in many versions. Write `t-out` in new code. The template and QWeb chapters cover the distinction.
{% endhint %}

### Menus

`<menuitem>` is shorthand for creating `ir.ui.menu` rows:

```xml
<menuitem id="menu_library_root" name="Library" sequence="30"/>
<menuitem id="menu_library_books" name="Books"
          parent="menu_library_root" action="action_library_book" sequence="10"/>
```

Omitting `parent` makes a top-level app entry. Menu structure follows from `parent` XML IDs, and `groups` restricts visibility.

### function, delete

```xml
<function model="library.book" name="_demo_populate"/>
<delete model="ir.ui.view" search="[('name', '=', 'library.book.legacy')]"/>
```

`<function>` calls a model method (by name, on the model, with no records unless you pass ids). Because `<function>` runs on every load of the file, the method must be idempotent. `<delete>` removes by `id` or by `search` and appears mostly in migration-style cleanup.

## Inheritance in XML

Extending someone else's view is XML-level editing: the new record names its parent and describes edits as XPath operations.

```xml
<record id="library_book_view_form_inherit" model="ir.ui.view">
    <field name="name">library.book.form.inherit</field>
    <field name="model">library.book</field>
    <field name="inherit_id" ref="library.library_book_view_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='year']" position="after">
            <field name="isbn"/>
        </xpath>
    </field>
</record>
```

`expr` is an XPath 1.0 expression evaluated against the parent arch. The mechanics (positions, `attributes`, priorities, and why a broad XPath breaks on update) have a chapter of their own; the syntax you need here is XPath's: `//` any depth, `[@name='x']` attribute test, `[1]` first match, `..` parent.

You can try XPath outside Odoo to learn it:

```python
from lxml import etree
arch = etree.fromstring("""
<form><sheet><group>
  <field name="name"/><field name="year"/>
</group></sheet></form>""")
print(arch.xpath("//field[@name='year']"))      # one element
print(arch.xpath("//group/field[1]/@name"))     # ['name']
print(arch.xpath("//field[@name='missing']"))   # [] -> in Odoo this raises at view-combine time
```

## Checking a file before you start the server

Starting Odoo to find a typo costs a minute. Check well-formedness first:

```bash
# libxml2 tools (Linux, macOS; Windows via WSL or a package)
xmllint --noout library/views/book_views.xml

# No xmllint? Python is already installed
python -c "import sys, lxml.etree as e; e.parse(sys.argv[1]); print('ok')" library/views/book_views.xml
```

Both report the line and column of the first error. This catches syntax only; unknown fields in a view, bad XML IDs, and schema errors surface when Odoo loads the file. Running the module with a throwaway database speeds that cycle:

```bash
odoo-bin -d scratch -i library --stop-after-init
```

## A mental checklist for a failing data file

1. Is the parse error `XMLSyntaxError`? It is a syntax problem: escaping, unclosed tag, or a character before the XML declaration. Look at the reported line.
2. Is the error `ValueError: External ID not found in the system: module.name`? A `ref` points at a record that does not exist yet. Check the file order in the manifest (a file can only reference records created by files earlier in the list or by modules in `depends`) and the module prefix.
3. Is the error `Invalid field 'x' on model 'y'` in a view? The field name is wrong, or the field belongs to a module not in `depends`.
4. Did the record load but not change after `-u`? It is under `noupdate`, or an XML ID with a different prefix created a second record.
5. Did the whole view vanish? It may be `active=False`, or an inheriting view failed and was skipped in a way you did not see; read the server log from top.

## Pitfalls

- **Unescaped `<` and `&`** in domains, `eval`, `t-if`, and `invisible`. Always `&lt;` and `&amp;`. A text editor with XML syntax highlighting makes the mistake visible.
- **Text before the XML declaration** (BOM aside): a blank first line causes `XML or text declaration not at start of entity`.
- **`noupdate` surprises.** You change a record in the XML, upgrade, and nothing happens. Either the record is in a `noupdate` block, or someone edited it manually and the loader respects that for `noupdate` records only. Check `ir.model.data.noupdate` for the XML ID. The inverse also hurts: a QWeb template you wanted users to customise gets overwritten on every update.
- **Wrong file order in the manifest.** Security files first, then data that other files reference, then views, then menus and actions that reference views. A menu that references an action defined in a later file fails.
- **Same `id` in two files of one module.** The second silently becomes an update of the first. Use a naming scheme such as `<model>_view_<type>` so collisions are visible.
- **Whitespace-sensitive content.** An `Html` field or a `Text` field with newlines picks up your indentation. Put it flush-left, or strip it in code.
- **Boolean and number as text.** `<field name="active">False</field>` is a string. Use `eval`.
- **Putting `<` in CDATA inside an attribute.** CDATA works only in text nodes.
- **Tabs and mixed encodings.** A file saved as Latin-1 with an `encoding="utf-8"` declaration fails on the first accented character, usually in a translated string.
- **Assuming the data file is run like a script.** Records are created in document order, but a `<function>` earlier in the file runs when the loader reaches it, before records below it exist.

## Try it

**1. Find the errors.** This file fails to load. List every problem.

```xml
 <?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="book_a" model="library.book">
        <field name="name">Rock & Roll</field>
        <field name="year">1999
        <field name="active">False</field>
    </record>
    <record id=book_b model="library.book"/>
</odoo>
```

<details>
<summary>Solution</summary>

1. A space before `<?xml`: the declaration must be the first bytes of the file.
2. `Rock & Roll`: raw `&`, write `Rock &amp; Roll`.
3. `<field name="year">1999` is never closed (`</field>` missing), so the following `<field>` nests inside it and the tags no longer match.
4. `id=book_b` is missing quotes around the value.
5. Not a syntax error but wrong: `<field name="active">False</field>` stores the string; use `eval="False"`.

Check with `xmllint --noout file.xml`; it reports problems one at a time, so fix and rerun.
</details>

**2. Write a record with relations.** Write a `library.loan` record whose `book_id` points to the XML ID `book_dune` and whose `tag_ids` (Many2many to `library.tag`) links two records with XML IDs `tag_fiction` and `tag_classic`, and whose `date_out` is three days ago.

<details>
<summary>Solution</summary>

```xml
<record id="loan_demo_1" model="library.loan">
    <field name="book_id" ref="book_dune"/>
    <field name="tag_ids" eval="[(6, 0, [ref('tag_fiction'), ref('tag_classic')])]"/>
    <field name="date_out" eval="(datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')"/>
</record>
```

`ref` as an attribute works for the `Many2one`; the `Many2many` needs a command list in `eval`. The `(6, 0, ids)` command replaces the whole set.
</details>

**3. Escape a domain.** A window action needs the domain "year before 2000 and copies at least 2". Write it as a `<field name="domain">` of a `ir.actions.act_window` record.

<details>
<summary>Solution</summary>

```xml
<field name="domain">[('year', '&lt;', 2000), ('copies', '&gt;=', 2)]</field>
```

`&lt;` is required. `&gt;` is legal raw, but keeping both escaped makes the pattern uniform.
</details>

**4. Namespaces.** Parse `<root xmlns="urn:a"><item>1</item><item>2</item></root>` in Python and print the text of both items.

<details>
<summary>Solution</summary>

```python
from lxml import etree
root = etree.fromstring(b'<root xmlns="urn:a"><item>1</item><item>2</item></root>')
print([e.text for e in root.xpath('//a:item', namespaces={'a': 'urn:a'})])
# ['1', '2']
```

`root.xpath('//item')` returns an empty list because unprefixed XPath names mean "no namespace". Bind a prefix, or use `{urn:a}item` with `findall`.
</details>

**5. Update behaviour.** You mark `<data noupdate="1">` around an email template, install the module, edit the template body in the UI, change the body in the XML, and run `-u library`. What does the UI show, and how do you force the XML version?

<details>
<summary>Solution</summary>

The UI keeps the edited body, because the loader skips updating `noupdate` records. To force the XML version, delete the record (or its `ir.model.data` row so the record is recreated), or temporarily remove the `noupdate` flag and update; do this on a copy of the database first, because the manual edits are lost.
</details>
