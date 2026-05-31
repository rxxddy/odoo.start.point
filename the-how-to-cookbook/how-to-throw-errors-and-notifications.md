# How to Throw Errors and Notifications

## 🚨 How to Throw Errors and Notifications

> Status: USER EXPERIENCE & SAFETY | Focus: TRANSACTION CONTROL

When an external API sends malformed data, or a user tries to execute a process they shouldn't, a silent failure is the worst possible outcome. If the system fails silently, the user assumes the action succeeded, and data corruption begins.

In Odoo, you have two primary weapons for handling unexpected behavior: Hard Exceptions (which rollback the database transaction and block the user) and Soft Notifications (which let the transaction succeed but inform the user of the outcome).

Here is how to deploy both.

#### 🛑 1. Hard Stops: `UserError` and `ValidationError`

When a business rule is violated, you must crash the current process safely. Odoo intercepts these specific exceptions, stops the PostgreSQL transaction (preventing partial data saves), and displays a clean, red warning dialog to the user.

Always import `exceptions` and the translation marker `_` from `odoo`.

Python

```python
import logging
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)

class DoomsdayProtocol(models.Model):
    _inherit = 'doomsday.protocol'

    @api.constrains('severity_level')
    def _check_severity_lockdown(self):
        # 1. THE VALIDATION ERROR
        # Typically used inside @api.constrains or create/write methods 
        # to ensure data integrity before it hits the database.
        for record in self:
            if record.severity_level == 'critical' and not record.protocol_notes:
                # Execution stops here. The database is rolled back.
                raise exceptions.ValidationError(
                    _("A Critical severity level requires mandatory architectural notes.")
                )

    def action_initiate_purge(self):
        # 2. THE USER ERROR
        # Typically used in button actions to block a user from doing something stupid
        # based on business logic or permissions.
        if not self.env.user.has_group('base.group_system'):
            # Always wrap hardcoded strings in _() for translation support.
            raise exceptions.UserError(
                _("You lack the required security clearance to initiate a system purge.")
            )
            
        # If the user has permission, the code continues here...
        _logger.info("System purge initiated by %s", self.env.user.name)
        return True
```

#### 🍞 2. Soft Notifications: The "Toast" Message

Sometimes you want the Python method to finish its database work successfully, but you still need to warn the user that something specific happened (e.g., "The API is slow, but the request was queued").

You can do this by returning a `display_notification` client action. It creates a small pop-up (a "toast") in the top right corner of the screen.

Python

```python
    def action_sync_external_data(self):
        for record in self:
            # Assume some data processing happens here
            record.active = True

        # Returning this dictionary instructs the web client to render a toast notification.
        # It does NOT interrupt the database transaction.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Synchronization Queued"),
                'message': _("The external API has been notified. Data will update shortly."),
                'type': 'warning',  # Options: 'success', 'warning', 'danger', 'info'
                'sticky': False,    # If True, it stays on screen until the user clicks 'X'
                'next': {'type': 'ir.actions.act_window_close'}, # Optional: Close a wizard after
            }
        }
```

#### 🌈 3. The Rainbow Man (Success Effects)

When a user completes a major workflow (like clearing a massive queue of Doomsday Protocols or closing a high-value order), Odoo has a built-in gamification feature called the "Rainbow Man".

It acts as a highly visual, temporary success screen. Use it sparingly, only for significant milestones.

Python

```python
    def action_defuse_protocol(self):
        for record in self:
            record.severity_level = 'low'
            
        # Trigger the full-screen success animation
        return {
            'effect': {
                'fadeout': 'slow',
                'message': _('Crisis successfully averted. Returning to standby mode.'),
                'type': 'rainbow_man',
            }
        }
```

**🛡️ Best Practices for Error Handling:**

1. Never use standard Python `Exception` or `ValueError` to block users. These will generate massive traceback logs on your server and display ugly, technical error screens to the user. Always use `exceptions.UserError`.
2. Translate everything. If your string is inside a `raise` statement or a notification dictionary, it must be wrapped in `_("Your Text")`. If you forget the underscore, the system cannot translate the error when a user changes their interface language.
