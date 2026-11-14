---
description: Reading rows with SELECT: filtering, NULL logic, sorting, dates, strings, subqueries, and CTEs.
---

# SELECT, FROM, WHERE

Most of your SQL as an Odoo developer is `SELECT`: finding out what is really in a table, counting the records a domain would match, checking which rows a bug touched. This chapter covers a single-table `SELECT` thoroughly, including the three-valued logic of NULL that causes more wrong results than any other feature, and ends with subqueries and common table expressions. Joins across tables come next. The queries use the library schema from [Relational basics](relational-basics.md); load it first.

## Anatomy and evaluation order

```sql
SELECT   title, price
FROM     books
WHERE    status = 'available'
ORDER BY price DESC
LIMIT    3;
```

```
     title     | price
---------------+-------
 Quiet Engines | 18.00
 Salt Roads    | 15.00
 Tidewater     | 12.50
(3 rows)
```

You write `SELECT` first, but the database thinks in a different order, and knowing it explains most "why can't I use this alias here" errors:

1. `FROM` picks the source rows (and joins, next chapter).
2. `WHERE` throws away rows that do not match.
3. `GROUP BY` collapses rows into groups; aggregates are computed.
4. `HAVING` throws away groups.
5. `SELECT` computes the output expressions.
6. `DISTINCT` removes duplicate output rows.
7. `ORDER BY` sorts.
8. `LIMIT` / `OFFSET` cut the result.

Consequence: a column alias defined in `SELECT` does not exist yet in `WHERE`, but it does in `ORDER BY`:

```sql
SELECT title, price * 2 AS double_price FROM books WHERE double_price > 20;
```

```
ERROR:  column "double_price" does not exist
LINE 1: SELECT title, price * 2 AS double_price FROM books WHERE dou...
```

Repeat the expression in `WHERE`, or wrap the query (a subquery or a CTE, below).

## Choosing columns

