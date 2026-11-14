---
description: "Building collections and streaming large data without loading it all."
---

# Comprehensions and generators

Most loops in business code do one of two things: build a new collection from an old one, or walk through data without needing all of it in memory at once. Python has dedicated syntax for both. A **comprehension** builds a list, dict, or set from an iterable in one expression. A **generator** produces items one at a time, on demand. Odoo code uses comprehensions everywhere you see `[x.name for x in records]`, and generators matter the moment you export or import tens of thousands of rows. This chapter explains both, shows where they pay off, and shows where plain loops are the better choice.

## List comprehensions

The loop

```pycon
>>> squares = []
>>> for n in range(5):
...     squares.append(n * n)
...
>>> squares
[0, 1, 4, 9, 16]
```

is written as a comprehension:

```pycon
>>> [n * n for n in range(5)]
[0, 1, 4, 9, 16]
```

The shape is `[expression for name in iterable]`. Read it as "the expression, for each name in the iterable". The result is always a new list.

### Filtering with `if`

An `if` after the `for` keeps only the items that satisfy it:

```pycon
>>> nums = range(10)
>>> [n for n in nums if n % 2 == 0]
[0, 2, 4, 6, 8]
>>> [n * n for n in nums if n % 2 == 0]
[0, 4, 16, 36, 64]
>>> titles = ["Dune", "", "Emma", "  "]
>>> [t.strip() for t in titles if t.strip()]
['Dune', 'Emma']
```

The filter decides which items enter; the expression decides what each becomes.

### Choosing between two values: `if` and `else` in the expression

An `if`/`else` that picks a value goes **before** the `for`:

```pycon
>>> ["even" if n % 2 == 0 else "odd" for n in range(4)]
['even', 'odd', 'even', 'odd']
```

The two positions differ. `x for x in y if cond` filters. `a if cond else b for x in y` transforms every item. Mixing them up is a syntax error or a wrong result, so check which one you mean.

### Several `for` clauses

Multiple `for` clauses nest, with the leftmost as the outermost loop:

```pycon
>>> [(x, y) for x in range(3) for y in range(2)]
[(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
>>> orders = [{"ref": "A", "lines": [1, 2]}, {"ref": "B", "lines": [3]}]
>>> [line for order in orders for line in order["lines"]]
[1, 2, 3]
```

The second example flattens a list of lists: for each order, for each line. This is the plain-Python equivalent of `mapped("order_line")` followed by iterating the result. More than two `for` clauses usually reads badly; use a loop.

### Using them on records

A recordset iterates like a list, so every comprehension applies to it. The records below are dictionaries standing in for them, to keep the examples runnable anywhere:

```pycon
>>> loans = [
...     {"id": 1, "member": "ada", "state": "open", "days": 14},
...     {"id": 2, "member": "bob", "state": "returned", "days": 7},
...     {"id": 3, "member": "ada", "state": "open", "days": 21},
... ]
>>> [l["id"] for l in loans if l["state"] == "open"]
[1, 3]
>>> sum(l["days"] for l in loans if l["member"] == "ada")
35
```

In real Odoo code the same shapes read `[l.id for l in loans if l.state == "open"]`. For plain extraction, `loans.mapped("id")` or `loans.ids` is shorter. For filtering where you want records back, `loans.filtered(...)` is better than a comprehension because it returns a recordset you can keep working with. Use a comprehension when you want plain values or a different structure, such as a list of tuples or a dict.

## Dict and set comprehensions

Curly braces with a colon build a dict. Without the colon, they build a set:

```pycon
>>> {l["id"]: l["member"] for l in loans}
{1: 'ada', 2: 'bob', 3: 'ada'}
>>> sorted({l["member"] for l in loans})
['ada', 'bob']
>>> {m: sum(l["days"] for l in loans if l["member"] == m) for m in {l["member"] for l in loans}} == {"ada": 35, "bob": 7}
True
```

The last line shows the problem with nesting: it works, but scans the list once per member and is hard to read. Group with `defaultdict` instead ([Lists, tuples, dicts, sets](collections.md)).

Common dict comprehension uses:

```pycon
>>> prices = {"A": 10.0, "B": 5.5}
>>> {sku: round(p * 1.2, 2) for sku, p in prices.items()}
{'A': 12.0, 'B': 6.6}
>>> {v: k for k, v in {"a": 1, "b": 2}.items()}      # invert
{1: 'a', 2: 'b'}
>>> {k: v for k, v in prices.items() if v > 6}
{'A': 10.0}
```

In Odoo, rebuilding a `vals` dict without some keys, or with converted values, is a typical case:

