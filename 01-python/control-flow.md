---
description: "Conditions, loops, and the idioms that replace most loops."
---

# Control flow

Up to now every example ran top to bottom, once. Real code has to make decisions ("is this loan overdue?"), repeat work ("do this for each record"), and stop early ("nothing to do, return"). Python's tools for that are `if`, `for`, `while`, and a small set of built-ins that replace many hand-written loops. Odoo methods are mostly loops over records with conditions inside, so fluency here pays back on every page of the rest of the book.

## Indentation is syntax

Python marks blocks by indentation, not by braces. A line ending in a colon opens a block, and the lines indented under it form the body:

```python
stock = 0
if stock == 0:
    print("out of stock")
    print("reorder")
print("done")
```

```text
out of stock
reorder
done
```

The two indented lines belong to the `if`. The unindented line runs regardless. Use four spaces per level and never mix tabs and spaces. Moving a line one level left or right changes what the program does without producing any error, so review indentation in diffs with care.

## if, elif, else

```pycon
>>> def loan_status(days_late):
...     if days_late <= 0:
...         return "on time"
...     elif days_late <= 7:
...         return "late"
...     else:
...         return "overdue"
...
>>> loan_status(-2), loan_status(3), loan_status(30)
('on time', 'late', 'overdue')
```

Conditions are checked top to bottom and the first true one wins. Order matters when ranges overlap. Anything can serve as a condition (see truthiness in [Values and types](values-and-types.md)), but be explicit when the distinction between `0`, `None`, and empty matters.

Combine tests with `and`, `or`, `not`, and use chained comparisons for ranges:

```pycon
>>> age = 15
>>> 13 <= age < 18
True
>>> age < 13 or age >= 18
False
>>> not (13 <= age < 18)
False
```

Membership tests are more readable than strings of `or`:

```pycon
>>> state = "done"
>>> state in ("done", "cancel")
True
>>> state == "done" or state == "cancel"
True
```

The `in` form scales and is hard to get wrong.

### Guard clauses

Deeply nested conditions are hard to read:

```python
def renew(loan):
    if loan.state == "open":
        if not loan.renewed:
            if loan.member_active:
                loan.due_days += 7
```

Invert the conditions and exit early:

```python
def renew(loan):
    if loan.state != "open":
        return
    if loan.renewed:
        return
    if not loan.member_active:
        return
    loan.due_days += 7
```

Each condition is now an independent line, and the main action sits at the left margin. In Odoo you will see the same pattern as `if not self: return` at the top of a method, or `if not record.partner_id: continue` inside a loop.

### Conditional expressions

`A if cond else B` picks a value inside an expression:

```pycon
>>> qty = 3
>>> label = "copy" if qty == 1 else "copies"
>>> f"{qty} {label}"
'3 copies'
```

Do not nest them. If the second-level condition needs more than a glance, use a full `if`.

## match (Python 3.10+)

Structural pattern matching compares a value against several shapes. For plain value dispatch it reads better than a chain of `elif`:

```pycon
>>> def next_state(state):
...     match state:
...         case "draft":
...             return "open"
...         case "open":
...             return "returned"
...         case "returned" | "lost":
...             return None
...         case _:
...             raise ValueError(f"unknown state {state!r}")
...
>>> next_state("draft"), next_state("lost")
('open', None)
```

`_` is the wildcard that matches anything and is the "else" branch. `|` combines alternatives. `match` can also take apart tuples, lists, and dictionaries:

```pycon
>>> def describe(command):
...     match command:
...         case (0, _, vals):
...             return f"create {vals}"
...         case (4, rec_id):
...             return f"link {rec_id}"
...         case (5,):
...             return "clear all"
...         case _:
...             return "other"
...
>>> describe((0, 0, {"name": "x"})), describe((4, 7)), describe((5,))
("create {'name': 'x'}", 'link 7', 'clear all')
```

The tuples here have the shape of Odoo's x2many commands, which is the kind of data `match` suits. It needs Python 3.10, so check your target Odoo version's interpreter before using it in a module. A chain of `if`/`elif` works everywhere.

## for loops

`for name in iterable:` runs the body once per item. An **iterable** is anything you can loop over: lists, tuples, strings, dicts, sets, files, ranges, generators, and Odoo recordsets.

```pycon
>>> for title in ["Dune", "Emma"]:
...     print(title.upper())
DUNE
EMMA
>>> for ch in "abc":
...     print(ch, end="-")
...
a-b-c-
```

The `end="-"` argument replaces the newline that `print` normally appends.

The loop variable keeps its last value after the loop ends, and it is an ordinary variable in the enclosing scope, not one scoped to the loop.

### range

