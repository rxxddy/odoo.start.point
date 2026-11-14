---
description: "Arguments, defaults, *args, **kwargs, return values, scope."
---

# Functions

A function is a named, reusable block of code that takes inputs and gives back a result. Everything you write for Odoo is a function in one form or another: a compute method, a button action, an `onchange` handler, a cron entry point, a `lambda` that provides a field default. The details of how Python passes arguments are what make Odoo overrides work, because an override must accept whatever its parent accepts and hand it on unchanged. This chapter covers definition, argument passing, `*args` and `**kwargs`, scope, closures, and lambdas.

## Defining and calling

```pycon
>>> def add(a, b):
...     return a + b
...
>>> add(2, 3)
5
>>> total = add(10, 5)
>>> total
15
```

`def` introduces the function name, its **parameters** in parentheses, and a colon, followed by an indented body. When you call it, the values you pass are **arguments**. `return` ends the function and hands a value back to the caller.

A function without a `return`, or with a bare `return`, gives back `None`:

```pycon
>>> def greet(name):
...     print(f"Hello, {name}")
...
>>> result = greet("Ada")
Hello, Ada
>>> result is None
True
```

The distinction between **printing** and **returning** trips up beginners. `print` shows text to a human and the value is lost. `return` gives the value to the calling code, which can store it, test it, or pass it on. Code that is meant to be reused returns values; printing belongs at the outermost layer. In Odoo there is no terminal for a method to print to, and a method that "prints" its result writes into the server log at best. Return the value.

### Return multiple values

A function returns one object. To return several, return a tuple, and unpack at the call site:

```pycon
>>> def min_max(values):
...     return min(values), max(values)
...
>>> low, high = min_max([4, 9, 2])
>>> low, high
(2, 9)
>>> min_max([4, 9, 2])
(2, 9)
```

### Early return

A `return` can sit anywhere, and the rest of the body is skipped. Use it for guard clauses (see [Control flow](control-flow.md)).

```pycon
>>> def safe_ratio(a, b):
...     if b == 0:
...         return None
...     return a / b
...
>>> safe_ratio(1, 4), safe_ratio(1, 0)
(0.25, None)
```

Be consistent. A function that sometimes returns a value and sometimes falls off the end returns `None` in the second case, which the caller will then fail on far from the cause. If some paths return a value, make every path say what it returns, even if that is an explicit `return None`.

### Docstrings

A string as the first statement of a function is its **docstring**. `help()` and editors display it.

```pycon
>>> def late_fee(days_late, rate=0.5):
...     """Return the fee for a loan returned `days_late` days after the due date.
...
...     A loan returned on time (days_late <= 0) costs nothing.
...     """
...     return max(days_late, 0) * rate
...
>>> late_fee(4), late_fee(-3), late_fee(4, rate=1)
(2.0, 0.0, 4)
>>> late_fee.__doc__.splitlines()[0]
'Return the fee for a loan returned `days_late` days after the due date.'
```

Write the first line as a complete summary of what the function does. In Odoo, docstrings on model methods that are exposed to the client are shown in some tooling, and on public methods they are the only documentation your colleagues will find.

## Parameters in detail

### Positional and keyword arguments

You can pass arguments by position or by name:

```pycon
>>> def make_ref(prefix, year, number):
...     return f"{prefix}-{year}-{number:04d}"
...
>>> make_ref("LIB", 2025, 42)
'LIB-2025-0042'
>>> make_ref(prefix="LIB", number=42, year=2025)
'LIB-2025-0042'
>>> make_ref("LIB", number=42, year=2025)
'LIB-2025-0042'
```

Positional arguments come first, then keyword ones. Passing the same parameter twice, or too few or too many, is a `TypeError`:

```pycon
>>> make_ref("LIB", 2025)
Traceback (most recent call last):
    ...
TypeError: make_ref() missing 1 required positional argument: 'number'
>>> make_ref("LIB", 2025, 42, year=2026)
Traceback (most recent call last):
    ...
TypeError: make_ref() got multiple values for argument 'year'
```

Keyword arguments make call sites self-documenting. `create_loan(book, member, True)` says nothing about the `True`; `create_loan(book, member, renewable=True)` does.

### Default values

A parameter with a default is optional:

```pycon
>>> def make_ref(prefix, year, number=1, width=4):
...     return f"{prefix}-{year}-{number:0{width}d}"
...
>>> make_ref("LIB", 2025)
'LIB-2025-0001'
>>> make_ref("LIB", 2025, width=6)
'LIB-2025-000001'
```

