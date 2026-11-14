---
description: How Odoo turns models into tables, columns, constraints, and relation tables, and where its own metadata lives.
---

# The Odoo schema

Odoo never asks you to write `CREATE TABLE`. You declare a model in Python, and at install or update time the framework creates and alters tables to match. The mapping is regular enough to learn once: a model name gives a table name, a field type gives a column type, a `Many2many` gives a relation table, and a small set of `ir_*` tables record what the framework did and why. Knowing the rules lets you go from a Python class to the SQL (and back), find the rows behind a screen, and write a correct diagnostic query without opening the source. This chapter states the rules for Odoo 16 to 18, flags the points that differ by version, and finishes with a toolbox of discovery queries.

The teaching module `library` is used throughout: models `library.book`, `library.author`, `library.loan`, `library.tag`. The standard tables mentioned (`res_partner`, `ir_model`, ...) are the same in every Odoo database.

{% hint style="info" %}
Everything here describes behaviour of the Odoo 16, 17, and 18 series. Where a detail changed between them it is marked, and where it is stated without a marker it holds for all three. Whenever the exact column type or constraint matters to you, confirm it on your own database with `\d table_name` (the discovery habit this chapter teaches) rather than trusting a book.
{% endhint %}

## From model name to table name

The table name is the model's `_name` with dots replaced by underscores:

| Model | Table |
|---|---|
| `res.partner` | `res_partner` |
| `sale.order.line` | `sale_order_line` |
| `library.book` | `library_book` |
| `library.loan` | `library_loan` |

A model can override this with `_table = 'my_table'`, and a few standard models do. For a model you do not know, ask the registry instead of guessing (query below).

Not every model has a table:

- **Regular models** (`models.Model`) get a table.
- **Transient models** (`models.TransientModel`, used for wizards) get a table too. Odoo vacuums old rows from it periodically, so rows are short-lived.
- **Abstract models** (`models.AbstractModel`, mixins like `mail.thread`) have no table. Their fields are copied into the concrete models that inherit them.
- **Models with `_auto = False`** have no automatically created table. Reports commonly define one as a database view in `init()` (`CREATE VIEW sale_report AS ...`). They are listed by `\dv`, not `\dt`.

## The columns every table has

Each regular model table starts with an `id` primary key and four audit columns:

| Column | Type | Meaning |
|---|---|---|
| `id` | `integer`, from `<table>_id_seq` (`serial`) | primary key |
| `create_uid` | `integer`, foreign key to `res_users(id)`, `ON DELETE SET NULL` | user who created the row |
| `create_date` | `timestamp without time zone` | creation time, UTC |
| `write_uid` | `integer`, foreign key to `res_users(id)`, `ON DELETE SET NULL` | user of the last write |
| `write_date` | `timestamp without time zone` | time of the last write, UTC |

The audit columns exist because `_log_access` defaults to true; a model that sets `_log_access = False` (typical of high-volume technical tables, such as `ir_attachment`-like or log tables, and of `_auto = False` views) has none. Because `create_uid` and `write_uid` point at `res_users`, deleting a user is allowed even though their ids appear everywhere: the audit columns become NULL.

Other columns that appear by convention, not by rule: `active` (boolean, makes the ORM hide rows with false), `name`, `sequence`, `company_id`, `parent_id` and `parent_path` (when `_parent_store = True`, a varchar like `1/5/12/` that makes subtree queries a prefix match), and `state` (selection stored as its key). They are ordinary fields; they just recur.

## Field type to column type

| Field | Column type | Notes |
|---|---|---|
| `Integer` | `int4` | |
| `Float` | `float8` (`double precision`) | with `digits`, may be `numeric`; see hint |
| `Monetary` | `numeric` | no `digits` limit in the column |
| `Char` | `varchar` | `size=n` adds a limit: `varchar(n)` |
| `Text`, `Html` | `text` | |
| `Boolean` | `bool` | may be NULL on rows from before the field existed |
| `Date` | `date` | |
| `Datetime` | `timestamp` (without time zone) | stored as UTC |
| `Selection` | `varchar` | holds the key, e.g. `'available'`; no check constraint |
| `Binary` | `bytea`, or no column | default `attachment=True` stores the file in `ir_attachment` and the field has no column |
| `Image` | like `Binary` | |
| `Json` | `jsonb` | |
| `Many2one` | `int4` plus a foreign key | column name equals the field name, e.g. `author_id` |
| `Reference` | `varchar` | text `'model,id'`, no foreign key |
| `Many2oneReference` | `int4` | an id into a model named by another field; no foreign key |
| `One2many` | no column | the column is on the other model (the `inverse_name`) |
| `Many2many` | no column on either table | a separate relation table (below) |
| computed, not stored | no column | computed in Python on read |
| computed with `store=True`, related with `store=True` | a normal column | maintained by the ORM; stale if you write SQL |
| `Properties` | `jsonb` | free-form properties (Odoo 17 and later) |

