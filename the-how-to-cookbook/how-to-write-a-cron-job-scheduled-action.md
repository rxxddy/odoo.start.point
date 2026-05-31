# How to Write a Cron Job (Scheduled Action)

## ⏳ How to Write a Cron Job (Scheduled Action)

> Status: AUTOMATION | Focus: ASYNCHRONOUS BATCH PROCESSING

When the sun sets and your users log off, the ERP ecosystem must continue to breathe. Synchronizations must process, old logs must be purged, and pending invoices must be generated.

In Odoo, background automation is handled by Scheduled Actions (`ir.cron`). However, a poorly written cron job is a ticking time bomb. Because it runs without a user interface, a silent failure goes unnoticed. Worse, if a cron job tries to process 500,000 records in a single loop, it will exhaust the server's RAM, triggering an Out-Of-Memory (OOM) kill that crashes the entire PostgreSQL transaction.

Here is the architectural standard for engineering safe, resilient, and headless automated scripts.

#### 🐍 Phase 1: The Python Engine (The Logic)

A cron job requires a Python method to execute. Because this method is triggered by the system—not by a user clicking a specific record—it must be decorated with `@api.model`.

This method must be strictly self-contained. It must search for its own data, process it in safe batches, and log its own telemetry.

Python

```python
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class DoomsdayProtocol(models.Model):
    _inherit = 'doomsday.protocol'

    @api.model
    def _cron_process_pending_protocols(self):
        """
        Executes pending doomsday protocols. 
        Designed to process in chunks to prevent transaction timeouts.
        """
        _logger.info("Cron Triggered: Scanning for pending protocols...")
        
        # 1. BATCH LIMITER
        # Never search without a limit in a cron job. If the backlog grows to 
        # 100,000 records, a limitless search will crash the worker thread.
        batch_size = 500
        
        # 2. THE SEARCH
        pending_records = self.search([
            ('active', '=', True),
            ('severity_level', '=', 'critical'),
            ('execution_date', '<=', fields.Datetime.now())
        ], limit=batch_size)
        
        if not pending_records:
            _logger.info("Cron Finished: No pending protocols found.")
            return

        _logger.info("Processing batch of %s records.", len(pending_records))
        
        # 3. THE EXECUTION
        success_count = 0
        for record in pending_records:
            try:
                # Execute the business logic
                record.action_execute_protocol()
                success_count += 1
                
                # Optional: Force a database commit after each record if the process 
                # is extremely heavy. Use with extreme caution.
                # self.env.cr.commit() 
                
            except Exception as e:
                # 4. ISOLATING FAILURES
                # If one record fails, do not let it crash the entire batch.
                # Catch the exception, log it, and move to the next record.
                _logger.exception("Failed to process protocol %s: %s", record.id, str(e))
                
        _logger.info("Cron Finished: Successfully processed %s/%s records.", success_count, len(pending_records))
```

#### ⚙️ Phase 2: The XML Declaration (The Trigger)

Now you must tell Odoo's internal scheduler to run this Python method automatically. We do this by creating a record in the `ir.cron` table via an XML file.

Create a file named `data/scheduled_crons.xml`.

The `noupdate="1"` Directive: Notice the `<data noupdate="1">` tag. This is critical. If a system administrator manually changes the cron's execution time from 1 hour to 12 hours via the UI, upgrading the module will overwrite their changes back to 1 hour _unless_ you wrap the record in `noupdate="1"`.

XML

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">

        <record id="ir_cron_execute_doomsday_protocols" model="ir.cron">
            <field name="name">Doomsday: Execute Pending Protocols</field>
            <field name="model_id" ref="model_doomsday_protocol"/>
            
            <field name="state">code</field>
            <field name="code">model._cron_process_pending_protocols()</field>
            
            <field name="active" eval="True"/>
            <field name="user_id" ref="base.user_root"/>
            
            <field name="interval_number">1</field>
            <field name="interval_type">hours</field>
            
            <field name="numbercall">-1</field>
            
            <field name="doall" eval="False"/>
        </record>

    </data>
</odoo>
```

#### 🗂️ Phase 3: Manifest Inclusion

Because cron jobs are structural data records, they must be loaded when the module is installed. Add the XML file to the `data` array in your `__manifest__.py`.

It is architectural best practice to load `data/` files _after_ `security/` files, but _before_ `views/`.

Python

```python
    'data': [
        'security/ir.model.access.csv',
        'data/scheduled_crons.xml',  # Load the automation records here
        'views/doomsday_views.xml',
    ],
```

#### ☢️ 4. Doomsday Rules for Background Automation

If you are deploying crons in a highly volatile environment, memorize these three rules:

1. The Rule of Idempotency: Your cron job must be safe to run twice. If the server crashes at 50% completion, the next scheduled run must cleanly pick up where it left off without duplicating records or sending duplicate webhook payloads. Always mark records as "Done" or "Processing" immediately.
2. The Silent Timeout: Odoo workers have a `limit_time_real` configuration (usually 120 seconds). If your cron loop takes 121 seconds, Odoo will ruthlessly murder the process, and nothing will be saved. Always use small `batch_size` limits. It is better for a cron to process 100 records every 5 minutes than to try 10,000 records once a day and fail.
3. Log Aggressively: A cron job without `_logger` output is a ghost. If it breaks, you will have zero forensic data to reconstruct the failure. Log the start, the batch size, any caught exceptions, and the total success count.
