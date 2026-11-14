---
description: Chatter, tracking, followers, and scheduled activities.
---

# Mail thread and activities

Two mixins give a model its chatter: `mail.thread` (messages, followers, tracking) and `mail.activity.mixin` (scheduled to-dos). Inheriting them is one line, but what they do on every `create` and `write` is worth understanding, because it is the main reason bulk operations on tracked models are slow.

## Adding them

```python
class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    state = fields.Selection(
        [('open', 'Open'), ('late', 'Late'), ('done', 'Done')],
        default='open', tracking=True)
    user_id = fields.Many2one('res.users', tracking=True)
```

Add `message_follower_ids`, `message_ids` and `activity_ids` to the form view, or the shorthand `<chatter/>` element in Odoo 18 (16 and 17 use the explicit `<div class="oe_chatter">` block).

## Tracking

`tracking=True` on a field logs its changes as a message with a before and after value. An integer value orders the fields in the message. A tracked change triggers on `write`, not on raw SQL, and not when the context has `tracking_disable` or `mail_notrack`.

```python
@api.model_create_multi
def create(self, vals_list):
    return super().create(vals_list).with_context(tracking_disable=True)
```

Disable tracking for imports and large batch creates by passing `tracking_disable=True` on the call that creates, not by editing the model. On creation, `mail_create_nolog=True` removes the "created" message and `mail_create_nosubscribe=True` stops adding the creator as a follower.

Override `_track_subtype(self, initial_values)` to choose the message subtype (for example a "Loan became late" subtype) so followers can subscribe to it selectively.

## Posting messages

```python
loan.message_post(
    body=self.env._("Loan marked late."),
    subtype_xmlid='mail.mt_note',
)
```

`message_post` is keyword-only. Main parameters: `body`, `subject`, `message_type` (`'notification'` by default, `'comment'` for something a user wrote), `subtype_xmlid` (`mail.mt_comment` notifies followers, `mail.mt_note` is internal), `partner_ids`, `attachment_ids`.

Other entry points:

- `message_notify(...)` sends a message to given partners without making them followers, and without writing in the thread.
- `_message_log(body=...)` writes a log note with no notification.
- `message_post_with_source(...)` renders a template or view as the body.

Bodies are HTML. Pass plain strings only when they are already escaped; for user input, use `Markup` and `markupsafe.escape`, or the body gets sanitised.

## Followers

```python
loan.message_subscribe(partner_ids=[partner.id])
loan.message_unsubscribe(partner_ids=[partner.id])
```

Followers receive notifications for subtypes they chose. Odoo adds the author of a message as a follower unless `mail_post_autofollow` is disabled in context. Default subtypes per model come from `mail.message.subtype` records whose `res_model` matches.

## Activities

Activities are scheduled to-dos for a user on a record: a call, a reminder, an approval.

```python
loan.activity_schedule(
    'mail.mail_activity_data_todo',
    date_deadline=fields.Date.add(fields.Date.today(), days=7),
    summary=self.env._("Check return"),
    user_id=loan.user_id.id,
)
```

The signature is `activity_schedule(act_type_xmlid='', date_deadline=None, summary='', note='', **act_values)`. Extra values (such as `user_id`) go straight into `mail.activity`. When `user_id` is not given, the activity type's default user, then the current user, is used. The activity type is referenced by XML ID; defining your own type in data lets managers rename and reconfigure it.

Closing activities:

```python
loan.activity_feedback(['mail.mail_activity_data_todo'], feedback=self.env._("Returned"))
loan.activity_unlink(['mail.mail_activity_data_todo'])
```

`activity_feedback(act_type_xmlids, user_id=None, feedback=None, attachment_ids=None)` marks done and posts the feedback in the chatter; `activity_unlink` removes without trace. Prefer feedback: it leaves an audit trail.

The mixin also adds stored fields such as `activity_state` and `activity_date_deadline`, which power the list-view activity widget and the "My activities" filters.

## Pitfalls

{% hint style="warning" %}
Each tracked write creates a message, tracking values and notifications; each `create` subscribes followers. A loop with `write` per record on a tracked model is far slower than one `write` on the recordset.
{% endhint %}

- Tracking a computed field works only if it is stored.
- Tracking a One2many or Many2many does not produce a before and after; the ORM tracks columns. Post a message by hand.
- `message_post` from a cron or `sudo()` is authored by the environment user (often the superuser, shown as a system user). Pass `author_id` for human-looking messages.
- Notifications go out by email through the mail queue. A test or staging database with outgoing mail enabled will email real followers. Check outgoing mail servers before running a data load.
- `activity_schedule` with a missing XML ID raises; guard custom types with `raise_if_not_found=False` through `env.ref`.
- Mail sending errors are logged by the queue, not raised in your method, so a post can succeed while the email fails.

## Try it

On a throwaway database:

```python
loan = env['library.loan'].create({'name': 'Test loan'})
loan.message_post(body='Hello', subtype_xmlid='mail.mt_note')
loan.activity_schedule('mail.mail_activity_data_todo', summary='Check')
print(loan.message_ids.mapped('body'), loan.activity_ids.mapped('summary'))
```

Then open the form to see both in the chatter.
