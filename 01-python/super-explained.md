---
description: What super() really resolves to, and the mistakes that break override chains.
---

# super() explained

Most of what you do in an existing Odoo code base is override a method that some other module already defines, and call `super()` to keep the rest of the system working. A wrong `super()` call does not usually crash. It skips another module's logic, drops a return value, or runs checks twice, and the symptom appears in a different feature days later. This chapter explains what `super()` does, using plain Python classes first, then reproduces the structure Odoo builds for its models and walks through the typical override patterns and the ways they go wrong.

Read [Classes and inheritance](classes-and-inheritance.md) first, in particular the section on the method resolution order (MRO).

## The simple case

```pycon
>>> class Base:
...     def describe(self):
...         return "base"
...
>>> class Child(Base):
...     def describe(self):
...         return "child>" + super().describe()
...
>>> Child().describe()
'child>base'
```

In a single-inheritance chain, `super().describe()` means "the `describe` of my parent class". That mental model is correct there and wrong in general. The accurate definition:

> `super()` looks at the MRO of the **type of the object** (`type(self)`), finds the class where the current method was defined, and returns a proxy that searches the classes **after** it in that MRO.

"After it in the MRO of `type(self)`" is not the same as "the parent of the class I am written in". The difference is invisible until a class has more than one base, and in Odoo it always does.

## What zero-argument `super()` does

`super()` without arguments is shorthand for `super(__class__, self)`, where `__class__` is the class in whose body the method is written (the compiler records it for you), and `self` is the first argument of the method:

```pycon
>>> class Child(Base):
...     def describe(self):
...         return "child>" + super(Child, self).describe()
...
>>> Child().describe()
'child>base'
```

The two-argument form still works and appears in older code, in Python 2-era Odoo modules, and in places where there is no suitable first argument. New code uses the zero-argument form.

You can ask a `super` object what it would find:

```pycon
>>> c = Child()
>>> super(Child, c).describe()
'base'
>>> [k.__name__ for k in type(c).__mro__]
['Child', 'Base', 'object']
```

## Why "next in the MRO" and not "the parent"

Take the diamond from the previous chapter, where each class passes the call up with `super()`:

```pycon
>>> class A:
...     def chain(self):
...         return ["A"]
...
>>> class B(A):
...     def chain(self):
...         return ["B"] + super().chain()
...
>>> class C(A):
...     def chain(self):
...         return ["C"] + super().chain()
...
>>> class D(B, C):
...     def chain(self):
...         return ["D"] + super().chain()
...
>>> D().chain()
['D', 'B', 'C', 'A']
```

`B` is written as a subclass of `A`. If `super()` in `B` meant "my parent", `C` would be skipped, and the result would be `['D', 'B', 'A']`. Instead `B`'s `super()` consults the MRO of `D`, which is `D, B, C, A, object`, and moves to the class after `B`, which is `C`. `C` then moves on to `A`. Every class runs exactly once, in a well-defined order. This is called **cooperative** inheritance, and it works only if every class in the chain calls `super()`.

The consequence for `B`: it does not know and must not assume which class runs next. It only knows that "whatever is next" implements `chain`. That is exactly the situation of an Odoo module overriding `write`: it cannot know which other modules also override it, or in what order.

## Odoo's model chain, reproduced in plain Python

When several modules extend one model, Odoo creates a single class whose bases are the contributing classes, with later modules earlier in the base list. You can reproduce the effect without Odoo using `type()`, which builds a class from a name, a tuple of bases, and a namespace:

```pycon
>>> log = []
>>> class CoreBook:                       # the module that defines the model
...     def write(self, vals):
...         log.append(f"core.write {vals}")
...         return True
...
>>> class LibraryExt(CoreBook):           # a later module
...     def write(self, vals):
...         log.append("library: before")
...         result = super().write(vals)
...         log.append("library: after")
...         return result
...
>>> class AuditExt(CoreBook):             # an even later module
...     def write(self, vals):
...         log.append("audit: before")
...         result = super().write(vals)
...         log.append("audit: after")
...         return result
...
>>> Book = type("Book", (AuditExt, LibraryExt), {})   # later module first
>>> [k.__name__ for k in Book.__mro__]
['Book', 'AuditExt', 'LibraryExt', 'CoreBook', 'object']
>>> Book().write({"title": "Dune"})
True
>>> log
['audit: before', 'library: before', "core.write {'title': 'Dune'}", 'library: after', 'audit: after']
```