```pycon
>>> vals = {"title": " Dune ", "pages": "612", "note": None}
>>> {k: v for k, v in vals.items() if v is not None}
{'title': ' Dune ', 'pages': '612'}
```

## Scope and evaluation details

The loop variable of a comprehension is local to it and does not leak into the surrounding scope (unlike a `for` statement):

```pycon
>>> [i for i in range(3)]
[0, 1, 2]
>>> i
Traceback (most recent call last):
    ...
NameError: name 'i' is not defined
```

Comprehensions evaluate eagerly and fully, the whole list is built before the next line runs. That is also why a bug inside the expression stops the entire comprehension.

## When not to use a comprehension

A comprehension is for building a collection. Do not use it for side effects:

```python
[record.unlink() for record in records]       # wrong: builds a throwaway list
```

That builds a list of return values nobody wants. Write a loop. Equally, do not stack conditions until the line needs three readings:

```python
result = [(a, b) for a in xs if a.ok for b in a.children if b.visible and not b.deleted]
```

A three-line loop is clearer than that. A rule that holds up in practice: if it does not fit on one line without a squint, or needs more than one `if`, write the loop and name the intermediate steps.

## Generator expressions

Replace the square brackets of a list comprehension with parentheses and you get a **generator expression**. It does not build the list. It produces one item at a time, when asked:

```pycon
>>> gen = (n * n for n in range(5))
>>> gen
<generator object <genexpr> at 0x...>
>>> next(gen), next(gen)
(0, 1)
>>> list(gen)
[4, 9, 16]
>>> list(gen)
[]
```

Three things to notice:

1. The generator did no work when created. Each `next()` computes one item.
2. It remembers where it is. After two `next` calls, `list(gen)` gives the remaining three.
3. It is **exhausted** after one pass. The second `list(gen)` returns an empty list, and no error is raised. This is the most common generator surprise.

Pass a generator expression directly to a function that consumes an iterable; when it is the only argument you can drop the extra parentheses:

```pycon
>>> sum(n * n for n in range(1000))
332833500
>>> any(l["state"] == "open" for l in loans)
True
>>> max(len(t) for t in ["Dune", "Ulysses"])
7
>>> ", ".join(str(l["id"]) for l in loans)
'1, 2, 3'
```

This avoids building an intermediate list. `any` and `all` also stop at the first decisive item, so a generator is not merely cheaper, it does less work.

### Memory: a measurable difference

```pycon
>>> import sys
>>> big_list = [n for n in range(1_000_000)]
>>> big_gen = (n for n in range(1_000_000))
>>> sys.getsizeof(big_list) > 1_000_000
True
>>> sys.getsizeof(big_gen) < 1000
True
```

A list of a million integers takes megabytes (plus the integers). The generator holds a few hundred bytes regardless of length. In an Odoo worker that has a memory limit, that difference is the difference between finishing an export and being killed.

## Generator functions and `yield`

A function with `yield` in its body is a **generator function**. Calling it does not run the body. It returns a generator, and the body runs in slices, each time up to the next `yield`:

```pycon
>>> def countdown(n):
...     print("start")
...     while n > 0:
...         yield n
...         n -= 1
...     print("done")
...
>>> g = countdown(3)
>>> next(g)
start
3
>>> next(g)
2
>>> list(g)
done
[1]
```

Nothing printed when `countdown(3)` was called. `start` appeared at the first `next`. The function's local state (`n`) persists between `next` calls. When the body ends, the generator raises `StopIteration`, which `for` loops and `list()` catch for you.

A `for` loop does exactly this behind the scenes:

```pycon
>>> for n in countdown(2):
...     print("got", n)
...
start
got 2
got 1
done
```

### Why generators matter: streaming

A generator can describe a pipeline over data that does not fit in memory. Process a big file one line at a time:

```python
def read_rows(path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            yield line.rstrip("\n").split(",")

def only_open(rows):
    for row in rows:
        if row[1] == "open":
            yield row

def count(rows):
    return sum(1 for _ in rows)

print(count(only_open(read_rows("loans.csv"))))
```

At any moment only one row exists in memory. Each stage pulls from the one before it, and nothing is read until the final consumer asks. Stages compose without intermediate lists.

Here is a version you can run without a file:

```pycon
>>> def read_rows(lines):
...     for line in lines:
...         yield line.split(",")
...
>>> def only_open(rows):
...     for row in rows:
...         if row[1] == "open":
...             yield row
...
>>> data = ["b1,open", "b2,returned", "b3,open"]
>>> sum(1 for _ in only_open(read_rows(data)))
2
```

The `_` is a conventional name for a value you do not use.

### Chunking: batches of records

Processing a large set of ids in batches limits memory and transaction size. A generator that yields slices:

