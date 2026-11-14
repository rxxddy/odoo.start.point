---
description: "Numbering, ir.sequence, and translatable fields."
---

# Sequences and translations

Two unrelated topics that every model with a user-facing reference eventually meets: generating document numbers, and making text show up in the user's language.

## ir.sequence

A sequence is a configurable number generator stored in `ir.sequence`. Define one in data:

```xml
<odoo>
    <data noupdate="1">
        <record id="seq_library_loan" model="ir.sequence">
            <field name="name">Loan</field>
            <field name="code">library.loan</field>
            <field name="prefix">LN/%(year)s/</field>
            <field name="padding">5</field>
            <field name="company_id" eval="False"/>
        </record>
    </data>
</odoo>
```

Use it in `create`:

```python
@api.model_create_multi
def create(self, vals_list):
    for vals in vals_list:
        if not vals.get('name') or vals['name'] == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('library.loan') or '/'
    return super().create(vals_list)
```

`next_by_code(sequence_code)` picks the sequence by `code`, preferring one of the current company and falling back to one with no company. It returns `False` when none matches, hence the `or '/'`. `next_by_id()` on a sequence record takes no code.

Prefix and suffix support interpolation: `%(year)s`, `%(month)s`, `%(day)s`, `%(y)s`, and the `range_*` variants for date ranges. Enable `use_date_range` for yearly or monthly resets: each range keeps its own counter.

### Standard and no-gap

The `implementation` field has two values (`odoo/addons/base/models/ir_sequence.py`):

- `standard`: backed by a PostgreSQL sequence. Fast, never blocks, and never rolls back. A failed transaction burns a number.
- `no_gap`: a counter row locked and incremented in the transaction. No number is skipped by a rollback, but concurrent creators wait for each other.

Choose `no_gap` only when the law or the auditor requires contiguous numbers, and expect contention. Even then, deleted records leave gaps.

{% hint style="info" %}
Accounting documents do not use `ir.sequence` in recent versions; they build their own sequence from the journal and the previous record. Use `ir.sequence` for the rest.
{% endhint %}

## Translations

User-visible strings in Python code and in view XML are extracted into `.po` files per module (`i18n/fr.po`). Two kinds of text need to be handled differently:

### Static strings in code

```python
raise UserError(self.env._("Loan %s is already closed.", loan.name))
```

`self.env._()` translates into the user's language (`env.lang`) at call time and takes `%s` arguments that it substitutes after translation. It is available in Odoo 18; in 16 and 17 use `from odoo import _` and `_("...", arg)`. Never format before translating: `_("Loan %s" % name)` produces a string that exists in no catalogue.

Strings defined at import time, such as `selection` labels or module-level constants, need a lazy form, since the language is not known yet:

```python
from odoo.tools import LazyTranslate
_lt = LazyTranslate(__name__)

STATES = [('open', _lt("Open")), ('done', _lt("Done"))]
```

Selection labels and field `string=` values in field definitions are extracted automatically; you do not wrap them.

### Translatable field values

`translate=True` on a Char, Text or Html field stores one value per language.

```python
name = fields.Char(translate=True)
```

In Odoo 16 and later such a column is JSONB, with a key per language code, instead of rows in `ir_translation`. That table is gone. Consequences:

- `book.with_context(lang='fr_FR').name` reads the French value, falling back to the source value (`en_US`) when the French one is missing.
- Writing with a context language writes that language only. Writing without one (English) updates the source and, for Html and Text, tries to keep existing translations aligned.
- To set several languages in one call, use `update_field_translations`:

```python
book.update_field_translations('name', {'fr_FR': 'Dune', 'it_IT': 'Dune'})
```

- Searching on a translated field compares against the user's language with fallback.
- Raw SQL must address the JSON: use `_field_to_sql`, as in the raw SQL chapter.

Loading a language, exporting and importing `.po` files, and updating terms are done from Settings, Translations, or the command line with `odoo-bin -d db -l fr_FR --i18n-export` style options. Do these on staging first.

## Pitfalls

{% hint style="warning" %}
Translating at import time. A string wrapped with `_()` at module level is evaluated once, in no language, and the extracted term is attached to nothing useful. Use the lazy form or translate inside the method.
{% endhint %}

- Sequences with `company_id` set are invisible to other companies. `next_by_code` then returns `False`, and the name falls back to `/`.
- The sequence `code` must be unique per intent. Two modules using `'sale.order'` as a code share the counter.
- `noupdate="1"` on the sequence record keeps the live counter from being reset by module updates. Without it, an update can overwrite the prefix an administrator changed.
- Changing the prefix of an existing sequence does not renumber existing records.
- Translating a field value with `translate=True` that holds an identifier, such as a code or a technical name, makes lookups depend on the user's language. Leave identifiers untranslated.
- A `.po` file entry with a changed source term no longer matches; terms are matched on exact source text.

## Try it

```python
seq = env['ir.sequence'].search([('code', '=', 'library.loan')], limit=1)
print(seq.implementation, seq.prefix, seq.number_next_actual)
```

`number_next_actual` shows the next value without consuming it (unlike `next_by_code`, which burns one).