`SELECT *` returns every column and is fine in psql while exploring. In code it is a liability: a new column changes your result shape, and on tables with `bytea` or large `text` columns (Odoo's `ir_attachment` with `db_datas`, `mail_message` bodies) it pulls megabytes you did not want. Name your columns.

Expressions and aliases:

```sql
SELECT title,
       price,
       pages,
       round(price / pages * 100, 2) AS price_per_100_pages
FROM books
ORDER BY id;
```

```
      title      | price | pages | price_per_100_pages
-----------------+-------+-------+---------------------
 Tidewater       | 12.50 |   310 |                4.03
 Salt Roads      | 15.00 |   420 |                3.57
 The Long Ledger |  9.90 |   250 |                3.96
 Paper Moons     | 11.00 |   180 |                6.11
 Quiet Engines   | 18.00 |   520 |                3.46
 Orphan Volume   |  5.00 |    90 |                5.56
(6 rows)
```

Beware of integer division: `pages / 100` between two integers truncates (`310 / 100` is `3`). Cast one side (`pages / 100.0` or `pages::numeric / 100`). The `::` cast operator is PostgreSQL's shorthand for `CAST(x AS type)`; you will see both in Odoo code.

A `SELECT` without `FROM` is legal and useful as a calculator:

```sql
SELECT 7 / 2 AS int_div, 7 / 2.0 AS dec_div, 7 % 2 AS remainder;
```

```
 int_div |      dec_div       | remainder
---------+--------------------+-----------
       3 | 3.5000000000000000 |         1
(1 row)
```

## WHERE: comparing and combining

Comparison operators are `=`, `<>` (also `!=`), `<`, `<=`, `>`, `>=`. Note the single `=` for equality. Beyond those:

```sql
-- range, inclusive on both ends
SELECT title, price FROM books WHERE price BETWEEN 10 AND 15 ORDER BY price;
```

```
    title    | price
-------------+-------
 Paper Moons | 11.00
 Tidewater   | 12.50
 Salt Roads  | 15.00
(3 rows)
```

```sql
-- membership
SELECT title FROM books WHERE author_id IN (1, 3) ORDER BY title;
```

```
     title
---------------
 Quiet Engines
 Salt Roads
 Tidewater
(3 rows)
```

`IN (...)` is shorthand for a chain of `OR`. The array form `author_id = ANY(ARRAY[1,3])` is equivalent and is how drivers pass a Python list as one parameter; Odoo's `cr.execute("... WHERE id = ANY(%s)", [ids])` uses it.

### AND, OR, NOT and precedence

`AND` binds tighter than `OR`. Without parentheses the next query does not mean what it appears to:

```sql
SELECT title, published_year, price FROM books
WHERE status = 'available' AND published_year < 2005 OR price > 17
ORDER BY id;
```

```
     title     | published_year | price
---------------+----------------+-------
 Tidewater     |           1998 | 12.50
 Salt Roads    |           2004 | 15.00
 Quiet Engines |           2019 | 18.00
 Orphan Volume |           2001 |  5.00
(4 rows)
```

It parses as `(available AND old) OR expensive`. It happens to produce the same rows as the parenthesized variant on this data, which is exactly how this bug survives code review. Parenthesize every mixed `AND`/`OR`; Odoo domains do the same with their prefix notation, and the SQL it generates is always fully parenthesized.

### Pattern matching

```sql
SELECT name FROM members WHERE email LIKE '%@example.com' ORDER BY id;
```

```
 name
-------
 Nora
 Omar
 Quinn
(3 rows)
```

`%` matches any run of characters, `_` exactly one. `LIKE` is case sensitive; `ILIKE` ignores case. Odoo's `ilike` operator compiles to `ILIKE` (and, where a field opts in and the `unaccent` extension is installed, wraps both sides in `unaccent()`). A pattern with a leading `%` cannot use an ordinary btree index (see [Indexes and EXPLAIN](indexes-and-explain.md)). Escape a literal `%` or `_` with a backslash. PostgreSQL also has regular expression operators: `~` (match), `~*` (case-insensitive), `!~`.

```sql
SELECT title FROM books WHERE title ~ '^[A-Q]' ORDER BY title;
```

```
     title
---------------
 Orphan Volume
 Paper Moons
 Quiet Engines
(3 rows)
```

## NULL: the value that is not a value

NULL means "unknown" or "absent", not zero or empty string. Every comparison with NULL yields neither true nor false but NULL, and `WHERE` keeps only rows where the condition is true. This is three-valued logic, and it is the source of a family of bugs.

```sql
SELECT title FROM books WHERE author_id = NULL;
```

```
 title
-------
(0 rows)
```

`author_id = NULL` is NULL for every row, so nothing matches, including the book that has a NULL author. The correct test:

```sql
SELECT title FROM books WHERE author_id IS NULL;
```

```
     title
---------------
 Orphan Volume
(1 row)
```

The second trap: `<>` also drops NULL rows.

```sql
SELECT title FROM books WHERE author_id <> 1 ORDER BY id;
```

```
      title
-----------------
 The Long Ledger
 Paper Moons
 Quiet Engines
(3 rows)
```

"Not by author 1" intuitively includes `Orphan Volume`; SQL leaves it out, because `NULL <> 1` is NULL. If you want the intuitive meaning, use `IS DISTINCT FROM`, which treats NULL as an ordinary comparable value:

```sql
SELECT title FROM books WHERE author_id IS DISTINCT FROM 1 ORDER BY id;
```

```
      title
-----------------
 The Long Ledger
 Paper Moons
 Quiet Engines
 Orphan Volume
(4 rows)
```

When you translate an Odoo domain like `[('author_id', '!=', 1)]`, the ORM adds the NULL handling for you (it generates `author_id IS NULL OR author_id != 1`). Written by hand, that is your job.

The logic tables, because they explain what you see:

| a | b | a AND b | a OR b |
|---|---|---|---|
| true | NULL | NULL | true |
| false | NULL | false | NULL |
| NULL | NULL | NULL | NULL |

and `NOT NULL` is `NULL`.

### The NOT IN trap

`x NOT IN (1, 2, NULL)` means `x <> 1 AND x <> 2 AND x <> NULL`. The last term is NULL for every x, so the whole expression is never true:

```sql
SELECT title FROM books WHERE author_id NOT IN (1, NULL);
```

```
 title
-------
(0 rows)
```

This bites when the list comes from a subquery whose column can be NULL. Here the subquery excludes NULLs naturally, so it works:

```sql
SELECT title FROM books
WHERE author_id NOT IN (SELECT author_id FROM books WHERE status = 'lost')
ORDER BY id;
```

```
     title
---------------
 Tidewater
 Salt Roads
 Quiet Engines
(3 rows)
```

Put a book with an unknown author in the lost set, and the inner query returns a NULL: now the outer query returns nothing, silently. Prefer `NOT EXISTS`, which has no such surprise (shown below), or add `WHERE author_id IS NOT NULL` inside the subquery.

### COALESCE and NULLIF

`COALESCE(a, b, ...)` returns the first non-NULL argument; `NULLIF(a, b)` returns NULL if the two are equal, else `a`.

```sql
SELECT name, COALESCE(email, '(none)') AS email FROM members ORDER BY id;
```

```
 name  |       email
-------+-------------------
 Nora  | nora@example.com
 Omar  | omar@example.com
 Petra | (none)
 Quinn | quinn@example.com
(4 rows)
```

`NULLIF` is the standard defence against division by zero: `total / NULLIF(count, 0)` yields NULL instead of an error. Odoo stores unset `Char`, `Date`, and many2one fields as NULL, not as empty string or zero; a boolean that was never written is NULL too (not false) on rows created before the column existed, which matters for `WHERE NOT active`. Write `COALESCE(active, false)` when you read such columns, or compare with `IS NOT TRUE`.

Aggregates ignore NULL, which we use in [the next chapters](aggregation-and-window-functions.md), and `NULL || 'text'` is NULL (use `concat()` or `COALESCE` to build strings from nullable parts).

## Sorting and paging

```sql
SELECT title, author_id FROM books ORDER BY author_id, title;
```

```
      title      | author_id
-----------------+-----------
 Salt Roads      |         1
 Tidewater       |         1
 Paper Moons     |         2
 The Long Ledger |         2
 Quiet Engines   |         3
 Orphan Volume   |
(6 rows)
```

In PostgreSQL, NULL sorts as larger than any value: last in ascending order, first in descending. Control it explicitly with `NULLS FIRST` or `NULLS LAST`:

```sql
SELECT title, author_id FROM books ORDER BY author_id DESC NULLS LAST, title LIMIT 3;
```

```
      title      | author_id
-----------------+-----------
 Quiet Engines   |         3
 Paper Moons     |         2
 The Long Ledger |         2
(3 rows)
```

`ORDER BY` can use column numbers (`ORDER BY 2`) and expressions, and accepts a different direction per key. Sorting strings follows the database's collation: with a `en_US.UTF-8` collation, `'a' < 'B'`, with `C` collation, uppercase sorts before lowercase. Odoo databases are created with whatever the cluster default is (often `en_US.UTF-8`, sometimes `C`), so the same query can sort differently on two servers.

### LIMIT, OFFSET, and keyset paging

```sql
SELECT id, title FROM books ORDER BY id LIMIT 2 OFFSET 2;
```

```
 id |     title
----+-----------------
  3 | The Long Ledger
  4 | Paper Moons
(2 rows)
```

`OFFSET n` still reads and discards the first `n` rows, so page 5000 of a long list is slow, and if rows are inserted between page requests you see duplicates or gaps. For stable deep paging remember where you stopped and seek from there:

```sql
SELECT id, title FROM books WHERE id > 3 ORDER BY id LIMIT 2;
```

```
 id |    title
----+---------------
  4 | Paper Moons
  5 | Quiet Engines
(2 rows)
```

With a unique, indexed sort key this reads only the rows it returns. Always combine `LIMIT` with `ORDER BY`: without it you get "some" rows, and not necessarily the same ones next time. Odoo's `search_read` with `limit`/`offset` and its default `_order = 'id'` has the same trade-offs; batch jobs that walk a large table should page by id.

## DISTINCT and DISTINCT ON

```sql
SELECT DISTINCT status FROM books;
```

```
  status
-----------
 available
 lost
(2 rows)
```

(Row order is not guaranteed without `ORDER BY`.) `DISTINCT` compares whole output rows and treats NULLs as equal to each other.

`DISTINCT ON (expr)` is a PostgreSQL extension that keeps the first row for each value of `expr`, "first" decided by `ORDER BY`. It answers "latest row per group" in one clause:

```sql
SELECT DISTINCT ON (member_id) member_id, book_id, loaned_on
FROM loans
ORDER BY member_id, loaned_on DESC;
```

```
 member_id | book_id | loaned_on
-----------+---------+------------
         1 |       5 | 2024-05-20
         2 |       5 | 2024-03-12
         3 |       1 | 2024-05-01
(3 rows)
```

The `ORDER BY` must start with the `DISTINCT ON` expression(s), or PostgreSQL refuses the query. Window functions give the same result more flexibly (next-but-one chapter).

## Dates and times

Dates are first-class types with arithmetic. Subtracting two `date` values gives an integer number of days; adding an integer to a date adds days:

```sql
SELECT id, returned_on - due_on AS days_late
FROM loans
WHERE returned_on > due_on;
```

```
 id | days_late
----+-----------
  2 |         5
(1 row)
```

```sql
SELECT id, due_on, due_on + 7 AS extended_to, loaned_on + interval '1 month' AS plus_month
FROM loans WHERE id <= 2;
```

```
 id |   due_on   | extended_to |      plus_month
----+------------+-------------+---------------------
  1 | 2024-01-19 | 2024-01-26  | 2024-02-05 00:00:00
  2 | 2024-02-15 | 2024-02-22  | 2024-03-01 00:00:00
(2 rows)
```

Adding an `interval` turns a `date` into a `timestamp`. Truncate or extract to bucket:

```sql
SELECT id,
       date_trunc('month', loaned_on) AS month_start,
       extract(year FROM loaned_on)   AS yr,
       to_char(loaned_on, 'YYYY-MM')  AS ym
FROM loans WHERE id <= 3 ORDER BY id;
```

```
 id |     month_start     | yr   |   ym
----+---------------------+------+---------
  1 | 2024-01-01 00:00:00 | 2024 | 2024-01
  2 | 2024-02-01 00:00:00 | 2024 | 2024-02
  3 | 2024-03-01 00:00:00 | 2024 | 2024-03
(3 rows)
```

`current_date` and `now()` give today and the transaction start time. Note that `now()` is frozen for the whole transaction: it does not advance while the transaction runs. `clock_timestamp()` returns the real current time. Odoo's own `create_date` and `write_date` are set from the ORM's Python clock (`fields.Datetime.now()`) in most cases, not from `now()`, and the column is `timestamp without time zone` holding UTC. When you compare it to a local date, convert explicitly:

```sql
SELECT now() AT TIME ZONE 'UTC' AS utc_now;
```

`timestamp AT TIME ZONE 'UTC'` on a plain `timestamp` reinterprets it as UTC and returns a `timestamptz`; `timestamptz AT TIME ZONE 'UTC'` returns a plain `timestamp`. The direction flips depending on the input type, and almost everyone gets it wrong once. To convert an Odoo UTC datetime to a local wall-clock time in a given zone:

```sql
SELECT create_date AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Rome' FROM some_odoo_table LIMIT 1;
```

The first `AT TIME ZONE` makes the stored value a proper UTC instant, the second renders it in the target zone. (`some_odoo_table` is a placeholder; the lab schema has no timestamp column.)

### Ranges: use half-open intervals

To select "everything in March" on a timestamp column, `BETWEEN '2024-03-01' AND '2024-03-31'` silently excludes anything after midnight on the 31st. Use a half-open range:

```sql
SELECT id, loaned_on FROM loans
WHERE loaned_on >= '2024-03-01' AND loaned_on < '2024-04-01'
ORDER BY id;
```

```
 id | loaned_on
----+------------
  3 | 2024-03-10
  4 | 2024-03-12
(2 rows)
```

The same pattern is correct for dates and timestamps, and composes with adjacent ranges without gaps or overlaps. It is also what you want when the end boundary is the start of the next period.

## Strings

```sql
SELECT title, upper(title) AS up, length(title) AS len, substring(title FROM 1 FOR 4) AS first4,
       position('o' IN title) AS pos_o
FROM books WHERE id <= 2 ORDER BY id;
```

```
   title    |     up     | len | first4 | pos_o
------------+------------+-----+--------+-------
 Tidewater  | TIDEWATER  |   9 | Tide   |     0
 Salt Roads | SALT ROADS |  10 | Salt   |     7
(2 rows)
```

Other tools you will use: `lower`, `trim`, `replace`, `split_part(str, ',', 2)`, `left`/`right`, `lpad`, `regexp_replace`, `string_agg` (an aggregate, later), and `format('%s (%s)', title, published_year)` for building text. `||` concatenates but returns NULL when either side is NULL; `concat(a, b)` skips NULLs.

```sql
SELECT 'a' || NULL AS with_pipes, concat('a', NULL, 'b') AS with_concat;
```

```
 with_pipes | with_concat
------------+-------------
            | ab
(1 row)
```

## CASE

`CASE` is the expression form of if/else, usable anywhere an expression is:

```sql
SELECT title,
       CASE WHEN pages < 200 THEN 'short'
            WHEN pages < 400 THEN 'medium'
            ELSE 'long' END AS length
FROM books ORDER BY id;
```

```
      title      | length
-----------------+--------
 Tidewater       | medium
 Salt Roads      | long
 The Long Ledger | medium
 Paper Moons     | short
 Quiet Engines   | long
 Orphan Volume   | short
(6 rows)
```

Branches are tried in order; without `ELSE`, no match yields NULL.

## Subqueries

A scalar subquery returns one value and can sit wherever a value can:

```sql
SELECT title, price FROM books
WHERE price > (SELECT avg(price) FROM books)
ORDER BY id;
```

```
     title     | price
---------------+-------
 Tidewater     | 12.50
 Salt Roads    | 15.00
 Quiet Engines | 18.00
(3 rows)
```

(The average is 11.90.) If a scalar subquery returns more than one row, PostgreSQL raises `more than one row returned by a subquery used as an expression`.

`EXISTS` asks "is there at least one matching row", and is the safe way to express "has none":

```sql
SELECT name FROM authors a
WHERE NOT EXISTS (SELECT 1 FROM books b WHERE b.author_id = a.id);
```

```
     name
---------------
 Dmitri Okafor
(1 row)
```

The inner query refers to the outer row `a`; that is a correlated subquery. What it selects is irrelevant (`SELECT 1` by convention). `NOT EXISTS` stops at the first match and, unlike `NOT IN`, is not fooled by NULLs.

## Common table expressions

A `WITH` clause names an intermediate result, so you can read the query top to bottom:

```sql
WITH late AS (
    SELECT id, book_id, member_id
    FROM loans
    WHERE returned_on > due_on
)
SELECT late.id AS loan_id, b.title
FROM late
JOIN books b ON b.id = late.book_id;
```

```
 loan_id |   title
---------+------------
       2 | Salt Roads
(1 row)
```

(The `JOIN` is the subject of the next chapter.) Since PostgreSQL 12, a non-recursive CTE that is referenced once and has no side effects is inlined into the outer query, as if you had written a subquery, so it costs nothing and the planner optimizes across it. Before 12 every CTE was an optimization fence, materialized once. You can force either behaviour with `WITH x AS MATERIALIZED (...)` or `AS NOT MATERIALIZED (...)`. Odoo 16 to 18 require PostgreSQL 12 or newer, so the inlining is the norm.

`WITH RECURSIVE` walks hierarchies; Odoo's `parent_path` mostly spares you from it, but `res_company`/`res_partner` trees and category trees are classic uses. A minimal one counting 1 to 3:

```sql
WITH RECURSIVE n(i) AS (
    SELECT 1
    UNION ALL
    SELECT i + 1 FROM n WHERE i < 3
)
SELECT i FROM n;
```

```
 i
---
 1
 2
 3
(3 rows)
```

## Arrays and jsonb, briefly

Odoo uses two compound types you will hit when reading data. Arrays appear as parameters (`= ANY(%s)`). `jsonb` is where translated field values live from Odoo 16 on: one key per language.

```sql
SELECT '{"en_US": "Tidewater", "fr_FR": "Maree"}'::jsonb ->> 'en_US' AS en,
       '{"en_US": "Tidewater"}'::jsonb ->> 'de_DE'                     AS missing;
```

```
    en     | missing
-----------+---------
 Tidewater |
(1 row)
```

`->` returns jsonb, `->>` returns text; a missing key yields NULL. So `SELECT name->>'en_US' FROM product_template` is how you read a product name, and a translated field with no entry for your language is NULL, not the English fallback (the ORM adds the fallback in Python). Chapter [The Odoo schema](the-odoo-schema.md) returns to this.

## Reading production data safely

For the first look at any database you do not own, make the session incapable of writing:

```bash
psql "dbname=handbook_lab options='-c default_transaction_read_only=on -c statement_timeout=30000'"
```

Or inside a session:

```sql
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
```

`statement_timeout` ends runaway queries (a join missing its `ON` condition returns millions of rows). Add `LIMIT` to exploratory queries on big tables, and prefer `count(*)` or `EXPLAIN` first to see how large the answer will be.

## Pitfalls

- **`= NULL` and `<> value` with NULLs.** Both silently drop NULL rows. Use `IS NULL`, `IS NOT NULL`, `IS DISTINCT FROM`.
- **`NOT IN` against a subquery that can return NULL.** One NULL empties the result. Use `NOT EXISTS`.
- **Unparenthesized `AND`/`OR`.** The result looks right on your sample and is wrong on the full table.
- **Integer division.** `count / total` between integers is 0 for any fraction below one. Cast to `numeric`.
- **`BETWEEN` on timestamps.** Excludes the last day's time of day. Use `>= start AND < next_start`.
- **`LIMIT` without `ORDER BY`.** You get arbitrary rows, and the set changes between runs and after an `UPDATE`.
- **Deep `OFFSET`.** Page 10,000 reads 10,000 pages of rows to throw them away. Page by key.
- **`SELECT *` on big tables.** Binary and HTML columns make a harmless-looking query move gigabytes.
- **Time zones.** Odoo's datetime columns are UTC without a zone marker. A report grouped with `date_trunc('day', create_date)` groups UTC days, so evening records in a positive-offset zone land on the next day. Convert before you truncate.
- **Case and accents.** `=` is exact. Names in Odoo come in any capitalization; use `ILIKE` or `lower()` and expect no index help.
- **Sort order differences across servers.** Collation decides string order; do not write tests that depend on it unless you set it.

## Try it

Use the library schema.

1. List the titles of books that are not lost and cost more than 10 but at most 15, cheapest first.

2. List members whose email is missing or whose account is inactive. Return `name` and a column `reason` that says `no email` or `inactive`, with `no email` taking priority if both apply.

3. For every loan, show the loan id, the number of days it was kept (returned minus loaned, or NULL if not returned) and a column `state` that reads `open`, `late` or `on time`. A loan is late if it was returned after its due date.

4. Return the three most recently published books after skipping the newest one, with `OFFSET`. Then explain what goes wrong if a book is inserted between two page requests, and how keyset paging avoids it.

5. Find the authors who have at least one book that is lost, using `EXISTS`, and then write the same with `IN`. Predict what each returns if you add a lost book with no author.

<details>
<summary>Solution</summary>

1. 
```sql
SELECT title, price FROM books
WHERE status <> 'lost' AND price > 10 AND price <= 15
ORDER BY price;
```
```
    title    | price
-------------+-------
 Paper Moons | 11.00
 Tidewater   | 12.50
 Salt Roads  | 15.00
(3 rows)
```
`status` is `NOT NULL`, so `<>` is safe here.

2. 
```sql
SELECT name,
       CASE WHEN email IS NULL THEN 'no email' ELSE 'inactive' END AS reason
FROM members
WHERE email IS NULL OR NOT active
ORDER BY id;
```
```
 name  |  reason
-------+----------
 Petra | no email
 Quinn | inactive
(2 rows)
```

3. 
```sql
SELECT id,
       returned_on - loaned_on AS days_kept,
       CASE WHEN returned_on IS NULL THEN 'open'
            WHEN returned_on > due_on THEN 'late'
            ELSE 'on time' END AS state
FROM loans ORDER BY id;
```
```
 id | days_kept |  state
----+-----------+---------
  1 |        13 | on time
  2 |        19 | late
  3 |           | open
  4 |        13 | on time
  5 |           | open
  6 |         9 | on time
  7 |        12 | on time
(7 rows)
```

4. 
```sql
SELECT id, title, published_year FROM books
ORDER BY published_year DESC, id LIMIT 3 OFFSET 1;
```
```
 id |      title      | published_year
----+-----------------+----------------
  4 | Paper Moons     |           2015
  3 | The Long Ledger |           2010
  2 | Salt Roads      |           2004
(3 rows)
```
If a newer book is inserted after you fetched the first page, the next `OFFSET` window shifts by one row and you see a row twice (or, after a delete, skip one). Keyset: remember `(published_year, id)` of the last row and ask for `WHERE (published_year, id) > (...)` in the appropriate direction. Tie-break on `id` so the order is total.

5. 
```sql
SELECT a.name FROM authors a
WHERE EXISTS (SELECT 1 FROM books b WHERE b.author_id = a.id AND b.status = 'lost');

SELECT a.name FROM authors a
WHERE a.id IN (SELECT author_id FROM books WHERE status = 'lost');
```
Both return `Boris Venn`. A lost book without an author adds a NULL to the inner list of the `IN` version, which still matches correctly (`IN` only needs one true), so both keep returning the same row. The problem would appear with `NOT IN`: `a.id NOT IN (SELECT author_id ...)` would return no rows at all once that NULL is in the list, while `NOT EXISTS` keeps working.

</details>
