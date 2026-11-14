---
description: ir.actions.server types and base.automation triggers.
---

# Server actions and automation

A server action is a stored operation on a model: write fields, create a record, run Python, call a webhook, or chain other actions. An automation rule (`base.automation`) attaches server actions to events such as record creation, a field change, or a time condition. Together they are the low-code layer; knowing their limits tells you when to write a module instead.

## Server action types (Odoo 18)

Verified in the 18 source, `state` offers: `object_write` (Update Record), `object_create` (Create Record), `code` (Execute Code), `webhook` (Send Webhook Notification), `multi` (Execute Existing Actions).

```xml
<record id="action_loan_mark_late" model="ir.actions.server">
  <field name="name">Mark overdue loans</field>
  <field name="model_id" ref="model_library_loan"/>
  <field name="binding_model_id" ref="model_library_loan"/>
  <field name="state">code</field>
  <field name="code">
for loan in records.filtered(lambda l: l.due_date and l.due_date &lt; datetime.date.today()):
    loan.write({'state': 'late'})
  </field>
</record>
```

## Code context

Python in a server action runs in a restricted evaluator with: `env`, `model`, `record` (single, when called on one), `records` (the selection), `uid`, `user`, `time`, `datetime`, `dateutil`, `timezone`, `float_compare`, `log(message, level)`, `UserError`, `Warning`, and `_logger` style helpers. To return a next step, assign an `action` variable:

```python
action = {"type": "ir.actions.act_window", "res_model": "library.loan", "view_mode": "list"}
```

No imports and no attribute names starting with underscore. Anything non-trivial belongs in a model method that the action calls: `records.action_mark_late()`. Method code is versioned, testable, and reviewable; the code field is data in a database.

## Triggers for automation

`base.automation` (module `base_automation`) fields:

- `model_id`, `trigger`: `on_create`, `on_write`, `on_create_or_write`, `on_unlink`, `on_change`, `on_time`, `on_time_created`, `on_time_updated`, `on_state_set`, `on_user_set`, `on_tag_set`, `on_priority_set`, `on_archive`, `on_unarchive`, `on_message_received`, `on_message_sent`, `on_webhook`, `on_stage_set` depending on the fields the model has.
- `trigger_field_ids`: for write triggers, fire only if one of these fields changed.
- `filter_pre_domain` (Before Update Domain) and `filter_domain` (Apply on): the record must match the first before the change and the second after. Together they detect transitions.
- `action_server_ids`: the server actions to run, in order.
- `on_time` triggers use `trg_date_id` (a date field), `trg_date_range` and `trg_date_range_type`, run by a cron.

```xml
<record id="automation_late_loan" model="base.automation">
  <field name="name">Library: flag late loans</field>
  <field name="model_id" ref="model_library_loan"/>
  <field name="trigger">on_time</field>
  <field name="trg_date_id" ref="field_library_loan__due_date"/>
  <field name="trg_date_range">1</field>
  <field name="trg_date_range_type">day</field>
  <field name="filter_domain">[('state', '=', 'out')]</field>
  <field name="action_server_ids" eval="[(4, ref('action_loan_mark_late'))]"/>
</record>
```

## Execution behaviour

Write and create automations run synchronously inside the transaction of the triggering call, after the ORM operation. An exception in the action rolls back the user's save. Time-based rules run from a cron every few minutes and only evaluate records created or updated after the last run window, so adding one later does not back-fill history.

Automations triggered by their own writes can loop; the engine guards against direct recursion for the same rule, not through a chain of different rules.

## Pitfalls

- Heavy code in an `on_write` automation on a hot model: every save pays for it, including imports and RPC.
- Data in the database not in the repo: an automation created through the UI vanishes on a database rebuild and escapes code review. Ship the ones you depend on as XML.
- Server action `code` indentation: a leading newline is fine, inconsistent indentation is not; use spaces.
- Using `record` when the action is run on a list selection: it is empty; use `records`.
- Testing on staging with real outgoing webhooks or mail: neutralize first.
- `binding_model_id` makes the action visible to every user with access to the model unless you add `groups_id`.

## Versions

{% hint style="info" %}
`webhook` as a server action type is new in 17/18 (the 18 source has it; check your version's selection). The automation trigger list was extended in 17 and 18 (tags, priorities, message events, `on_webhook`). In 16 trigger names are fewer and `filter_pre_domain` works the same way.
{% endhint %}

## Try it

Read what is already defined on your model before adding anything:

```sql
select id, name->>'en_US', state from ir_act_server where model_id = (select id from ir_model where model = 'library.loan');
```
