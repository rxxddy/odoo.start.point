# Table of contents

* [Odoo Developer Handbook](README.md)

## Start Here

* [How to read this book](00-start/how-to-read-this-book.md)
* [Conventions and version notes](00-start/conventions-and-versions.md)
* [The Odoo mental model](00-start/the-odoo-mental-model.md)

## Python for Odoo

* [Setup and running code](01-python/setup-and-running-code.md)
* [Values and types](01-python/values-and-types.md)
* [Lists, tuples, dicts, sets](01-python/collections.md)
* [Control flow](01-python/control-flow.md)
* [Functions](01-python/functions.md)
* [Comprehensions and generators](01-python/comprehensions-and-generators.md)
* [Classes and inheritance](01-python/classes-and-inheritance.md)
* [super() explained](01-python/super-explained.md)
* [Decorators](01-python/decorators.md)
* [Errors and exceptions](01-python/errors-and-exceptions.md)
* [Modules and imports](01-python/modules-and-imports.md)
* [Standard library toolbox](01-python/standard-library-toolbox.md)
* [Money, dates, and time zones](01-python/working-with-money-and-dates.md)

## PostgreSQL for Odoo

* [Relational basics](02-postgresql/relational-basics.md)
* [SELECT, FROM, WHERE](02-postgresql/select-from-where.md)
* [Joins](02-postgresql/joins.md)
* [Aggregation and window functions](02-postgresql/aggregation-and-window-functions.md)
* [INSERT, UPDATE, DELETE](02-postgresql/writing-data.md)
* [Indexes and EXPLAIN](02-postgresql/indexes-and-explain.md)
* [Transactions and isolation](02-postgresql/transactions-and-isolation.md)
* [Locks](02-postgresql/locks.md)
* [The Odoo schema](02-postgresql/the-odoo-schema.md)
* [psql and operations](02-postgresql/psql-and-operations.md)

## Web basics

* [XML for Odoo](03-web-basics/xml-for-odoo.md)
* [HTML and CSS you need](03-web-basics/html-and-css.md)
* [JavaScript fundamentals](03-web-basics/javascript-fundamentals.md)
* [Async and the DOM](03-web-basics/async-and-the-dom.md)
* [HTTP and JSON](03-web-basics/http-and-json.md)

## Odoo architecture

* [Installing and running](04-architecture/installing-and-running.md)
* [Command line reference](04-architecture/command-line-reference.md)
* [Project layout and addons path](04-architecture/project-layout-and-addons-path.md)
* [Anatomy of a module](04-architecture/anatomy-of-a-module.md)
* [Registry and model loading](04-architecture/registry-and-model-loading.md)
* [Request lifecycle](04-architecture/request-lifecycle.md)
* [Workers, cron, and longpolling](04-architecture/workers-cron-and-longpolling.md)
* [Odoo.sh and deployment](04-architecture/odoo-sh-and-deployment.md)

## Shell and debugging

* [The Odoo shell](05-shell-and-debugging/odoo-shell.md)
* [Running scripts](05-shell-and-debugging/running-scripts.md)
* [Remote scripts over RPC](05-shell-and-debugging/remote-scripts-over-rpc.md)
* [Logging](05-shell-and-debugging/logging.md)
* [Debugging with pdb and debugpy](05-shell-and-debugging/debugging-with-pdb-and-debugpy.md)
* [Developer mode and tools](05-shell-and-debugging/developer-mode-and-tools.md)
* [Reading tracebacks](05-shell-and-debugging/reading-tracebacks.md)
* [Inspecting SQL](05-shell-and-debugging/inspecting-sql.md)
* [Profiling](05-shell-and-debugging/profiling.md)
* [Safe bulk scripts](05-shell-and-debugging/safe-bulk-scripts.md)
* [Common errors catalog](05-shell-and-debugging/common-errors-catalog.md)

## The ORM

* [Models and recordsets](06-orm/models-and-recordsets.md)
* [Fields reference](06-orm/fields-reference.md)
* [Create, read, write, unlink](06-orm/crud.md)
* [Search and domains](06-orm/search-and-domains.md)
* [Grouping and aggregation](06-orm/grouping-and-aggregation.md)
* [Computed and related fields](06-orm/computed-and-related-fields.md)
* [Constraints and defaults](06-orm/constraints-and-defaults.md)
* [Inheritance](06-orm/inheritance.md)
* [Environment, context, sudo](06-orm/environment-context-sudo.md)
* [Overriding create, write, unlink](06-orm/overriding-crud-methods.md)
* [Cache and prefetch](06-orm/cache-and-prefetch.md)
* [Raw SQL from the ORM](06-orm/raw-sql-from-the-orm.md)
* [XML IDs and references](06-orm/xml-ids-and-references.md)
* [Mail thread and activities](06-orm/mail-thread-and-activities.md)
* [Sequences and translations](06-orm/sequences-and-translations.md)