A column exists only for stored fields. When a field is "missing" from the table, check whether it is computed without `store`, a `One2many`, a `Many2many`, or an attachment-backed binary.

{% hint style="info" %}
Versions. Whether `Float(digits=...)` creates a `numeric` or a `float8` column has varied; use `\d` on the real table. Translated `Char`/`Text`/`Html` fields (`translate=True`) are `jsonb` from Odoo 16, holding one entry per language code (`{"en_US": "Tidewater", "fr_FR": "..."}`); in Odoo 15 and earlier they are plain `varchar`/`text` and translations sit in `ir_translation`. Company-dependent fields (`company_dependent=True`) are stored in `ir_property` rows up to Odoo 17; from Odoo 18 they are, to my knowledge, a `jsonb` column on the model's own table keyed by company id (confirm in the release notes). In all versions reading them with SQL needs care.
{% endhint %}

## Many2one: the foreign key column

`author_id = fields.Many2one('library.author')` creates `author_id integer` and a foreign key `library_book_author_id_fkey` referencing `library_author(id)`. The `ondelete` argument sets the foreign-key action:

| `ondelete=` | Foreign key action |
|---|---|
| (not given) | `SET NULL` for an optional field; `RESTRICT` for a required one (Odoo refuses `set null` on a required field) |
| `'set null'` | `ON DELETE SET NULL` |
| `'restrict'` | `ON DELETE RESTRICT` |
| `'cascade'` | `ON DELETE CASCADE` (lines that cannot live without their header) |

`index=True` adds a B-tree index `library_book_author_id_index`. Without it, there is no index on the foreign key column, so joins from `library_author` to its books and deletes of an author need a scan of `library_book`. The index habits of [Indexes and EXPLAIN](indexes-and-explain.md) apply.

A One2many has no column. `loan_ids = fields.One2many('library.loan', 'book_id')` is a view of the `book_id` many2one on `library_loan`. To read it in SQL you query `library_loan WHERE book_id = ...`.

## Many2many: the relation table

`tag_ids = fields.Many2many('library.tag')` on `library.book` creates a table named from the two table names sorted alphabetically, joined, with `_rel` appended:

```
library_book_library_tag_rel
```

The two columns are named `<table>_id` for each side: `library_book_id` and `library_tag_id`. Both are `integer NOT NULL`, with foreign keys `ON DELETE CASCADE` to their parents, a unique constraint over the pair, and an index on the second column (so lookups from either side are indexed). Each row is one link; there is no `id`, no audit column, and so no way to know who linked what or when.

You can override any of the three names in the field definition:

```python
tag_ids = fields.Many2many('library.tag', relation='library_book_tag_rel',
                           column1='book_id', column2='tag_id')
```

Standard Odoo does this all the time, so the alphabetical rule describes the default, not every table. For example `res.users` and `res.groups` are linked by `res_groups_users_rel` with columns `gid` and `uid`. Never assume; ask the registry (query below).

PostgreSQL limits identifiers to 63 bytes, and Odoo refuses to create a relation table whose name would exceed it. For long model names the symptom is an error at module load telling you to pass `relation=` explicitly.

Reading a many2many in SQL is the join from [Joins](joins.md):

```sql
SELECT b.id, b.name->>'en_US' AS book, t.name->>'en_US' AS tag
FROM library_book b
JOIN library_book_library_tag_rel r ON r.library_book_id = b.id
JOIN library_tag t                  ON t.id = r.library_tag_id
ORDER BY b.id, t.id;
```