Parameters with defaults must come after those without.

### The mutable default trap

Default values are evaluated **once**, when `def` runs, not at each call. For immutable defaults (numbers, strings, `None`) this is invisible. For a list or dict, every call that omits the argument shares the same object:

```pycon
>>> def add_tag(tag, tags=[]):
...     tags.append(tag)
...     return tags
...
>>> add_tag("a")
['a']
>>> add_tag("b")
['a', 'b']
```

The second call returns `['a', 'b']`, because the same list was reused. The standard fix is a `None` sentinel:

```pycon
>>> def add_tag(tag, tags=None):
...     if tags is None:
...         tags = []
...     tags.append(tag)
...     return tags
...
>>> add_tag("a"), add_tag("b")
(['a'], ['b'])
```

This bug is nasty because the first call works. In Odoo it shows up when a default dict (for example, a context template) is declared in a signature and then modified by every caller.

### Keyword-only and positional-only parameters

A bare `*` in the parameter list means everything after it must be passed by keyword:

```pycon
>>> def make_loan(book, member, *, days=14, renewable=True):
...     return (book, member, days, renewable)
...
>>> make_loan("Dune", "ada", days=7)
('Dune', 'ada', 7, True)
>>> make_loan("Dune", "ada", 7)
Traceback (most recent call last):
    ...
TypeError: make_loan() takes 2 positional arguments but 3 were given
```

This prevents mistakes with long parameter lists. A `/` marks the preceding parameters as positional-only (Python 3.8+):

```pycon
>>> def clamp(value, low, high, /):
...     return max(low, min(value, high))
...
>>> clamp(15, 0, 10)
10
```

You will rarely write `/`, and you will see it in signatures printed by `help()`.

### `*args` and `**kwargs`

A parameter prefixed with `*` collects extra positional arguments into a tuple. A parameter prefixed with `**` collects extra keyword arguments into a dict:

```pycon
>>> def show(*args, **kwargs):
...     print("args:", args)
...     print("kwargs:", kwargs)
...
>>> show(1, 2, x=3)
args: (1, 2)
kwargs: {'x': 3}
>>> show()
args: ()
kwargs: {}
```

The names `args` and `kwargs` are conventions, and the stars do the work. The same stars at the call site **unpack** a sequence or a dict into arguments:

```pycon
>>> point = (3, 4)
>>> opts = {"width": 6}
>>> def fmt(x, y, width=2):
...     return f"{x:>{width}},{y:>{width}}"
...
>>> fmt(*point, **opts)
'     3,     4'
>>> fmt(*point)
' 3, 4'
```

The unpacking forms combine: `f(*a, *b, **c, **d)` is legal.

#### Why Odoo cares

An override of a model method must pass through whatever arguments it does not understand. The usual form is:

```python
def write(self, vals):
    # ... adjust vals or do something before
    result = super().write(vals)
    # ... do something after
    return result
```

This works because `write` takes exactly `vals`. For methods whose signature differs between Odoo versions or is extended by other modules (for example, `create` receives a list of dicts in recent versions and a single dict in older ones), overrides often accept `*args, **kwargs` and forward them untouched:

```python
def action_confirm(self, *args, **kwargs):
    # pre-check
    return super().action_confirm(*args, **kwargs)
```

A wrapper written like this keeps working when another module adds a keyword argument to the method in the chain. A wrapper with a fixed narrow signature breaks the moment a caller passes something it did not anticipate. [super() explained](super-explained.md) shows why the chain makes this necessary.

The pass-through pattern in plain Python:

```pycon
>>> def base(a, b=0, *, scale=1):
...     return (a + b) * scale
...
>>> def wrapper(*args, **kwargs):
...     print("calling base with", args, kwargs)
...     return base(*args, **kwargs)
...
>>> wrapper(1, 2, scale=10)
calling base with (1, 2) {'scale': 10}
30
```

### Argument passing: references, not copies

Python passes a reference to the object. If the object is mutable and the function changes it, the caller sees the change:

```pycon
>>> def add_default(order):
...     order["state"] = "draft"
...
>>> o = {"ref": "SO1"}
>>> add_default(o)
>>> o
{'ref': 'SO1', 'state': 'draft'}
```

Reassigning the parameter name inside the function does not affect the caller, because it only rebinds the local name:

```pycon
>>> def reset(items):
...     items = []
...
>>> data = [1, 2]
>>> reset(data)
>>> data
[1, 2]
```

Rule: a function should either return a new value or modify its argument in place, and the name and docstring should say which. Mixing both is how bugs hide. Python's own convention illustrates it: `sorted(x)` returns a new list, `x.sort()` mutates and returns `None`.

## Scope

A **scope** is where a name is visible. Python looks a name up in this order, nicknamed LEGB:

1. **L**ocal: names assigned inside the current function.
2. **E**nclosing: names in outer functions (for nested functions).
3. **G**lobal: names at module level.
4. **B**uilt-in: names such as `len`, `print`, `sum`.

```pycon
>>> rate = 0.5            # global
>>> def fee(days):
...     cap = 10          # local
...     return min(days * rate, cap)
...
>>> fee(30)
10
>>> cap
Traceback (most recent call last):
    ...
NameError: name 'cap' is not defined
```

Reading a global from a function works. **Assigning** to a name inside a function creates a local, even if a global of the same name exists:

```pycon
>>> counter = 0
>>> def bump():
...     counter = counter + 1
...
>>> bump()
Traceback (most recent call last):
    ...
UnboundLocalError: cannot access local variable 'counter' where it is not associated with a value
```

Because `counter` is assigned in the function, Python treats it as local for the whole function and complains when you read it before it is set. To rebind a module-level name, declare it `global`:

```pycon
>>> def bump():
...     global counter
...     counter += 1
...
>>> bump(); bump()
>>> counter
2
```

Avoid `global`. State that changes at module level is shared by every request in the process, and Odoo servers run many requests in the same interpreter, sometimes in several threads. A module-level cache that two requests modify at once is a bug that appears only under load, and in Odoo it can also leak data between databases. If you need shared state, keep it on the registry or the environment as the framework provides, or in a database table.

Mutating a global list or dict does not need `global`, because that does not rebind the name. It is exactly as hazardous.

### Closures and `nonlocal`

A function defined inside another function can read the outer function's names, and keeps them alive after the outer function returns. That is a **closure**:

```pycon
>>> def make_fee(rate):
...     def fee(days):
...         return days * rate
...     return fee
...
>>> daily = make_fee(0.5)
>>> daily(4)
2.0
>>> make_fee(2)(4)
8
```

`fee` remembers `rate`. To assign to an enclosing variable use `nonlocal`:

```pycon
>>> def make_counter():
...     n = 0
...     def tick():
...         nonlocal n
...         n += 1
...         return n
...     return tick
...
>>> t = make_counter()
>>> t(), t(), t()
(1, 2, 3)
```

Closures are what [decorators](decorators.md) are built from.

#### The late-binding trap

A closure looks up the variable when it is **called**, not when it is defined:

```pycon
>>> funcs = [lambda: i for i in range(3)]
>>> [f() for f in funcs]
[2, 2, 2]
>>> funcs = [lambda i=i: i for i in range(3)]
>>> [f() for f in funcs]
[0, 1, 2]
```

All three lambdas share the one `i`, which ends at 2. Binding it as a default argument (`i=i`) captures the current value. The same thing happens when you create callbacks in a loop in Odoo code.

## Functions are objects

A function is a value like any other. You can store it, pass it to other functions, and return it:

```pycon
>>> def shout(s):
...     return s.upper() + "!"
...
>>> f = shout
>>> f("hi")
'HI!'
>>> [shout(w) for w in ["a", "b"]]
['A!', 'B!']
>>> list(map(shout, ["a", "b"]))
['A!', 'B!']
>>> handlers = {"loud": shout, "quiet": str.lower}
>>> handlers["loud"]("x"), handlers["quiet"]("X")
('X!', 'x')
```

A dict of functions is a clean replacement for a long `if/elif` chain. Passing a function to another function is how `sorted(key=...)`, `filter`, and Odoo's `filtered(...)` work.

### lambda

`lambda args: expression` is a nameless function with a single expression as its body:

```pycon
>>> square = lambda x: x * x
>>> square(5)
25
>>> sorted(["bb", "a", "ccc"], key=lambda s: -len(s))
['ccc', 'bb', 'a']
>>> list(filter(lambda n: n % 2, range(6)))
[1, 3, 5]
```

Use `lambda` for short throwaway functions passed as arguments. Do not assign a lambda to a name; use `def`, which gives the function a name that appears in tracebacks. A lambda cannot contain statements.

