---
description: "The four containers, when to use which, and how Odoo uses them."
---

# Lists, tuples, dicts, sets

A single value is rarely enough. A book has many loans, an order has many lines, a search returns many records. Python gives you four built-in containers for "many values": the **list** (ordered, changeable), the **tuple** (ordered, fixed), the **dict** (lookup by key), and the **set** (unique members). Odoo code uses all four constantly. Domains are lists of tuples, `vals` dictionaries feed `create()` and `write()`, `context` is a dict, and sets answer "which ids are in both groups". This chapter teaches each container, how to choose between them, and the grouping idioms that replace most manual bookkeeping.

## Lists

A list is an ordered, mutable sequence written with square brackets:

```pycon
>>> books = ["Dune", "Emma", "Ulysses"]
>>> books[0], books[-1]
('Dune', 'Ulysses')
>>> len(books)
3
>>> books[1:]
['Emma', 'Ulysses']
```

Indexing and slicing work exactly as on strings (see [Values and types](values-and-types.md)). Unlike strings, lists can be changed in place:

```pycon
>>> books[1] = "Persuasion"
>>> books.append("Hamlet")
>>> books.insert(0, "Beloved")
>>> books
['Beloved', 'Dune', 'Persuasion', 'Ulysses', 'Hamlet']
>>> books.remove("Dune")
>>> last = books.pop()
>>> last, books
('Hamlet', ['Beloved', 'Persuasion', 'Ulysses'])
>>> books.extend(["Emma", "Walden"])
>>> books
['Beloved', 'Persuasion', 'Ulysses', 'Emma', 'Walden']
```

| Operation | Effect | Cost |
|---|---|---|
| `lst.append(x)` | add at the end | fast |
| `lst.insert(i, x)` | add at position `i` | slow for large lists |
| `lst.extend(other)` | add all items of `other` | proportional to `other` |
| `lst.pop()` | remove and return the last item | fast |
| `lst.pop(i)` | remove and return item `i` | slow for large lists |
| `lst.remove(x)` | remove the first item equal to `x` | scans the list |
| `x in lst` | membership test | scans the list |
| `lst.index(x)` | position of first `x` | scans the list |
| `lst.count(x)` | number of occurrences | scans the list |

The "scans the list" cost is the reason a membership test inside a loop over a large list gets slow: 10,000 items checked against a 10,000-item list is 100 million comparisons. Sets (below) answer the same question almost instantly.

### Operators on lists

```pycon
>>> [1, 2] + [3]
[1, 2, 3]
>>> [0] * 4
[0, 0, 0, 0]
>>> 3 in [1, 2, 3]
True
>>> min([4, 1, 7]), max([4, 1, 7]), sum([4, 1, 7])
(1, 7, 12)
>>> list("abc")
['a', 'b', 'c']
>>> list(range(5))
[0, 1, 2, 3, 4]
```

`+` builds a new list. `lst += other` modifies `lst` in place, which behaves differently when other names refer to the same list (next section).

### Mutation and shared references

A name refers to an object; assignment does not copy. For a list, that means two names can change the same data:

```pycon
>>> a = [1, 2, 3]
>>> b = a
>>> b.append(4)
>>> a
[1, 2, 3, 4]
>>> c = a.copy()      # or a[:] or list(a)
>>> c.append(5)
>>> a, c
([1, 2, 3, 4], [1, 2, 3, 4, 5])
```

`copy()` makes a **shallow** copy: a new outer list that holds the same inner objects. If the items are themselves lists or dicts, the copies share them:

```pycon
>>> grid = [[0, 0], [0, 0]]
>>> shallow = grid.copy()
>>> shallow[0][0] = 9
>>> grid
[[9, 0], [0, 0]]
```

`copy.deepcopy(obj)` copies recursively when you need full independence.

The `*` operator has the same trap, because it repeats references:

```pycon
>>> rows = [[0] * 2] * 3
>>> rows[0][0] = 1
>>> rows
[[1, 0], [1, 0], [1, 0]]
>>> rows = [[0] * 2 for _ in range(3)]
>>> rows[0][0] = 1
>>> rows
[[1, 0], [0, 0], [0, 0]]
```

The second form builds three separate inner lists using a comprehension ([Comprehensions and generators](comprehensions-and-generators.md)).

### Sorting

`sorted(iterable)` returns a new sorted list. `lst.sort()` sorts in place and returns `None`.