(That assumes translated `name` fields on both models; for a non-translated `Char` write `b.name`.)

## A worked example: Python to DDL

```python
class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Book'

    name = fields.Char(required=True, translate=True)
    isbn = fields.Char(size=13)
    state = fields.Selection([('available', 'Available'), ('lost', 'Lost')],
                             default='available', required=True)
    active = fields.Boolean(default=True)
    weight = fields.Float()
    author_id = fields.Many2one('library.author', ondelete='set null', index=True)
    tag_ids = fields.Many2many('library.tag')
    loan_ids = fields.One2many('library.loan', 'book_id')
    loan_count = fields.Integer(compute='_compute_loan_count', store=True)

    _sql_constraints = [
        ('isbn_unique', 'unique(isbn)', 'The ISBN must be unique.'),
    ]
```

After installing the module, `\d library_book` shows (abridged, with details that vary by release):

```
                                          Table "public.library_book"
    Column    |            Type             | Nullable |                 Default
--------------+-----------------------------+----------+------------------------------------------
 id           | integer                     | not null | nextval('library_book_id_seq'::regclass)
 create_uid   | integer                     |          |
 create_date  | timestamp without time zone |          |
 write_uid    | integer                     |          |
 write_date   | timestamp without time zone |          |
 name         | jsonb                       | not null |
 isbn         | character varying(13)       |          |
 state        | character varying           | not null |
 active       | boolean                     |          |
 weight       | double precision            |          |
 author_id    | integer                     |          |
 loan_count   | integer                     |          |
Indexes:
    "library_book_pkey" PRIMARY KEY, btree (id)
    "library_book_author_id_index" btree (author_id)
    "library_book_isbn_unique" UNIQUE CONSTRAINT, btree (isbn)
Foreign-key constraints:
    "library_book_author_id_fkey" FOREIGN KEY (author_id) REFERENCES library_author(id) ON DELETE SET NULL
    "library_book_create_uid_fkey" FOREIGN KEY (create_uid) REFERENCES res_users(id) ON DELETE SET NULL
    "library_book_write_uid_fkey" FOREIGN KEY (write_uid) REFERENCES res_users(id) ON DELETE SET NULL
Referenced by:
    TABLE "library_book_library_tag_rel" CONSTRAINT "library_book_library_tag_rel_library_book_id_fkey" ...
    TABLE "library_loan" CONSTRAINT "library_loan_book_id_fkey" ...
```

Note what is not in the table: `tag_ids` (a relation table) and `loan_ids` (a column on `library_loan`). Note also the constraint name: `_sql_constraints` entries become `<table>_<constraint name>`, here `library_book_isbn_unique`. That name is what appears in the error text, which is how you map a raw database error back to the declaration: `duplicate key value violates unique constraint "library_book_isbn_unique"`.

Odoo also writes a comment on each column with the field's label and on the table with the model's `_description`. These come out in the descriptive form of `\d`:

```sql
\d+ library_book
SELECT col_description('library_book'::regclass, attnum) AS label, attname
FROM pg_attribute
WHERE attrelid = 'library_book'::regclass AND attnum > 0 AND NOT attisdropped
ORDER BY attnum;
```

The labels give the screen name for each column, which helps when you meet an unfamiliar table.

{% hint style="info" %}
Versions. Up to Odoo 18, `_sql_constraints` is the mechanism. Later versions replace it with constraint objects declared on the class; the database objects and their naming stay close, but check the release notes of the version you work on.
{% endhint %}

## Inheritance and the table

How a model extends another decides what happens in the database.

- **Extension in place** (`_inherit = 'res.partner'` without a new `_name`): the new fields become columns on the **same** table `res_partner`. This is how modules add fields to standard models, and why `res_partner` grows wide.
- **Prototype inheritance** (`_name = 'x.y'` with `_inherit = 'a.b'`): a new model with its own new table, copying a's fields.
- **Delegation** (`_inherits = {'res.partner': 'partner_id'}`): the child has its own table with a required many2one to the parent table, and reads and writes of the inherited fields transparently go to the parent row. `res_users` is the standard example: a user row has a `partner_id`, and the user's name, email, and image live in `res_partner`.
- **Mixins** (abstract): no table of their own. `mail.thread` adds no column to your table; its data lives in `mail_message`, `mail_followers`, and friends, tied to your records by `model` and `res_id`.

