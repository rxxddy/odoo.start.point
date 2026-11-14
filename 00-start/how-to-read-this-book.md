---
description: "Reading paths, prerequisites, and how the chapters are laid out."
---

# How to read this book

The book is long on purpose. It takes someone who has written a little code in any language to a point where they can build, extend, debug, and deploy Odoo modules with business logic, security, views, reports, a frontend component, and integrations. You will not read it front to back in one sitting, and you should not. This chapter tells you which parts to read for the job you have, what each chapter assumes, how a chapter is built, and how to use the exercises so the material sticks.

## What you need before you start

Almost nothing, but be honest about these four things:

- **You can use a terminal.** You can change directories, run a command, read its output, and edit a text file. The shell examples use Bash syntax; on Windows, use Git Bash or WSL, and the book notes where PowerShell differs.
- **You have written some code in some language.** Variables, loops, and functions should not be new concepts. Python and JavaScript are taught from the ground up in Parts 1 and 3, but they are taught at a pace that assumes you already know what a function is.
- **You can install software.** Part 4 walks through installing Odoo and PostgreSQL, but you will have to deal with your operating system's package manager and a Python virtual environment.
- **You can read English technical prose.** Error messages and source code are in English, and so is the Odoo community.

You do not need to know Odoo as a user. The next chapter after these two, "The Odoo mental model", explains what Odoo is made of before you write anything.

## Reading paths

Pick the row that matches you. Chapter groups are the Parts listed in the table of contents.

| You are | Read first | Then | Skim or skip |
|---------|------------|------|--------------|
| New to programming and to Odoo | Start Here, Python for Odoo (all), PostgreSQL for Odoo (first four chapters) | Web basics, Odoo architecture, Shell and debugging, The ORM, then the first Blueprint | Migration until you need it |
| A Python developer new to Odoo | Start Here, the Odoo mental model, Odoo architecture | The ORM, Data and views, Security, Shell and debugging | Python for Odoo except decorators and super; skim the SQL part |
| A web developer new to Odoo | Start Here, Odoo architecture, The ORM | Data and views, Frontend and JavaScript, Backend logic | Web basics (skim), HTML/CSS |
| An Odoo user turning developer | Start Here, Python for Odoo, Odoo architecture | The ORM, Data and views, a Blueprint | Frontend until the ORM and views feel natural |
| An Odoo developer from older versions | Migration and versions, Deprecations | The frontend part (OWL) | Python and SQL basics |
| Maintaining production | Shell and debugging, PostgreSQL (locks, transactions, psql), Backend logic (concurrency, queues) | Security, Odoo.sh and deployment | Frontend |
| Building integrations | Web basics (HTTP and JSON), Backend logic (APIs, webhooks, sync) | Security, Testing | Views and frontend |

If you want a first working module as fast as possible: read the Odoo mental model, Anatomy of a module, Models and recordsets, Form views, Actions and menus, then run the first Blueprint alongside. Come back to fill in the gaps; the chapters are written so that you can.

### Reading order inside the book

The parts are ordered so that each depends only on earlier ones, with two deliberate exceptions. The ORM part uses SQL ideas, so the PostgreSQL chapters on joins and transactions are worth having behind you. And "Data and views" mentions JavaScript behaviours that "Frontend and JavaScript" explains fully. Where a chapter needs something from later, it says so with a pointer rather than assuming you know.

## How a chapter is structured

Chapters follow the same shape, so you can find things without rereading:

1. **The opening paragraph** states the problem the chapter solves and what you can do after it. If the paragraph describes a problem you do not have, skip the chapter.
2. **Core material**: concepts, then runnable examples. Concepts come with the reason a rule exists, because a rule without its reason is forgotten at the first exception.
3. **Hints** in colour boxes, used sparingly (see the conventions chapter for what each colour means).
4. **Versions**, a section or hint, only where behaviour differs between Odoo 16 and the newest verified release.
5. **Pitfalls**: the failure modes that cost people real time. Read this section even if you skim the rest; it is where the chapter pays back the most.
6. **Try it**: three to five exercises with solutions hidden behind a fold.

