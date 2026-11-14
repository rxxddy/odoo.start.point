---
description: A self-contained handbook for building Odoo modules, from Python and SQL basics to production backend logic.
---

# Odoo Developer Handbook

A working reference for writing Odoo modules without needing anyone, or anything, to ask. It starts from the language fundamentals and ends with complete modules that change standard views, extend standard workflows, and run backend logic safely in production.

Everything here is written for Odoo 16 through 20. Where behaviour differs between versions, the page says so in a marked note. Examples were checked against a real Odoo 18 installation and against code written for production use.

## What is in the book

| Part | What it covers |
| --- | --- |
| Python for Odoo | The language, only the parts Odoo code depends on |
| PostgreSQL for Odoo | SQL, transactions, locks, and the Odoo schema |
| Web basics | XML, HTML, CSS, JavaScript, HTTP |
| Odoo architecture | Installation, module anatomy, the request lifecycle, Odoo.sh |
| Shell and debugging | The Odoo shell, scripts, logging, debuggers, profiling, an error catalogue |
| The ORM | Fields, recordsets, search, inheritance, overrides, performance |
| Security | Access rights, record rules, multi-company, secure coding |
| Data and views | XML data, views, XPath inheritance, wizards, reports, cron |
| Frontend and JavaScript | OWL, assets, patching, widgets, portal pages |
| Backend logic | Controllers, state machines, concurrency, APIs, synchronisation |
| Testing and quality | Tests, standards, git workflow |
| Migration and versions | What changed between versions and how to upgrade code |
| Blueprints | Complete modules built step by step |
| Reference | Cheat sheets and catalogues |

## Where to start

- New to programming: read from Python for Odoo onward, in order.
- Know Python, new to Odoo: begin at Odoo architecture, then the ORM.
- Debugging something right now: go to Shell and debugging, then the common errors catalogue.
- Upgrading a module: go straight to Migration and versions.