Custom fields created through the UI or Studio are model fields too: their names start with `x_` and their rows in `ir_model_fields` have `state = 'manual'`, and they produce columns like any other stored field. They are not part of any module's Python, which is why they are easy to lose when a database is copied without the right database dump of the metadata tables.

## Odoo's own metadata tables

The `ir_*` tables are Odoo's catalogue about itself. These are the ones a developer reads.

### ir_model and ir_model_fields

`ir_model` lists every model; `ir_model_fields` lists every field, including those with no column:

```sql
SELECT m.model, m.name->>'en_US' AS label, m.transient
FROM ir_model m
WHERE m.model LIKE 'library.%'
ORDER BY m.model;
```

```
      model      |  label  | transient
-----------------+---------+-----------
 library.author  | Author  | f
 library.book    | Book    | f
 library.loan    | Loan    | f
 library.tag     | Tag     | f
(4 rows)
```

(`name` is `jsonb` from Odoo 16; in 15 and earlier read it as plain text.) The table behind a model:

```sql
SELECT model, replace(model, '.', '_') AS expected_table
FROM ir_model WHERE model = 'library.book';
```

`replace(model, '.', '_')` is right unless the model sets `_table`; confirm with `\dt library_book`.

List the fields of a model, stored or not:

```sql
SELECT name, ttype, relation, store, required, index, compute IS NOT NULL AS computed
FROM ir_model_fields
WHERE model = 'library.book'
ORDER BY name;
```

```
     name     |   ttype   |    relation    | store | required | index | computed
--------------+-----------+----------------+-------+----------+-------+----------
 active       | boolean   |                | t     | f        | f     | f
 author_id    | many2one  | library.author | t     | f        | t     | f
 create_date  | datetime  |                | t     | f        | f     | f
 create_uid   | many2one  | res.users      | t     | f        | f     | f
 display_name | char      |                | f     | f        | f     | t
 id           | integer   |                | t     | f        | f     | f
 isbn         | char      |                | t     | f        | f     | f
 loan_count   | integer   |                | t     | f        | f     | t
 loan_ids     | one2many  | library.loan   | f     | f        | f     | f
 name         | char      |                | t     | t        | f     | f
 state        | selection |                | t     | t        | f     | f
 tag_ids      | many2many | library.tag    | f     | f        | f     | f
 weight       | float     |                | t     | f        | f     | f
 write_date   | datetime  |                | t     | f        | f     | f
 write_uid    | many2one  | res.users      | t     | f        | f     | f
(15 rows)
```

The inherited technical field `display_name` is listed too, with no column. Some releases also list `__last_update` (non-stored). Fields you did not declare, such as `message_ids`, appear as soon as the model inherits a mixin.

`store = f` fields have no column. For a many2many the same table records the relation table and its two column names, so you never need to infer them:

```sql
SELECT name, relation, relation_table, column1, column2
FROM ir_model_fields
WHERE model = 'res.users' AND ttype = 'many2many';
```

Selection values live in `ir_model_fields_selection` (columns `field_id`, `value`, `name`, `sequence`), one row per option.

### ir_model_data: XML IDs

Every record created from a data file, and many created in code, has a row in `ir_model_data` that maps a stable name to a database id:

| Column | Meaning |
|---|---|
| `module` | the module that owns the record, e.g. `base` |
| `name` | the local part of the XML ID |
| `model` | the model of the record, e.g. `res.groups` |
| `res_id` | the record's `id` in that model's table |
| `noupdate` | if true, module updates do not overwrite this record's data |

The full XML ID is `module.name`. Resolve one in either direction:

```sql
-- XML ID to record id
SELECT model, res_id FROM ir_model_data WHERE module = 'base' AND name = 'group_user';

-- record to XML ID(s)
SELECT module || '.' || name AS xml_id, noupdate
FROM ir_model_data
WHERE model = 'res.groups' AND res_id = 1;
```

This is how you find the row behind `env.ref('base.group_user')` without a shell. It is also the first place to look when a "record was deleted" error appears at module update: an `ir_model_data` row exists, but its target is gone (a raw `DELETE` somewhere), and the update stops with a missing-reference error.

### ir_ui_view and the others

