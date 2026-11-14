---
description: "GROUP BY, HAVING, and window functions for reporting queries."
---

# Aggregation and window functions

Counting records per state, summing amounts per month, ranking customers, finding the previous row: these are the questions behind every Odoo list view with a "group by", every pivot, and most report SQL. Aggregates collapse many rows into one; window functions compute over a set of related rows without collapsing them. This chapter covers both, including the NULL and fan-out behaviours that make totals wrong, with the library schema from [Relational basics](relational-basics.md) and the extra tables from [Joins](joins.md).

## Aggregate functions

An aggregate reads many rows and returns one value. Without `GROUP BY`, the whole filtered table is one group:

```sql
SELECT count(*)                 AS all_rows,
       count(author_id)         AS with_author,
       count(DISTINCT author_id) AS distinct_authors,
       sum(price)               AS total_price,
       avg(price)               AS avg_price,
       min(price)               AS cheapest,
       max(price)               AS dearest,
       sum(pages)               AS total_pages
FROM books;
```

```
 all_rows | with_author | distinct_authors | total_price |      avg_price      | cheapest | dearest | total_pages
----------+-------------+------------------+-------------+---------------------+----------+---------+-------------
        6 |           5 |                3 |       71.40 | 11.9000000000000000 |     5.00 |   18.00 |        1770
(1 row)
```

Read the first three columns carefully, they are the core of the NULL behaviour:

- `count(*)` counts rows.
- `count(expr)` counts rows where `expr` is not NULL. Here one book has no author, so 5.
- `count(DISTINCT expr)` counts different non-NULL values: authors 1, 2, 3.

Every aggregate except `count(*)` ignores NULL inputs. `avg(price)` divides by the number of non-NULL prices, not by the number of rows. If an input set is empty (or all NULL), `sum`, `avg`, `min`, `max` return NULL, while `count` returns 0:

```sql
SELECT count(*) AS n, sum(price) AS total FROM books WHERE status = 'missing';
```

```
 n | total
---+-------
 0 |
(1 row)
```

So `sum(...)` of nothing is NULL, not zero, and an application doing arithmetic on it will fail or, in Python, hit `None`. Write `COALESCE(sum(price), 0)`.

`avg` of integers returns `numeric`, so it is safe. The integer-division surprise lives in `sum(a) / sum(b)`: `sum` of an `integer` column is `bigint`, and dividing two bigints truncates. Cast one side to `numeric`.

## GROUP BY

`GROUP BY` splits rows into groups sharing the same value of the listed expressions, and each aggregate is computed per group:

```sql
SELECT status, count(*) AS n, round(avg(price), 2) AS avg_price
FROM books
GROUP BY status
ORDER BY status;
```

```
  status   | n | avg_price
-----------+---+-----------
 available | 5 |     12.30
 lost      | 1 |      9.90
(2 rows)
```

Every column in `SELECT` must either appear in `GROUP BY` or sit inside an aggregate. Otherwise:

```sql
SELECT status, title, count(*) FROM books GROUP BY status;
```

```
ERROR:  column "books.title" must appear in the GROUP BY clause or be used in an aggregate function
```

The error is correct: which title would represent five different books? There is one exception that you will see in Odoo SQL: if you group by a table's primary key, every other column of that table is functionally dependent and may be selected without listing it (`GROUP BY b.id` and then `SELECT b.title`). PostgreSQL knows this; MySQL-style laxness elsewhere does not exist.

NULL forms its own group:

```sql
SELECT author_id, count(*) AS books, sum(pages) AS pages
FROM books
GROUP BY author_id
ORDER BY author_id;
```

```
 author_id | books | pages
-----------+-------+-------
         1 |     2 |   730
         2 |     2 |   430
         3 |     1 |   520
           |     1 |    90
(4 rows)
```

The last row is the group of books with no author. In `GROUP BY` and `DISTINCT`, NULLs are treated as equal to each other, unlike in `WHERE` comparisons. This is exactly what the Odoo list view shows as "None" in a grouped list.

You can group by an expression, and `GROUP BY 1` refers to the first select column:

```sql
SELECT to_char(date_trunc('month', loaned_on), 'YYYY-MM') AS month, count(*) AS loans
FROM loans
GROUP BY 1
ORDER BY 1;
```

