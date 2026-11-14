---
description: "Finding bad data and fixing it with an audit trail."
---

# Data repair scripts

Production data goes wrong: a bug wrote duplicates, an import left orphans, a migration missed a field. A repair is safe when it is a read-only finding, a reviewed fix, and a record of what changed. This blueprint is a pattern, using `library.loan` as the example.

## The pattern

1. Write the read-only query that defines "bad".
2. Count and sample it. Show the numbers to whoever owns the data.
3. Write the fix, idempotent, with a dry-run mode that rolls back.
4. Save the before values.
5. Run on a restored copy, then on production.
6. Verify with the query from step 1; it must return zero.

## Find

```sql
SELECT id, name, book_id, date_out, date_due
FROM library_loan
WHERE state = 'open' AND date_due < date_out
ORDER BY id;
```

Keep this query in the script; it is the acceptance test.

## A script that runs through `odoo shell`

Run it on a copy first. The script is a file you pass on stdin, so it is reviewed and versioned:

```bash
odoo-bin shell -d lib_copy --no-http < repair_loans.py
```

```python
# repair_loans.py
import csv
import logging

_logger = logging.getLogger('repair')
DRY_RUN = True          # flip to False deliberately, in review

Loan = env['library.loan']
bad = Loan.search([('state', '=', 'open')]).filtered(lambda l: l.date_due < l.date_out)
_logger.info("found %s bad loans", len(bad))

with open('/tmp/loans_before.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['id', 'date_out', 'date_due'])
    for loan in bad:
        w.writerow([loan.id, loan.date_out, loan.date_due])

for loan in bad:
    loan.with_context(tracking_disable=True).write({'date_due': loan.date_out})
    loan.message_post(body="Due date corrected by data repair.")

if DRY_RUN:
    env.cr.rollback()
    _logger.info("dry run, rolled back")
else:
    env.cr.commit()
    _logger.info("committed")
```

The script writes a CSV before touching anything, posts a chatter note on each record (the audit trail inside the database), and never commits unless the flag is switched.

## SQL variant for large volumes

```sql
BEGIN;
CREATE TABLE repair_loans_20250101 AS
  SELECT * FROM library_loan WHERE state = 'open' AND date_due < date_out;

UPDATE library_loan SET date_due = date_out
WHERE id IN (SELECT id FROM repair_loans_20250101);

-- check, then COMMIT or ROLLBACK
SELECT count(*) FROM library_loan WHERE state = 'open' AND date_due < date_out;
```

The backup table lets you restore exact old values with a join. Name it with a date and drop it after sign-off.

{% hint style="warning" %}
SQL bypasses constraints, computed fields and the cache. After a SQL update of a field that other stored fields depend on, recompute them through the ORM, or the data is inconsistent.
{% endhint %}

## Pitfalls

- Fixing and verifying in the same transaction without a fresh query; use a new connection for the check.
- Repairing in a loop that fires emails and automations. Use `tracking_disable` and review active automations first.
- No before-values. If the fix was wrong, you cannot reverse it.
- Running on production before a copy. The sample you looked at is rarely the full shape of the problem.
- Not scoping by company in a multi-company database.

## Try it

Create three loans on a test database, set `date_due` earlier than `date_out` by SQL on two of them, run the script with `DRY_RUN = True`, confirm the log says two found and nothing changed, then flip the flag.
