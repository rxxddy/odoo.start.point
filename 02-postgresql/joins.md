---
description: Inner, left, and the join patterns the Odoo schema needs.
---

# Joins

A single Odoo record is spread over several tables: the sale order points at a partner, the partner at a country, a product at several tags through a relation table. Reading anything meaningful from the database means following those keys, and the join is the tool. This chapter covers inner and outer joins, the difference between `ON` and `WHERE` in an outer join, the anti-join and semi-join patterns, many-to-many traversal, the row multiplication that corrupts totals, `LATERAL`, and set operations. Examples use the library schema from [Relational basics](relational-basics.md) and [SELECT, FROM, WHERE](select-from-where.md).

## Two more tables for many-to-many

A book can have several genres and a genre several books. Add the pair of tables:

```sql
CREATE TABLE genres (
    id    serial PRIMARY KEY,
    name  varchar NOT NULL
);

CREATE TABLE book_genre (
    book_id   integer NOT NULL REFERENCES books (id)  ON DELETE CASCADE,
    genre_id  integer NOT NULL REFERENCES genres (id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, genre_id)
);

INSERT INTO genres (name) VALUES ('Fiction'), ('History'), ('Poetry');

INSERT INTO book_genre (book_id, genre_id) VALUES
    (1, 1), (1, 2), (2, 1), (3, 1), (5, 1), (5, 3);
```

`book_genre` is the shape Odoo gives a `Many2many` field: two key columns, one row per pair. Odoo would call this table `library_book_library_genre_rel` (naming rules in [The Odoo schema](the-odoo-schema.md)); the short name keeps the lab readable.

## What a join does

A join combines rows from two sources according to a condition and emits one output row for each pair that satisfies it. Conceptually, the database forms every pair (the Cartesian product) and keeps the ones matching `ON`. Physically it does nothing of the kind: the planner picks a nested loop, a hash join, or a merge join (see [Indexes and EXPLAIN](indexes-and-explain.md)) and produces the same rows far faster. You reason with the conceptual model and let the planner pick the physical one.

## INNER JOIN

```sql
SELECT b.id, b.title, a.name AS author
FROM books b
JOIN authors a ON a.id = b.author_id
ORDER BY b.id;
```

```
 id |      title      |   author
----+-----------------+-------------
  1 | Tidewater       | Ada Marlowe
  2 | Salt Roads      | Ada Marlowe
  3 | The Long Ledger | Boris Venn
  4 | Paper Moons     | Boris Venn
  5 | Quiet Engines   | Chiara Lund
(5 rows)
```

`JOIN` alone means `INNER JOIN`. Only pairs that match survive: `Orphan Volume` has no author and vanishes, `Dmitri Okafor` has no book and vanishes. That is the single most common cause of "my report is missing rows" in hand-written SQL, and it is silent.

Table aliases (`b`, `a`) are not decoration. Both tables have `id` and `name`-like columns; an unqualified `id` raises `column reference "id" is ambiguous`. Qualify every column in a join, always, even those that are unambiguous today: a column added later to the other table breaks an unqualified reference.

## LEFT JOIN

A left join keeps every row of the left table, and fills the right-side columns with NULL when nothing matches:

```sql
SELECT b.id, b.title, a.name AS author
FROM books b
LEFT JOIN authors a ON a.id = b.author_id
ORDER BY b.id;
```

```
 id |      title      |   author
----+-----------------+-------------
  1 | Tidewater       | Ada Marlowe
  2 | Salt Roads      | Ada Marlowe
  3 | The Long Ledger | Boris Venn
  4 | Paper Moons     | Boris Venn
  5 | Quiet Engines   | Chiara Lund
  6 | Orphan Volume   |
(6 rows)
```

Rule for Odoo: a join from a record to an optional many2one must be a `LEFT JOIN`. A required many2one (`NOT NULL`) can safely be an inner join, but inner joining an optional one deletes the records without a value from your result. The ORM always uses `LEFT JOIN` when a domain walks through a many2one path (when it joins at all; see the hint below).

`RIGHT JOIN` is a left join with the tables swapped; nobody needs it, since you can swap the tables yourself and the reading order stays natural. `FULL JOIN` keeps unmatched rows from both sides:

```sql
SELECT a.name AS author, b.title
FROM authors a
FULL JOIN books b ON b.author_id = a.id
ORDER BY a.id, b.id;
```

```
    author     |      title
---------------+-----------------
 Ada Marlowe   | Tidewater
 Ada Marlowe   | Salt Roads
 Boris Venn    | The Long Ledger
 Boris Venn    | Paper Moons
 Chiara Lund   | Quiet Engines
 Dmitri Okafor |
               | Orphan Volume
(7 rows)
```

(NULL sorts last in ascending order, so `Orphan Volume` ends the list.) A full join is the right tool for reconciling two lists: "in A but not B, in B but not A, in both" in one pass.

{% hint style="info" %}
Versions. When a search domain contains a path like `[('partner_id.country_id.code', '=', 'IT')]`, Odoo 16 to 18 normally compiles each many2one step into a subquery (`partner_id IN (SELECT id FROM res_partner WHERE ...)`), and into real `LEFT JOIN`s only for fields declared with `auto_join=True`. Print the SQL with the `odoo.sql_db` logger at DEBUG to see what your domain generates; the techniques are in the shell-and-debugging part.
{% endhint %}

## ON versus WHERE in an outer join

For an inner join, a condition in `ON` and the same condition in `WHERE` give identical results. For an outer join they do not, and the difference is the classic mistake. Compare:

```sql
-- condition in ON: the filter applies while matching
SELECT a.name, b.title
FROM authors a
LEFT JOIN books b ON b.author_id = a.id AND b.status = 'available'
ORDER BY a.id, b.id;
```

```
     name      |     title
---------------+---------------
 Ada Marlowe   | Tidewater
 Ada Marlowe   | Salt Roads
 Boris Venn    | Paper Moons
 Chiara Lund   | Quiet Engines
 Dmitri Okafor |
(5 rows)
```

```sql
-- condition in WHERE: the filter applies after the join
SELECT a.name, b.title
FROM authors a
LEFT JOIN books b ON b.author_id = a.id
WHERE b.status = 'available'
ORDER BY a.id, b.id;
```

```
     name     |     title
--------------+---------------
 Ada Marlowe  | Tidewater
 Ada Marlowe  | Salt Roads
 Boris Venn   | Paper Moons
 Chiara Lund  | Quiet Engines
(4 rows)
```

In the first, Dmitri stays with an empty title: the `ON` clause decides which books match an author, and an author with no matching book is still emitted. In the second, the join first produced the Dmitri row with `b.status` NULL, and `WHERE b.status = 'available'` threw it away. Filtering the right-hand table in `WHERE` quietly converts your left join into an inner join.

The rule: conditions that describe which right-hand rows may match go in `ON`; conditions that filter the final result go in `WHERE`. The one deliberate exception is the anti-join below, where you test the right side for NULL in `WHERE`.

## Anti-join: rows with no match

"Authors without books", "partners without invoices", "products never sold". Two idioms:

```sql
-- NOT EXISTS
SELECT a.name FROM authors a
WHERE NOT EXISTS (SELECT 1 FROM books b WHERE b.author_id = a.id);

-- LEFT JOIN ... IS NULL
SELECT a.name
FROM authors a
LEFT JOIN books b ON b.author_id = a.id
WHERE b.id IS NULL;
```

Both return:

```
     name
---------------
 Dmitri Okafor
(1 row)
```

Test the right table's primary key (or any `NOT NULL` column) for NULL, never a nullable column, whose NULL could be real data. Both forms are optimized into the same anti-join by the planner; `NOT EXISTS` states the intent more directly, and `NOT IN` is the one to avoid when the subquery column is nullable (see the previous chapter).

## Semi-join: rows with at least one match

"Members who ever borrowed something". Using `JOIN` returns a member once per loan; what you want is a membership test:

```sql
SELECT m.name FROM members m
WHERE EXISTS (SELECT 1 FROM loans l WHERE l.member_id = m.id)
ORDER BY m.id;
```

```
 name
-------
 Nora
 Omar
 Petra
(3 rows)
```

