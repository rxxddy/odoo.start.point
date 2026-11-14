---
description: "Notation used throughout, and how version differences from Odoo 16 to 20 are marked."
---

# Conventions and version notes

Small decisions in notation decide whether a code sample can be pasted or has to be decoded. This chapter lists them in one place: how code, commands, and placeholders are written, what each hint colour means, how version differences between Odoo 16 and 20 are marked, and what the teaching module `library` is. Read it once; refer back when a notation puzzles you.

## Code and commands

**Code blocks** carry a language tag (`python`, `xml`, `js`, `bash`, `sql`, `text`, `json`). A block is one of three kinds, and the text around it says which:

- **Runnable**: complete enough to run as written. Python snippets run in a plain interpreter or the Odoo shell; JavaScript snippets run in Node as `.mjs` files (or the browser console when marked `// browser`); SQL runs in `psql`.
- **Fragment**: a piece of a larger file, marked with a comment such as `# fragment` or `<!-- fragment -->`. It shows the lines that matter and omits imports, surrounding classes, or manifest entries.
- **Output**: plain `text` blocks, or trailing `# ...` comments that show what a statement prints.

**Shell commands** are written for Bash. A line beginning with `$` is not used: commands are shown without a prompt so they can be copied. Long commands break with a trailing backslash:

```bash
odoo-bin -d <db> -i library \
  --stop-after-init \
  --log-level=info
```

On Windows PowerShell, the line continuation is the backtick, environment variables are set with `$env:NAME = "value"`, and paths use backslashes. Where a Windows variation matters, the text gives it. In SQL examples, `psql` meta-commands (`\d table`) are used where they are shorter than the catalogue query.

**Inline names** use code font: `library.book`, `partner_id`, `res.partner`, `action_library_book`, `odoo-bin`. File paths use forward slashes: `library/models/book.py`.

**Ellipsis** (`...`) inside code means "omitted here", never valid syntax to copy. In Python, a literal `Ellipsis` is never used in the book's examples.

**Python style** follows the project coding standards covered in the testing part: four-space indentation, double or single quotes consistently within a file, and Odoo naming conventions (`_name = "library.book"`, method names `action_*`, `_compute_*`, `_onchange_*`, `_check_*`). **JavaScript style** uses ES modules, `const`/`let`, double quotes, semicolons, and four spaces in Odoo-facing code but two in short generic snippets for width.

**Command safety.** Commands that change data are always preceded by their read-only counterpart. If the book shows `UPDATE`, you will see the `SELECT` with the same `WHERE` first. If it shows `-u library`, it first shows how to check what the update would touch. This is a convention of the book and a habit to copy.

## Placeholders

Angle brackets mark a value you replace. They are never typed literally.

| Placeholder | Means | Example value |
|-------------|-------|---------------|
| `<db>` | Name of a PostgreSQL database | `library_dev` |
| `<model>` | Technical model name | `library.book` |
| `<module>` | Technical module name (directory name) | `library` |
| `<field>` | A field name on a model | `year` |
| `<xml_id>` | Full external identifier `module.name` | `library.book_dune` |
| `<login>`, `<password>` | Credentials; never commit real ones | |
| `<uid>` | Numeric user id | `2` |
| `<host>`, `<port>` | Network address of a server | `localhost`, `8069` |
| `<path>` | A filesystem path you choose | |
| `<version>` | An Odoo version number | `18.0` |
| `<ids>` | A list of record ids | `[1, 2, 3]` |

All names, people, and numbers in examples are invented. Example people are "Ann" and "Bob"; example books are well-known public-domain titles. Hosts are `localhost` or `example.com`-style reserved names. No example contains a real client, a real company, or real data, and neither should yours when you copy it into a ticket or a forum post.

## Hints

The book uses GitBook hint boxes, sparingly. They have fixed meanings:

{% hint style="info" %}
Info. Background, a version note, or a pointer to another chapter. Safe to skip on a first read.
{% endhint %}

{% hint style="warning" %}
Warning. A pitfall that costs time: a behaviour that looks like it works and does not, or that works only in certain conditions.
{% endhint %}

{% hint style="danger" %}
Danger. Data loss, a security hole, or a breaking change. If you ignore a danger hint, the damage may not be reversible.
{% endhint %}

{% hint style="success" %}
Success. The recommended practice when several options exist.
{% endhint %}

Tabs, where used, separate per-version or per-operating-system variants of the same step. They are never used for content that every reader needs.

## Exercises

A "Try it" section ends most chapters. Solutions sit inside `<details><summary>Solution</summary> ... </details>` blocks, which render as folds in GitBook and in any Markdown viewer that supports HTML.

## Version notes

The book targets Odoo 16 through 20 (the number is the major version; each release is `<number>.0`). Text is written for the newest version that has been verified, and differences are marked, never silently blended.

### How differences are marked

1. **An info hint headed "Versions"** for a difference that changes how you write code but does not break old code:

   {% hint style="info" %}
   Versions: the view root `<tree>` was replaced by `<list>` in 18. Version 17 and earlier require `<tree>`.
   {% endhint %}

