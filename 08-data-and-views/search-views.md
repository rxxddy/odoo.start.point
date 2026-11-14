---
description: "Fields, filters, group by, and search defaults."
---

# Search views

The search view defines what the user can type into the search box, which filters appear in the dropdown, and how records can be grouped. It is a separate view record of type `search`, attached to an action through `search_view_id` or picked by priority.

## Anatomy

```xml
<record id="library_book_search" model="ir.ui.view">
  <field name="name">library.book.search</field>
  <field name="model">library.book</field>
  <field name="arch" type="xml">
    <search string="Books">
      <field name="name" string="Title" filter_domain="['|', ('name', 'ilike', self), ('isbn', '=', self)]"/>
      <field name="author_id"/>
      <field name="tag_ids"/>
      <separator/>
      <filter name="available" string="Available" domain="[('state', '=', 'available')]"/>
      <filter name="late" string="Overdue" domain="[('due_date', '&lt;', context_today().strftime('%Y-%m-%d'))]"/>
      <separator/>
      <filter name="archived" string="Archived" domain="[('active', '=', False)]"/>
      <group expand="0" string="Group By">
        <filter name="group_author" string="Author" context="{'group_by': 'author_id'}"/>
        <filter name="group_year" string="Published" context="{'group_by': 'published_date:year'}"/>
      </group>
      <searchpanel>
        <field name="category_id" icon="fa-folder" enable_counters="1"/>
      </searchpanel>
    </search>
  </field>
</record>
```

### Fields

A `<field>` makes the search box offer "Search Title for: ...". The operator defaults to `ilike` for text and `=` for numbers and relations. `filter_domain` overrides it; `self` stands for the typed value. List several fields and the user chooses; fields marked `operator` or with `filter_domain` search that way. `string` renames the entry.

### Filters

- `domain`: applied when toggled. Filters in the same block (no `<separator/>` between) are ORed; separated blocks are ANDed. This is the single most misunderstood rule; test it with two filters toggled.
- `name` is needed if you want `search_default_<name>` in an action context, and for inheriting.
- `date` attribute: `<filter name="d" date="create_date" string="Created"/>` renders the period picker (month/quarter/year) in the dropdown.
- Domains can use `context_today()`, `relativedelta`, `datetime`, `time`, and `uid`. Escape `<` as `&lt;` in XML.

### Group by

A `group_by` context on a filter. Date fields accept a granularity suffix: `:day`, `:week`, `:month`, `:quarter`, `:year`. Grouping by a related field works if it is stored.

### Search panel

`<searchpanel>` adds a side tree for a many2one or selection field. Use `select="multi"` for checkboxes with a `groupby` for hierarchies. It issues extra read_group calls, so avoid it on huge models without a good index.

## Search defaults

On the action, `context`:

```
{'search_default_available': 1, 'search_default_author_id': 3}
```

The first toggles the filter named `available`; the second pre-fills the `author_id` field with a value. `search_default_*` keys are read by the view, not by the server, so they have no effect in a plain `search()` call.

## Custom saved filters

Users create their own through "Save current search"; these are `ir.filters` records. If you want to ship one, create an `ir.filters` record with `model_id`, `domain`, `context`, and `user_id` empty for a shared filter.

## Pitfalls

- Searching on a non-stored computed field fails unless you give it a `search` method.
- `filter_domain` using `self` in a field of `many2one` is evaluated against the typed text; use `name_search` semantics deliberately, not the id.
- Using `attrs` or `states` in a search view is meaningless; they are for form fields. See Versions.
- A filter without a `name` cannot be targeted by `search_default_*` or by an xpath in an inherited view.
- Default filters hide data: a user who sees "no records" because `search_default_available` hides most of them files a bug. Show the active filter in a help text.

## Versions

{% hint style="info" %}
In 16 the search view takes the same elements as in 17 and 18. What changed is around it: `attrs` and `states` were dropped on form elements in 17 (use `invisible`, `readonly` and `required` with Python-like expressions), and in 18 `tree` became `list` in actions. Search views themselves were stable across these versions.
{% endhint %}

## Try it

Open the Books list, toggle "Available" and "Overdue" together, then add "Archived" after the separator. Watch the domain with developer mode's "Edit Domain" or the network panel to see how OR and AND combine.
