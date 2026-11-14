---
description: "How @api.depends, @api.model and friends are built, and writing your own."
---

# Decorators

Odoo model code is full of lines starting with `@`: `@api.depends("price", "qty")`, `@api.constrains("date_start", "date_end")`, `@api.model`, `@api.model_create_multi`. Beginners treat them as magic words to copy. They are ordinary Python: a decorator is a function that takes a function and returns a function (or the same function with a note attached). Once you can write one yourself, the Odoo ones stop being mysterious, and you can predict what happens when you stack them, forget one, or override a decorated method. This chapter builds decorators from [functions](functions.md) and closures, then shows how the Odoo decorators fit the same mould, using plain Python equivalents.

## The idea

Functions are values (see [Functions](functions.md)). You can pass one to another function and get one back:

```pycon
>>> def shout(func):
...     def wrapper(*args, **kwargs):
...         result = func(*args, **kwargs)
...         return result.upper()
...     return wrapper
...
>>> def greet(name):
...     return f"hello {name}"
...
>>> greet = shout(greet)
>>> greet("ada")
'HELLO ADA'
```

`shout` takes a function, defines an inner `wrapper` that calls the original and changes its result, and returns the wrapper. Reassigning the name `greet` to the wrapper replaces the function. Every later call to `greet` goes through `wrapper`.

The `@` syntax is a shorthand for that reassignment:

```pycon
>>> @shout
... def greet(name):
...     return f"hello {name}"
...
>>> greet("ada")
'HELLO ADA'
```

This is exactly `greet = shout(greet)` executed right after the `def`. That is the entire mechanism. Everything else is variations on what the decorator does with the function it receives.

## Anatomy of a wrapper

A useful decorator usually follows this template:

```python
def decorator(func):
    def wrapper(*args, **kwargs):
        # before
        result = func(*args, **kwargs)
        # after
        return result
    return wrapper
```

- `*args, **kwargs` let the wrapper accept and forward any call, so the decorator works on any function regardless of its signature.
- `return result` keeps the wrapped function's return value. Leaving it out turns every decorated function into one that returns `None`, which is the decorator version of the missing-`return` bug.
- `func` is remembered by the wrapper through a closure.

### `functools.wraps`

The wrapper replaces the original, and takes over its name and documentation:

```pycon
>>> @shout
... def greet(name):
...     """Say hello."""
...     return f"hello {name}"
...
>>> greet.__name__, greet.__doc__
('wrapper', None)
```

Tracebacks, `help()`, and logging then show `wrapper` instead of `greet`. Fix it with `functools.wraps`, itself a decorator:

```pycon
>>> from functools import wraps
>>> def shout(func):
...     @wraps(func)
...     def wrapper(*args, **kwargs):
...         return func(*args, **kwargs).upper()
...     return wrapper
...
>>> @shout
... def greet(name):
...     """Say hello."""
...     return f"hello {name}"
...
>>> greet.__name__, greet.__doc__
('greet', 'Say hello.')
>>> greet.__wrapped__("x")       # the original is still reachable
'hello x'
```

`wraps` copies the name, docstring, and other attributes, and sets `__wrapped__`. Always use it. The frameworks that inspect function names and attributes (Odoo does, extensively) depend on it.

## Useful examples

### Timing

```pycon
>>> import time
>>> def timed(func):
...     @wraps(func)
...     def wrapper(*args, **kwargs):
...         start = time.perf_counter()
...         try:
...             return func(*args, **kwargs)
...         finally:
...             elapsed = time.perf_counter() - start
...             print(f"{func.__name__} took {elapsed:.3f}s")
...     return wrapper
...
>>> @timed
... def slow():
...     time.sleep(0.05)
...     return "ok"
...
>>> slow()      # doctest: +SKIP
slow took 0.050s
'ok'
```

`try/finally` makes the timing print even when the function raises.

### Logging calls

```pycon
>>> def log_calls(func):
...     @wraps(func)
...     def wrapper(*args, **kwargs):
...         print(f"-> {func.__name__}{args}{kwargs or ''}")
...         result = func(*args, **kwargs)
...         print(f"<- {result!r}")
...         return result
...     return wrapper
...
>>> @log_calls
... def add(a, b):
...     return a + b
...
>>> add(2, 3)
-> add(2, 3)
<- 5
5
```

### Checking preconditions

