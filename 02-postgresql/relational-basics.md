---
description: Tables, keys, types, and constraints, with the small library schema the rest of this part uses.
---

# Relational basics

Odoo keeps every record in PostgreSQL, and sooner or later you will need to look at the rows themselves: to see what a script really wrote, to find out why a constraint fired, or to repair data the ORM cannot reach. This chapter gives you the vocabulary (table, row, key, constraint, type, sequence), a lab database you can break freely, and the habits that keep a relational schema honest. Every later chapter in this part runs against the lab schema defined here.

## The model in five sentences

A database holds tables. A table has a fixed list of named, typed columns and any number of rows. Each row is one record; each column holds one value per row. Rows have no inherent order, and a table is a set in spirit: if you need an order you ask for it. Tables refer to each other by storing the key of the row they point at.

That last sentence is the whole "relational" idea. A loan does not contain a copy of the book; it contains the book's `id`. Change the title once, and every loan sees it. The cost is that you need a join to read the title next to the loan (chapter [Joins](joins.md)), and the benefit is that there is exactly one place where each fact lives.

Odoo's ORM is a translation layer over this model. A model is a table, a record is a row, a field is a column, a `Many2one` is a stored key. When the ORM misbehaves, the table is the ground truth.

## A lab database

Install PostgreSQL 14 or newer locally (Odoo 16 to 18 support 12 and up; 14+ is a safe baseline for this book). Create a scratch database that you never confuse with a real one:

```bash
createdb handbook_lab
psql -d handbook_lab
```

`createdb` and `psql` connect through the local socket (Linux/macOS) or TCP on `localhost:5432` (Windows) as your operating-system user, unless you pass `-h`, `-p`, `-U`. If your install needs a password, `psql -h localhost -U postgres -d handbook_lab` will ask for it. When you finish with the book you remove everything with `dropdb handbook_lab`.

{% hint style="warning" %}
Run the exercises of this part only on a database you created for it. Several examples delete rows and hold locks on purpose. Never point them at a database that belongs to a running system, and never at a customer or production database.
{% endhint %}

You are in the `psql` prompt when you see `handbook_lab=#`. Two things to know right now: every SQL statement ends with a semicolon, and backslash commands (`\dt`, `\d table`, `\q`) are psql's own, not SQL. The full tour of psql is in [psql and operations](psql-and-operations.md).

## Column types you will meet

PostgreSQL has dozens of types. These cover almost everything Odoo creates and everything this book uses:

| Type | Holds | Odoo field that produces it |
|---|---|---|
| `integer` (`int4`) | whole numbers, about +/- 2.1 billion | `Integer`, `Many2one` key columns, `id` |
| `bigint` (`int8`) | whole numbers, about +/- 9.2e18 | rarely; some counters |
| `numeric(p,s)` | exact decimals | `Monetary`; `Float` with `digits` (see hint) |
| `double precision` (`float8`) | binary floating point | `Float` without `digits` |
| `varchar` / `text` | strings; no practical length difference | `Char`, `Selection` (varchar); `Text`, `Html` (text) |
| `boolean` | true, false, or NULL | `Boolean` |
| `date` | a calendar day | `Date` |
| `timestamp` (without time zone) | a date and time, no zone attached | `Datetime` (stored as UTC by convention) |
| `timestamptz` | an absolute instant | not used by Odoo fields; common in logs |
| `bytea` | raw bytes | `Binary` stored in the database |
| `jsonb` | parsed JSON | `Json`; translated `Char`/`Text`/`Html` fields since Odoo 16 |

{% hint style="info" %}
Versions. The `jsonb` storage for translatable fields arrived in Odoo 16: before that, translations lived in the separate `ir_translation` table and the column held the source term as plain text. Whether a `Float` with `digits` becomes `numeric` or stays `double precision` has also changed over time. Do not guess; run `\d your_table` on your own database and read the column type.
{% endhint %}

Two rules about types save a lot of grief.

First, money and anything where `0.1 + 0.2` must equal `0.3` belongs in `numeric`, never in floating point:

```sql
SELECT 0.1::float8 + 0.2::float8 AS float_sum,
       0.1::numeric + 0.2::numeric AS numeric_sum;
```

```
      float_sum      | numeric_sum
---------------------+-------------
 0.30000000000000004 |         0.3
(1 row)
```