2. **A danger hint** for a breaking change: code written for one version fails or silently misbehaves on another.

   {% hint style="danger" %}
   Versions: view attributes `attrs` and `states` were removed in 17. Code that uses them loads in 16 and fails in 17 and later.
   {% endhint %}

3. **A "Versions" section** at the end of a chapter when the differences are several and belong together. The chapter "Version differences, 16 to 20" in the migration part collects them across the whole book, and "Deprecations and replacements" lists the old name next to the new one.

4. **Tabs** for side-by-side code that differs between versions, so you can read your own version and ignore the other.

A statement without a version mark holds for every version in scope. If a hint says "Odoo 17 and later", it holds from 17 to the newest verified release unless a later hint says otherwise. Where a behaviour is the same but a name changed, the text gives both names.

The examples above are real differences, and they show the style. Read the details in the chapters where they occur.

### What "verified" means

Every standard-Odoo name in the book (a model, a field, an XML ID, a method, a template) was checked against real source code of at least one release before it was written. Where a name could not be checked, it is left out rather than guessed; when you see an instruction to "check the source for your version", it is because that detail varies and the book could not pin it down for every release.

Examples were run against a real Odoo 18 installation unless a chapter says otherwise. Behaviour in 16 and 17 is marked where it is known to differ; behaviour that has not been checked in a given release is not claimed for it.

{% hint style="warning" %}
Odoo 20 content is added only after it can be verified against a release. Until then the book does not state anything specific about Odoo 20: statements marked "and later" mean "up to the newest verified release", and you must check the version-differences chapter and your own installation before assuming they hold for 20.
{% endhint %}

### Checking your version

```bash
# From the installation directory
python odoo-bin --version

# From the Odoo shell
env["ir.module.module"].search([("name", "=", "base")]).latest_version

# From the source
grep version_info odoo/release.py
```

The first prints the series (for example `Odoo Server 18.0`). The shell command reads the installed version of the `base` module in the current database, which can lag the source after a code upgrade until you run `-u base`. Odoo.sh exposes the version in the branch settings. Learn which of these your team trusts and use it.

### Editions and platforms

Odoo exists as Community and Enterprise, and as Odoo Online and Odoo.sh. The book covers what a module developer meets in Community and notes where behaviour needs Enterprise or depends on the platform (Odoo.sh restrictions are in their own chapter). Enterprise modules are not available for inspection in every setup; when the text refers to an Enterprise-only feature it says so.

## The neutral teaching module: `library`

Almost every example in the book uses a small module called `library`. It exists only to teach, so that no example drags in a real business's rules.

Models:

| Model | Purpose | Notable fields |
|-------|---------|----------------|
| `library.book` | A title in the catalogue | `name`, `isbn`, `year`, `author_id`, `tag_ids`, `copies`, `state` |
| `library.loan` | A book lent to a member | `name`, `book_id`, `member_id`, `date_out`, `date_due`, `date_back`, `state`, `line_ids` |
| `library.loan.line` | One line of a loan | `loan_id`, `book_id`, `copies` |
| `library.tag` | A label for books | `name`, `color` |

Members are standard partners (`res.partner`), authors too. Using real standard models next to the invented ones lets examples show relationships to things that exist in every installation.

External IDs follow a fixed pattern so they can be recognised: `library.book_dune` is a demo book, `library.library_book_view_form` is a form view (`<module>_<model>_view_<type>`), `library.action_library_book` is a window action, `library.menu_library_books` is a menu, `library.group_library_manager` is a security group. Example people: Ann and Bob. Example books: Dune, Emma, Ulysses.

The `library` module is not an installable package you must obtain; the Blueprints part builds it from scratch, and every chapter's snippets are self-explanatory without it. When a snippet uses a field of `library.book`, the field is shown or its type is evident from use.

When a standard Odoo model is the better teacher (a sale order for extending a workflow, a partner for relationships), the chapter uses it and says so.

## Terms used consistently

A few words are used in one sense only, to avoid confusion:

- **Module** and **addon**: an Odoo module is a directory with a manifest; "addon" refers to the same thing in the context of the addons path. The book uses "module" for the thing you write and "addons path" for where Odoo finds them.
- **Record** is one database row of a model; **recordset** is an ordered collection of records of one model (possibly empty, possibly one).
- **Model** is the Python class and its database table; **table** is only the database side.
- **XML ID** (also external ID) is the `module.name` identifier stored in `ir.model.data`.
- **Backend** is the web client used by internal users, **website** the public pages, **portal** the logged-in customer area.
- **Staging** and **production** are environments; "production" is never changed without a copy-first plan.

The glossary in the reference part defines the rest.

## When you find a mistake

A name that does not exist in your version, an example that does not run, or a statement the source contradicts is a bug in the book, not in you. Reproduce it on a scratch database, note your version and the exact error, and compare with the source of your installation. In practice this takes five minutes and teaches more than the chapter did.