Reference chapters at the end (cheat sheets, catalogues, glossary) break this pattern on purpose. They are for lookup, not for reading.

## How to use the exercises

An exercise you read but did not do teaches roughly nothing. Use this procedure:

1. Read the exercise and **close the solution**. Predict the answer on paper if it is a prediction task, or write the code.
2. **Run it.** Every code exercise can be run with `node`, `python`, `psql`, `curl`, or an Odoo shell. If your answer disagrees with the solution, run both and diff the output; the difference teaches more than either answer alone.
3. **Open the solution** and compare approach, not only result. Several exercises have more than one valid answer, and the solution usually names the trade-off.
4. **Break it on purpose.** Remove a closing tag, drop an `await`, change a field name, and read the error message. Odoo's error messages are legible once you have seen each of them once, and the Shell and debugging part collects the most common.

Keep a scratch folder outside any Odoo addons path for exercises and experiments, and a scratch database you can drop at any time. Habit number one of a safe developer is never experimenting where it could damage something that matters. The book's data-changing commands are always preceded by their read-only counterpart for the same reason.

## Work through a project, not only chapters

The Blueprints part builds complete modules step by step on the neutral `library` teaching module. The effective way to use the book is to pick a small module you actually want, such as a loan tracker, a checklist on a standard form, a PDF with a total, or a portal page, and build it as you read. When you hit something you do not understand, find the chapter in the table of contents, read the core material and the pitfalls, and continue.

## How the book maps to the work of an Odoo developer

The part order follows what a task usually needs, in the order you reach for it:

| The work | Where the knowledge lives |
|----------|---------------------------|
| Understand a request and where it belongs in Odoo | The Odoo mental model, Business logic design |
| Set up a machine, run a database, run Odoo | Odoo architecture; PostgreSQL for Odoo (psql and operations) |
| Define data: models, fields, constraints | The ORM; Fields reference; Constraints and defaults |
| Decide who can see and do what | Security |
| Present it: menus, forms, lists, search, kanban | Data and views |
| Print it: PDF reports, email templates | QWeb templates; PDF reports; HTML and CSS |
| Automate: workflows, cron, server actions, queues | State machines; Scheduled actions; Queues and background work |
| Make the UI do something new | Frontend and JavaScript; Async and the DOM |
| Connect to other systems | HTTP and JSON; External APIs; Webhooks; Bidirectional sync |
| Find out why it fails | Shell and debugging; Common errors catalogue; Inspecting SQL |
| Make it fast | Cache and prefetch; Performance; Indexes and EXPLAIN; Profiling |
| Prove it works and keep it working | Testing and quality; Git workflow |
| Move to a new Odoo version | Migration and versions |
| Ship and operate | Odoo.sh and deployment; Safe bulk scripts |

Real tasks cross several rows. "Add a field to the sales order and print it on the PDF" touches the ORM (field), Data and views (inheritance), PDF reports (QWeb), Security (does anyone need a group for it?), and Testing. The Blueprints show these combinations deliberately.

## Habits that pay off

- **Read the error first.** Most Odoo failures print a Python traceback or an XML/JS error naming the file and line. Read the last line, then the nearest frame in your code.
- **Reproduce on a scratch database.** A small database with only your module installed produces cleaner errors and faster restarts.
- **Look at the source.** Odoo is open code. When this book names a method or a template, find it in the `odoo/` and `addons/` folders of your installation. Reading the standard module that does what you want is the best documentation, and the book shows where to look for each topic.
- **Check the version.** Your server's version decides which advice applies. Run `odoo-bin --version` or read the version in `odoo/release.py` before following a recipe.
- **Keep changes small and reversible.** Commit often; run the read-only query before the write; test an upgrade on a copy.

## What this book does not do

It does not teach you the functional side of Odoo (how to configure accounting, how a sales process should work), it does not replace the official documentation for each standard app's user features, and it does not cover Odoo Studio, the no-code builder. It also does not attempt to be a complete API listing for every model; the reference chapters list what a developer needs often, and show how to find the rest in the source.

When the book and the source disagree, the source of your installed version is right and the book has a bug. Note the difference and move on.
