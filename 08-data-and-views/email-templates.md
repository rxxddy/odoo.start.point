---
description: mail.template, inline_template placeholders, and sending from code.
---

# Email templates

A `mail.template` stores a subject, body, recipients and attachments for one model, with placeholders filled in per record at send time. Use it when the text should be editable by an administrator without touching code.

## A template record

```xml
<odoo noupdate="1">
  <record id="mail_template_loan_due" model="mail.template">
    <field name="name">Library: loan due</field>
    <field name="model_id" ref="model_library_loan"/>
    <field name="subject">Loan {{ object.name }} is due on {{ object.due_date }}</field>
    <field name="email_from">{{ (object.company_id.email_formatted or user.email_formatted) }}</field>
    <field name="partner_to">{{ object.borrower_id.id }}</field>
    <field name="report_template_ids" eval="[(4, ref('library.action_report_loan'))]"/>
    <field name="body_html" type="html">
      <div>
        <p>Hello <t t-out="object.borrower_id.name or ''"/>,</p>
        <p>Your loan <strong t-out="object.name"/> is due on
           <t t-out="format_date(object.due_date)"/>.</p>
      </div>
    </field>
  </record>
</odoo>
```

Two syntaxes live side by side:

- Fields like `subject`, `email_from`, `partner_to`, `email_to`, `email_cc`, `reply_to`, `lang` use inline expressions: `{{ expression }}`, Python evaluated by the inline renderer.
- `body_html` uses QWeb: `t-out`, `t-if`, `t-foreach`. The context has `object`, `user`, `ctx`, and helpers such as `format_date`, `format_datetime`, `format_amount`.

`noupdate="1"` is the norm: administrators edit these through the UI, and an update must not overwrite their wording. See the data files chapter.

`partner_to` takes ids as a comma-separated string, evaluated per record. `email_to` is for raw addresses. Prefer partners: they carry the language, the bounce history, and the opt-out flags.

## Sending from code

```python
template = self.env.ref("library.mail_template_loan_due")
template.send_mail(loan.id, force_send=False, email_values={"email_cc": "desk@example.com"})
```

- `force_send=False` queues the `mail.mail` for the mail cron instead of sending inside the transaction. This is what you want in loops, and if the SMTP server is down your transaction still commits.
- `email_values` overrides template fields for this send only.
- `send_mail` creates a `mail.mail` and, with `mail.compose.message` semantics, logs the message on the record's chatter unless you pass `email_layout_xmlid` or use `message_post_with_source`.

For chatter-integrated sending prefer:

```python
loan.message_post_with_source(
    "library.mail_template_loan_due",
    subtype_xmlid="mail.mt_comment",
)
```

This renders the template, posts it in the chatter and emails followers. Use `email_layout_xmlid="mail.mail_notification_light"` to wrap the body in the notification layout.

## Previewing and testing

`template.generate_email(res_ids, ["subject", "body_html", "email_to"])` returns the rendered values as a dict without sending. The template form has a "Preview" button in developer mode that does the same for a chosen record.

## Languages

Set the `lang` field to an inline expression like `{{ object.borrower_id.lang }}`. Translations of the template are stored per field, so translate through the UI or `.po` files; the template is rendered in that language when `lang` resolves.

## Pitfalls

- Mixing syntaxes: `{{ }}` in `body_html` does not work as in subject; QWeb is used there. And `t-out` in subject is meaningless.
- `object.name or ''` guards against `False` printing as nothing odd in some contexts; with `t-out` False renders empty anyway, but inside `{{ }}` concatenation it can raise.
- Outgoing mail server not configured on a staging copy: use mail neutralization so staging does not send real mail. Never test against real addresses.
- Missing recipients: `mail.mail` created, state "Outgoing", no error. Check the `mail.mail` list and the log.
- Editing the template in the UI and then updating the module: the `noupdate` flag protects the edits; a missing flag overwrites them.
- Sandbox: users without the technical group cannot edit dynamic placeholders; only designated groups can write expressions.

## Versions

{% hint style="info" %}
Inline placeholders `{{ }}` replaced the old `${}` Mako syntax in 15, so 16 and later are on the new form. In 17, templates gained `report_template_ids` (many2many) in place of the single `report_template`; in 18 the field is the many2many form.
{% endhint %}

## Try it

Preview a rendered template without sending anything, in a development shell:

```python
env.ref("library.mail_template_loan_due").generate_email([1], ["subject", "body_html"])
```