```
  month  | loans
---------+-------
 2024-01 |     1
 2024-02 |     1
 2024-03 |     2
 2024-04 |     1
 2024-05 |     2
(5 rows)
```

Months with no loans are absent, which is how charts end up with gaps. Fill them by joining against `generate_series`:

```sql
SELECT to_char(m, 'YYYY-MM') AS month, count(l.id) AS loans
FROM generate_series('2024-01-01'::timestamp, '2024-06-01'::timestamp, interval '1 month') AS m
LEFT JOIN loans l ON l.loaned_on >= m AND l.loaned_on < m + interval '1 month'
GROUP BY m
ORDER BY m;
```

```
  month  | loans
---------+-------
 2024-01 |     1
 2024-02 |     1
 2024-03 |     2
 2024-04 |     1
 2024-05 |     2
 2024-06 |     0
(6 rows)
```

## HAVING: filter groups

`WHERE` filters rows before grouping; `HAVING` filters groups after aggregation, and can use aggregates:

```sql
SELECT author_id, count(*) AS books
FROM books
GROUP BY author_id
HAVING count(*) > 1
ORDER BY author_id;
```

```
 author_id | books
-----------+-------
         1 |     2
         2 |     2
(2 rows)
```

Put every condition that does not need an aggregate in `WHERE`, since it removes rows before the work of grouping. `HAVING status = 'available'` returns the same rows as `WHERE status = 'available'` but computes all groups first.

## FILTER: conditional aggregates

Counting several conditions in one scan is common in dashboards. The standard SQL way is `FILTER`:

```sql
SELECT count(*) FILTER (WHERE returned_on IS NULL)      AS open,
       count(*) FILTER (WHERE returned_on > due_on)     AS late,
       count(*)                                         AS total
FROM loans;
```

```
 open | late | total
------+------+-------
    2 |    1 |     7
(1 row)
```

The older idiom `sum(CASE WHEN cond THEN 1 ELSE 0 END)` works everywhere and you will see it in a lot of code; `FILTER` is clearer and keeps NULL out of the way (`CASE` without `ELSE` yields NULL, and `sum` of nothing is NULL).

## Collecting values: string_agg, array_agg

To read a group as a list rather than a count:

```sql
SELECT m.name,
       string_agg(b.title, ', ' ORDER BY l.loaned_on) AS titles,
       array_agg(b.id ORDER BY l.loaned_on)           AS book_ids
FROM members m
JOIN loans l ON l.member_id = m.id
JOIN books b ON b.id = l.book_id
GROUP BY m.id, m.name
ORDER BY m.id;
```

```
 name  |                titles                | book_ids
-------+--------------------------------------+----------
 Nora  | Tidewater, Salt Roads, Quiet Engines | {1,2,5}
 Omar  | Tidewater, Quiet Engines             | {1,5}
 Petra | Paper Moons, Tidewater               | {4,1}
(3 rows)
```

The `ORDER BY` inside the aggregate makes the list order deterministic; without it the order is whatever the scan produced. `string_agg` skips NULL values. `array_agg` keeps them. A grouped `array_agg(id)` is what the ORM's `read_group` uses to return the ids of records in a group, and it is handy for answering "which records are in this bucket" while debugging.

Other useful aggregates: `bool_and` / `bool_or` (all/any true), `percentile_cont(0.5) WITHIN GROUP (ORDER BY x)` for the median, `mode()`, `stddev`, and `jsonb_agg`/`jsonb_object_agg` for building JSON.

```sql
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median_price FROM books;
```

```
 median_price
--------------
        11.75
(1 row)
```

`avg` is 11.90 and the median 11.75: with six values the median is the mean of the middle two (11.00 and 12.50).

## Subtotals: ROLLUP and GROUPING SETS

`GROUP BY ROLLUP (a, b)` adds subtotal and grand-total rows; `GROUPING SETS` lists exactly the groupings you want:

```sql
SELECT member_id, count(*) AS loans
FROM loans
GROUP BY ROLLUP (member_id)
ORDER BY member_id;
```

```
 member_id | loans
-----------+-------
         1 |     3
         2 |     2
         3 |     2
           |     7
(4 rows)
```