```pycon
>>> def require_positive(func):
...     @wraps(func)
...     def wrapper(amount):
...         if amount <= 0:
...             raise ValueError(f"{func.__name__}: amount must be > 0, got {amount}")
...         return func(amount)
...     return wrapper
...
>>> @require_positive
... def refund(amount):
...     return f"refunded {amount}"
...
>>> refund(10)
'refunded 10'
>>> refund(-1)
Traceback (most recent call last):
    ...
ValueError: refund: amount must be > 0, got -1
```

### Retrying

Network calls fail transiently; a decorator can retry. This needs arguments, which is the next section.

## Decorators with arguments

`@retry(times=3)` is a function call that returns a decorator. So you need three nested layers: the outer function takes the arguments, the middle one takes the function, the inner one is the wrapper:

```pycon
>>> def retry(times=3, exceptions=(Exception,)):
...     def decorator(func):
...         @wraps(func)
...         def wrapper(*args, **kwargs):
...             for attempt in range(1, times + 1):
...                 try:
...                     return func(*args, **kwargs)
...                 except exceptions as exc:
...                     print(f"attempt {attempt} failed: {exc}")
...                     if attempt == times:
...                         raise
...         return wrapper
...     return decorator
...
>>> calls = {"n": 0}
>>> @retry(times=3, exceptions=(ConnectionError,))
... def flaky():
...     calls["n"] += 1
...     if calls["n"] < 3:
...         raise ConnectionError("boom")
...     return "connected"
...
>>> flaky()
attempt 1 failed: boom
attempt 2 failed: boom
'connected'
```

Order of evaluation: `retry(times=3, ...)` runs first and returns `decorator`. Then `decorator(flaky)` runs, as with a plain decorator. Forgetting the parentheses is a classic mistake:

```pycon
>>> @retry
... def f():
...     return 1
...
>>> f
<function retry.<locals>.decorator at 0x...>
```

Here `retry(f)` was called with `times=f`, and what came back is `decorator`, not a wrapped `f`. Calling `f()` then fails with a confusing `TypeError`. A decorator factory must always be written with its parentheses, even with no arguments: `@retry()`.

### Optional arguments

Some decorators work both with and without arguments. The usual trick is to check whether the first argument is callable:

```pycon
>>> def tag(func=None, *, label="x"):
...     def decorator(f):
...         @wraps(f)
...         def wrapper(*args, **kwargs):
...             return f"[{label}] " + f(*args, **kwargs)
...         return wrapper
...     if func is not None:       # used as @tag
...         return decorator(func)
...     return decorator           # used as @tag(label=...)
...
>>> @tag
... def a():
...     return "A"
...
>>> @tag(label="y")
... def b():
...     return "B"
...
>>> a(), b()
('[x] A', '[y] B')
```

This is neat but adds complexity. Prefer one clear form for your own code.

## Decorators that do not wrap

A decorator does not have to return a wrapper. It can return the **same function**, after recording something about it. That is the pattern behind most Odoo decorators.

### Registering

```pycon
>>> HANDLERS = {}
>>> def handler(event):
...     def decorator(func):
...         HANDLERS[event] = func          # remember it
...         return func                     # return it unchanged
...     return decorator
...
>>> @handler("loan.created")
... def on_created(payload):
...     return f"created {payload}"
...
>>> @handler("loan.returned")
... def on_returned(payload):
...     return f"returned {payload}"
...
>>> sorted(HANDLERS)
['loan.created', 'loan.returned']
>>> HANDLERS["loan.created"]("L1")
'created L1'
```

A dispatcher can now find handlers by name, with no `if/elif` chain. Plugin systems, web routes, and command-line sub-commands are built this way. Odoo's `@http.route(...)` for web controllers records route metadata on the method in a comparable fashion.

### Tagging with attributes

A function is an object, so you can attach attributes to it. A decorator can mark a function and let a framework discover it later:

```pycon
>>> def depends(*fields):
...     def decorator(func):
...         func._depends = fields
...         return func
...     return decorator
...
>>> class LoanLike:
...     @depends("start", "days")
...     def compute_due(self):
...         return "due"
...
...     @depends("amount")
...     def compute_fee(self):
...         return "fee"
...
...     def helper(self):
...         return "plain"
...
>>> for name in sorted(dir(LoanLike)):
...     attr = getattr(LoanLike, name)
...     if hasattr(attr, "_depends"):
...         print(name, attr._depends)
compute_due ('start', 'days')
compute_fee ('amount',)
```