```pycon
>>> nums = [3, 1, 2]
>>> sorted(nums)
[1, 2, 3]
>>> nums
[3, 1, 2]
>>> nums.sort(reverse=True)
>>> nums
[3, 2, 1]
>>> result = nums.sort()
>>> result is None
True
```

Sorting by something other than the item itself uses `key`, a function that maps each item to the value to compare:

```pycon
>>> words = ["pear", "Fig", "apple", "kiwi"]
>>> sorted(words)
['Fig', 'apple', 'kiwi', 'pear']
>>> sorted(words, key=str.lower)
['apple', 'Fig', 'kiwi', 'pear']
>>> sorted(words, key=len)
['Fig', 'pear', 'kiwi', 'apple']
>>> sorted(words, key=lambda w: (len(w), w))
['Fig', 'kiwi', 'pear', 'apple']
```

Python's sort is **stable**: items with equal keys keep their original order. That lets you sort in passes, least significant key first. A tuple key `(len(w), w)` compares the first element, then the second on ties. `lambda` is an anonymous one-expression function, introduced in [Functions](functions.md). Odoo's `recordset.sorted(key=...)` works on the same principle.

Mixing types in a sort fails:

```pycon
>>> sorted([3, "a", 1])
Traceback (most recent call last):
    ...
TypeError: '<' not supported between instances of 'str' and 'int'
```

Odoo specific variant: a field that is `False` when empty cannot be compared with a date. Sorting records by an optional date with `key=lambda r: r.date_due` raises `TypeError` as soon as one record has no date. The fix is a key that maps missing values to a comparable placeholder, for example `(r.date_due is False, r.date_due or date.min)`, which also decides whether empties come first or last.

### Unpacking

Assign several names at once:

```pycon
>>> first, second = [10, 20]
>>> first, second
(10, 20)
>>> head, *rest = [1, 2, 3, 4]
>>> head, rest
(1, [2, 3, 4])
>>> *init, tail = "abcd"
>>> init, tail
(['a', 'b', 'c'], 'd')
>>> x, y = 1, 2
>>> x, y = y, x        # swap without a temporary
>>> x, y
(2, 1)
```

The number of names must match unless one starred name absorbs the rest. A mismatch raises `ValueError: too many values to unpack (expected 2)`.

## Tuples

A tuple is an ordered, **immutable** sequence written with parentheses (the commas make the tuple; the parentheses are mostly for grouping):

```pycon
>>> point = (3, 4)
>>> point[0]
3
>>> point[0] = 9
Traceback (most recent call last):
    ...
TypeError: 'tuple' object does not support item assignment
>>> single = (5,)       # the trailing comma matters
>>> type(single), type((5))
(<class 'tuple'>, <class 'int'>)
>>> empty = ()
>>> a, b = point
```

Use a tuple when the number of items is fixed and the position carries meaning: `(latitude, longitude)`, `(field, operator, value)`. Use a list when the length varies and all items mean the same kind of thing. Tuples are **hashable** when their contents are, so they can be dictionary keys and set members, lists cannot.

Odoo's search domains are the standard example. A domain is a list of conditions, and each condition is a three-element tuple:

```python
domain = [
    ("state", "=", "open"),
    ("date_due", "<", "2025-01-01"),
    ("book_id.title", "ilike", "dune"),
]
```

The list is long-lived and may be extended, the tuples are tiny fixed records. Domain operators (`"&"`, `"|"`, `"!"`) are plain strings in the same list; domain syntax is covered in the ORM part. In Python terms you can build and filter such a list like any other.

### Named tuples

When positions carry meaning, names read better than indexes:

```pycon
>>> from collections import namedtuple
>>> Loan = namedtuple("Loan", ["book", "member", "days"])
>>> loan = Loan("Dune", "ada", 14)
>>> loan.book, loan[2]
('Dune', 14)
>>> loan._replace(days=21)
Loan(book='Dune', member='ada', days=21)
>>> loan._asdict()
{'book': 'Dune', 'member': 'ada', 'days': 14}
```

`typing.NamedTuple` and `dataclasses` do similar jobs with type hints; they are covered in [Classes and inheritance](classes-and-inheritance.md).

### One-item tuple trap

`(5)` is just `5` in parentheses. `(5,)` is a tuple. Forgetting the comma bites when a function expects a tuple, for example `IN` clauses in SQL: `cr.execute(..., (tuple(ids),))` needs the parameter list itself to be a tuple, and a single-parameter list is exactly the one-item case.

## Dictionaries

A dict maps keys to values. It is the workhorse container. Lookup by key is fast regardless of size.