| Table | Content | Useful columns |
|---|---|---|
| `ir_ui_view` | every view | `name`, `model`, `type`, `arch_db` (the XML), `inherit_id`, `mode` (`primary` or `extension`), `key`, `priority`, `active` |
| `ir_act_window` | window actions | `name`, `res_model`, `view_mode`, `domain`, `context` |
| `ir_ui_menu` | the menu tree | `name`, `parent_id`, `action` (a reference string `ir.actions.act_window,<id>`), `sequence` |
| `ir_attachment` | files | `name`, `res_model`, `res_id`, `res_field`, `type`, `store_fname`, `file_size`, `mimetype`, `db_datas` |
| `ir_config_parameter` | system parameters | `key`, `value` |
| `ir_cron` | scheduled actions | `cron_name` (or the linked action), `active`, `interval_number`, `interval_type`, `nextcall` |
| `ir_module_module` | installed modules | `name`, `state`, `latest_version` |
| `ir_model_access` | ACL rows | `model_id`, `group_id`, `perm_read`, `perm_write`, `perm_create`, `perm_unlink` |
| `ir_rule` | record rules | `model_id`, `domain_force`, `global`, `groups` |
| `ir_sequence` | numbering sequences | `code`, `prefix`, `padding`, `number_next` |

A view's XML is in `arch_db`, which is how you see what a view really looks like after all inheritance is stored (but not applied; the combined view is built at load). Find the extensions of a view:

```sql
SELECT v.id, v.name, v.mode, v.priority
FROM ir_ui_view v
WHERE v.inherit_id = (SELECT id FROM ir_ui_view WHERE key = 'library.view_book_form')
ORDER BY v.priority, v.id;
```

(Use a real view key from your database; keys are `module.xmlid`.) Installed modules and their states:

```sql
SELECT name, state, latest_version
FROM ir_module_module
WHERE state IN ('installed', 'to upgrade', 'to install', 'to remove')
ORDER BY name;
```

Module `state` takes the values `uninstalled`, `installed`, `to install`, `to upgrade`, `to remove`, and `uninstallable`. A module stuck in `to upgrade` after an interrupted update is a common reason an instance refuses to start cleanly.

Be careful with attachment files: `ir_attachment.db_datas` holds file contents when `ir.attachment.location` is `db`; otherwise `store_fname` names a file on disk (the filestore) and the column is NULL. Select without `db_datas` unless you want megabytes.

## The core business tables

You will read these constantly. The names are stable across 16 to 18:

| Table | Notes |
|---|---|
| `res_partner` | every contact, company, and address. `parent_id` links a contact to its company; `is_company`; `type` (`contact`, `invoice`, `delivery`, ...); `active`; `company_id` optional |
| `res_users` | one row per login (`login`, `active`, `partner_id`, `company_id`, `share`). The person's name, email, and image are on the linked `res_partner` row. Never select the password column |
| `res_company` | companies, linked to a `partner_id`; `parent_id` for hierarchies |
| `res_groups` | security groups. Memberships in `res_groups_users_rel (gid, uid)`; implied groups in another relation table |
| `res_country`, `res_currency`, `res_lang` | reference data. `res_currency_rate` has the exchange rates |
| `mail_message` | chatter messages and logged notes: `model`, `res_id`, `body`, `message_type`, `author_id`, `date` |
| `mail_followers` | followers: `res_model`, `res_id`, `partner_id` |
| `product_template`, `product_product` | product and its variants; the variant has `product_tmpl_id` |
| `account_move`, `account_move_line` | invoices, bills, journal entries and their lines (all in one table pair, told apart by `move_type`) |
| `sale_order`, `sale_order_line`, `purchase_order`, `stock_picking`, `stock_move`, `stock_quant` | the usual document tables |

Two modelling patterns explain many joins:

- Generic references from `mail_message`, `ir_attachment`, and `mail_followers` use a pair of columns: the model name as a string, and the id as an integer, with no foreign key. "All messages of this partner" is `WHERE model = 'res.partner' AND res_id = 42`. Such rows are not removed by database cascades; the ORM deletes them when the owning record is unlinked, so a raw delete of the owner leaves orphans.
- The header/line pattern: a `*_line` table has a many2one to its header (`order_id`, `move_id`, `picking_id`), usually `ondelete='cascade'`, and the money totals on the header are stored computed fields maintained from the lines.