This is the heart of `@api.depends`. The decorator does not change how the function runs. It records which fields the result depends on. When Odoo builds a model it scans the class for functions carrying that mark and uses it to build the dependency graph: when `start` or `days` changes, the field computed by `compute_due` is marked for recomputation. The same is true for `@api.constrains` (which fields trigger the check) and `@api.onchange`. You do not need the internal attribute names, and you should not read or set them yourself; the takeaway is that these decorators attach declarative information, and that **the information is only read when the registry is built**.

That has practical consequences:

- Changing a decorator argument takes effect only after the module is updated or the server restarts, because the registry is built at load time.
- A decorator applied to a function that the framework never scans does nothing. `@api.depends` on a method that is not named in any field's `compute=` does not make it run.
- Typos in the dependency strings are not detected by Python. The decorator accepts any string, so a misspelt field name is a silent bug (or a startup error in the framework, depending on the version).

### `@api.model`, `@api.model_create_multi`, and friends

Odoo also has decorators that influence **how a method is called**: whether `self` is expected to hold specific records or just represent the model, and whether `create` receives one dict or a list of dicts. Conceptually they do the following, in plain Python terms:

```pycon
>>> def model_level(func):
...     """Pretend decorator: the method does not care about specific records."""
...     func._model_level = True
...     return func
...
>>> class Shelf:
...     @model_level
...     def default_title(self):
...         return "Untitled"
...
...     def shout_title(self):
...         return self.title.upper()
...
>>> Shelf.default_title._model_level
True
```

The real ones do more: the framework's calling machinery reads the mark and adapts the arguments it passes and the way it returns results. What you must know as a user:

- `@api.model` methods are called on the model, not on records: `self.env["library.book"].some_method()`. Inside, `self` has no meaningful records, so do not iterate it or read fields from it.
- `@api.model_create_multi` on `create` means the method receives a list of dicts (`vals_list`) and must return a recordset with one record per dict. Overrides of `create` keep this decorator.
- Methods without these decorators are record-level: `self` is a recordset of the records the call applies to, and you loop `for record in self`.
- An override must carry the same decorator as the method it overrides, as noted in [super() explained](super-explained.md).

Exact semantics, including how arguments are adapted across versions, belong to the ORM part of this book. The point here is that these are the same pattern: a decorator that attaches or consumes information about a function.

## Stacking decorators

Several decorators on one function apply bottom-up (the one closest to `def` first):

```pycon
>>> def bold(func):
...     @wraps(func)
...     def wrapper(*a, **k):
...         return "<b>" + func(*a, **k) + "</b>"
...     return wrapper
...
>>> def italic(func):
...     @wraps(func)
...     def wrapper(*a, **k):
...         return "<i>" + func(*a, **k) + "</i>"
...     return wrapper
...
>>> @bold
... @italic
... def text():
...     return "hi"
...
>>> text()
'<b><i>hi</i></b>'
```

`@bold @italic def text` means `text = bold(italic(text))`. The call goes through `bold`'s wrapper first, then `italic`'s, then the original. Order matters when decorators interact. For instance a "check permissions" decorator above a "log the call" decorator logs only permitted calls; swap them and it logs denied calls too.

When mixing a wrapping decorator with one that only tags a function, put the tagging decorator where its tag survives. A wrapping decorator without `functools.wraps` hides attributes set by the tagging one underneath. With `wraps`, attributes in `__dict__` are copied to the wrapper, which is another reason to always use it.

## Class-based decorators

Any callable works as a decorator. A class with `__call__` holds state across calls:

```pycon
>>> class CountCalls:
...     def __init__(self, func):
...         self.func = func
...         self.count = 0
...         wraps(func)(self)
...     def __call__(self, *args, **kwargs):
...         self.count += 1
...         return self.func(*args, **kwargs)
...
>>> @CountCalls
... def ping():
...     return "pong"
...
>>> ping(), ping()
('pong', 'pong')
>>> ping.count
2
```

A class-based decorator is a reasonable choice when you need to inspect state later. For methods, class-based wrappers need extra care (the descriptor protocol), and plain function wrappers are simpler.

## Class decorators

A decorator can also take a class and return a class. `dataclass` is one (see [Classes and inheritance](classes-and-inheritance.md)). A simple custom one:

```pycon
>>> def add_repr(cls):
...     def __repr__(self):
...         fields = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
...         return f"{cls.__name__}({fields})"
...     cls.__repr__ = __repr__
...     return cls
...
>>> @add_repr
... class Book:
...     def __init__(self, title, pages):
...         self.title, self.pages = title, pages
...
>>> Book("Dune", 612)
Book(title='Dune', pages=612)
```

## Decorating methods

A decorator written for plain functions works on methods, because the wrapper receives `self` as its first positional argument and forwards it via `*args`:

```pycon
>>> class Loan:
...     def __init__(self, days):
...         self.days = days
...
...     @log_calls
...     def extend(self, extra):
...         self.days += extra
...         return self.days
...
>>> loan = Loan(14)
>>> loan.extend(7)         # doctest: +ELLIPSIS
-> extend(<...Loan object at 0x...>, 7)
<- 21
21
```

When your wrapper needs `self` itself, for example to read a setting from the record, declare it explicitly: `def wrapper(self, *args, **kwargs)`.

Here is a method decorator in the style of Odoo business code, with no Odoo dependency. It checks a condition on the record before running:

```pycon
>>> def only_in_state(*states):
...     def decorator(func):
...         @wraps(func)
...         def wrapper(self, *args, **kwargs):
...             if self.state not in states:
...                 raise ValueError(
...                     f"{func.__name__} requires state in {states}, got {self.state!r}"
...                 )
...             return func(self, *args, **kwargs)
...         return wrapper
...     return decorator
...
>>> class LoanDoc:
...     def __init__(self):
...         self.state = "draft"
...
...     @only_in_state("draft")
...     def confirm(self):
...         self.state = "open"
...
...     @only_in_state("open")
...     def close(self):
...         self.state = "returned"
...
>>> doc = LoanDoc()
>>> doc.close()
Traceback (most recent call last):
    ...
ValueError: close requires state in ('open',), got 'draft'
>>> doc.confirm(); doc.close(); doc.state
'returned'
```

On a multi-record recordset, `self.state` would be an error (reading a field on a recordset of several records raises). A real Odoo method decorator must loop over `self` or call `self.ensure_one()`. This is a general rule in Odoo: a helper that reads fields from `self` must say whether it supports one record or many.

## Caching decorators

`functools.cache` (3.9+) and `functools.lru_cache` memoise results by arguments:

```pycon
>>> from functools import lru_cache
>>> calls = []
>>> @lru_cache(maxsize=None)
... def square(n):
...     calls.append(n)
...     return n * n
...
>>> square(4), square(4), square(5)
(16, 16, 25)
>>> calls
[4, 5]
>>> square.cache_info()
CacheInfo(hits=1, misses=2, maxsize=None, currsize=2)
```

Use them for pure functions: the result depends only on the arguments. Three cautions:

1. **Arguments must be hashable.** A list or a dict argument raises `TypeError: unhashable type`.
2. **On methods, `self` becomes part of the key**, so the cache keeps every instance alive and a record reference outlives its use. With Odoo records, a long-lived cache holding records or environments keeps cursors, caches, and data in memory.
3. **There is no invalidation.** A cached value never changes while the process lives. In Odoo, the data behind a function can change at any time (another user edits a record, a module is updated), and multiple databases may run in one process. A plain `lru_cache` over database-derived values returns stale data, or worse, data from another database. Odoo provides its own cache decorators for ORM-related caching, tied to the registry of a database and cleared when the registry is reloaded; use those for data that comes from the database, and keep `lru_cache` for pure computations such as parsing a string or building a regular expression.

## Pitfalls

- **Forgetting `return` in the wrapper.** The decorated function returns `None`.
- **Forgetting `functools.wraps`.** Names and docstrings vanish, tracebacks show `wrapper`, and frameworks that inspect function attributes may misbehave.
- **`@decorator` versus `@decorator()`.** A factory used without parentheses replaces your function with an unexpected object.
- **Fixed signatures in wrappers.** Use `*args, **kwargs` unless the wrapper deliberately constrains the call.
- **Wrong stacking order.** Decorators apply bottom-up. A check placed under a logger behaves differently from the reverse.
- **Dropping the Odoo decorator on an override.** The override then runs with the default calling convention and receives arguments it does not expect.
- **Using `@api.depends` expecting it to run the method.** It only declares the dependency. The method runs only if a field points to it with `compute=`.
- **Misspelt dependency names.** Python does not validate them; the model graph silently lacks the edge or the registry load fails.
- **Decorator side effects at import time.** A registering decorator runs when the module is imported. Import order and double imports can register a handler twice or never.
- **`lru_cache` on methods.** The cache holds `self`, causing memory leaks and stale data across requests and databases.
- **Reading fields on a multi-record `self`** inside a method decorator. Loop over records or call `ensure_one()` first.
- **Swallowing exceptions in a wrapper.** A `try/except` that logs and returns `None` hides failures from callers and from the transaction. Re-raise unless you have a reason not to.
- **Stateful decorators shared between threads.** A counter or cache on the wrapper is shared by every request in the process, and Odoo serves many requests concurrently.

