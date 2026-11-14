---
description: One-off scripts against a database, locally and on a server.
---

# Running scripts

A script is a repeatable change you can review, version and re-run. This chapter covers the ways to run one against a database you have shell access to, and when each fits. For a remote instance see [Remote scripts over RPC](remote-scripts-over-rpc.md).

## Option 1: pipe a file into the shell

```bash
./odoo-bin shell -d mydb -c /etc/odoo/odoo.conf --no-http < scripts/fix_isbn.py
```

The file sees `env` as an interactive session does. Be explicit about the transaction, and make the dry run the default:

```python
# scripts/fix_isbn.py
import logging
import os

_logger = logging.getLogger("script.fix_isbn")
APPLY = os.environ.get("APPLY") == "1"

books = env["library.book"].search([("isbn", "=", False), ("legacy_code", "!=", False)])
_logger.info("candidates: %d", len(books))

for book in books:
    book.isbn = book.legacy_code.replace("-", "")

if APPLY:
    env.cr.commit()
    _logger.info("committed")
else:
    env.cr.rollback()
    _logger.info("dry run: rolled back")
```

```bash
./odoo-bin shell -d mydb --no-http < scripts/fix_isbn.py            # dry run
APPLY=1 ./odoo-bin shell -d mydb --no-http < scripts/fix_isbn.py    # real
```

Forgetting the variable is harmless. A traceback ends the script and the transaction is rolled back, which is what you want.

## Option 2: a standalone script that loads Odoo

When you need arguments or exit codes, build the environment yourself:

```python
#!/usr/bin/env python3
import sys
import odoo
from odoo.api import Environment
from odoo.tools import config

config.parse_config(["-c", "/etc/odoo/odoo.conf"])
registry = odoo.registry(sys.argv[1])
with registry.cursor() as cr:
    env = Environment(cr, odoo.SUPERUSER_ID, {})
    print(env["res.users"].search_count([]))
    # the cursor commits when the block exits cleanly
```

Run it with the Python that runs Odoo and with `odoo` importable (`PYTHONPATH=/opt/odoo`). Registry and environment construction changed slightly between releases; check the signatures in your version before copying this.

{% hint style="info" %}
With `registry.cursor()`, leaving the block normally commits and an exception rolls back. The interactive shell rolls back at the end of the session. State the commit policy in a comment at the top of every script.
{% endhint %}

## Option 3: a method in a module

Logic that others must review, or that cron will run, belongs in a model method:

```python
env["library.book"]._cron_fix_isbn()
```

A script run three times should become a method: it is then tested and deployed with the module.

## Migration scripts

A fix that belongs to an upgrade runs once per database when the module version increases:

```
library/migrations/17.0.1.2/post-fix_isbn.py
```

```python
def migrate(cr, version):
    cr.execute("UPDATE library_book SET isbn = replace(isbn, '-', '') WHERE isbn LIKE '%-%'")
```

`pre-` scripts run before the module's models load, `post-` after. Both get a cursor; build `Environment(cr, SUPERUSER_ID, {})` if you need the ORM.

## Running on a server

- Use `tmux`, `screen` or `nohup` so a dropped SSH session does not kill a half-finished job.
- Run as the service user with the service's virtualenv. A script run as root creates root-owned filestore files the service cannot read.
- Keep a log: `... 2>&1 | tee run-$(date +%F-%H%M).log`.
- Take a backup before any run that commits.

```bash
sudo -u odoo nohup /opt/odoo/venv/bin/python /opt/odoo/odoo-bin shell \
  -d mydb -c /etc/odoo/odoo.conf --no-http < scripts/fix_isbn.py \
  > /var/log/odoo/fix_isbn.log 2>&1 &
```

## Pitfalls

- **Editing the script on the server.** What ran no longer matches the repository.
- **Buffered output.** Use `logging`, and `python -u` for standalone scripts.
- **Wrong Python.** System Python lacks Odoo's dependencies.
- **Unbounded search.** `search([])` on a million rows loads every id; batch it.
- **Multi-company blindness.** Superuser scripts have no `allowed_company_ids`, so company-dependent fields can resolve to the wrong company. Pass the context.

## Try it

Write a script that logs how many books lack an ISBN and rolls back. Run it piped, then add the `APPLY` switch.