In Odoo you will write lambdas constantly:

```python
recs.filtered(lambda r: r.state == "open")
recs.sorted(key=lambda r: r.date_due)
active = fields.Boolean(default=lambda self: True)
```

The third line shows a field default given as a function, so that the value is computed when each record is created and not once when the class is loaded. For a constant, `default=True` is fine. For a date or a value that depends on the current user, it must be a callable. A date default written as `default=date.today()` is evaluated once at server start and is stale from the next day on.

You can see the problem in plain Python:

```pycon
>>> from datetime import datetime
>>> import time
>>> def stamp(at=datetime.now()):      # evaluated once, at definition
...     return at
...
>>> first = stamp()
>>> time.sleep(0.01)
>>> stamp() == first
True
```

### functools.partial

`partial` fixes some arguments of an existing function and gives you a new function:

```pycon
>>> from functools import partial
>>> def fee(days, rate):
...     return days * rate
...
>>> weekly = partial(fee, rate=3.5)
>>> weekly(2)
7.0
```

It is cleaner than a lambda when you only want to pre-fill arguments.

## Type hints

Python lets you annotate parameters and return values. The interpreter does not enforce them, but editors and checkers use them, and they document intent:

```pycon
>>> def late_fee(days_late: int, rate: float = 0.5) -> float:
...     return max(days_late, 0) * rate
...
>>> late_fee(3)
1.5
>>> late_fee.__annotations__
{'days_late': <class 'int'>, 'rate': <class 'float'>, 'return': <class 'float'>}
```

Common forms: `list[str]`, `dict[str, int]`, `tuple[int, int]` (Python 3.9+), `str | None` (3.10+; on older versions `Optional[str]` from `typing`). Odoo core code mostly omits annotations in model methods; some recent modules add them. Follow the style of the code base you work in. Wrong hints never raise errors at runtime, so a hint that lies is worse than none.

## Recursion

A function can call itself. It needs a base case that stops the recursion:

```pycon
>>> def depth(node):
...     children = node.get("children", [])
...     return 1 + max((depth(c) for c in children), default=0)
...
>>> tree = {"name": "root", "children": [{"name": "a", "children": [{"name": "b"}]}, {"name": "c"}]}
>>> depth(tree)
3
```

This suits tree structures such as product categories or parent-child account hierarchies. Python limits recursion depth (about 1000 frames by default) and raises `RecursionError` beyond it. Hierarchies in Odoo data can contain a cycle by mistake (a category that is its own ancestor), which turns a recursive function into an infinite one; the ORM has a recursion check for `parent_id` fields, and your own traversal should track visited ids.

## Designing functions

- **One job.** A function that "validates and saves and sends email" is three functions. Test and reuse suffer otherwise.
- **Names are verbs for actions, nouns for values.** `compute_total`, `late_fee`, `is_overdue`.
- **Return rather than print, and return rather than mutate** unless the function's purpose is the mutation.
- **Few parameters.** More than four or five suggests a group of values that should travel together, such as a dict or a small class (see [Classes and inheritance](classes-and-inheritance.md)).
- **Keyword-only for flags.** Booleans passed positionally are unreadable.
- **No hidden globals.** If the result depends on something other than the arguments, say so in the docstring.

A small worked example in the shape of Odoo business logic, without any Odoo dependency:

```pycon
>>> from datetime import date, timedelta
>>> def due_date(start, days=14, *, skip_weekends=True):
...     """Return the due date for a loan that starts on `start`."""
...     due = start + timedelta(days=days)
...     if skip_weekends:
...         while due.weekday() >= 5:      # 5 = Saturday, 6 = Sunday
...             due += timedelta(days=1)
...     return due
...
>>> due_date(date(2025, 3, 3))          # Monday + 14 -> Monday
datetime.date(2025, 3, 17)
>>> due_date(date(2025, 3, 5))          # Wednesday + 14 -> Wednesday
datetime.date(2025, 3, 19)
>>> due_date(date(2025, 3, 8), days=7)  # Saturday + 7 -> Saturday -> Monday
datetime.date(2025, 3, 17)
>>> due_date(date(2025, 3, 8), days=7, skip_weekends=False)
datetime.date(2025, 3, 15)
```

## Pitfalls