`range(stop)`, `range(start, stop)`, `range(start, stop, step)` produce integers, stopping before `stop`:

```pycon
>>> list(range(4))
[0, 1, 2, 3]
>>> list(range(2, 8, 2))
[2, 4, 6]
>>> list(range(5, 0, -1))
[5, 4, 3, 2, 1]
```

A `range` does not build the list; it computes numbers as needed, so `range(10**9)` costs no memory.

### Looping the Python way

A common beginner habit is looping over indexes:

```python
for i in range(len(books)):
    print(books[i])
```

Loop over the items:

```python
for book in books:
    print(book)
```

When you need the position too, use `enumerate`:

```pycon
>>> for i, title in enumerate(["Dune", "Emma", "Ulysses"], start=1):
...     print(i, title)
1 Dune
2 Emma
3 Ulysses
```

To walk two sequences in step, use `zip`:

```pycon
>>> titles = ["Dune", "Emma"]
>>> pages = [612, 474]
>>> for t, p in zip(titles, pages):
...     print(t, p)
Dune 612
Emma 474
>>> dict(zip(titles, pages))
{'Dune': 612, 'Emma': 474}
```

`zip` stops at the shortest input silently. Python 3.10 adds `zip(a, b, strict=True)`, which raises `ValueError` on different lengths and is worth using when a mismatch would mean a bug.

`reversed(seq)` iterates backwards without copying, `sorted(iterable)` iterates in sorted order:

```pycon
>>> list(reversed([1, 2, 3]))
[3, 2, 1]
>>> [n for n in sorted({3, 1, 2})]
[1, 2, 3]
```

### Looping over dictionaries

```pycon
>>> stock = {"Dune": 3, "Emma": 0}
>>> for title, qty in stock.items():
...     status = "in stock" if qty else "sold out"
...     print(f"{title}: {status}")
Dune: in stock
Emma: sold out
```

### break, continue, and the loop `else`

`break` leaves the loop. `continue` skips to the next item.

```pycon
>>> for n in range(10):
...     if n % 2 == 0:
...         continue
...     if n > 7:
...         break
...     print(n)
1
3
5
7
```

A `for` loop can have an `else` block that runs only if the loop finished without hitting `break`. It reads awkwardly, and is the cleanest way to express "search, and act if nothing was found":

```pycon
>>> def first_free(slots):
...     for slot in slots:
...         if slot is None:
...             result = "found"
...             break
...     else:
...         result = "all busy"
...     return result
...
>>> first_free([1, None, 3]), first_free([1, 2, 3])
('found', 'all busy')
```

### Odoo shape: `for record in self`

Odoo model methods receive `self`, which is a recordset, and the idiom is to loop over it:

```python
def action_close(self):
    for loan in self:
        if loan.state != "open":
            continue
        loan.state = "returned"
```

Everything in this chapter applies: `continue` as a guard, `if` conditions on fields, assignment in the body. Two habits that matter in Odoo (and that later chapters explain fully): the loop should not trigger a database query per iteration when one query could serve all records, and a method decorated for a single record must say so. For now, read `for loan in self:` as "for each record in this group".

### Modifying a collection while looping

Removing items from a list during iteration skips elements, because the list shrinks under the loop:

```pycon
>>> nums = [1, 2, 3, 4, 5, 6]
>>> for n in nums:
...     if n % 2 == 0:
...         nums.remove(n)
...
>>> nums
[1, 3, 5]
>>> nums = [1, 2, 2, 3, 4, 4]
>>> for n in nums:
...     if n % 2 == 0:
...         nums.remove(n)
...
>>> nums
[1, 2, 3, 4]
```

The first output looks right by luck. The second shows the skip: the second `2` and the second `4` were never examined. Build a new list instead:

```pycon
>>> nums = [1, 2, 2, 3, 4, 4]
>>> [n for n in nums if n % 2 != 0]
[1, 3]
```

## while loops

`while condition:` repeats while the condition is true. Use it when you do not know in advance how many iterations you need.

```pycon
>>> n = 27
>>> steps = 0
>>> while n != 1:
...     n = n // 2 if n % 2 == 0 else 3 * n + 1
...     steps += 1
...
>>> steps
111
```

The typical Odoo use is batching: process records in chunks until none are left.

```pycon
>>> pending = list(range(1, 8))
>>> batch_size = 3
>>> while pending:
...     batch, pending = pending[:batch_size], pending[batch_size:]
...     print(batch)
[1, 2, 3]
[4, 5, 6]
[7]
```

An infinite loop with an explicit exit is also a normal form:

```python
while True:
    chunk = read_next_chunk()
    if not chunk:
        break
    process(chunk)
```