```pycon
>>> book = {"title": "Dune", "pages": 612, "available": True}
>>> book["title"]
'Dune'
>>> book["pages"] += 1
>>> book["author"] = "F. Herbert"      # add a new key
>>> book
{'title': 'Dune', 'pages': 613, 'available': True, 'author': 'F. Herbert'}
>>> "title" in book, "isbn" in book
(True, False)
>>> len(book)
4
>>> del book["available"]
>>> book.pop("author")
'F. Herbert'
```

Since Python 3.7 a dict remembers insertion order, and you can rely on it. Keys must be hashable: strings, numbers, tuples of hashables, and `frozenset` are fine, lists and dicts are not.

```pycon
>>> hash([1, 2])
Traceback (most recent call last):
    ...
TypeError: unhashable type: 'list'
```

### Safe lookup

Indexing a missing key raises `KeyError`. `get` returns a default instead:

```pycon
>>> book = {"title": "Dune", "pages": 612}
>>> book["isbn"]
Traceback (most recent call last):
    ...
KeyError: 'isbn'
>>> book.get("isbn")                 # None if absent
>>> book.get("isbn", "unknown")
'unknown'
>>> book.setdefault("tags", []).append("scifi")
>>> book
{'title': 'Dune', 'pages': 612, 'tags': ['scifi']}
```

`setdefault(key, default)` returns the existing value or inserts and returns the default. The one-line form above is the manual version of grouping, and `defaultdict` below does it better.

Choose between `d[key]` and `d.get(key)` by whether absence is an error. If a key must be there, index it, and a missing key fails loudly at the right place. If absence is normal, use `get`. In Odoo, `vals.get("state")` is the standard idiom inside `create()` and `write()` overrides, because the caller passes only the fields it wants to set.

### Iterating

```pycon
>>> stock = {"Dune": 3, "Emma": 0, "Ulysses": 5}
>>> for title in stock:                       # keys
...     print(title)
Dune
Emma
Ulysses
>>> list(stock.keys()), list(stock.values())
(['Dune', 'Emma', 'Ulysses'], [3, 0, 5])
>>> for title, qty in stock.items():
...     print(f"{title}: {qty}")
Dune: 3
Emma: 0
Ulysses: 5
```

Do not add or remove keys while looping over the dict. Changing values of existing keys is fine, but changing the size raises `RuntimeError: dictionary changed size during iteration`. Loop over a copy (`list(d)`) if you need to delete.

### Building and merging

```pycon
>>> dict(a=1, b=2)
{'a': 1, 'b': 2}
>>> dict([("a", 1), ("b", 2)])
{'a': 1, 'b': 2}
>>> dict(zip(["a", "b"], [1, 2]))
{'a': 1, 'b': 2}
>>> defaults = {"state": "draft", "qty": 1}
>>> overrides = {"qty": 5}
>>> {**defaults, **overrides}
{'state': 'draft', 'qty': 5}
>>> defaults | overrides            # Python 3.9+
{'state': 'draft', 'qty': 5}
>>> merged = dict(defaults)
>>> merged.update(overrides)
>>> merged
{'state': 'draft', 'qty': 5}
```

`{**a, **b}` and `a | b` build a new dict in which the right side wins on conflicts. `update` changes in place. `a | b` needs Python 3.9. Dict comprehensions build dicts from an iterable:

```pycon
>>> {title: len(title) for title in ["Dune", "Emma"]}
{'Dune': 4, 'Emma': 4}
>>> {k: v for k, v in stock.items() if v > 0}
{'Dune': 3, 'Ulysses': 5}
```

### Nested data and the JSON shape

Real data nests. JSON, the format used by APIs and Odoo's controllers, is made of dicts, lists, strings, numbers, booleans, and `null` (`None`), and maps one-to-one onto Python containers:

```pycon
>>> order = {
...     "ref": "SO001",
...     "customer": {"name": "Ada", "country": "UK"},
...     "lines": [
...         {"sku": "A", "qty": 2, "price": 10.0},
...         {"sku": "B", "qty": 1, "price": 5.5},
...     ],
... }
>>> order["customer"]["name"]
'Ada'
>>> order["lines"][1]["sku"]
'B'
>>> sum(line["qty"] * line["price"] for line in order["lines"])
25.5
```

Chained indexing fails loudly when a level is missing. When parts of the structure are optional, chain `get` with an empty-dict default: `order.get("customer", {}).get("name")`.

### `vals` dictionaries in Odoo

Odoo's `create` and `write` take a dict of field names to values. Writing one in plain Python looks like this:

```python
vals = {
    "title": "Dune",
    "pages": 612,
    "author_ids": [(0, 0, {"name": "F. Herbert"})],
}
```

The tuples inside `author_ids` are x2many commands, a three-element tuple whose first element selects the operation (here `0` means "create a new record"). The command tuples are a convention of the ORM, not of Python, and later chapters spell out each one. What matters now is that `vals` is an ordinary dict, so everything above applies: you can merge defaults, copy it before changing it, and read optional keys with `get`.

Copying matters. If a method receives `vals` and modifies it, the caller's dictionary changes too, because only the reference was passed. When you override `create` and want to adjust values without surprising the caller, work on `dict(vals)`.

```pycon
>>> def normalise(vals):
...     vals = dict(vals)               # do not mutate the caller's dict
...     if "title" in vals:
...         vals["title"] = vals["title"].strip().title()
...     return vals
...
>>> original = {"title": "  the hobbit "}
>>> normalise(original), original
({'title': 'The Hobbit'}, {'title': '  the hobbit '})
```

## Sets

A set holds unique, hashable items with no order:

```pycon
>>> s = {3, 1, 2, 3, 1}
>>> s == {1, 2, 3}
True
>>> len(s)
3
>>> 2 in s
True
>>> set([1, 1, 2]), set("hello") == {"h", "e", "l", "o"}
({1, 2}, True)
>>> empty = set()     # {} is an empty dict, not an empty set
>>> type({}), type(set())
(<class 'dict'>, <class 'set'>)
```

Membership tests on a set take roughly constant time. Converting a list of ids to a set before a loop turns a quadratic scan into a linear one.

```pycon
>>> a = {1, 2, 3, 4}
>>> b = {3, 4, 5}
>>> a | b, a & b, a - b, a ^ b
({1, 2, 3, 4, 5}, {3, 4}, {1, 2}, {1, 2, 5})
>>> {1, 2} <= a, a.isdisjoint({9})
(True, True)
>>> a.add(10); a.discard(10); a.discard(99)     # discard never raises
>>> sorted(a)
[1, 2, 3, 4]
```

`|` is union, `&` intersection, `-` difference, `^` symmetric difference (in exactly one). Typical Odoo-flavoured uses: "which book ids were on the old list but not the new one", "do these two sets of group ids overlap", "deduplicate while I build a list of partner ids".

```pycon
>>> old_ids = [1, 2, 3, 4]
>>> new_ids = [2, 3, 5]
>>> sorted(set(old_ids) - set(new_ids)), sorted(set(new_ids) - set(old_ids))
([1, 4], [5])
```

Sets are unordered, so printing a set of strings can give a different order on different runs (string hashing is randomised per process). If you need deterministic output, `sorted()` it. To deduplicate while keeping order, use a dict:

```pycon
>>> list(dict.fromkeys(["b", "a", "b", "c", "a"]))
['b', 'a', 'c']
```

`frozenset` is the immutable set, usable as a dict key.

## Choosing the container

| You need | Use |
|---|---|
| Ordered items that grow or change | list |
| A fixed-size record, or a dict key made of several parts | tuple |
| Lookup by a key | dict |
| Uniqueness or fast membership; set arithmetic | set |
| A counter per key | `collections.Counter` |
| Group items by a key | `collections.defaultdict(list)` |
| A queue with fast removal at the front | `collections.deque` |

## `collections` helpers

### Counter

```pycon
>>> from collections import Counter
>>> c = Counter(["open", "open", "returned", "open", "lost"])
>>> c
Counter({'open': 3, 'returned': 1, 'lost': 1})
>>> c["open"], c["never"]
(3, 0)
>>> c.most_common(2)
[('open', 3), ('returned', 1)]
>>> c.update(["lost", "lost"])
>>> c["lost"]
3
```

A missing key counts as zero and is not inserted when read. `Counter` is the right tool for "how many of each state".

### defaultdict

A `defaultdict` creates a missing value with a factory the first time you ask for the key:

```pycon
>>> from collections import defaultdict
>>> loans = [("ada", "Dune"), ("bob", "Emma"), ("ada", "Ulysses")]
>>> by_member = defaultdict(list)
>>> for member, title in loans:
...     by_member[member].append(title)
...
>>> dict(by_member)
{'ada': ['Dune', 'Ulysses'], 'bob': ['Emma']}
>>> totals = defaultdict(float)
>>> for sku, amount in [("A", 2.5), ("B", 1.0), ("A", 4.0)]:
...     totals[sku] += amount
...
>>> dict(totals)
{'A': 6.5, 'B': 1.0}
```

