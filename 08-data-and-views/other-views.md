---
description: "Pivot, graph, calendar, gantt, activity, and map views."
---

# Other views

Besides list, form and kanban, Odoo ships analytical and scheduling views. All are declared as `ir.ui.view` records of the matching type and enabled by adding the type to the action's `view_mode`. Several of them depend on the Enterprise edition; check before promising them to a Community project.

| View | Edition | Purpose |
|---|---|---|
| `pivot` | Community | Cross-tab of measures by row and column groups |
| `graph` | Community | Bar, line, pie charts from the same grouping engine |
| `calendar` | Community | Records as events on a date grid |
| `activity` | Community (needs `mail`) | Matrix of records by scheduled activity type |
| `cohort`, `gantt`, `map`, `grid` | Enterprise | Retention, timeline planning, geographic, timesheet entry |

## Pivot

```xml
<pivot string="Loans" sample="1">
  <field name="book_id" type="row"/>
  <field name="loan_date" interval="month" type="col"/>
  <field name="fee" type="measure"/>
</pivot>
```

`type` is `row`, `col`, or `measure`. Date fields take `interval` (`day`, `week`, `month`, `quarter`, `year`). A measure must be a stored numeric field with an aggregator; `aggregator="sum"` (the default) can be changed to `avg`, `min`, `max`, `count_distinct` on the field definition in Python. Odoo 16 spelled this `group_operator`; 17 and later use `aggregator`.

## Graph

```xml
<graph type="bar" stacked="True">
  <field name="loan_date" interval="month"/>
  <field name="book_id"/>
  <field name="fee" type="measure"/>
</graph>
```

The first dimension field is the x axis; the second splits into series. `type` is `bar`, `line`, or `pie`. Graph and pivot read through `formatted_read_group` style grouping, so everything shown must be stored.

## Calendar

```xml
<calendar string="Loans" date_start="loan_date" date_stop="due_date" color="book_id" mode="month" quick_create="0">
  <field name="book_id"/>
  <field name="borrower_id" avatar_field="avatar_128"/>
</calendar>
```

`date_start` is required; `date_stop` or `date_delay` (hours) set the length; `all_day` names a boolean field. `color` accepts a many2one or selection field and picks a color per value. `mode` is `day`, `week`, `month`, or `year`. Filters in the right panel come from `<field ... filters="1"/>`.

## Activity

```xml
<activity string="Books">
  <templates>
    <t t-name="activity-box">
      <field name="name"/>
    </t>
  </templates>
</activity>
```

Requires `mail.activity.mixin` on the model. The card template is `activity-box`. The view shows one row per record and one column per activity type.

## Gantt, map, cohort (Enterprise)

These live in `web_gantt`, `web_map`, `web_cohort`. Gantt needs `date_start` and `date_stop` plus `default_scale`; map needs a `res_partner` many2one (`res_partner`) with coordinates; cohort needs `date_start`, `date_stop`, `measure`, `interval`. Because they are Enterprise code, test your module on both editions and keep the view in a separate file loaded only when the dependency is present.

## Pitfalls

- A view type missing from `view_mode`: the switch button never appears and nothing logs an error.
- Pivot on a non-stored measure: the field list is empty or the measure raises on load.
- Putting thousands of rows into a calendar month: every record is fetched for the visible range; add a domain via action context.
- Many2one `color` field in calendar must be stored; computed values flicker.
- Dates in the calendar are converted to the user's timezone, but `date` fields have none; use `datetime` for events.

## Versions

{% hint style="info" %}
16 uses `<tree>`-style naming elsewhere but these views are unchanged by name. In 17 `group_operator` became `aggregator` on fields; 18 keeps `aggregator`. The 18 pivot and graph use the new `formatted_read_group` on the server when available.
{% endhint %}

## Try it

Add `pivot,graph` to the loans action's `view_mode`, upgrade the module, and open the Pivot. Drag "Book" from row to column and watch the grouping change the RPC call in the network tab.