{% hint style="warning" %}
A `while` whose condition never becomes false runs forever. In an Odoo worker, an endless loop pins a CPU until the worker is killed on its time limit. Every `while` needs a clear path to its exit, and long-running ones need a visible progress counter in the log.
{% endhint %}

## pass, and placeholders

`pass` does nothing and exists because a block cannot be empty:

```python
class LoanError(Exception):
    pass

def todo():
    pass
```

A docstring or `...` (Ellipsis) works as an empty body too.

## Replacing loops with built-ins

A loop that accumulates a single answer is often a built-in call.

### sum, min, max, len

```pycon
>>> prices = [12.5, 8.0, 20.0]
>>> sum(prices), min(prices), max(prices), len(prices)
(40.5, 8.0, 20.0, 3)
>>> sum(p for p in prices if p > 10)
32.5
>>> max(["pear", "fig", "apple"], key=len)
'apple'
>>> min([], default=None)
>>> max([3, 1], default=0)
3
```

`min([])` and `max([])` raise `ValueError` on empty input, so pass `default=` whenever the input might be empty.

### any and all

```pycon
>>> loans = [{"state": "open", "days": 5}, {"state": "returned", "days": 2}]
>>> any(l["state"] == "open" for l in loans)
True
>>> all(l["days"] > 3 for l in loans)
False
>>> any([]), all([])
(False, True)
```

`any` is true if at least one item is truthy; `all` is true if every item is truthy. On an empty input `all` is `True` ("no counter-example") and `any` is `False`. That empty-input rule is a source of subtle bugs: "all lines are delivered" is `True` for an order with no lines.

Both stop at the first deciding item. Pass a generator expression (see [Comprehensions and generators](comprehensions-and-generators.md)) so no intermediate list is built.

### next with a default: first match

```pycon
>>> next((l for l in loans if l["state"] == "returned"), None)
{'state': 'returned', 'days': 2}
>>> next((l for l in loans if l["state"] == "lost"), None) is None
True
```

`next(iterator, default)` returns the first item or the default. It is the idiomatic "find the first X". Without the default, an empty result raises `StopIteration`.

### Counting and summing booleans

```pycon
>>> sum(l["state"] == "open" for l in loans)
1
>>> sum(1 for l in loans if l["days"] > 3)
1
```

### Sorting and ranking instead of looping

```pycon
>>> sorted(loans, key=lambda l: l["days"], reverse=True)[0]["state"]
'open'
>>> max(loans, key=lambda l: l["days"])["state"]
'open'
```

### Odoo recordset equivalents

Odoo's recordsets carry methods that wrap these same loops. Their behaviour, expressed in plain Python over a list, is:

| Odoo style | Plain Python equivalent |
|---|---|
| `recs.filtered(lambda r: r.state == "open")` | `[r for r in recs if r.state == "open"]` |
| `recs.mapped("name")` | `[r.name for r in recs]` |
| `recs.sorted(key=lambda r: r.days)` | `sorted(recs, key=lambda r: r.days)` |
| `any(r.state == "open" for r in recs)` | same, built-in `any` |
| `sum(recs.mapped("amount"))` | `sum(r.amount for r in recs)` |

The Odoo methods return recordsets, not lists, so the result can be used for further ORM operations (`.write(...)`, `.unlink()`, more `filtered`). The plain-Python forms return lists. When you only need values, either works. When you need records back, use the Odoo method.

## The walrus operator

`:=` (Python 3.8+) assigns inside an expression. It saves repeating a computation in a condition:

```pycon
>>> import re
>>> line = "ref=LIB-0042"
>>> if m := re.search(r"LIB-(\d+)", line):
...     print(int(m.group(1)))
42
```

Use it sparingly, when it removes a duplicated call or an extra line. Do not use it to make one-liners cleverer.

## Putting it together

A function that decides what to do with loan records, using guard clauses, a loop, a dictionary for dispatch, and a counter for a summary:

```pycon
>>> from collections import Counter
>>> def process(loans, today):
...     summary = Counter()
...     for loan in loans:
...         if loan["state"] != "open":
...             summary["skipped"] += 1
...             continue
...         days_late = (today - loan["due"]).days
...         if days_late <= 0:
...             summary["on_time"] += 1
...         elif days_late <= 7:
...             summary["late"] += 1
...         else:
...             summary["overdue"] += 1
...     return dict(summary)
...
>>> from datetime import date
>>> data = [
...     {"state": "open", "due": date(2025, 3, 10)},
...     {"state": "open", "due": date(2025, 3, 1)},
...     {"state": "returned", "due": date(2025, 2, 1)},
...     {"state": "open", "due": date(2025, 3, 20)},
... ]
>>> process(data, date(2025, 3, 12))
{'late': 1, 'overdue': 1, 'skipped': 1, 'on_time': 1}
```