## Discovery queries

Keep these in a snippet file. They answer the first questions about any Odoo database.

**Row counts of the largest tables** (estimates, instant):

```sql
SELECT relname, reltuples::bigint AS approx_rows,
       pg_size_pretty(pg_total_relation_size(oid)) AS total_size
FROM pg_class
WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
ORDER BY pg_total_relation_size(oid) DESC
LIMIT 15;
```

On a database that has run for years, `ir_attachment` (when stored in the database), `mail_message`, `mail_tracking_value`, `bus_bus`, and accounting lines typically lead the list.

**Which tables reference `res_partner`** (and with what delete rule), the reason a contact cannot be deleted:

```sql
SELECT conrelid::regclass AS referencing_table,
       a.attname           AS column,
       CASE confdeltype WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT'
                        WHEN 'c' THEN 'CASCADE'  WHEN 'n' THEN 'SET NULL'
                        WHEN 'd' THEN 'SET DEFAULT' END AS on_delete
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
WHERE c.contype = 'f' AND c.confrelid = 'res_partner'::regclass
ORDER BY 1, 2;
```

**Columns that exist in the table but not in the registry**, a sign of removed fields (Odoo does not drop the column when a field disappears; it only drops the `NOT NULL`):

```sql
SELECT c.column_name
FROM information_schema.columns c
WHERE c.table_name = 'library_book'
  AND c.column_name NOT IN (SELECT name FROM ir_model_fields WHERE model = 'library.book' AND store)
ORDER BY 1;
```

**Which module defines a model.** `ir_model_data` rows for the model's `model_*` xml ids name the owners:

```sql
SELECT module, name FROM ir_model_data WHERE model = 'ir.model' AND res_id = (SELECT id FROM ir_model WHERE model = 'library.book');
```

**A record's chatter.** Messages of a record:

```sql
SELECT id, date, message_type, left(regexp_replace(body, '<[^>]+>', '', 'g'), 80) AS text
FROM mail_message
WHERE model = 'library.book' AND res_id = 1
ORDER BY date DESC
LIMIT 5;
```

The `regexp_replace` strips HTML tags so the body is readable in a terminal.

**Which cron jobs will run next:**

```sql
SELECT id, active, nextcall, interval_number, interval_type
FROM ir_cron
ORDER BY nextcall
LIMIT 10;
```