`WHERE m.id IN (SELECT member_id FROM loans)` gives the same rows. Each member appears once however many loans they have. Choose `EXISTS`/`IN` whenever you do not need columns from the other table.

## Joining more than two tables

Chain joins; each `ON` relates the new table to something already present:

```sql
SELECT l.id, b.title, m.name AS member, l.loaned_on
FROM loans l
JOIN books b   ON b.id = l.book_id
JOIN members m ON m.id = l.member_id
ORDER BY l.id;
```

```
 id |     title     | member | loaned_on
----+---------------+--------+------------
  1 | Tidewater     | Nora   | 2024-01-05
  2 | Salt Roads    | Nora   | 2024-02-01
  3 | Tidewater     | Omar   | 2024-03-10
  4 | Quiet Engines | Omar   | 2024-03-12
  5 | Paper Moons   | Petra  | 2024-04-02
  6 | Tidewater     | Petra  | 2024-05-01
  7 | Quiet Engines | Nora   | 2024-05-20
(7 rows)
```

Joins are logically associative for inner joins, so the order you write them does not change the result and the planner reorders freely (up to the `join_collapse_limit`, default 8 tables; Odoo's reports sometimes exceed it). Mixing inner and outer joins is different: order matters, and a later inner join on a column from the right side of an earlier left join kills the NULL rows, like the `WHERE` example above. When mixing, put the outer joins last, or use parentheses.

Chain with an optional step in the middle:

```sql
SELECT b.title, a.name AS author, count(l.id) AS loans
FROM books b
LEFT JOIN authors a ON a.id = b.author_id
LEFT JOIN loans l   ON l.book_id = b.id
GROUP BY b.id, b.title, a.name
ORDER BY b.id;
```

```
      title      |   author    | loans
-----------------+-------------+-------
 Tidewater       | Ada Marlowe |     3
 Salt Roads      | Ada Marlowe |     1
 The Long Ledger | Boris Venn  |     0
 Paper Moons     | Boris Venn  |     1
 Quiet Engines   | Chiara Lund |     2
 Orphan Volume   |             |     0
(6 rows)
```

`count(l.id)` counts only non-NULL values, so the unlucky books show 0. `count(*)` would show 1 for them; keep that distinction in mind for the next chapter.

## Many-to-many through the relation table

Join from one side to the relation table to the other side:

```sql
SELECT b.title, g.name AS genre
FROM books b
JOIN book_genre bg ON bg.book_id = b.id
JOIN genres g      ON g.id = bg.genre_id
ORDER BY b.id, g.id;
```

```
      title      |  genre
-----------------+---------
 Tidewater       | Fiction
 Tidewater       | History
 Salt Roads      | Fiction
 The Long Ledger | Fiction
 Quiet Engines   | Fiction
 Quiet Engines   | Poetry
(6 rows)
```

Books with several genres appear several times: the output has one row per pair. Books without a genre (`Paper Moons`, `Orphan Volume`) are missing, again because of the inner join. Find them with an anti-join:

```sql
SELECT b.title
FROM books b
LEFT JOIN book_genre bg ON bg.book_id = b.id
WHERE bg.book_id IS NULL
ORDER BY b.id;
```

```
     title
---------------
 Paper Moons
 Orphan Volume
(2 rows)
```

This is how you find orphans in Odoo's own relation tables, for instance partners without any category or users without any group.

## Row multiplication: the join that inflates totals

A join with a one-to-many or many-to-many relation yields several rows per left-hand row. Every aggregate computed over the joined result then counts each left-hand value several times.

```sql
SELECT sum(b.price) AS wrong_total
FROM books b
JOIN book_genre bg ON bg.book_id = b.id;
```

```
 wrong_total
-------------
       85.90
(1 row)
```

The books in `book_genre` cost 55.40 in total (12.50 + 15.00 + 9.90 + 18.00); the join counted Tidewater and Quiet Engines twice because each has two genres. The same effect hits you whenever you join two independent one-to-many relations in one query:

```sql
SELECT b.title,
       count(*)              AS joined_rows,
       count(DISTINCT l.id)  AS loans
FROM books b
JOIN book_genre bg ON bg.book_id = b.id
JOIN loans l       ON l.book_id = b.id
GROUP BY b.id, b.title
ORDER BY b.id;
```

```
     title     | joined_rows | loans
---------------+-------------+-------
 Tidewater     |           6 |     3
 Salt Roads    |           1 |     1
 Quiet Engines |           4 |     2
(3 rows)
```

Tidewater has 2 genres and 3 loans: the join emits 2 x 3 = 6 rows. Any `sum` over loan columns would be doubled, any `sum` over genre columns tripled. The remedies, in order of preference:

1. Aggregate each many-side separately, then join the one-row-per-key results.
2. Use a correlated scalar subquery for a single number per row.
3. Use `count(DISTINCT ...)` for counts only, and only when you understand why; it does not fix sums.

```sql
-- 1. aggregate first, join after
SELECT b.title, COALESCE(lc.loans, 0) AS loans, COALESCE(gc.genres, 0) AS genres
FROM books b
LEFT JOIN (SELECT book_id, count(*) AS loans  FROM loans      GROUP BY book_id) lc ON lc.book_id = b.id
LEFT JOIN (SELECT book_id, count(*) AS genres FROM book_genre GROUP BY book_id) gc ON gc.book_id = b.id
ORDER BY b.id;
```

```
      title      | loans | genres
-----------------+-------+--------
 Tidewater       |     3 |      2
 Salt Roads      |     1 |      1
 The Long Ledger |     0 |      1
 Paper Moons     |     1 |      0
 Quiet Engines   |     2 |      2
 Orphan Volume   |     0 |      0
(6 rows)
```

```sql
-- 2. scalar subquery
SELECT b.id, b.title,
       (SELECT count(*) FROM loans l WHERE l.book_id = b.id) AS loans
FROM books b
ORDER BY b.id;
```

Odoo reporting code (`_read_group`, SQL views for reports) fights this all the time: a sale report joining order lines and invoice lines multiplies amounts unless each side is pre-aggregated. When a figure from your SQL differs from the UI, suspect row multiplication first.

## Self-joins

A table joined to itself needs two aliases. Pairs of loans of the same book:

```sql
SELECT x.id AS loan_a, y.id AS loan_b, x.book_id
FROM loans x
JOIN loans y ON y.book_id = x.book_id AND x.id < y.id
ORDER BY loan_a, loan_b;
```

```
 loan_a | loan_b | book_id
--------+--------+---------
      1 |      3 |       1
      1 |      6 |       1
      3 |      6 |       1
      4 |      7 |       5
(4 rows)
```

The `x.id < y.id` condition keeps each unordered pair once and excludes a loan paired with itself. Odoo's own self-referencing tables are `res_partner` (`parent_id`), `product_category`, `account_account` groups, and `stock_location`; "children and their parent's name" is a self join:

```sql
-- fragment against an Odoo database
SELECT c.id, c.name, p.name AS parent_name
FROM res_partner c
LEFT JOIN res_partner p ON p.id = c.parent_id
LIMIT 10;
```

## CROSS JOIN, and the accidental one

`CROSS JOIN` returns every pair. It is sometimes what you want (all months times all products for a grid), and otherwise a disaster:

```sql
SELECT m.name, b.title
FROM members m
CROSS JOIN books b
WHERE m.id <= 2 AND b.id <= 2
ORDER BY m.id, b.id;
```

```
 name |   title
------+------------
 Nora | Tidewater
 Nora | Salt Roads
 Omar | Tidewater
 Omar | Salt Roads
(4 rows)
```

The accidental version is `FROM members, books` with the join condition forgotten in `WHERE`: 4 members x 6 books gives 24 rows here; on `res_partner` x `sale_order_line` it gives billions and a query that eats the server until `statement_timeout`. A missing join condition is a bug whose symptom is "the query never finishes". Prefer the explicit `JOIN ... ON` syntax: it makes the condition mandatory, since the parser rejects a `JOIN` without `ON` (except `CROSS JOIN`).

## USING and NATURAL

When the join columns have the same name on both sides, `JOIN ... USING (col)` is a shorter `ON` and returns the column once. Our schema uses `book_id` in both `loans` and `book_genre`:

```sql
SELECT bg.genre_id, l.id AS loan_id
FROM loans l
JOIN book_genre bg USING (book_id)
ORDER BY l.id, bg.genre_id;
```

Odoo columns are named `<field>_id`, usually with a different name from the target's `id`, so `USING` rarely fits; spell out `ON`. Avoid `NATURAL JOIN` entirely: it joins on every same-named column, so adding a column such as `create_date` to either table changes the meaning of the query without any edit to it. Every Odoo table has `id`, `create_uid`, `create_date`, `write_uid`, `write_date`, and `NATURAL JOIN` would try to match all of them.

## LATERAL: a subquery that sees the row to its left

A `LATERAL` subquery may refer to columns of earlier tables in the same `FROM`. It is the natural tool for "top N per row", the newest loan for each member, the latest price per product, the last message per record:

```sql
SELECT a.name, b.title, b.published_year
FROM authors a
JOIN LATERAL (
    SELECT title, published_year
    FROM books
    WHERE author_id = a.id
    ORDER BY published_year DESC
    LIMIT 1
) b ON true
ORDER BY a.id;
```

```
     name     |     title     | published_year
--------------+---------------+----------------
 Ada Marlowe  | Salt Roads    |           2004
 Boris Venn   | Paper Moons   |           2015
 Chiara Lund  | Quiet Engines |           2019
(3 rows)
```

`JOIN LATERAL (...) ON true` behaves like an inner join (authors without books drop out); `LEFT JOIN LATERAL (...) ON true` keeps them with NULLs:

```sql
SELECT a.name, b.title
FROM authors a
LEFT JOIN LATERAL (
    SELECT title FROM books WHERE author_id = a.id ORDER BY published_year DESC LIMIT 1
) b ON true
ORDER BY a.id;
```

```
     name      |     title
---------------+---------------
 Ada Marlowe   | Salt Roads
 Boris Venn    | Paper Moons
 Chiara Lund   | Quiet Engines
 Dmitri Okafor |
(4 rows)
```

With an index on `(author_id, published_year)` this does one index probe per author, usually far better than sorting all books; with window functions (next chapter) it is a second option.

## Combining result sets: UNION, INTERSECT, EXCEPT

Set operators stack queries with the same column count and compatible types:

```sql
SELECT title FROM books WHERE author_id = 1
UNION
SELECT title FROM books WHERE status = 'lost'
ORDER BY title;
```

```
      title
-----------------
 Salt Roads
 The Long Ledger
 Tidewater
(3 rows)
```

`UNION` removes duplicates (it sorts or hashes to do so); `UNION ALL` keeps all rows and is much cheaper, so use it whenever duplicates are impossible or acceptable. `INTERSECT` keeps rows found in both; `EXCEPT` rows in the first but not the second:

```sql
SELECT member_id FROM loans WHERE book_id = 1
INTERSECT
SELECT member_id FROM loans WHERE book_id = 5
ORDER BY 1;
```

```
 member_id
-----------
         1
         2
(2 rows)
```

Swap `INTERSECT` for `EXCEPT` and the result is member 3: borrowed book 1, never book 5. The column names come from the first query. Odoo uses `UNION ALL` heavily in SQL-view reports (`CREATE VIEW ... AS SELECT ... UNION ALL SELECT ...`).

## Pitfalls

- **Inner join on an optional key.** Records with NULL in the foreign key vanish from the result. Use `LEFT JOIN` for anything that is not `NOT NULL`.
- **Filtering the right table in `WHERE` after a left join.** It turns the join into an inner join. Put the condition in `ON`.
- **Fan-out in aggregates.** Two one-to-many joins in one query multiply rows; sums and counts inflate. Pre-aggregate each side.
- **`count(*)` over a left join.** The unmatched row counts as 1. Count a column of the right table.
- **A missing join condition.** The query returns the product of the two tables, or never returns. Always write `ON`, and always check row counts on a first run with `LIMIT` or `count(*)`.
- **`NATURAL JOIN` and `SELECT *` across joins.** Shared column names (`id`, `name`, audit columns) collide; clients that read result rows into a dict silently keep one of them. Alias what you select.
- **Unqualified column names.** They work until someone adds a same-named column to another joined table.
- **Joining on translated fields or JSON.** In Odoo 16+ `name` of `product_template` is `jsonb`; `JOIN ... ON a.name = b.name` compares JSON documents, not display names.
- **Assuming a join ordering you wrote is the order of execution.** The planner reorders inner joins; you are describing the result, not the procedure.
- **`UNION` where `UNION ALL` is meant.** Deduplication hides legitimate duplicate rows and costs a sort.

## Try it

1. List each loan with the book title, the author's name (or `unknown` when the book has none), and the member's name. Keep all seven loans.

2. Which members have never borrowed anything? Write it twice: once with `LEFT JOIN ... IS NULL` and once with `NOT EXISTS`.

3. For each author, return the number of books and the total price of those books, including authors without books (show 0 for both). Then add a join to `loans` to count loans per author and explain what happens to the price total if you join naively.

4. For every member, show the title of the book they borrowed most recently. Members with no loans should appear with an empty title. Use `LATERAL`.

5. List the genres that have no books. Then list pairs of distinct genres that occur together on at least one book (each pair once).

<details>
<summary>Solution</summary>

1. 
```sql
SELECT l.id, b.title, COALESCE(a.name, 'unknown') AS author, m.name AS member
FROM loans l
JOIN books b   ON b.id = l.book_id
LEFT JOIN authors a ON a.id = b.author_id
JOIN members m ON m.id = l.member_id
ORDER BY l.id;
```
The books in all loans have an author, so `unknown` does not appear; the left join is still the correct choice. Seven rows.

2. 
```sql
SELECT m.name FROM members m
LEFT JOIN loans l ON l.member_id = m.id
WHERE l.id IS NULL;

SELECT m.name FROM members m
WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.member_id = m.id);
```
Both return `Quinn`.

3. 
```sql
SELECT a.name, count(b.id) AS books, COALESCE(sum(b.price), 0) AS total_price
FROM authors a
LEFT JOIN books b ON b.author_id = a.id
GROUP BY a.id, a.name
ORDER BY a.id;
```
```
     name      | books | total_price
---------------+-------+-------------
 Ada Marlowe   |     2 |       27.50
 Boris Venn    |     2 |       20.90
 Chiara Lund   |     1 |       18.00
 Dmitri Okafor |     0 |           0
(4 rows)
```
Adding `LEFT JOIN loans l ON l.book_id = b.id` repeats each book once per loan: `Tidewater` (12.50) appears 3 times, so Ada's total becomes 12.50 x 3 + 15.00 x 1 = 52.50 and her book count 4 unless you use `count(DISTINCT b.id)`. The price sum cannot be repaired with `DISTINCT`: aggregate loans per book first in a subquery and join that.

4. 
```sql
SELECT m.name, last_loan.title
FROM members m
LEFT JOIN LATERAL (
    SELECT b.title
    FROM loans l JOIN books b ON b.id = l.book_id
    WHERE l.member_id = m.id
    ORDER BY l.loaned_on DESC, l.id DESC
    LIMIT 1
) last_loan ON true
ORDER BY m.id;
```
```
 name  |     title
-------+---------------
 Nora  | Quiet Engines
 Omar  | Quiet Engines
 Petra | Tidewater
 Quinn |
(4 rows)
```

5. 
```sql
SELECT g.name FROM genres g
WHERE NOT EXISTS (SELECT 1 FROM book_genre bg WHERE bg.genre_id = g.id);
```
Returns no rows: every genre has a book (History belongs to Tidewater). For pairs:
```sql
SELECT DISTINCT g1.name AS genre_a, g2.name AS genre_b
FROM book_genre x
JOIN book_genre y ON y.book_id = x.book_id AND x.genre_id < y.genre_id
JOIN genres g1 ON g1.id = x.genre_id
JOIN genres g2 ON g2.id = y.genre_id
ORDER BY 1, 2;
```
```
 genre_a | genre_b
---------+---------
 Fiction | History
 Fiction | Poetry
(2 rows)
```
The `x.genre_id < y.genre_id` condition is the self-join trick from above that yields each pair once.

</details>