The last row, with NULL in the grouping column, is the grand total. When the grouping column can itself be NULL, the subtotal row and a genuine NULL group look the same; use `grouping(member_id)` (1 on a subtotal row) to tell them apart. Odoo's pivot view works much like this, though it computes its totals in separate queries.

## Aggregates over joins: the fan-out again

Recall from [Joins](joins.md) that a one-to-many join repeats the left row. Aggregating after the join multiplies. Compare:

```sql
-- authors, their book counts, and loan counts, done wrong
SELECT a.name, count(b.id) AS books, count(l.id) AS loans
FROM authors a
LEFT JOIN books b ON b.author_id = a.id
LEFT JOIN loans l ON l.book_id = b.id
GROUP BY a.id, a.name
ORDER BY a.id;
```

```
     name      | books | loans
---------------+-------+-------
 Ada Marlowe   |     4 |     4
 Boris Venn    |     2 |     1
 Chiara Lund   |     2 |     2
 Dmitri Okafor |     0 |     0
(4 rows)
```

Ada has two books, not four: Tidewater matched three loans, so it was counted three times. `count(DISTINCT b.id)` fixes the book count; the loan count is right because each loan row is unique. The clean method is to aggregate the many side first:

```sql
SELECT a.name, count(b.id) AS books, COALESCE(sum(lc.loans), 0) AS loans
FROM authors a
LEFT JOIN books b ON b.author_id = a.id
LEFT JOIN (SELECT book_id, count(*) AS loans FROM loans GROUP BY book_id) lc ON lc.book_id = b.id
GROUP BY a.id, a.name
ORDER BY a.id;
```

```
     name      | books | loans
---------------+-------+-------
 Ada Marlowe   |     2 |     4
 Boris Venn    |     2 |     1
 Chiara Lund   |     1 |     2
 Dmitri Okafor |     0 |     0
(4 rows)
```

Now Ada has 2 books and 4 loans, and Chiara 1 book and 2 loans, as in the data. (Check the first result again: Chiara showed 2 books, because her one book matched two loans.) Any time a "count" is larger than the number of records you can see in the UI, look for an unaggregated join.

## Window functions

A window function computes a value for each row from a set of related rows (its window) but does not collapse the rows. The syntax is `function(...) OVER (PARTITION BY ... ORDER BY ... frame)`. `PARTITION BY` splits rows into independent groups (like `GROUP BY` without collapsing), `ORDER BY` orders rows inside each partition, and the optional frame narrows the rows considered for the current one.

### Aggregates as windows

Any aggregate becomes a window function with `OVER`. Compare each book with the overall average:

```sql
SELECT title, price,
       round(avg(price) OVER (), 2)             AS overall_avg,
       round(price - avg(price) OVER (), 2)     AS diff
FROM books
ORDER BY id;
```

```
      title      | price | overall_avg |  diff
-----------------+-------+-------------+-------
 Tidewater       | 12.50 |       11.90 |  0.60
 Salt Roads      | 15.00 |       11.90 |  3.10
 The Long Ledger |  9.90 |       11.90 | -2.00
 Paper Moons     | 11.00 |       11.90 | -0.90
 Quiet Engines   | 18.00 |       11.90 |  6.10
 Orphan Volume   |  5.00 |       11.90 | -6.90
(6 rows)
```

`OVER ()` means one window containing all rows. With `PARTITION BY`, each author's books are compared to the author's best:

```sql
SELECT title, author_id, price,
       max(price) OVER (PARTITION BY author_id) AS best_in_author
FROM books
WHERE author_id IS NOT NULL
ORDER BY id;
```

```
      title      | author_id | price | best_in_author
-----------------+-----------+-------+----------------
 Tidewater       |         1 | 12.50 |          15.00
 Salt Roads      |         1 | 15.00 |          15.00
 The Long Ledger |         2 |  9.90 |          11.00
 Paper Moons     |         2 | 11.00 |          11.00
 Quiet Engines   |         3 | 18.00 |          18.00
(5 rows)
```

This replaces a self-join or a correlated subquery, and the plan reads the table once.

### Ranking: row_number, rank, dense_rank, ntile

```sql
SELECT id, member_id, loaned_on,
       row_number() OVER (PARTITION BY member_id ORDER BY loaned_on) AS nth_loan
FROM loans
ORDER BY member_id, loaned_on;
```