The `ir_cron` columns that name the job and its code differ between versions (the job's name is on the linked `ir_act_server` row in recent releases), so join accordingly or `\d ir_cron` first.

**The company of a record**, **the stored translation of a term**, **the properties of a record**: all of these follow the same recipe: find the model in `ir_model`, list its fields in `ir_model_fields`, then query the table.

## Reading translated and JSON values

In Odoo 16 and later a translated field is a JSON object:

```sql
SELECT id, name, name->>'en_US' AS en, name->>'fr_FR' AS fr
FROM library_book
ORDER BY id
LIMIT 3;
```

```
 id |                   name                    |     en     |       fr
----+-------------------------------------------+------------+-----------------
  1 | {"en_US": "Tidewater"}                    | Tidewater  |
  2 | {"en_US": "Salt Roads", "fr_FR": "Routes de sel"} | Salt Roads | Routes de sel
```

A missing language key gives NULL, not a fallback to English; the ORM applies the fallback in Python. When you filter with `ILIKE` against a translated field in SQL, filter on the key: `name->>'en_US' ILIKE '%road%'`. And when you update, use `jsonb_set` to change one language without erasing the others ([INSERT, UPDATE, DELETE](writing-data.md)).

## Pitfalls

- **Assuming `model.name` is `table_name`.** It is, until a model sets `_table`. Check `ir_model` and `\dt`.
- **Looking for a column that does not exist.** One2many, Many2many, non-stored computed fields, and attachment-backed binaries have none. Query `ir_model_fields` for `store`.
- **Guessing relation-table names.** Standard modules override them. Read `relation_table`, `column1`, and `column2` from `ir_model_fields`.
- **Writing a stored computed or related field in SQL and not its dependants.** The ORM will not recompute. Update both, or recompute in the shell.
- **Treating `jsonb` names as text.** On 16+, `WHERE name = 'x'` compares to a JSON value. Use `name->>'en_US'`.
- **Selecting binary columns by accident.** `SELECT *` on `ir_attachment` or `res_partner` (image fields in attachments) can transfer huge data. Name your columns.
- **Raw deletes leaving orphans.** No foreign key protects `mail_message`, `ir_attachment`, or `ir_model_data` rows that reference a deleted record by model name and id.
- **Believing `active` means deleted.** Archived rows are still there; a count that ignores `active` includes them. Odoo's UI count excludes them.
- **Joining `res_users` to `res_partner` incorrectly.** A user's display name is the partner's `name`. `res_users` has no name column of its own.
- **Reading local time out of UTC columns.** `create_date` and `write_date` are UTC. Convert deliberately.
- **Unique error names read as noise.** A constraint named `library_book_isbn_unique` tells you the module, the model, and the declaration; search the code for the suffix.

## Try it

Use any Odoo database you may read (a throwaway development database, or a restored copy; never a live production system), or reason from the `library_book` example if you have none.

1. Find the table and the stored columns of the model `res.partner` using `ir_model` and `ir_model_fields` (your database must be Odoo 16 or later to see jsonb labels; otherwise drop the `->>`). Which of its relational fields have no column?

2. For `res.users`, find every many2many field, with its relation table and the two column names. Then write the SQL join listing user logins and their group names for one user.

3. Resolve the XML ID `base.user_root` (or `base.main_company`) to a record id and a table, then fetch the row from that table.

4. Write a query that lists, for the model `library.book`, the foreign keys declared on its table, using `pg_constraint`, and compare with the `many2one` rows of `ir_model_fields`. Which foreign keys have no counterpart among the fields, and why?

5. Given the error `duplicate key value violates unique constraint "library_loan_book_member_uniq"`, work out the table, the likely `_sql_constraints` name, and the columns involved, using only the catalog.

<details>
<summary>Solution</summary>

1. 
```sql
SELECT name, ttype, relation, store
FROM ir_model_fields
WHERE model = 'res.partner'
ORDER BY store DESC, name;
```
The model's table is `res_partner`. Fields with `store = f` and `ttype` of `one2many` or `many2many` (for example `child_ids`, `category_id`, `user_ids`) have no column on `res_partner`, and non-stored computed fields (many) have none either. The remaining stored fields are the columns of `\d res_partner`.

2. 
```sql
SELECT name, relation, relation_table, column1, column2
FROM ir_model_fields
WHERE model = 'res.users' AND ttype = 'many2many';
```
For the groups, `groups_id` points at `res.groups` with relation table `res_groups_users_rel` and columns `uid`, `gid`. The join:
```sql
SELECT u.login, g.name->>'en_US' AS grp
FROM res_users u
JOIN res_groups_users_rel r ON r.uid = u.id
JOIN res_groups g           ON g.id = r.gid
WHERE u.login = 'someone'
ORDER BY 2;
```
On Odoo 16 and later `res_groups.name` is `jsonb`; in earlier versions use `g.name`.

3. 
```sql
SELECT model, res_id FROM ir_model_data WHERE module = 'base' AND name = 'user_root';
```
The result names `res.users` and an id. The table is `res_users`: `SELECT id, login, partner_id FROM res_users WHERE id = <res_id>;`.

4. 
```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'library_book'::regclass AND contype = 'f';

SELECT name, relation FROM ir_model_fields
WHERE model = 'library.book' AND ttype = 'many2one' AND store;
```
Both lists contain `author_id`, `create_uid`, and `write_uid`: every stored many2one has one foreign key, named `<table>_<column>_fkey`. The foreign keys that are not many2one fields live on other tables: the relation table `library_book_library_tag_rel` carries two (to `library_book` and `library_tag`), and `library_loan` carries one pointing at `library_book`. They appear under "Referenced by" in `\d library_book`, not in its own constraint list.

5. 
```sql
SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'library_loan_book_member_uniq';
```
The result gives the table `library_loan` and a definition such as `UNIQUE (book_id, member_id)`. The Odoo name is the part after `library_loan_`: the `_sql_constraints` entry called `book_member_uniq` in the `library.loan` model.

</details>