## Try it

1. Write `@log_calls` that prints the function name, arguments, and result, using `functools.wraps`. Apply it to a function with keyword arguments and check that `__name__` and `__doc__` survive.
2. Write `@retry(times, exceptions)` that retries, and a test function that fails twice then succeeds. Show the effect of omitting `raise` on the last attempt.
3. Implement `@depends(*fields)` and a function `collect_dependencies(cls)` that returns `{method_name: fields}` for every decorated method of a class, as in this chapter, and test it on a base class plus a subclass that overrides one decorated method without repeating the decorator. Methods from base classes must appear, and the override must be reported as `None`.
4. Write `@memoize` for single-argument functions using a dict stored on the wrapper, then explain why a version that stores a cache on a long-lived object would be a problem for database-derived data.
5. Explain what the following prints, then run it: a function decorated with `@a` above `@b` above `def f`, where each decorator wraps and prints its name before calling the inner function.

<details>
<summary>Solution</summary>

1.

```pycon
>>> def log_calls(func):
...     @wraps(func)
...     def wrapper(*args, **kwargs):
...         result = func(*args, **kwargs)
...         print(f"{func.__name__} args={args} kwargs={kwargs} -> {result!r}")
...         return result
...     return wrapper
...
>>> @log_calls
... def fee(days, rate=0.5):
...     """Late fee."""
...     return days * rate
...
>>> fee(4, rate=2)
fee args=(4,) kwargs={'rate': 2} -> 8
8
>>> fee.__name__, fee.__doc__
('fee', 'Late fee.')
```

2. The `retry` from this chapter works. If the last attempt does not `raise`, the loop ends and the wrapper returns `None`: the caller sees no error, but also no result. The `raise` on the last attempt is what keeps the failure visible.

3.

```pycon
>>> def depends(*fields):
...     def decorator(func):
...         func._depends = fields
...         return func
...     return decorator
...
>>> def collect_dependencies(cls):
...     result = {}
...     for name in dir(cls):
...         if name.startswith("__"):
...             continue
...         attr = getattr(cls, name)
...         if callable(attr):
...             result[name] = getattr(attr, "_depends", None)
...     return result
...
>>> class Base:
...     @depends("a")
...     def compute_x(self): ...
...     @depends("b")
...     def compute_y(self): ...
...
>>> class Child(Base):
...     def compute_y(self): ...          # override without decorator
...
>>> collect_dependencies(Child)
{'compute_x': ('a',), 'compute_y': None}
```

This illustrates why an Odoo override of a decorated method must repeat the decorator when the dependencies matter: the override is a new function object, and the mark is not inherited by it.

4.

```pycon
>>> def memoize(func):
...     cache = {}
...     @wraps(func)
...     def wrapper(arg):
...         if arg not in cache:
...             cache[arg] = func(arg)
...         return cache[arg]
...     wrapper.cache = cache
...     return wrapper
...
>>> @memoize
... def double(n):
...     return n * 2
...
>>> double(2), double(2), double.cache
(4, 4, {2: 4})
```

A cache that lives as long as the process never sees the database change. In a server where records are edited by other users, and where several databases share a process, the cache returns stale or foreign data. Database-derived data needs a cache that is tied to the database registry and invalidated on change.

5. Decorators apply bottom-up (`f = a(b(f))`), and calls run top-down:

```pycon
>>> def make(name):
...     def deco(func):
...         @wraps(func)
...         def wrapper(*a, **k):
...             print("enter", name)
...             return func(*a, **k)
...         return wrapper
...     return deco
...
>>> @make("a")
... @make("b")
... def f():
...     print("body")
...
>>> f()
enter a
enter b
body
```

</details>