```
 id | member_id | loaned_on  | nth_loan
----+-----------+------------+----------
  1 |         1 | 2024-01-05 |        1
  2 |         1 | 2024-02-01 |        2
  7 |         1 | 2024-05-20 |        3
  3 |         2 | 2024-03-10 |        1
  4 |         2 | 2024-03-12 |        2
  5 |         3 | 2024-04-02 |        1
  6 |         3 | 2024-05-01 |        2
(7 rows)
```

`row_number` numbers rows 1, 2, 3 within each partition; ties get arbitrary but distinct numbers, so always add a tie-breaker (`ORDER BY loaned_on, id`) when the order must be reproducible. `rank` gives equal rows the same number and then skips; `dense_rank` does not skip; `ntile(n)` cuts the ordered rows into n buckets.

```sql
SELECT m.name, count(l.id) AS loans,
       rank()       OVER (ORDER BY count(l.id) DESC) AS rank,
       dense_rank() OVER (ORDER BY count(l.id) DESC) AS dense_rank
FROM members m
LEFT JOIN loans l ON l.member_id = m.id
GROUP BY m.id, m.name
ORDER BY rank, m.name;
```

```
 name  | loans | rank | dense_rank
-------+-------+------+------------
 Nora  |     3 |    1 |          1
 Omar  |     2 |    2 |          2
 Petra |     2 |    2 |          2
 Quinn |     0 |    4 |          3
(4 rows)
```

This query shows an important ordering: windows are evaluated after `GROUP BY` and `HAVING`, so a window function can rank aggregated results, as here (a window over `count(l.id)`). Omar and Petra tie at rank 2; `rank` then jumps to 4, `dense_rank` continues with 3.

### The top-N-per-group pattern

You cannot filter on a window function in `WHERE` (it is evaluated later than `WHERE`). Wrap the query:

```sql
SELECT id, member_id, loaned_on
FROM (
    SELECT id, member_id, loaned_on,
           row_number() OVER (PARTITION BY member_id ORDER BY loaned_on DESC, id DESC) AS rn
    FROM loans
) t
WHERE rn = 1
ORDER BY member_id;
```

```
 id | member_id | loaned_on
----+-----------+------------
  7 |         1 | 2024-05-20
  4 |         2 | 2024-03-12
  6 |         3 | 2024-05-01
(3 rows)
```

That is the latest loan per member. It is the window-function sibling of `DISTINCT ON` and `LATERAL`; pick `DISTINCT ON` for brevity, `LATERAL` when an index can serve each probe, and the window form when you also need ranks or several rows per group.

### lag and lead: look at neighbouring rows

```sql
SELECT id, member_id, loaned_on,
       lag(loaned_on) OVER (PARTITION BY member_id ORDER BY loaned_on) AS previous_loan,
       loaned_on - lag(loaned_on) OVER (PARTITION BY member_id ORDER BY loaned_on) AS days_since
FROM loans
ORDER BY member_id, loaned_on;
```

```
 id | member_id | loaned_on  | previous_loan | days_since
----+-----------+------------+---------------+------------
  1 |         1 | 2024-01-05 |               |
  2 |         1 | 2024-02-01 | 2024-01-05    |         27
  7 |         1 | 2024-05-20 | 2024-02-01    |        109
  3 |         2 | 2024-03-10 |               |
  4 |         2 | 2024-03-12 | 2024-03-10    |          2
  5 |         3 | 2024-04-02 |               |
  6 |         3 | 2024-05-01 | 2024-04-02    |         29
(7 rows)
```

`lag(x, n, default)` looks back n rows (default 1), `lead` looks forward; the first row of a partition has no predecessor, hence NULL, or the default you pass. This is the standard way to compute gaps between events, durations between a record's states from a tracking table, or a running balance difference.

### Running totals and frames

Adding `ORDER BY` inside `OVER` turns an aggregate into a running one:

```sql
SELECT title, price, sum(price) OVER (ORDER BY id) AS running_total
FROM books
ORDER BY id;
```

```
      title      | price | running_total
-----------------+-------+---------------
 Tidewater       | 12.50 |         12.50
 Salt Roads      | 15.00 |         27.50
 The Long Ledger |  9.90 |         37.40
 Paper Moons     | 11.00 |         48.40
 Quiet Engines   | 18.00 |         66.40
 Orphan Volume   |  5.00 |         71.40
(6 rows)
```

