---
description: Extending standard views without copying them: inherit_id, xpath, positions, priorities.
---

# View inheritance and XPath

Every customisation of a standard screen is a view that inherits another view. Odoo never edits the parent record: at render time it takes the parent arch, applies each child's patch in order, and returns the merged result. Done well, your module survives upgrades of the module you extend. Done badly, it breaks on the first minor release that moves a `<group>`.

## The minimal inheritance record

```xml
<record id="view_partner_form_library" model="ir.ui.view">
    <field name="name">res.partner.form.library</field>
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.view_partner_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='vat']" position="after">
            <field name="library_card_number"/>
        </xpath>
    </field>
</record>
```

`inherit_id` takes an external ID, with the module prefix when it is not your own. The parent must be loaded before the child, so the module that owns it has to be in `depends`. The `name` field is only a label; make it unique and descriptive because it is what you will search for in Settings > Technical > Views.

## The shorthand form

When the target is a single element you can skip `xpath` and write the element itself. Odoo builds the expression from the tag and its attributes:

```xml
<field name="vat" position="after">
    <field name="library_card_number"/>
</field>
```

This is equivalent to `//field[@name='vat']`. It only works with a unique match on `name`; anything more specific needs an explicit `xpath`.

## Positions

| position | effect |
|---|---|
| `after` | insert the content as next sibling |
| `before` | insert the content as previous sibling |
| `inside` | append to the end of the matched element (default) |
| `replace` | replace the matched element; with an empty body, delete it |
| `attributes` | change attributes of the matched element, content is `<attribute name="...">` |
| `move` | inside an `xpath` child, relocate a matched node (see below) |

### Attributes

```xml
<xpath expr="//field[@name='vat']" position="attributes">
    <attribute name="invisible">not is_company</attribute>
    <attribute name="string">Registration number</attribute>
</xpath>
```

Setting an attribute overwrites the parent's value. To append to an existing expression, use `add` and `separator`:

```xml
<attribute name="class" add="text-muted" separator=" "/>
<attribute name="invisible" add="state == 'cancel'" separator=" or "/>
```

`remove` does the opposite for token lists such as `class`.

### Moving nodes

```xml
<xpath expr="//field[@name='ref']" position="after">
    <xpath expr="//field[@name='vat']" position="move"/>
</xpath>
```

The inner `xpath` with `position="move"` takes the node out of its old place and puts it where the outer one points. Use it instead of deleting and re-declaring a field, because it keeps the field's own attributes and children.

### Replace with `$0`

In `replace`, the string `$0` inside the new content stands for the original node. It lets you wrap an element without copying it:

```xml
<xpath expr="//field[@name='vat']" position="replace">
    <div class="o_row">$0</div>
</xpath>
```

## Writing selectors that survive

Selectors are XPath 1.0 over the parent arch. In order of robustness:

1. `//field[@name='x']`: a field name is part of the model contract.
2. `//group[@name='sale_info']` or `//page[@name='...']`: named containers. Odoo core sets `name` on most structural nodes on purpose.
3. `//button[@name='action_confirm']`: button method names.
4. Position-based: `//group[2]`, `//sheet/div[1]`. Avoid. They break when someone inserts an element above.

Anchor on the element nearest to where you want the change, not on the form root. `//field[@name='partner_id']/..` is a legitimate way to reach the enclosing group.

### Duplicate fields

A form may show the same field twice (once visible, once `invisible="1"` for computing a domain). `//field[@name='partner_id']` then matches the first in document order. If that is the wrong one, qualify it: `//group[@name='main']//field[@name='partner_id']`, or use `[@invisible]` / `[not(@invisible)]`.

## Mode: extension versus primary

```xml
<field name="mode">primary</field>
```

The default `mode` is `extension`: your patch is applied on top of the parent every time the parent is rendered. With `primary`, the child is an independent view that starts from a copy of the parent. Choose primary when an action needs its own form variant without touching the original, for example a read-only variant for a portal-like menu. Reference it with `view_id` on the action, or through `ir.actions.act_window.view`.

