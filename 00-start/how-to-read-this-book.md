---
description: "Prerequisites, reading paths by role, how chapters are laid out, and how to use the exercises."
---

# How to read this book

The book takes someone who has written some code in any language to the point of building, extending, debugging and deploying Odoo modules: business logic, security, views, reports, a frontend component and integrations. Nobody reads it front to back. This chapter lists what you need, which parts to read for which job, how a chapter is laid out, and how to work through the exercises.

## What you need

- **A terminal.** You can change directories, run a command, read its output and edit a text file. Shell examples use Bash. On Windows, use Git Bash or WSL; the text notes where PowerShell differs.
- **Some programming.** Variables, loops and functions should not be new. Python and JavaScript are taught from the start in parts 1 and 3, at a pace that assumes you know what a function is.
- **The ability to install software.** Part 4 covers installing Odoo and PostgreSQL. You still deal with your system's package manager and a Python virtual environment.
- **Reading English.** Error messages, source code and the Odoo community are in English.

You do not need to know Odoo as a user. "The Odoo mental model" explains what Odoo is made of before you write anything.

## Reading paths

| You are | Read first | Then | Skip or skim |
|---------|------------|------|--------------|
| New to programming and to Odoo | Start Here, Python for Odoo, the first four PostgreSQL chapters | Web basics, Odoo architecture, Shell and debugging, The ORM, the first Blueprint | Migration, until you need it |
| A Python developer new to Odoo | Start Here, the Odoo mental model, Odoo architecture | The ORM, Data and views, Security, Shell and debugging | Python for Odoo except decorators and `super`; skim the SQL part |
| A web developer new to Odoo | Start Here, Odoo architecture, The ORM | Data and views, Frontend and JavaScript, Backend logic | Web basics |
| An Odoo user turning developer | Start Here, Python for Odoo, Odoo architecture | The ORM, Data and views, a Blueprint | Frontend, until the ORM and views make sense |
| An Odoo developer on older versions | Migration and versions, Deprecations | The frontend part (OWL) | Python and SQL basics |
| Maintaining production | Shell and debugging, PostgreSQL (locks, transactions, psql), Backend logic (concurrency, queues) | Security, Odoo.sh and deployment | Frontend |
| Building integrations | Web basics (HTTP and JSON), Backend logic (APIs, webhooks, sync) | Security, Testing | Views and frontend |

For a first working module quickly: the Odoo mental model, Anatomy of a module, Models and recordsets, Form views, Actions and menus, with the first Blueprint open next to them.

Parts depend only on earlier parts, with two exceptions. The ORM part uses SQL ideas from the joins and transactions chapters. "Data and views" mentions JavaScript behaviour that "Frontend and JavaScript" explains. A chapter that needs something from later points to it.

## How a chapter is laid out

1. **Opening paragraph.** The problem the chapter solves. If you do not have that problem, skip the chapter.
2. **Material.** Concepts with the reason behind each rule, then examples you can run.
3. **Hints.** Coloured boxes; the conventions chapter lists what each colour means.
4. **Versions.** A section or hint, only where Odoo 16 to 20 differ.
5. **Pitfalls.** Failures that cost real time.
6. **Try it.** Three to five exercises, solutions behind a fold.

Reference chapters at the end (cheat sheets, catalogues, glossary) are for lookup and do not follow this layout.

## Exercises

1. Read the exercise and keep the solution closed. Predict the answer or write the code.
2. Run it with `node`, `python`, `psql`, `curl` or an Odoo shell. If your result differs from the solution, run both and compare the output.
3. Open the solution and compare the approach as well as the result. Some exercises have more than one valid answer, and the solution names the trade-off.
4. Break it: remove a closing tag, drop an `await`, rename a field, and read the error. The Shell and debugging part lists the common ones.

Keep a scratch folder outside any addons path and a scratch database you can drop. Data-changing commands in the book always come after the read-only query for the same data.

## Building a project alongside

The Blueprints part builds complete modules on the `library` teaching module. Pick a small module you actually want (a loan tracker, a checklist on a standard form, a PDF with a total, a portal page) and build it as you read. When something is unclear, find the chapter in the table of contents, read the material and the pitfalls, and continue.

## Where each kind of work is covered

| The work | Where |
|----------|-------|
| Understand a request and where it belongs in Odoo | The Odoo mental model, Business logic design |
| Set up a machine, a database, Odoo | Odoo architecture; PostgreSQL for Odoo (psql and operations) |
| Define data: models, fields, constraints | The ORM; Fields reference; Constraints and defaults |
| Decide who sees and does what | Security |
| Menus, forms, lists, search, kanban | Data and views |
| PDF reports, email templates | QWeb templates; PDF reports; HTML and CSS |
| Workflows, cron, server actions, queues | State machines; Scheduled actions; Queues and background work |
| New behaviour in the UI | Frontend and JavaScript; Async and the DOM |
| Other systems | HTTP and JSON; External APIs; Webhooks; Bidirectional sync |
| Finding out why it fails | Shell and debugging; Common errors; Inspecting SQL |
| Speed | Cache and prefetch; Performance; Indexes and EXPLAIN; Profiling |
| Tests and upkeep | Testing and quality; Git workflow |
| A new Odoo version | Migration and versions |
| Shipping and operating | Odoo.sh and deployment; Safe bulk scripts |

Real tasks cross several rows. Adding a field to the sales order and printing it on the PDF touches the ORM (the field), Data and views (inheritance), PDF reports (QWeb), Security (does it need a group?) and Testing. The Blueprints work through such combinations.

## Working habits

- **Read the error first.** Most failures print a traceback or an XML or JS error that names a file and a line. Read the last line, then the nearest frame in your code.
- **Reproduce on a scratch database** with only your module installed: cleaner errors, faster restarts.
- **Read the source.** When the book names a method or a template, find it under `odoo/` and `addons/` in your installation. The standard module that already does what you want is the best example.
- **Check the version.** Run `odoo-bin --version` or read `odoo/release.py` before following a recipe.
- **Keep changes small and reversible.** Commit often, run the read-only query before the write, test an upgrade on a copy.

## What is not covered

The functional side of Odoo (configuring accounting, designing a sales process), the user documentation of each standard app, and Odoo Studio. Reference chapters list what developers need often and show how to find the rest in the source.

If the book and the source of your installed version disagree, trust the source and report the difference.