The default frame with an `ORDER BY` is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, and `RANGE` includes all peers: rows that tie on the ordering value. Order by something that is not unique and you see it:

```sql
SELECT title, author_id, pages,
       sum(pages) OVER (ORDER BY author_id) AS running_pages
FROM books
ORDER BY author_id, title;
```

```
      title      | author_id | pages | running_pages
-----------------+-----------+-------+---------------
 Salt Roads      |         1 |   420 |           730
 Tidewater       |         1 |   310 |           730
 Paper Moons     |         2 |   180 |          1160
 The Long Ledger |         2 |   250 |          1160
 Quiet Engines   |         3 |   520 |          1680
 Orphan Volume   |           |    90 |          1770
(6 rows)
```

Both of author 1's books show 730, not 420 and then 730, because they are peers. For a true row-by-row running total use a unique ordering (add `id`) or an explicit `ROWS` frame:

```sql
SELECT id, price,
       sum(price) OVER (ORDER BY id ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) AS two_book_sum
FROM books
ORDER BY id;
```

```
 id | price | two_book_sum
----+-------+--------------
  1 | 12.50 |        12.50
  2 | 15.00 |        27.50
  3 |  9.90 |        24.90
  4 | 11.00 |        20.90
  5 | 18.00 |        29.00
  6 |  5.00 |        23.00
(6 rows)
```

That is a moving sum over the current and previous row. Frames can also look ahead (`1 FOLLOWING`) or cover everything (`UNBOUNDED FOLLOWING`). `first_value`, `last_value`, and `nth_value` read values from the frame, and be careful with `last_value`: with the default frame it returns the current row's value, not the partition's last. Specify the frame if you want the end of the partition.

### Named windows

Repeating the same `OVER (...)` is tedious and error-prone. Define it once:

```sql
SELECT id, member_id,
       row_number() OVER w AS rn,
       lag(loaned_on) OVER w AS previous_loan
FROM loans
WINDOW w AS (PARTITION BY member_id ORDER BY loaned_on, id)
ORDER BY member_id, loaned_on;
```

The `WINDOW` clause goes after `HAVING` and before `ORDER BY`.

## Where this shows up in Odoo

`_read_group` and `read_group` compile into `GROUP BY` queries with `count(*)` and `sum(...)` columns; your debugging queries are just the same thing written by hand. Accounting reports use window functions for running balances and previous-period comparison, and SQL-view reports often use `row_number() OVER (PARTITION BY ...)` to pick "the latest" row. Know these shapes so you can read and fix them.

{% hint style="info" %}
Versions. The Python API of `read_group` changed in Odoo 17 to 18 (a new `_read_group` signature with `groupby`/`aggregates` names, and `formatted_read_group` appearing later). That is ORM territory, covered in the ORM part. The SQL it produces is still `GROUP BY` plus aggregates.
{% endhint %}

## Pitfalls

- **Forgetting that `count(col)` skips NULLs.** `count(*)` counts rows; `count(col)` counts values. Mixing them gives "off by the empty ones".
- **Empty aggregates return NULL.** `sum` over no rows is NULL; wrap with `COALESCE(..., 0)` before arithmetic.
- **Aggregating after a one-to-many join.** The fan-out doubles or triples sums and counts. Pre-aggregate the many side, or move the measure into a subquery.
- **`HAVING` for what belongs in `WHERE`.** Same rows, more work.
- **`avg` of a rate.** The average of per-row percentages is not the percentage of the totals. Compute `sum(a) / sum(b)`, cast to `numeric`, and guard the division with `NULLIF`.
- **Window function in `WHERE`.** Not allowed ("window functions are not allowed in WHERE"). Wrap in a subquery or CTE and filter outside.
- **Ties in `row_number`.** Without a unique tie-breaker the numbering differs between runs, and "top 1" picks a random row among equals.
- **Default frame surprises.** `last_value` returns the current row, and `sum(...) OVER (ORDER BY non_unique)` lumps ties together.
- **NULLs in `GROUP BY`.** They form one group; a "None" bucket is data, not a bug. A NULL subtotal row in `ROLLUP` is confusable with it, use `grouping()`.
- **Group by timestamp.** `GROUP BY create_date` groups by the microsecond. Truncate: `date_trunc('day', create_date)`, and mind the UTC issue from the previous chapter.
- **Counting distinct on huge sets.** `count(DISTINCT x)` sorts or hashes every value; for large tables, aggregate in stages.