## Priorities and ordering

Children of one parent apply in ascending `priority`, then ascending `id`. The default is 16.

```xml
<field name="priority" eval="20"/>
```

Raise the priority when your patch depends on elements added by another child. A child that targets a node created by a sibling with a lower priority works; the reverse fails with a missing-node error at install. If two unrelated modules patch the same node, the later one wins, so a module that must always win declares a high priority rather than relying on install order.

## Inheriting views of other view types

The same mechanism works for list, kanban, search, calendar and QWeb views. For list views, use `<list>` as the parent element in new code:

```xml
<record id="view_partner_list_library" model="ir.ui.view">
    <field name="name">res.partner.list.library</field>
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.view_partner_tree"/>
    <field name="arch" type="xml">
        <field name="email" position="after">
            <field name="library_card_number" optional="show"/>
        </field>
    </field>
</record>
```

The ID of the standard partner list is `base.view_partner_tree` even though the element inside is now `<list>`; Odoo did not rename external IDs. See the [view ID catalogue](../14-reference/view-id-catalogue.md).

## Groups on inherited elements

Restrict a patch to users of a group with the `groups` attribute on the inserted element, not on `xpath`:

```xml
<field name="library_card_number" position="after" groups="library.group_librarian">
```

An element with unmet `groups` is dropped from the arch server-side, so users never receive it. Keep this in mind for the next point.

## Pitfalls

{% hint style="warning" %}
**A parent that loses its anchor.** If a later upgrade removes `//field[@name='vat']`, your view fails to load and the whole module update aborts with `Element '<field name="vat">' cannot be located in parent view`. Prefer anchors that core is unlikely to drop, and test module updates against the next minor release.
{% endhint %}

* **Group-restricted anchors.** If the parent element you target has `groups="..."` and the user lacks the group, the element is already gone when your patch applies for them. Odoo applies patches on the unrestricted arch and then prunes, so this works in a normal run. It fails in custom contexts that pre-prune; keep anchors on ungrouped nodes where you can.
* **Copy-paste of the full arch.** Replacing the whole `<sheet>` with your own copy freezes the form in the version you copied. Every upgrade then needs a manual merge.
* **`position="replace"` on a container with children others patch.** Another module's child that targeted a node inside the replaced element now has no target. Prefer `attributes` or `move`.
* **Editing a view in the UI on production.** It creates a `ir.ui.view` record with `noupdate` behaviour disconnected from the module source; the next module update will overwrite or fight it. Make the change in code.
* **Name collisions in XML IDs.** Your child's ID must be unique in your module. Reusing `view_partner_form` inside a module that already defines one overwrites its own record, not the parent.

{% hint style="info" %}
**Versions.** In Odoo 16 and earlier, hiding was done with `attrs="{'invisible': [('state', '=', 'draft')]}"` and `states="draft"`. Odoo 17 replaced both with direct Python-style expressions: `invisible="state == 'draft'"`. In Odoo 18 the old syntax is gone; a view using `attrs` fails validation. If you patch the attribute from an old module, rewrite the expression, you cannot `add` to a domain list.
{% endhint %}

{% hint style="info" %}
**Versions.** Odoo 18 list views use `<list>`. The legacy `<tree>` tag was accepted as an alias for the list view type and is still read for compatibility, but new views should write `<list>`, and an `xpath` that targets `//tree` on a core 18 view will not match.
{% endhint %}

## Try it

Inspect the merged result of a view and the chain of children, read-only, from `odoo shell`:

```python
view = env.ref('base.view_partner_form')
print(len(view.inherit_children_ids), [c.name for c in view.inherit_children_ids])
merged = env['res.partner'].get_view(view.id, 'form')
print(merged['arch'][:2000])
```

`get_view` returns the arch after all inheritance and group pruning for the current user, which is what the web client actually receives.