Subtracting two `date` objects gives a `timedelta`, whose `.days` is an integer. Dates are covered in depth in [Money, dates, and time zones](working-with-money-and-dates.md).

## Pitfalls

- **Indentation drift.** Moving a line one level changes meaning without an error. Review diffs with whitespace visible.
- **`=` versus `==`.** `if x = 3:` is a syntax error in Python, which is a mercy. But `x == 3` as a statement on its own does nothing; it computes and discards a boolean.
- **Modifying a list while iterating it.** Elements are skipped. Build a new list or iterate over a copy.
- **Forgetting that `range` stops before `stop`.** `range(1, 5)` is `1, 2, 3, 4`.
- **`while` without a guaranteed exit.** Add a counter, a timeout, or a `break` path, and log progress in long loops.
- **`for` variable leaking.** After `for x in items`, `x` still exists, and holds the last item, or raises `NameError` if the loop never ran.
- **`all([])` is `True`.** "All lines done" passes for an empty collection. Add an explicit emptiness check when that is not what you mean.
- **`min`/`max` on empty input.** Raise `ValueError` unless `default=` is passed.
- **`next()` on an empty iterator.** Raises `StopIteration` unless a default is passed.
- **Truthiness in conditions.** `if qty:` treats `0` as "no value". Use `is None` for the real missing case.
- **Per-iteration queries.** In Odoo, a loop that performs a database search or write inside each iteration can take minutes on large data. Build the data once outside the loop, then loop in memory.
- **`zip` truncation.** Mismatched lengths are dropped silently unless you pass `strict=True` (3.10+).
- **Deep nesting.** More than three levels of indentation is a signal to use guard clauses, a helper function, or a dictionary dispatch.

## Try it

1. Write `classify(n)` that returns `"fizz"` for multiples of 3, `"buzz"` for multiples of 5, `"fizzbuzz"` for both, and the number as a string otherwise. Print the results for 1 to 15.
2. Given `values = [4, 8, 15, 16, 23, 42]`, find the first value greater than 20 with `next`, the index of that value with `enumerate`, and whether all values are positive.
3. Write a `while` loop that splits a list of 10 ids into chunks of 4 and prints each chunk. Then rewrite it as a `for` loop over `range`.
4. The following code is meant to remove all `None` entries and fails to remove adjacent ones. Explain why, and fix it: `for x in items: if x is None: items.remove(x)` with `items = [1, None, None, 2]`.
5. Write a function `first_overdue(loans, today)` that returns the first loan whose due date is before `today`, or `None`, using `next`. Then write a version using a `for` loop with `else`.

<details>
<summary>Solution</summary>

1.

```pycon
>>> def classify(n):
...     if n % 15 == 0:
...         return "fizzbuzz"
...     if n % 3 == 0:
...         return "fizz"
...     if n % 5 == 0:
...         return "buzz"
...     return str(n)
...
>>> [classify(n) for n in range(1, 16)]
['1', '2', 'fizz', '4', 'buzz', 'fizz', '7', '8', 'fizz', 'buzz', '11', 'fizz', '13', '14', 'fizzbuzz']
```

2.

```pycon
>>> values = [4, 8, 15, 16, 23, 42]
>>> next((v for v in values if v > 20), None)
23
>>> next((i for i, v in enumerate(values) if v > 20), None)
4
>>> all(v > 0 for v in values)
True
```

3.

```pycon
>>> ids = list(range(1, 11))
>>> rest = ids
>>> while rest:
...     chunk, rest = rest[:4], rest[4:]
...     print(chunk)
[1, 2, 3, 4]
[5, 6, 7, 8]
[9, 10]
>>> for start in range(0, len(ids), 4):
...     print(ids[start:start + 4])
[1, 2, 3, 4]
[5, 6, 7, 8]
[9, 10]
```

4. After the first `None` is removed, the list shifts left and the loop's internal position moves past the second `None`. Result is `[1, None, 2]`. Fix: `items = [x for x in items if x is not None]`.

5.

```pycon
>>> from datetime import date
>>> def first_overdue(loans, today):
...     return next((l for l in loans if l["due"] < today), None)
...
>>> def first_overdue_loop(loans, today):
...     for loan in loans:
...         if loan["due"] < today:
...             result = loan
...             break
...     else:
...         result = None
...     return result
...
>>> data = [{"due": date(2025, 3, 20)}, {"due": date(2025, 3, 1)}]
>>> first_overdue(data, date(2025, 3, 12)) == first_overdue_loop(data, date(2025, 3, 12))
True
>>> first_overdue(data, date(2025, 3, 12))
{'due': datetime.date(2025, 3, 1)}
```

</details>
