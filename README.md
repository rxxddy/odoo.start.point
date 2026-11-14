---
description: "Handbook for Odoo module developers: Python, PostgreSQL, the ORM, security, views, the OWL frontend, backend logic, testing and migration for Odoo 16 to 20."
---

# Odoo Developer Handbook

A handbook for people who write Odoo modules. It starts with the Python, SQL and web basics that Odoo code relies on, then covers the ORM, security, views, the frontend, backend logic, testing and migration, and ends with complete modules.

Odoo 18 is the reference version. Differences in 16, 17 and 20 are marked in version notes. Odoo 20 ships OWL 3, so the frontend differs a lot from 18; the chapter [OWL 3 and Odoo 20](09-frontend-js/owl3-and-odoo-20.md) covers the port.

## Contents

| Part | What it covers |
| --- | --- |
| Python for Odoo | The language, limited to what Odoo code uses |
| PostgreSQL for Odoo | SQL, indexes, transactions, locks, the Odoo schema |
| Web basics | HTML, CSS, JavaScript, HTTP, XML |
| Odoo architecture | Installation, module layout, the registry, the request lifecycle, Odoo.sh |
| Shell and debugging | `odoo shell`, scripts, logging, debuggers, profiling, common errors |
| The ORM | Fields, recordsets, search, inheritance, overrides |
| Security | Access rights, record rules, field access, multi-company, secure coding |
| Data and views | XML data, views, XPath inheritance, wizards, reports, cron |
| Frontend and JavaScript | OWL, assets, patching, widgets, portal pages, tours, tests |
| Backend logic | Controllers, state machines, concurrency, APIs, synchronisation |
| Testing and quality | Tests, coding standards, git workflow |
| Migration and versions | What changed between versions, upgrading modules and databases |
| Blueprints | Complete example modules |
| Reference | Cheat sheets and catalogues |

## Where to start

- New to programming: Python for Odoo, in order.
- Know Python, new to Odoo: Odoo architecture, then the ORM.
- Debugging something now: Shell and debugging, then the common errors chapter.
- Upgrading a module: Migration and versions.

Examples use a small teaching module called `library` (`library.book`, `library.loan`). The conventions chapter lists its models and naming.