Second, `varchar(n)`, `varchar`, and `text` are stored identically. The length limit is only a check. Odoo's `Char` fields create an unbounded `varchar` unless `size` is set, so do not invent length limits in your own tables for "performance"; there is none.

## The teaching schema

The library schema has four tables: `authors`, `books`, `members`, `loans`. A book has at most one author (the key may be empty), a loan ties a member to a book for a period. It is small enough to hold in your head and rich enough to need every kind of join.

Paste this into psql. It is the only setup the rest of the part needs; if you drop and recreate the lab, run it again.

```sql
CREATE TABLE authors (
    id         serial PRIMARY KEY,
    name       varchar NOT NULL,
    born_year  integer,
    country    varchar
);

CREATE TABLE books (
    id              serial PRIMARY KEY,
    title           varchar NOT NULL,
    author_id       integer REFERENCES authors (id) ON DELETE SET NULL,
    published_year  integer,
    price           numeric(8,2),
    pages           integer,
    status          varchar NOT NULL DEFAULT 'available',
    CONSTRAINT books_pages_positive CHECK (pages > 0)
);

CREATE TABLE members (
    id         serial PRIMARY KEY,
    name       varchar NOT NULL,
    email      varchar UNIQUE,
    joined_on  date NOT NULL,
    active     boolean NOT NULL DEFAULT true
);

CREATE TABLE loans (
    id           serial PRIMARY KEY,
    book_id      integer NOT NULL REFERENCES books (id) ON DELETE RESTRICT,
    member_id    integer NOT NULL REFERENCES members (id) ON DELETE RESTRICT,
    loaned_on    date NOT NULL,
    due_on       date NOT NULL,
    returned_on  date
);

INSERT INTO authors (name, born_year, country) VALUES
    ('Ada Marlowe',   1950, 'UK'),
    ('Boris Venn',    1962, 'US'),
    ('Chiara Lund',   1975, 'IT'),
    ('Dmitri Okafor', 1981, NULL);

INSERT INTO books (title, author_id, published_year, price, pages, status) VALUES
    ('Tidewater',       1,    1998, 12.50, 310, 'available'),
    ('Salt Roads',      1,    2004, 15.00, 420, 'available'),
    ('The Long Ledger', 2,    2010,  9.90, 250, 'lost'),
    ('Paper Moons',     2,    2015, 11.00, 180, 'available'),
    ('Quiet Engines',   3,    2019, 18.00, 520, 'available'),
    ('Orphan Volume',   NULL, 2001,  5.00,  90, 'available');

INSERT INTO members (name, email, joined_on, active) VALUES
    ('Nora',  'nora@example.com',  '2023-01-10', true),
    ('Omar',  'omar@example.com',  '2023-03-05', true),
    ('Petra', NULL,                '2024-02-20', true),
    ('Quinn', 'quinn@example.com', '2024-06-01', false);

INSERT INTO loans (book_id, member_id, loaned_on, due_on, returned_on) VALUES
    (1, 1, '2024-01-05', '2024-01-19', '2024-01-18'),
    (2, 1, '2024-02-01', '2024-02-15', '2024-02-20'),
    (1, 2, '2024-03-10', '2024-03-24', NULL),
    (5, 2, '2024-03-12', '2024-03-26', '2024-03-25'),
    (4, 3, '2024-04-02', '2024-04-16', NULL),
    (1, 3, '2024-05-01', '2024-05-15', '2024-05-10'),
    (5, 1, '2024-05-20', '2024-06-03', '2024-06-01');
```

Check that it landed:

```sql
SELECT id, title, author_id, price FROM books ORDER BY id;
```

```
 id |      title      | author_id | price
----+-----------------+-----------+-------
  1 | Tidewater       |         1 | 12.50
  2 | Salt Roads      |         1 | 15.00
  3 | The Long Ledger |         2 |  9.90
  4 | Paper Moons     |         2 | 11.00
  5 | Quiet Engines   |         3 | 18.00
  6 | Orphan Volume   |           |  5.00
(6 rows)
```

The empty cell in `author_id` is NULL. Three properties of this data are deliberate, and later chapters depend on them:

- Author 4 (Dmitri) wrote no book, so a join from authors to books must decide what to do with him.
- Book 6 has no author, so a join from books to authors must decide what to do with it.
- Loans 3 and 5 are not returned yet (`returned_on` is NULL), and member 4 never borrowed anything.

Real Odoo data has exactly these gaps everywhere: optional many2one fields, unreturned or unposted documents, partners that never bought anything.

## Primary keys

A primary key is a column (or set of columns) whose value identifies a row uniquely and is never NULL. PostgreSQL enforces it with a unique index. Odoo gives every table an `id` primary key and nothing else; compound keys do not exist in Odoo models, and uniqueness over several fields is expressed as a separate `UNIQUE` constraint.

Why a surrogate integer `id` rather than "the real key" such as an ISBN or an email? Real-world identifiers change, get reused, or turn out to be non-unique. An `id` the database generates never changes meaning. Keep the natural identifier as an ordinary `UNIQUE` column.

## Foreign keys and what happens on delete

A foreign key says "this column must contain the key of an existing row in that table, or be NULL". The database refuses anything else:

```sql
INSERT INTO books (title, author_id) VALUES ('Ghost Writer', 99);
```

```
ERROR:  insert or update on table "books" violates foreign key constraint "books_author_id_fkey"
DETAIL:  Key (author_id)=(99) is not present in table "authors".
```

The second half of the contract is what happens when the referenced row is deleted. You pick the behaviour per foreign key:

| `ON DELETE` | Effect on the referencing row | Typical Odoo use |
|---|---|---|
| `RESTRICT` / `NO ACTION` | the delete of the parent fails | required many2one without a better idea |
| `SET NULL` | the child's column becomes NULL | optional many2one (Odoo's usual default) |
| `CASCADE` | the child row is deleted too | lines owned by their header (`ondelete='cascade'`) |

`books.author_id` is `SET NULL`; `loans.book_id` is `RESTRICT`. Try both. First the read-only look at what would be affected:

```sql
SELECT id, title, author_id FROM books WHERE author_id = 3;
```

```
 id |     title     | author_id
----+---------------+-----------
  5 | Quiet Engines |         3
(1 row)
```

Now delete the author inside a transaction you will roll back, so the lab data stays intact (transactions are covered properly in [Transactions and isolation](transactions-and-isolation.md); for now `BEGIN` opens one and `ROLLBACK` throws it away):

```sql
BEGIN;
DELETE FROM authors WHERE id = 3;
SELECT id, title, author_id FROM books WHERE id = 5;
ROLLBACK;
```

```
DELETE 1
 id |     title     | author_id
----+---------------+-----------
  5 | Quiet Engines |
(1 row)
```

The book survived and lost its author. Now the same experiment on `RESTRICT`:

```sql
BEGIN;
DELETE FROM books WHERE id = 1;
ROLLBACK;
```

```
ERROR:  update or delete on table "books" violates foreign key constraint "loans_book_id_fkey" on table "loans"
DETAIL:  Key (id)=(1) is still referenced from table "loans".
```

In a failed transaction PostgreSQL refuses further commands until you finish it; the `ROLLBACK` clears the state. You will meet this in Odoo as `InFailedSqlTransaction` ("current transaction is aborted, commands ignored until end of transaction block") when code catches an SQL error and carries on without a savepoint. Chapter [Transactions and isolation](transactions-and-isolation.md) explains the fix.

{% hint style="info" %}
Versions. In Odoo 16 to 18 a `Many2one` creates the foreign key with `ON DELETE SET NULL` unless you pass `ondelete=`, and Odoo refuses `set null` on a required field at model setup. Check the actual constraint with `\d table` rather than trusting memory; modules can and do override it.
{% endhint %}

## NOT NULL, UNIQUE, CHECK

Three more constraints round out the toolkit. They all fire at the moment of the write, inside the statement.

```sql
INSERT INTO books (title, pages) VALUES (NULL, 100);
```

```
ERROR:  null value in column "title" of relation "books" violates not-null constraint
DETAIL:  Failing row contains (8, null, null, null, null, 100, available).
```

```sql
INSERT INTO members (name, email, joined_on) VALUES ('Nora II', 'nora@example.com', '2024-07-01');
```

```
ERROR:  duplicate key value violates unique constraint "members_email_key"
DETAIL:  Key (email)=(nora@example.com) already exists.
```