## Try it

1. For each member, return the number of loans, the number returned late, and the date of the first loan, including members without any loans.

2. Which author has the highest average book price? Return the name and the average. Then return the full ranking including authors with no books, ranking them last.

3. For each book, return the loan count and its rank by loan count (ties share a rank), showing only books ranked in the top 3.

4. For each member's loans in order, return the loan id, the days kept (returned minus loaned) and a running total of the days kept so far for that member. Open loans have no days; use a unique ordering.

5. Produce a month-by-month table for January to June 2024 showing how many loans were started and how many were returned in that month, with zeros for empty months.

<details>
<summary>Solution</summary>

1. 
```sql
SELECT m.name,
       count(l.id)                                   AS loans,
       count(*) FILTER (WHERE l.returned_on > l.due_on) AS late,
       min(l.loaned_on)                              AS first_loan
FROM members m
LEFT JOIN loans l ON l.member_id = m.id
GROUP BY m.id, m.name
ORDER BY m.id;
```
```
 name  | loans | late | first_loan
-------+-------+------+------------
 Nora  |     3 |    1 | 2024-01-05
 Omar  |     2 |    0 | 2024-03-10
 Petra |     2 |    0 | 2024-04-02
 Quinn |     0 |    0 |
(4 rows)
```
The `FILTER` condition is false for the NULL row that the left join creates for Quinn, so `count(*) FILTER (...)` is 0 and not 1. Using `count(l.id)` for the plain total avoids counting that placeholder row.

2. 
```sql
SELECT a.name, round(avg(b.price), 2) AS avg_price
FROM authors a
JOIN books b ON b.author_id = a.id
GROUP BY a.id, a.name
ORDER BY avg_price DESC
LIMIT 1;
```
Chiara Lund, 18.00 (Ada: 13.75, Boris: 10.45). For the full ranking with the empty author last, use a left join and `ORDER BY avg(b.price) DESC NULLS LAST`; the empty author's average is NULL.

3. 
```sql
SELECT title, loans, rnk
FROM (
    SELECT b.title, count(l.id) AS loans,
           rank() OVER (ORDER BY count(l.id) DESC) AS rnk
    FROM books b
    LEFT JOIN loans l ON l.book_id = b.id
    GROUP BY b.id, b.title
) t
WHERE rnk <= 3
ORDER BY rnk, title;
```
```
     title     | loans | rnk
---------------+-------+-----
 Tidewater     |     3 |   1
 Quiet Engines |     2 |   2
 Paper Moons   |     1 |   3
 Salt Roads    |     1 |   3
(4 rows)
```
Four rows because of the tie at rank 3.

4. 
```sql
SELECT id, member_id, loaned_on, returned_on - loaned_on AS days,
       sum(returned_on - loaned_on) OVER (
           PARTITION BY member_id ORDER BY loaned_on, id
       ) AS running_days
FROM loans
ORDER BY member_id, loaned_on, id;
```
`sum` skips NULL days (open loans). Member 1 shows running days 13, 32, 44. Member 2's first row is NULL (its only input so far is the open loan 3) and the second is 13. Member 3 is NULL, then 9.

5. 
```sql
SELECT to_char(m, 'YYYY-MM') AS month,
       (SELECT count(*) FROM loans l WHERE l.loaned_on   >= m AND l.loaned_on   < m + interval '1 month') AS started,
       (SELECT count(*) FROM loans l WHERE l.returned_on >= m AND l.returned_on < m + interval '1 month') AS returned
FROM generate_series('2024-01-01'::timestamp, '2024-06-01'::timestamp, interval '1 month') AS m
ORDER BY m;
```
```
  month  | started | returned
---------+---------+----------
 2024-01 |       1 |        1
 2024-02 |       1 |        1
 2024-03 |       2 |        1
 2024-04 |       1 |        0
 2024-05 |       2 |        1
 2024-06 |       0 |        1
(6 rows)
```
Two independent counts per month are done as scalar subqueries on purpose: joining loans twice would multiply rows.

</details>