Note both `LibraryExt` and `AuditExt` are written to inherit `CoreBook` only. They know nothing about each other. The chain `Audit -> Library -> Core` exists only in the combined class. Code placed before the `super()` call runs from the outermost (latest module) inward, and code after it runs inward to outward. In a real database the framework builds the combined class when it loads the registry, so what you see is what runs.

Two corollaries:

- **Ordering.** Your override runs before or after other modules' code depending on module load order, which follows module dependencies. If your module must run first, it has to depend on the others.
- **Cooperation.** One module that forgets to call `super()` cuts the chain: everything beneath it never runs, for every module, not just its own.

## The shapes of an override

Odoo overrides fall into a small number of patterns. Each is a plain Python pattern.

### Before and after

```python
def write(self, vals):
    # code before: validate or adjust vals
    result = super().write(vals)
    # code after: react to the change
    return result
```

Choose before or after on purpose:

- **Before** when you need to inspect or change the incoming values, or reject the operation.
- **After** when you need the saved state, for example the new id of a created record, or to react to a changed value.

Doing the same work after `super()` that should have been done before is a common bug. For instance, validating `vals` after the write has already happened leaves the invalid data in the transaction for a moment, and any exception you raise then relies on the transaction rolling back, which it does in Odoo when an exception propagates out of the request.

### Return the result

`super()` returns something, and so must you:

```pycon
>>> class Base:
...     def compute(self, x):
...         return x * 2
...
>>> class Wrong(Base):
...     def compute(self, x):
...         super().compute(x)          # result dropped
...
>>> class Right(Base):
...     def compute(self, x):
...         return super().compute(x) + 1
...
>>> Wrong().compute(5), Right().compute(5)
(None, 11)
```

For ORM methods the return value matters: `create` returns the new recordset, `write` returns `True`, `unlink` returns `True`, and button actions may return a dict describing a window action. An override that forgets to return breaks every caller that uses the result. The error then reads `'NoneType' object has no attribute ...` in code you did not touch.

### Pass the arguments through

The safest signature for an override whose parent signature you do not control is to forward everything:

```pycon
>>> class Base:
...     def action_done(self, force=False, *, notify=True):
...         return ("done", force, notify)
...
>>> class Ext(Base):
...     def action_done(self, *args, **kwargs):
...         # extra work here
...         return super().action_done(*args, **kwargs)
...
>>> Ext().action_done(True, notify=False)
('done', True, False)
```

A narrower signature, `def action_done(self, force=False)`, silently breaks callers that pass `notify`, with `TypeError: action_done() got an unexpected keyword argument 'notify'`. If you override a method that you know exactly (a standard `write(self, vals)`), the explicit signature is fine and documents intent.

### Modifying the arguments you pass up

You may pass different values to the parent. Copy a dict before changing it, so the caller's data is not altered:

```pycon
>>> class Base:
...     def write(self, vals):
...         return dict(vals)
...
>>> class Ext(Base):
...     def write(self, vals):
...         vals = dict(vals)
...         vals["note"] = "touched"
...         return super().write(vals)
...
>>> original = {"title": "Dune"}
>>> Ext().write(original), original
({'title': 'Dune', 'note': 'touched'}, {'title': 'Dune'})
```

In Odoo the same applies to `create(vals_list)` where `vals_list` is a list of dicts, so the copy must be per item.

### Guarding: when to skip the parent

Occasionally an override replaces the parent's behaviour for a special case, and calls `super()` for everything else:

```pycon
>>> class Base:
...     def price(self, qty):
...         return qty * 10
...
>>> class Promo(Base):
...     def price(self, qty):
...         if qty >= 100:
...             return qty * 8            # replaces the parent entirely
...         return super().price(qty)     # everything else: unchanged
...
>>> Promo().price(5), Promo().price(100)
(50, 800)
```