```sql
INSERT INTO books (title, pages) VALUES ('Empty Book', 0);
```

```
ERROR:  new row for relation "books" violates check constraint "books_pages_positive"
DETAIL:  Failing row contains (9, Empty Book, null, null, null, 0, available).
```

Note the ids in the `DETAIL` lines: 8 and 9. The failed inserts still consumed sequence values (7 went to the foreign-key failure earlier). We come back to that below.

A `UNIQUE` constraint treats NULLs as distinct. Petra has no email, and so does any number of other members, without violating `members_email_key`:

```sql
INSERT INTO members (name, joined_on) VALUES ('Rhea', '2024-07-02'), ('Sven', '2024-07-03');
SELECT id, name, email FROM members ORDER BY id;
```

```
INSERT 0 2
 id | name  |       email
----+-------+-------------------
  1 | Nora  | nora@example.com
  2 | Omar  | omar@example.com
  3 | Petra |
  4 | Quinn | quinn@example.com
  6 | Rhea  |
  7 | Sven  |
(6 rows)
```

(Rhea is 6 and not 5 because the failed duplicate insert burned value 5 of the members sequence. Your numbers depend on how many failures you triggered; the shape is what matters.) Remove them to keep later results as printed:

```sql
SELECT id, name FROM members WHERE id > 4;
DELETE FROM members WHERE id > 4;
```

On PostgreSQL 15 and newer, `UNIQUE NULLS NOT DISTINCT` flips that behaviour. Odoo's `_sql_constraints` (up to 18) creates ordinary `UNIQUE` constraints named `<table>_<constraint name>`, so they behave like `members_email_key` above: several NULLs pass.

## Sequences: where the ids come from

`serial` is shorthand. `id serial PRIMARY KEY` expands into: an `integer` column, a sequence called `books_id_seq`, a default of `nextval('books_id_seq')`, and `NOT NULL`. Odoo creates `id SERIAL NOT NULL, PRIMARY KEY(id)` for every model, and its sequence is `<table>_id_seq`. You can see all of it:

```sql
\d books
```

```
                                     Table "public.books"
     Column     |       Type        | Collation | Nullable |              Default
----------------+-------------------+-----------+----------+-----------------------------------
 id             | integer           |           | not null | nextval('books_id_seq'::regclass)
 title          | character varying |           | not null |
 author_id      | integer           |           |          |
 published_year | integer           |           |          |
 price          | numeric(8,2)      |           |          |
 pages          | integer           |           |          |
 status         | character varying |           | not null | 'available'::character varying
Indexes:
    "books_pkey" PRIMARY KEY, btree (id)
Check constraints:
    "books_pages_positive" CHECK (pages > 0)
Foreign-key constraints:
    "books_author_id_fkey" FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE SET NULL
Referenced by:
    TABLE "loans" CONSTRAINT "loans_book_id_fkey" FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE RESTRICT
```

Sequences are non-transactional by design. A rolled-back insert does not give its number back, because another session may already have taken the next one. Consequences:

- Gaps in `id` are normal and carry no meaning. Never write code that assumes ids are consecutive, and never "fix" a gap.
- Two sessions inserting concurrently get distinct ids without waiting for each other. That is why sequences scale.

The other end of the same fact is the classic post-restore bug. If you load rows with explicit ids (an `INSERT ... (id, ...)`, a `COPY`, a data migration), the sequence does not move. The next ordinary insert then collides with an existing row:

```sql
SELECT max(id) AS max_id, (SELECT last_value FROM books_id_seq) AS seq_last FROM books;
```

If `seq_last` is lower than `max_id`, you are one insert away from `duplicate key value violates unique constraint "books_pkey"`. The repair, after you have looked at the numbers above:

```sql
SELECT setval('books_id_seq', (SELECT max(id) FROM books));
```

`pg_dump` and a restore handle this for you; hand-rolled imports do not.

PostgreSQL 10 added the standard `GENERATED ... AS IDENTITY` column. It behaves the same for our purposes and is what you would choose in a new non-Odoo schema. Odoo still creates `serial`, so this book does too.

## Why tables get split: a short normalization story

Suppose you wanted to avoid the `authors` table and stored the author's name and country directly in each book row:

```
 id |     title     | author_name | author_country
----+---------------+-------------+----------------
  1 | Tidewater     | Ada Marlowe | UK
  2 | Salt Roads    | Ada Marlowe | UK
```

Now Ada moving country means updating every one of her books, and forgetting one leaves the data contradicting itself. A book whose author is spelled "Ada Marlow" is a different author as far as any `GROUP BY` is concerned. Splitting the author into its own table and pointing at it by key removes the whole class of contradiction: one fact, one row.

The rule of thumb: a column should depend on the key of its own row and nothing else. If a column's value is determined by another column in the same row (country by author), it belongs in the table that column is the key of.

The same logic explains many-to-many relations. A book can have several authors and an author several books; a single `author_id` column cannot express that. You create a third table whose rows are pairs:

```sql
CREATE TABLE book_author_rel (
    book_id    integer NOT NULL REFERENCES books (id)   ON DELETE CASCADE,
    author_id  integer NOT NULL REFERENCES authors (id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, author_id)
);
```

Odoo's `Many2many` creates exactly this: a relation table with two integer columns, two cascading foreign keys, a unique index over the pair, and one extra index. [The Odoo schema](the-odoo-schema.md) covers the naming rules. The table above is only to show the pattern; you will not need it for the exercises, and you can drop it (`DROP TABLE book_author_rel;`).

The opposite mistake exists too: splitting without reason. Odoo accepts denormalized, stored computed fields (`store=True`) on purpose, trading the contradiction risk for read speed, and keeps them in sync through the ORM. When you edit such a column with raw SQL you take on the job of the recompute. More on that in [INSERT, UPDATE, DELETE](writing-data.md) and in the ORM part.

## Looking around: the catalog

PostgreSQL describes itself in ordinary tables you can query. You will use these all the time against Odoo databases:

```sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'loans'
ORDER BY ordinal_position;
```

```
 table_name | column_name | data_type         | is_nullable
------------+-------------+-------------------+-------------
 loans      | id          | integer           | NO
 loans      | book_id     | integer           | NO
 loans      | member_id   | integer           | NO
 loans      | loaned_on   | date              | NO
 loans      | due_on      | date              | NO
 loans      | returned_on | date              | YES
(6 rows)
```

And the list of tables with an estimate of their row counts:

```sql
SELECT relname AS table_name, reltuples::bigint AS approx_rows
FROM pg_class
WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
ORDER BY relname;
```

```
 table_name | approx_rows
------------+-------------
 authors    |          -1
 books      |          -1
 loans      |          -1
 members    |          -1
(4 rows)
```

`-1` (PostgreSQL 14 and later) means "never analyzed yet"; after `ANALYZE` or autovacuum, it holds the estimate. `reltuples` is an estimate, never an exact count. For an exact number use `SELECT count(*) FROM ...`, which on a large table is a full scan.

## Schemas and databases

A PostgreSQL server hosts several databases; a connection belongs to exactly one, and you cannot query across them. Inside a database, tables live in schemas, and `public` is the default. The `search_path` setting decides which schema an unqualified name like `books` resolves in. Odoo uses a single schema and one database per Odoo "database" (the thing you pick on the login screen). When a script says "the database", it means this: one connection, one Odoo instance's worth of tables, with no schema prefixes needed.

## Pitfalls