## Security

* [The security model](07-security/security-model.md)
* [Groups and access rights](07-security/groups-and-access-rights.md)
* [Record rules](07-security/record-rules.md)
* [Field-level security](07-security/field-level-security.md)
* [Multi-company](07-security/multi-company.md)
* [Secure coding](07-security/secure-coding.md)

## Data and views

* [Data files](08-data-and-views/data-files.md)
* [Actions and menus](08-data-and-views/actions-and-menus.md)
* [Form views](08-data-and-views/form-views.md)
* [List views](08-data-and-views/list-views.md)
* [Search views](08-data-and-views/search-views.md)
* [Kanban views](08-data-and-views/kanban-views.md)
* [Pivot, graph, calendar, and more](08-data-and-views/other-views.md)
* [View inheritance and XPath](08-data-and-views/view-inheritance-and-xpath.md)
* [Wizards](08-data-and-views/wizards.md)
* [QWeb templates](08-data-and-views/qweb-templates.md)
* [PDF reports](08-data-and-views/pdf-reports.md)
* [Email templates](08-data-and-views/email-templates.md)
* [Server actions and automation](08-data-and-views/server-actions-and-automation.md)
* [Scheduled actions](08-data-and-views/scheduled-actions.md)

## Frontend and JavaScript

* [Frontend overview](09-frontend-js/frontend-overview.md)
* [Assets and bundles](09-frontend-js/assets-and-bundles.md)
* [OWL fundamentals](09-frontend-js/owl-fundamentals.md)
* [OWL 3 and Odoo 20](09-frontend-js/owl3-and-odoo-20.md)
* [Registries and services](09-frontend-js/registries-and-services.md)
* [Patching standard code](09-frontend-js/patching.md)
* [Custom field widgets](09-frontend-js/custom-fields-and-widgets.md)
* [Customising views](09-frontend-js/customising-views.md)
* [Website and portal](09-frontend-js/website-and-portal.md)
* [Tours and frontend tests](09-frontend-js/tours-and-frontend-tests.md)

## Backend logic

* [Thin controllers, fat models](10-backend-logic/thin-controllers-fat-models.md)
* [HTTP controllers](10-backend-logic/http-controllers.md)
* [State machines](10-backend-logic/state-machines.md)
* [Business logic design](10-backend-logic/business-logic-design.md)
* [Transactions in practice](10-backend-logic/transactions-in-practice.md)
* [Concurrency](10-backend-logic/concurrency.md)
* [Queues and background work](10-backend-logic/queues-and-background-work.md)
* [Consuming external APIs](10-backend-logic/external-apis.md)
* [Receiving webhooks](10-backend-logic/webhooks.md)
* [Bidirectional synchronisation](10-backend-logic/bidirectional-sync.md)
* [Performance](10-backend-logic/performance.md)
* [Importing and exporting data](10-backend-logic/importing-and-exporting-data.md)

## Testing and quality

* [Writing tests](11-testing-and-quality/writing-tests.md)
* [HTTP and tour tests](11-testing-and-quality/http-and-tour-tests.md)
* [Coding standards](11-testing-and-quality/coding-standards.md)
* [Git workflow for modules](11-testing-and-quality/git-workflow-for-modules.md)
* [Documenting your modules](11-testing-and-quality/documenting-your-modules.md)

## Migration and versions

* [Version differences, 16 to 20](12-migration-and-versions/version-differences.md)
* [Upgrading a module](12-migration-and-versions/upgrading-a-module.md)
* [Migration scripts](12-migration-and-versions/migration-scripts.md)
* [Upgrading a database](12-migration-and-versions/upgrading-a-database.md)
* [Deprecations and replacements](12-migration-and-versions/deprecations.md)

## Blueprints

* [A complete module from scratch](13-blueprints/blueprint-library-module.md)
* [Extending a standard workflow](13-blueprints/blueprint-extending-sales.md)
* [A wizard with a PDF report](13-blueprints/blueprint-wizard-and-report.md)
* [A REST integration](13-blueprints/blueprint-rest-integration.md)
* [A portal feature](13-blueprints/blueprint-customer-portal.md)
* [Data repair scripts](13-blueprints/blueprint-data-repair-scripts.md)
* [Spreadsheet import](13-blueprints/blueprint-spreadsheet-import.md)

## Reference

* [ORM cheat sheet](14-reference/cheat-sheet-orm.md)
* [Command cheat sheet](14-reference/cheat-sheet-commands.md)
* [Manifest reference](14-reference/manifest-reference.md)
* [Model catalogue](14-reference/model-catalogue.md)
* [View ID catalogue](14-reference/view-id-catalogue.md)
* [Glossary](14-reference/glossary.md)