Skipping `super()` is legitimate here because the early return is a deliberate special case. The rest of the chain is skipped for those inputs, so every other module's logic is skipped too. Know what you are cutting off. In Odoo, skipping `super()` in `create` or `write` is almost never right, because those methods carry framework behaviour (field storage, access checks, recomputation, tracking).

## Recordsets: super in methods called on many records

In Odoo, `self` is a recordset that may hold zero, one, or many records. The conventions are:

```python
def write(self, vals):
    # self may have many records; vals applies to all of them
    for record in self:
        ...                         # per-record checks
    return super().write(vals)      # one call, for the whole recordset
```

Calling `super()` once with the whole recordset is correct and efficient. Calling it inside the loop (`super(LibraryBook, record).write(vals)` for each record) works, but turns one batched write into many, which is slower and changes how the framework batches computations. Loop for your own checks, and call the parent once, unless you have a reason that differs per record.

The explicit two-argument form is needed when you do want the parent's method called on something other than `self`: `super(LibraryBook, record).write(vals)`. The zero-argument form always binds to the method's own first argument.

## Where zero-argument `super()` does not work

Zero-argument `super()` needs two things the compiler provides: the `__class__` cell, and the first argument of the **function it is written in**. That breaks in nested functions:

```pycon
>>> class P:
...     def vals(self):
...         return [1, 2]
...
>>> class Q(P):
...     def broken_lambda(self):
...         f = lambda: super().vals()
...         return f()
...     def broken_inner(self):
...         def inner():
...             return super().vals()
...         return inner()
...     def works(self):
...         parent = super()            # capture it in the method itself
...         return (lambda: parent.vals())()
...
>>> Q().works()
[1, 2]
>>> Q().broken_lambda()
Traceback (most recent call last):
    ...
RuntimeError: super(): no arguments
```