```pycon
>>> def chunked(items, size):
...     for start in range(0, len(items), size):
...         yield items[start:start + size]
...
>>> list(chunked(list(range(1, 8)), 3))
[[1, 2, 3], [4, 5, 6], [7]]
```

The batching helper takes a list; it works for lists of ids and also for an Odoo `ids` list. In Odoo, large jobs that should not run in one transaction commit between batches, which brings its own caveats (the transactions chapter in the PostgreSQL part). The loop shape is:

```python
for batch_ids in chunked(all_ids, 500):
    records = model.browse(batch_ids)
    process(records)
```

Here `model.browse(ids)` builds a recordset of the given ids without a query; the data is fetched lazily when fields are read. Odoo's recordsets also cache field values, so a long loop that touches many records holds a lot of cached data; batching with cache invalidation between batches keeps memory flat. The details belong to the ORM part of the book.

### Infinite generators

A generator need not end. Combine it with something that stops:

```pycon
>>> def naturals():
...     n = 1
...     while True:
...         yield n
...         n += 1
...
>>> from itertools import islice
>>> list(islice(naturals(), 5))
[1, 2, 3, 4, 5]
>>> next(n for n in naturals() if n * n > 50)
8
```

`itertools.islice` takes the first `k` items of any iterator. Never call `list()` on an infinite generator, since it never returns.

### `yield from`

`yield from other` hands over to another iterable and yields all of its items. It flattens nested generators:

```pycon
>>> def walk(node):
...     yield node["name"]
...     for child in node.get("children", []):
...         yield from walk(child)
...
>>> tree = {"name": "root", "children": [{"name": "a", "children": [{"name": "b"}]}, {"name": "c"}]}
>>> list(walk(tree))
['root', 'a', 'b', 'c']
```

This is a clean way to traverse hierarchies. Compare it with the recursive function in [Functions](functions.md), which returned only the depth.

## The iterator protocol

Why can `for` loop over lists, files, dicts, generators, and Odoo recordsets? They all implement the same two-method protocol:

- An **iterable** has `__iter__()`, which returns an iterator.
- An **iterator** has `__next__()`, which returns the next item or raises `StopIteration`, and `__iter__()` returning itself.

```pycon
>>> it = iter([10, 20])
>>> next(it), next(it)
(10, 20)
>>> next(it)
Traceback (most recent call last):
    ...
StopIteration
```

A list is an iterable, not an iterator. Each `iter(list)` call gives a fresh iterator, so you can loop over a list repeatedly. A generator is its own iterator, so you can loop over it only once. This is the whole reason for the "exhausted after one pass" behaviour.

You can make your own class iterable by defining `__iter__`, usually as a generator method:

```pycon
>>> class Shelf:
...     def __init__(self, books):
...         self.books = books
...     def __iter__(self):
...         for book in self.books:
...             yield book
...     def __len__(self):
...         return len(self.books)
...
>>> shelf = Shelf(["Dune", "Emma"])
>>> [b.upper() for b in shelf]
['DUNE', 'EMMA']
>>> len(shelf), list(shelf), list(shelf)
(2, ['Dune', 'Emma'], ['Dune', 'Emma'])
```

Because `Shelf.__iter__` returns a new generator each time, `Shelf` can be looped over repeatedly. An Odoo recordset works this way: it is iterable many times, and iterating yields single-record recordsets. That is why `for loan in self:` gives `loan` as a recordset of one record, not a bare value, and why `if loan:` is false for an empty recordset. Classes are the subject of [Classes and inheritance](classes-and-inheritance.md).

## Useful iterator tools

The `itertools` module is covered in the [Standard library toolbox](standard-library-toolbox.md). Three pieces worth knowing now:

```pycon
>>> from itertools import chain, islice, groupby
>>> list(chain([1, 2], [3], (4, 5)))
[1, 2, 3, 4, 5]
>>> list(islice(range(100), 3))
[0, 1, 2]
>>> data = sorted(loans, key=lambda l: l["member"])
>>> [(member, [l["id"] for l in group]) for member, group in groupby(data, key=lambda l: l["member"])]
[('ada', [1, 3]), ('bob', [2])]
```

`groupby` groups **consecutive** items with equal keys, so the input must be sorted by the same key first. Forgetting to sort gives several groups with the same key, silently. For grouping unsorted data, `defaultdict(list)` is safer. Also, each group is itself a lazy iterator that becomes invalid once you advance the outer loop, so consume the group (as the list comprehension above does) before moving on.

## Choosing: list, generator, or loop

