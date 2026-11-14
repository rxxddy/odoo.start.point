<p align="center">
  <img src="assets/banner.svg" alt="Odoo Developer Handbook" width="100%">
</p>

<p align="center">
  <a href="https://rxxddy.github.io/odoo.start.point/"><img alt="GitHub Pages" src="https://img.shields.io/badge/read-GitHub%20Pages-24292f?style=for-the-badge&logo=github&logoColor=white"></a>
  <a href="https://weden.gitbook.io/odoo-developer-handbook"><img alt="GitBook" src="https://img.shields.io/badge/read-GitBook-714B67?style=for-the-badge&logo=gitbook&logoColor=white"></a>
  <img alt="Odoo versions" src="https://img.shields.io/badge/Odoo-16%20%C2%B7%2017%20%C2%B7%2018%20%C2%B7%2020-714B67?style=for-the-badge">
  <img alt="Chapters" src="https://img.shields.io/badge/chapters-130-3b82f6?style=for-the-badge">
  <a href="../LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-f59e0b?style=for-the-badge"></a>
</p>

A handbook for people who write Odoo modules. It starts with the Python, SQL and web basics that Odoo code relies on, then covers the ORM, security, views, the frontend, backend logic, testing and migration, and ends with complete modules.

Read it online on [GitHub Pages](https://rxxddy.github.io/odoo.start.point/) or on [GitBook](https://weden.gitbook.io/odoo-developer-handbook).

Odoo 18 is the reference version. Differences in 16, 17 and 20 are marked in version notes. Odoo 20 ships OWL 3, so its frontend differs a lot from 18; [one chapter](../09-frontend-js/owl3-and-odoo-20.md) covers the port.

<p align="center">
  <img src="assets/terminal.svg" alt="Animated Odoo shell session: a read-only query, a change, a rollback" width="82%">
</p>

## Contents

| # | Part | What it covers |
| ---: | --- | --- |
| 00 | [Start here](../00-start) | Reading paths, conventions, how Odoo is put together |
| 01 | [Python for Odoo](../01-python) | The language, limited to what Odoo code uses |
| 02 | [PostgreSQL for Odoo](../02-postgresql) | SQL, joins, indexes, transactions, locks, the Odoo schema |
| 03 | [Web basics](../03-web-basics) | HTML, CSS, JavaScript, HTTP and JSON, XML |
| 04 | [Odoo architecture](../04-architecture) | Installation, module layout, the registry, the request lifecycle, Odoo.sh |
| 05 | [Shell and debugging](../05-shell-and-debugging) | `odoo shell`, scripts, logging, debuggers, profiling, common errors |
| 06 | [The ORM](../06-orm) | Fields, recordsets, search, inheritance, overrides |
| 07 | [Security](../07-security) | Access rights, record rules, field access, multi-company, secure coding |
| 08 | [Data and views](../08-data-and-views) | XML data, views, XPath inheritance, wizards, reports, cron |
| 09 | [Frontend and JavaScript](../09-frontend-js) | OWL 2 and 3, assets, patching, widgets, portal, tours, hoot tests |
| 10 | [Backend logic](../10-backend-logic) | Controllers, state machines, concurrency, APIs, synchronisation |
| 11 | [Testing and quality](../11-testing-and-quality) | Tests, coding standards, git workflow |
| 12 | [Migration and versions](../12-migration-and-versions) | What changed between versions, upgrading modules and databases |
| 13 | [Blueprints](../13-blueprints) | Complete example modules |
| 14 | [Reference](../14-reference) | Cheat sheets and catalogues |

## Where to start

| If you are | Start with |
| --- | --- |
| New to programming | [Python for Odoo](../01-python), in order |
| Fluent in Python, new to Odoo | [Odoo architecture](../04-architecture), then [The ORM](../06-orm) |
| Debugging something now | [Shell and debugging](../05-shell-and-debugging) |
| Building a frontend | [Frontend overview](../09-frontend-js/frontend-overview.md) |
| Writing access rules | [The security model](../07-security/security-model.md) |
| Upgrading a module | [Migration and versions](../12-migration-and-versions) |

## Sources and versions

- Names, signatures and behaviour are taken from the Odoo source: 18 for most of the book, 20 where a chapter says so, and the 16.0 and 17.0 branches for version notes.
- Security (part 07), frontend (part 09) and the version tables in part 12 were rewritten against the source. The other parts are older and shorter; they are revised part by part.
- Examples use a small teaching module, `library`. They contain no client data.

## Reading offline

```bash
git clone https://github.com/rxxddy/odoo.start.point.git
```

Every chapter is a Markdown file and `SUMMARY.md` is the table of contents. The `{% hint %}` and `<details>` blocks are GitBook syntax and stay readable as plain text.

## Contributing

Open an issue for a wrong name, a changed signature or a command that failed, with the page, your Odoo version and what you saw. Pull requests should follow [`STYLE.md`](../STYLE.md).

## License

Apache License 2.0, see [`LICENSE`](../LICENSE).