The nested function has no first argument, so `super()` has nothing to bind to. Capture the `super()` object (or the parent's bound method) in the method body and use that inside the nested function, or use the explicit form `super(Q, self)`.

The same holds in generator expressions. List comprehensions behave differently across versions: before Python 3.12 a list comprehension was a hidden nested function, so `super()` inside it failed in the same way, and from 3.12 comprehensions are inlined and it works. Do not depend on that. Compute the value you need from `super()` before the comprehension.

`super()` also works in `@classmethod` and `@staticmethod` bodies in the zero-argument form for class methods (the first argument is `cls`), but not for static methods, which have no first argument:

```pycon
>>> class R:
...     @classmethod
...     def make(cls):
...         return cls.__name__
...
>>> class T(R):
...     @classmethod
...     def make(cls):
...         return "T:" + super().make()
...
>>> T.make()
'T:T'
```

Note that `cls` stays `T` inside `R.make`: `super()` changes where the method is looked up, not what `cls` or `self` is. `self` is the same object throughout the whole chain. That is why base code that calls `self.some_hook()` reaches the most derived override.

## Cooperative `__init__`

`__init__` follows the same rules, and diamonds make them important. If every class calls `super().__init__(...)`, each initialiser runs once, in MRO order. Because the next class in the chain is unknown, keyword arguments are the standard way to pass the remainder along:

```pycon
>>> class A:
...     def __init__(self, **kwargs):
...         print("A init", kwargs)
...         super().__init__()
...
>>> class B(A):
...     def __init__(self, x=0, **kwargs):
...         print("B init", x)
...         super().__init__(**kwargs)
...
>>> class C(A):
...     def __init__(self, y=0, **kwargs):
...         print("C init", y)
...         super().__init__(**kwargs)
...
>>> class D(B, C):
...     pass
...
>>> d = D(x=1, y=2)
B init 1
C init 2
A init {}
```

Each class consumes the keywords it owns and forwards the rest. `A`, the root of the hierarchy, calls `super().__init__()` with no arguments, which reaches `object.__init__`. Passing unconsumed arguments all the way to `object` raises `TypeError`, which is how a misspelt keyword is eventually reported.

## What goes wrong: a catalogue

### Not calling `super()` at all

```pycon
>>> class Base:
...     def save(self):
...         return ["base saved"]
...
>>> class Ext(Base):
...     def save(self):
...         return ["ext saved"]          # forgot super()
...
>>> Ext().save()
['ext saved']
```

No error. The base behaviour is simply gone. In Odoo this is usually how a record is "saved" without being stored, or a module's tracking silently stops. Look for it first when a feature stops working after a new module is installed.

### Calling `super()` with the wrong method name

```pycon
>>> class Ext(Base):
...     def save(self):
...         return super().store()
...
>>> Ext().save()
Traceback (most recent call last):
    ...
AttributeError: 'super' object has no attribute 'store'
```

A typo in the method name is a runtime error, raised only when the code path runs.

### Calling `super()` twice

```pycon
>>> calls = []
>>> class Base:
...     def action(self):
...         calls.append("base")
...
>>> class Ext(Base):
...     def action(self):
...         super().action()
...         super().action()              # pasted twice by mistake
...
>>> Ext().action()
>>> calls
['base', 'base']
```

In Odoo a duplicated `super().write(vals)` writes twice, fires tracking twice, and can send two notifications.

### Calling `super()` inside a conditional that sometimes skips it

```python
def action_confirm(self):
    if self.env.context.get("skip_checks"):
        return True                    # skips every module below this one
    return super().action_confirm()
```

This may be intentional, but it cuts the entire chain for that case. Document it, and avoid bypassing `super()` for operations other modules rely on.

### Missing `@api` decorator information

An Odoo override must carry the same decorator as the method it overrides when that decorator changes how the method is called (for example, `@api.model` or `@api.model_create_multi` on `create`). If you drop the decorator on your override, the framework treats your method with the default conventions and the arguments no longer line up. Decorators are the subject of [Decorators](decorators.md).

### Different signatures in the chain

If one override in the chain narrows the signature while a later module passes an extra argument, the call fails with `TypeError` at the narrow override, not where the extra argument was added. The traceback shows the narrow function.

### Exceptions and partial work

If you do work before `super()` and the parent raises, your earlier work has happened. For in-memory state that you changed, you may need to restore it. For database work in Odoo, the whole request is one transaction, and an uncaught exception rolls it back, so database writes before the failing `super()` call are undone. Files written to disk, emails sent through an external service, and values in module-level caches are **not** rolled back. Do irreversible side effects after `super()` returns successfully.

## Inspecting the chain

When an override does something unexpected, look at the MRO:

```pycon
>>> [k.__name__ for k in Book.__mro__]
['Book', 'AuditExt', 'LibraryExt', 'CoreBook', 'object']
```

Then find which class provides the method you are running:

```pycon
>>> for k in Book.__mro__:
...     if "write" in vars(k):
...         print(k.__name__)
AuditExt
LibraryExt
CoreBook
```

That list is the exact order your override and the others will execute. In Odoo, the MRO of a model's class is available through `type(record).__mro__`, and a debugger will step through the same chain.

## Pitfalls

- **Dropping the return value.** `super().method()` without `return` makes the override return `None`.
- **Skipping `super()` accidentally.** The framework and other modules silently lose behaviour.
- **Calling it twice.** Duplicate writes, duplicate side effects.
- **Assuming `super()` means "my parent".** It means "next in the MRO of the object's actual class". A class that inherits two bases may find its `super()` pointing to a sibling.
- **Narrow signatures.** Overrides that fix arguments break when another module extends the call. Forward `*args, **kwargs` if you do not control the signature.
- **Mutating the caller's `vals`.** Copy before editing, per record for lists of values.
- **Irreversible side effects before `super()`.** An email sent before the parent raises is not rolled back with the transaction.
- **`super()` in nested functions, lambdas, and generator expressions.** Raises `RuntimeError: super(): no arguments` or a `TypeError`. Capture it first.
- **Static methods.** They have no first argument, so zero-argument `super()` cannot work there. Reference the base class explicitly.
- **Wrong class in the two-argument form.** `super(OtherClass, self)` with a class that is not in `type(self).__mro__` raises `TypeError`.
- **Looping and calling `super()` per record** when one batched call would do. It multiplies queries.
- **Forgetting the decorator.** An override without the parent's `@api.model`-style decorator is called with different conventions.
- **Reading code without the MRO.** When behaviour surprises you, print `type(self).__mro__` before theorising.

## Try it

1. Build three classes `Core`, `ModA(Core)`, `ModB(Core)`, each with `save(self, data)` that appends a line to a shared `log` list before and after calling `super()` (except `Core`, which only logs once). Combine them with `type("Final", (ModB, ModA), {})`, call `save`, and read the order in the log. Swap the base order and compare.
2. Add a fourth class `ModC(Core)` whose `save` forgets to call `super()`. Put it in the middle of the chain and show which classes no longer run.
3. Write an override of `compute(self, x)` that adds 1 to the parent's result. Show the bug when the `return` is missing, and write a test with `assert` that catches it.
4. Show the error raised by zero-argument `super()` inside a lambda in a method, and give two fixes.
5. Write a cooperative `__init__` chain for `Base`, `Timestamped(Base)`, and `Owned(Base)`, and a class `Record(Timestamped, Owned)`. Each initialiser should accept its own keyword (`created`, `owner`) and forward the rest. Construct `Record(created="2025-01-01", owner="ada", label="x")` and check that `label` reaches `Base`.

<details>
<summary>Solution</summary>

1.

```pycon
>>> log = []
>>> class Core:
...     def save(self, data):
...         log.append("core")
...
>>> class ModA(Core):
...     def save(self, data):
...         log.append("A before")
...         super().save(data)
...         log.append("A after")
...
>>> class ModB(Core):
...     def save(self, data):
...         log.append("B before")
...         super().save(data)
...         log.append("B after")
...
>>> Final = type("Final", (ModB, ModA), {})
>>> Final().save({})
>>> log
['B before', 'A before', 'core', 'A after', 'B after']
>>> log.clear()
>>> Final2 = type("Final2", (ModA, ModB), {})
>>> Final2().save({})
>>> log
['A before', 'B before', 'core', 'B after', 'A after']
```

2.

```pycon
>>> log.clear()
>>> class ModC(Core):
...     def save(self, data):
...         log.append("C only")          # no super()
...
>>> Final3 = type("Final3", (ModB, ModC, ModA), {})
>>> Final3().save({})
>>> log
['B before', 'C only', 'B after']
```

`ModA` and `Core` never run, because `ModC` ended the chain.

3.

```pycon
>>> class Base:
...     def compute(self, x):
...         return x * 2
...
>>> class Buggy(Base):
...     def compute(self, x):
...         super().compute(x) + 1
...
>>> Buggy().compute(5) is None
True
>>> class Fixed(Base):
...     def compute(self, x):
...         return super().compute(x) + 1
...
>>> assert Fixed().compute(5) == 11
```

The same `assert` applied to `Buggy` would raise `AssertionError`.

4. In the example earlier, `f = lambda: super().vals()` raises `RuntimeError: super(): no arguments`. Fix one: `parent = super()` in the method body, then `lambda: parent.vals()`. Fix two: `lambda: super(Q, self).vals()`.

5.

```pycon
>>> class Base:
...     def __init__(self, label="", **kwargs):
...         self.label = label
...         super().__init__(**kwargs)
...
>>> class Timestamped(Base):
...     def __init__(self, created=None, **kwargs):
...         self.created = created
...         super().__init__(**kwargs)
...
>>> class Owned(Base):
...     def __init__(self, owner=None, **kwargs):
...         self.owner = owner
...         super().__init__(**kwargs)
...
>>> class Record(Timestamped, Owned):
...     pass
...
>>> r = Record(created="2025-01-01", owner="ada", label="x")
>>> r.created, r.owner, r.label
('2025-01-01', 'ada', 'x')
>>> [k.__name__ for k in Record.__mro__]
['Record', 'Timestamped', 'Owned', 'Base', 'object']
```

`Timestamped` takes `created` and forwards `owner` and `label`. `Owned` takes `owner` and forwards `label`. `Base` takes `label`, and anything left over would reach `object.__init__` and raise `TypeError`.

</details>