| Situation | Use |
|---|---|
| You need to index, take `len()`, or iterate several times | list comprehension |
| You only iterate once, or feed `sum`, `any`, `max`, `join` | generator expression |
| Data is big, or comes from a file, a cursor, or a network | generator function |
| Several steps or side effects | plain `for` loop |
| You need a mapping or uniqueness | dict or set comprehension |

## Pitfalls

- **Consuming a generator twice.** The second pass is empty and silent. Convert to a list if you must iterate again, or build a new generator for each pass.
- **`list()` on an infinite generator.** It never returns and eats memory until the process is killed.
- **Side effects in comprehensions.** `[rec.write(...) for rec in recs]` builds an unused list. Write a loop.
- **Late errors.** A generator pipeline defers work, so an exception appears at the consumer, far from where the pipeline was built. A traceback through three generator frames is normal.
- **Closing resources too early.** A generator that reads from an open file must keep the file open until exhausted. Returning a generator from inside a `with` block that closes the file gives `ValueError: I/O operation on closed file` on first use. Either do the whole processing inside the `with`, or put the `with` inside the generator function.
- **`if` position confusion.** `[x for x in xs if c]` filters; `[a if c else b for x in xs]` transforms. Mixing them up changes meaning.
- **Overly clever comprehensions.** Nested comprehensions with two conditions are write-only code. Use a loop and named variables.
- **Variable capture in a generator expression.** The iterable of the first `for` is evaluated immediately, everything else lazily. `gen = (x * factor for x in xs)` followed by `factor = 10` uses the new `factor` when consumed.
- **`groupby` without sorting.** Equal keys must be adjacent.
- **Holding a recordset-sized list in memory.** `[r.name for r in huge_recordset]` loads every record in one go. Batch the ids and iterate per batch.
- **Dict comprehension duplicate keys.** Later values silently overwrite earlier ones: `{l["member"]: l for l in loans}` keeps only the last loan per member.

## Try it

1. Using the `loans` data from this chapter, build a dict from member to the total days they have on open loans, with a dict comprehension plus a generator expression (no `defaultdict`).
2. Write a generator `fibonacci()` yielding the Fibonacci numbers forever, then print all of them under 100 using `itertools.takewhile`.
3. Write `read_numbers(lines)` as a generator that yields `int` for each non-blank line, skipping lines that start with `#`. Use it to sum `["1", "# note", "", "4"]`.
4. Write `pairs(seq)` that yields consecutive pairs `(a, b)` from any iterable, for `[1, 2, 3, 4]` giving `(1, 2), (2, 3), (3, 4)`. It must also work with a generator input.
5. A colleague wrote `squares = (n * n for n in range(5)); print(sum(squares)); print(max(squares))` and gets a `ValueError`. Explain why, and fix it two ways.

<details>
<summary>Solution</summary>

1.

```pycon
>>> loans = [
...     {"id": 1, "member": "ada", "state": "open", "days": 14},
...     {"id": 2, "member": "bob", "state": "returned", "days": 7},
...     {"id": 3, "member": "ada", "state": "open", "days": 21},
... ]
>>> members = {l["member"] for l in loans}
>>> {m: sum(l["days"] for l in loans if l["member"] == m and l["state"] == "open") for m in members} == {"ada": 35, "bob": 0}
True
```

For large inputs, a single pass with `defaultdict(int)` is better, because this version rescans `loans` once per member.

2.

```pycon
>>> from itertools import takewhile
>>> def fibonacci():
...     a, b = 0, 1
...     while True:
...         yield a
...         a, b = b, a + b
...
>>> list(takewhile(lambda n: n < 100, fibonacci()))
[0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
```

3.

```pycon
>>> def read_numbers(lines):
...     for line in lines:
...         line = line.strip()
...         if not line or line.startswith("#"):
...             continue
...         yield int(line)
...
>>> sum(read_numbers(["1", "# note", "", "4"]))
5
```

4.

```pycon
>>> def pairs(seq):
...     it = iter(seq)
...     try:
...         previous = next(it)
...     except StopIteration:
...         return
...     for current in it:
...         yield previous, current
...         previous = current
...
>>> list(pairs([1, 2, 3, 4]))
[(1, 2), (2, 3), (3, 4)]
>>> list(pairs(n for n in range(3)))
[(0, 1), (1, 2)]
>>> list(pairs([]))
[]
```

5. `sum(squares)` consumes the generator. `max(squares)` then sees an empty iterator and raises `ValueError: max() ... empty sequence`. Fix one: make a list, `squares = [n * n for n in range(5)]`. Fix two: compute each from a fresh generator, for example by wrapping it in a function `def squares(): return (n * n for n in range(5))` and calling `sum(squares())` and `max(squares())`.

</details>