This is the standard grouping idiom, and it appears everywhere in Odoo code that processes records in Python: iterate once, append to `groups[key]`, then handle each group. It replaces `if key not in d: d[key] = []` boilerplate.

{% hint style="warning" %}
Reading `d[key]` on a `defaultdict` inserts the key. Calling `d["x"]` to "check" whether something exists silently creates an entry. Use `"x" in d` or `d.get("x")` for checks. When you finish grouping, convert with `dict(...)` before returning it to code that may probe it.
{% endhint %}

### deque

```pycon
>>> from collections import deque
>>> queue = deque([1, 2, 3])
>>> queue.append(4)
>>> queue.popleft()
1
>>> queue
deque([2, 3, 4])
```

Popping from the front of a list is slow (`pop(0)` shifts everything). `deque` does it fast, and is the right structure for a work queue.

## Odoo-flavoured: grouping, indexing, set arithmetic

A recordset is not a list, but it iterates like one, and everything here applies to records as well as plain data. The examples below use plain dictionaries standing in for records so that they run anywhere. Later chapters show the same logic over real recordsets.

```pycon
>>> loans = [
...     {"id": 1, "member": "ada", "book": "Dune", "state": "open", "days": 14},
...     {"id": 2, "member": "bob", "book": "Emma", "state": "returned", "days": 7},
...     {"id": 3, "member": "ada", "book": "Ulysses", "state": "open", "days": 21},
...     {"id": 4, "member": "cy", "book": "Dune", "state": "lost", "days": 30},
... ]
```

**Filter** is a loop with a condition. Odoo's `recordset.filtered(lambda l: l.state == "open")` is this:

```pycon
>>> open_loans = [l for l in loans if l["state"] == "open"]
>>> [l["id"] for l in open_loans]
[1, 3]
```

**Map** extracts one field from each item, which Odoo's `recordset.mapped("field")` does:

```pycon
>>> [l["book"] for l in loans]
['Dune', 'Emma', 'Ulysses', 'Dune']
>>> sorted({l["book"] for l in loans})            # unique, sorted
['Dune', 'Emma', 'Ulysses']
```

**Group by** a key with `defaultdict`:

```pycon
>>> by_member = defaultdict(list)
>>> for loan in loans:
...     by_member[loan["member"]].append(loan)
...
>>> {m: [l["id"] for l in group] for m, group in by_member.items()}
{'ada': [1, 3], 'bob': [2], 'cy': [4]}
```

**Aggregate** per group:

```pycon
>>> days_per_member = defaultdict(int)
>>> for loan in loans:
...     days_per_member[loan["member"]] += loan["days"]
...
>>> dict(days_per_member)
{'ada': 35, 'bob': 7, 'cy': 30}
>>> max(days_per_member, key=days_per_member.get)
'ada'
```

**Index by id** so that you can look records up without scanning:

```pycon
>>> by_id = {l["id"]: l for l in loans}
>>> by_id[3]["book"]
'Ulysses'
```

**Set arithmetic** between two views of the data:

```pycon
>>> borrowed = {l["book"] for l in loans if l["state"] == "open"}
>>> lost = {l["book"] for l in loans if l["state"] == "lost"}
>>> borrowed & lost
{'Dune'}
```

**Many-to-many consistency** is a set difference. Given a desired list of tag ids and the current ones, work out what to add and remove:

```pycon
>>> current, wanted = {1, 2, 3}, {2, 3, 4}
>>> to_add, to_remove = wanted - current, current - wanted
>>> to_add, to_remove
({4}, {1})
```

### Identity of keys in a mapping

Using a recordset or record as a dict key works because Odoo makes records hashable (they hash by model and id). For plain Python it means you can write `groups[loan.member_id]` and get one bucket per member, without first extracting ids. If you are not sure that an object is hashable, you can test it in the REPL with `hash(obj)`; an unhashable object raises `TypeError`.

## Copying, and what "equal" means for containers

Lists, dicts, and sets compare by content:

```pycon
>>> [1, 2] == [1, 2], {"a": 1} == {"a": 1}, {1, 2} == {2, 1}
(True, True, True)
>>> (1, 2) == [1, 2]
False
```

A tuple is never equal to a list holding the same items. This matters when a value round-trips through JSON: tuples become lists. A domain `[("state", "=", "open")]` sent over JSON-RPC arrives on the other side as `[["state", "=", "open"]]`, and code comparing it with tuples will not match.