- **Treating row order as stable.** `SELECT * FROM books` without `ORDER BY` often returns insertion order today and something else after an `UPDATE` or a vacuum. Odoo's `_order` always adds an `ORDER BY`; in raw SQL you must too.
- **Float for money.** `double precision` sums drift. If a computed total is off by `0.000000001`, look at the column type first.
- **Counting on gapless ids.** Rollbacks, failed inserts, and concurrent sessions leave holes. Use a dedicated `ir.sequence` (Odoo) or a locking scheme if you need gapless numbering, and expect it to serialize writers.
- **Setting ids by hand and forgetting the sequence.** After any import with explicit ids, compare `max(id)` with the sequence's `last_value`.
- **Assuming a unique constraint blocks duplicate NULLs.** It does not (before PostgreSQL 15's `NULLS NOT DISTINCT`, and not by default after). A "unique code" field with several empty values is legal.
- **Relying on `ON DELETE CASCADE` you did not read.** A cascade from `res.partner` can remove far more than you expect. Read `\d table` and the "Referenced by" list before any delete.
- **Mixing up the failed-transaction state.** After an SQL error inside a transaction every later statement fails with "current transaction is aborted". The cure is `ROLLBACK` or a `SAVEPOINT`, never "just try again".
- **Case-sensitive names by accident.** `CREATE TABLE "Books"` with quotes makes a table you must always quote. Odoo's names are lowercase with underscores; keep yours the same.

## Try it

Work in `handbook_lab` with the schema above loaded. Wrap anything that changes data in `BEGIN; ... ROLLBACK;` unless told otherwise.

1. List every column of `members` with its type and whether it accepts NULL, using `information_schema.columns`. Which column has a default, and what is it?

2. Make the sequence trap happen on purpose: insert a book with an explicit `id` of 100, then insert one without an id, and read the ids. Then insert one more explicit `id` equal to the sequence's next value and observe the error. (Do it in a transaction you roll back; note that the sequence itself does not roll back.)

3. Find out which tables reference `members`, and with what `ON DELETE` rule, using only `\d members` and then using the catalog view `information_schema.referential_constraints` together with `information_schema.table_constraints`.

4. Add a constraint so that `loans.due_on` can never be earlier than `loans.loaned_on`. First check that no existing row would violate it. Then add it, and show the error you get for an invalid insert.

5. A member can only have one open (unreturned) loan of the same book at a time. Express this as a database rule, without adding any column.

<details>
<summary>Solution</summary>

1. 
```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'members'
ORDER BY ordinal_position;
```
`id` has `nextval('members_id_seq'::regclass)` and `active` has `true`. `email`, `name` and `joined_on` have no default.

2. 
```sql
BEGIN;
INSERT INTO books (id, title) VALUES (100, 'Hand-numbered');
INSERT INTO books (title) VALUES ('Sequence-numbered') RETURNING id;
```
The second insert returns the next sequence value (7 or higher in a lab that has seen failures), not 101: the explicit id 100 did not move the sequence. To force the collision, still inside the transaction:
```sql
SELECT setval('books_id_seq', 99);
INSERT INTO books (title) VALUES ('Collision');
ROLLBACK;
```
The `INSERT` takes id 100 from the sequence and fails with `duplicate key value violates unique constraint "books_pkey"`. The `setval` is not undone by `ROLLBACK`, since sequences are non-transactional, so repair it with `SELECT setval('books_id_seq', (SELECT max(id) FROM books));`.

3. `\d members` ends with "Referenced by: TABLE "loans" CONSTRAINT "loans_member_id_fkey" FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE RESTRICT". With the catalog:
```sql
SELECT tc.table_name, tc.constraint_name, rc.delete_rule
FROM information_schema.referential_constraints rc
JOIN information_schema.table_constraints tc
  ON tc.constraint_name = rc.constraint_name AND tc.constraint_schema = rc.constraint_schema
JOIN information_schema.table_constraints ref
  ON ref.constraint_name = rc.unique_constraint_name AND ref.constraint_schema = rc.unique_constraint_schema
WHERE ref.table_name = 'members';
```
Result: `loans | loans_member_id_fkey | RESTRICT`.

4. 
```sql
SELECT id FROM loans WHERE due_on < loaned_on;   -- expect 0 rows
ALTER TABLE loans ADD CONSTRAINT loans_due_after_loan CHECK (due_on >= loaned_on);
INSERT INTO loans (book_id, member_id, loaned_on, due_on) VALUES (3, 1, '2024-07-10', '2024-07-01');
```
The insert fails with `new row for relation "loans" violates check constraint "loans_due_after_loan"`. If the `SELECT` had returned rows, `ADD CONSTRAINT` would fail on them; you would fix the data first, or add the constraint `NOT VALID` and validate later.

5. A partial unique index:
```sql
CREATE UNIQUE INDEX loans_one_open_per_member_book
    ON loans (book_id, member_id) WHERE returned_on IS NULL;
```
Rows with `returned_on` filled are outside the index, so history is unrestricted. Chapter [Indexes and EXPLAIN](indexes-and-explain.md) covers partial indexes. (Drop it afterwards if you want the lab data to behave as printed in later chapters: `DROP INDEX loans_one_open_per_member_book;`.)

</details>