- **Mutable defaults.** `def f(x, items=[])` shares one list across calls. Use `None` and create inside.
- **Evaluated-once defaults.** `def f(at=datetime.now())` is frozen at import. In Odoo `default=fields.Date.today()` is the same mistake; pass the callable instead.
- **Printing instead of returning.** The caller gets `None`.
- **Mutating arguments by accident.** A function that changes the caller's dict or list surprises everyone. Copy first (`dict(vals)`), or document the mutation.
- **`UnboundLocalError`.** Assigning to a name anywhere in a function makes it local everywhere in that function.
- **Late binding in closures and lambdas.** Create callbacks in a loop with `lambda i=i: ...` or `partial`.
- **Narrow override signatures.** An override of `def method(self, a)` breaks when another module in the chain passes an extra argument. Forward `*args, **kwargs` unless you are certain of the signature.
- **Forgetting to return the `super()` result.** An override that calls the parent and does not return its value silently returns `None` to every caller. See [super() explained](super-explained.md).
- **Inconsistent returns.** Some paths return a value, others fall off the end. The caller crashes with `'NoneType' object has no attribute ...` far away.
- **Shadowing built-ins.** A parameter named `id`, `type`, `filter`, or `sum` hides the built-in inside the function. Fine for `id` in most code, but a problem if you need the built-in on the next line.
- **Deep recursion.** `RecursionError` on large hierarchies or cyclic data. Prefer a loop with an explicit stack and a visited set.
- **Overusing `global`.** Module-level state is shared by all requests and threads.
- **Positional booleans.** `export(rows, True, False)` cannot be reviewed. Use keyword-only flags.

## Try it

1. Write `fee(days_late, rate=0.5, *, cap=None)` that returns `days_late * rate`, never negative, and no more than `cap` when `cap` is not `None`. Call it positionally and with keywords, and show that `fee(3, 0.5, 2)` fails.
2. Write `wrap(func)` that returns a new function calling `func` with the same arguments and printing `"calling <name>"` first. Use `*args, **kwargs`. Apply it to `fee`.
3. Predict the output, then run: `def f(x, acc=[]): acc.append(x); return acc` called as `f(1)`, `f(2)`, `f(3, [])`, `f(4)`. Fix the function.
4. Build a list of three functions that return 10, 20, 30 using a loop, first incorrectly (all return 30), then correctly in two different ways.
5. Write `group_by(items, key)` that takes an iterable and a function and returns a dict from key to list of items, preserving the input order inside each group.

<details>
<summary>Solution</summary>

1.

```pycon
>>> def fee(days_late, rate=0.5, *, cap=None):
...     amount = max(days_late, 0) * rate
...     if cap is not None:
...         amount = min(amount, cap)
...     return amount
...
>>> fee(10), fee(10, 0.5), fee(10, rate=1, cap=4), fee(-2)
(5.0, 5.0, 4, 0.0)
>>> fee(3, 0.5, 2)
Traceback (most recent call last):
    ...
TypeError: fee() takes from 1 to 2 positional arguments but 3 were given
```

2.

```pycon
>>> def wrap(func):
...     def inner(*args, **kwargs):
...         print("calling", func.__name__)
...         return func(*args, **kwargs)
...     return inner
...
>>> logged_fee = wrap(fee)
>>> logged_fee(4, cap=1)
calling fee
1
```

3. `f(1)` gives `[1]`, `f(2)` gives `[1, 2]` (shared default), `f(3, [])` gives `[3]`, `f(4)` gives `[1, 2, 4]`. Fix:

```pycon
>>> def f(x, acc=None):
...     if acc is None:
...         acc = []
...     acc.append(x)
...     return acc
...
>>> f(1), f(2)
([1], [2])
```

4.

```pycon
>>> bad = [lambda: n * 10 for n in (1, 2, 3)]
>>> [g() for g in bad]
[30, 30, 30]
>>> good1 = [lambda n=n: n * 10 for n in (1, 2, 3)]
>>> [g() for g in good1]
[10, 20, 30]
>>> from functools import partial
>>> good2 = [partial(lambda n: n * 10, n) for n in (1, 2, 3)]
>>> [g() for g in good2]
[10, 20, 30]
```

5.

```pycon
>>> def group_by(items, key):
...     groups = {}
...     for item in items:
...         groups.setdefault(key(item), []).append(item)
...     return groups
...
>>> group_by(["apple", "avocado", "banana", "blueberry", "cherry"], key=lambda w: w[0])
{'a': ['apple', 'avocado'], 'b': ['banana', 'blueberry'], 'c': ['cherry']}
```

</details>