```pycon
>>> import json
>>> json.loads(json.dumps(("a", 1)))
['a', 1]
```

## Pitfalls

- **Mutable default aliasing.** `b = a` does not copy. Use `a.copy()`, `list(a)`, `dict(a)`, or `copy.deepcopy` as needed.
- **Shallow copy of nested data.** `copy()` shares inner lists and dicts. Use `deepcopy` for independence.
- **`[[0] * n] * m`.** Builds `m` references to one inner list. Use a comprehension.
- **`sort()` returns `None`.** `items = items.sort()` destroys the list reference. Use `sorted()` or call `sort()` on its own line.
- **Sorting mixed types.** `None`, `False`, and dates or strings in one key raise `TypeError`. Normalise the key. This is common with Odoo optional fields.
- **Modifying a list while iterating.** Removing items inside `for x in lst:` skips elements. Iterate over a copy or build a new list.
- **Modifying a dict while iterating.** Changing its size raises `RuntimeError`.
- **`d[key]` on missing keys.** Use `get` when absence is normal.
- **`defaultdict` reads insert keys.** A "check" like `if groups["x"]:` creates the entry.
- **`{}` is a dict.** An empty set is `set()`.
- **Sets are unordered.** Never rely on iteration order of a set. Sort before printing or comparing text output.
- **Unhashable keys.** Lists and dicts cannot be keys or set members. Use tuples or `frozenset`.
- **One-item tuples.** `(x)` is not a tuple. Write `(x,)`.
- **Tuples become lists in JSON.** Compare after normalising, or convert back explicitly.
- **Quadratic membership tests.** `if x in big_list` inside a loop. Build a set once outside the loop.
- **Shared `vals`.** Mutating a dict argument changes the caller's data. Copy first.

## Try it

1. Given `words = ["pear", "fig", "apple", "kiwi", "fig"]`, produce: the unique words sorted by length then alphabetically, and a dict from word to count.
2. Given the `loans` list from this chapter, build a dict from `member` to the list of distinct book titles they borrowed, sorted alphabetically. Use `defaultdict(set)`.
3. Write `diff_ids(old, new)` that returns `(added, removed, kept)` as sorted lists, for two lists of ids that may contain duplicates.
4. Sort the list `[("ada", None), ("bob", 5), ("cy", 2)]` by the second element with `None` last, ascending otherwise.
5. Explain why `rows = [[0] * 3] * 2; rows[0][0] = 7` changes both rows, and show two correct ways to build the grid.

<details>
<summary>Solution</summary>

1.

```pycon
>>> words = ["pear", "fig", "apple", "kiwi", "fig"]
>>> sorted(set(words), key=lambda w: (len(w), w))
['fig', 'kiwi', 'pear', 'apple']
>>> from collections import Counter
>>> dict(Counter(words))
{'pear': 1, 'fig': 2, 'apple': 1, 'kiwi': 1}
```

2.

```pycon
>>> from collections import defaultdict
>>> loans = [("ada", "Dune"), ("bob", "Emma"), ("ada", "Ulysses"), ("ada", "Dune")]
>>> books = defaultdict(set)
>>> for member, title in loans:
...     books[member].add(title)
...
>>> {m: sorted(t) for m, t in books.items()}
{'ada': ['Dune', 'Ulysses'], 'bob': ['Emma']}
```

3.

```pycon
>>> def diff_ids(old, new):
...     old, new = set(old), set(new)
...     return sorted(new - old), sorted(old - new), sorted(old & new)
...
>>> diff_ids([1, 2, 2, 3], [2, 3, 3, 4])
([4], [1], [2, 3])
```

4. The key puts `None` into a second tier: `False` sorts before `True`, so rows with a value come first.

```pycon
>>> data = [("ada", None), ("bob", 5), ("cy", 2)]
>>> sorted(data, key=lambda row: (row[1] is None, row[1] or 0))
[('cy', 2), ('bob', 5), ('ada', None)]
```

5. `[[0] * 3] * 2` creates one inner list and repeats the reference to it twice, so both rows are the same object. Correct versions:

```pycon
>>> rows = [[0] * 3 for _ in range(2)]
>>> rows[0][0] = 7
>>> rows
[[7, 0, 0], [0, 0, 0]]
>>> import copy
>>> template = [0, 0, 0]
>>> rows = [copy.copy(template) for _ in range(2)]
>>> rows[0][0] = 7
>>> rows
[[7, 0, 0], [0, 0, 0]]
```

</details>
