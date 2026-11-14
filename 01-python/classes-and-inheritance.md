---
description: "Objects, methods, MRO, and why Odoo inheritance works the way it does."
---

# Classes and inheritance

Every Odoo model is a Python class. `library.book` is a class, a record of it is an object, and a module that extends the model adds methods to it by inheriting. You cannot read or write Odoo code without understanding what `self` is, where attributes live, how a method is found when several classes define it, and what "overriding" means. This chapter teaches classes from the beginning and ends with the exact inheritance mechanics (the method resolution order) that [super() explained](super-explained.md) builds on.

## Why classes

A dictionary can represent a book: `{"title": "Dune", "pages": 612}`. As soon as you want behaviour attached to that data, such as "is this long?", you start writing functions that take a dict and hope every caller builds the dict correctly. A **class** bundles the data (attributes) and the behaviour (methods) in one definition, and gives you a way to create many consistent objects from it.

```pycon
>>> class Book:
...     def __init__(self, title, pages):
...         self.title = title
...         self.pages = pages
...
...     def is_long(self, threshold=500):
...         return self.pages > threshold
...
>>> dune = Book("Dune", 612)
>>> dune.title
'Dune'
>>> dune.is_long()
True
>>> Book("Emma", 474).is_long()
False
```

Terms: `Book` is the **class**. `dune` is an **instance** (an object) of it. `title` and `pages` are **attributes**. `is_long` is a **method**, a function defined inside a class.

## `self` and `__init__`

When you write `dune.is_long()`, Python calls `Book.is_long(dune)`. The object before the dot becomes the first parameter, conventionally named `self`. That is all `self` is: the instance the method was called on.

```pycon
>>> Book.is_long(dune)
True
```

`__init__` is the **initialiser**. Python calls it right after creating a new instance, passing the arguments you gave to `Book(...)`. Inside it you set the initial attributes. It must not return a value.

Attributes are created by assignment on `self` and can be added at any time, even outside the class:

```pycon
>>> dune.isbn = "978-0441172719"
>>> dune.isbn
'978-0441172719'
```

That freedom is a trap. A typo creates a new attribute silently (`dune.pagez = 5`). Odoo models avoid this: fields are declared on the class and the ORM controls what a record has. For plain Python classes, `__slots__` or dataclasses (below) tighten things.

### Instance versus class attributes

An attribute assigned inside a method on `self` belongs to that one instance. An attribute assigned in the class body belongs to the class and is shared:

```pycon
>>> class Member:
...     max_loans = 3            # class attribute: shared
...     def __init__(self, name):
...         self.name = name     # instance attribute: one per object
...         self.loans = []
...
>>> ada, bob = Member("ada"), Member("bob")
>>> ada.max_loans, bob.max_loans, Member.max_loans
(3, 3, 3)
>>> Member.max_loans = 5
>>> ada.max_loans
5
>>> ada.max_loans = 1          # creates an instance attribute that hides the class one
>>> ada.max_loans, bob.max_loans
(1, 5)
```

Lookup goes instance first, then class, then base classes. In an Odoo model, the lines at class level (`_name = "library.book"`, `title = fields.Char()`) are class attributes; the framework reads them when it builds the model, and records then read field values through a different mechanism, not as plain instance attributes.

{% hint style="warning" %}
Never put a mutable object (list, dict, set) in a class body expecting each instance to get its own. It is shared by all of them, which is the same bug as a mutable default argument. Create per-instance containers in `__init__`.
{% endhint %}

## Representing objects: `__repr__` and `__str__`

By default an object prints as an unhelpful address:

```pycon
>>> class Plain:
...     pass
...
>>> repr(Plain())[:15]
'<__main__.Plain'
```

Define `__repr__` to return an unambiguous string, ideally one that looks like the constructor call. It is what the REPL, tracebacks, and log messages using `%r` show. `__str__` is the friendlier text for `print` and `str()`; if absent, `str()` falls back to `__repr__`.

```pycon
>>> class Book:
...     def __init__(self, title, pages):
...         self.title, self.pages = title, pages
...     def __repr__(self):
...         return f"Book({self.title!r}, {self.pages!r})"
...     def __str__(self):
...         return f"{self.title} ({self.pages} pages)"
...
>>> b = Book("Dune", 612)
>>> b
Book('Dune', 612)
>>> print(b)
Dune (612 pages)
>>> [b]
[Book('Dune', 612)]
```

Containers display their items with `repr`, so a good `__repr__` makes debugging output readable. Odoo records give you `library.book(1,)` style reprs, showing the model name and ids, which you will see constantly in logs and the shell.

## Methods, class methods, static methods

An ordinary method gets the instance as `self`. Two decorators change that ([Decorators](decorators.md) explains the mechanism):

```pycon
>>> class Book:
...     DEFAULT_PAGES = 100
...     def __init__(self, title, pages):
...         self.title, self.pages = title, pages
...
...     @classmethod
...     def from_line(cls, line):
...         """Alternative constructor: build a Book from 'title;pages'."""
...         title, pages = line.split(";")
...         return cls(title, int(pages))
...
...     @staticmethod
...     def normalise_title(raw):
...         return " ".join(raw.split()).title()
...
>>> b = Book.from_line("Dune;612")
>>> b.title, b.pages
('Dune', 612)
>>> Book.normalise_title("  the   hobbit ")
'The Hobbit'
```

- `@classmethod` receives the class as `cls`. Use it for alternative constructors and for logic that concerns the class, not one object. It works correctly for subclasses, because `cls` is whichever class it was called on.
- `@staticmethod` receives nothing extra. It is a plain function that lives in the class namespace for organisation. If it does not need the class or instance, a module-level function is often better.

Odoo has its own flavour: `@api.model` marks a method whose `self` is only a model-level recordset (no specific records), roughly the way `classmethod` marks "no instance". That relationship is worked out in [Decorators](decorators.md).

## Properties

A **property** is a method accessed like an attribute. Use it for derived values and for validation on assignment:

```pycon
>>> class Loan:
...     def __init__(self, days):
...         self.days = days
...
...     @property
...     def weeks(self):
...         return self.days / 7
...
...     @property
...     def days(self):
...         return self._days
...
...     @days.setter
...     def days(self, value):
...         if value < 0:
...             raise ValueError("days must be >= 0")
...         self._days = value
...
>>> loan = Loan(14)
>>> loan.weeks
2.0
>>> loan.days = 21
>>> loan.weeks
3.0
>>> loan.days = -1
Traceback (most recent call last):
    ...
ValueError: days must be >= 0
```

The underscore in `_days` is a convention: "internal, do not touch from outside". Python has no true private attributes. In Odoo, derived values are not properties but computed fields (`fields.Float(compute="_compute_weeks")`), because they must be stored, searched, and recomputed when dependencies change. A property is right for plain helper objects.

## Special ("dunder") methods

Names with double underscores let your class plug into the language:

| Method | Triggered by |
|---|---|
| `__repr__`, `__str__` | `repr(x)`, `str(x)`, `print(x)` |
| `__len__` | `len(x)` |
| `__iter__`, `__next__` | `for item in x`, `iter(x)` |
| `__contains__` | `item in x` |
| `__getitem__` | `x[key]`, `x[1:3]` |
| `__bool__` | `if x:` (falls back to `__len__`) |
| `__eq__`, `__lt__`, ... | `x == y`, `x < y` |
| `__hash__` | `hash(x)`, use as dict key or set member |
| `__add__`, `__sub__`, ... | `x + y`, `x - y` |
| `__call__` | `x(...)` |
| `__enter__`, `__exit__` | `with x:` |

A small collection class using several of them:

```pycon
>>> class Shelf:
...     def __init__(self, books=()):
...         self._books = list(books)
...     def __len__(self):
...         return len(self._books)
...     def __iter__(self):
...         return iter(self._books)
...     def __getitem__(self, index):
...         return self._books[index]
...     def __contains__(self, title):
...         return title in self._books
...     def __add__(self, other):
...         return Shelf(self._books + list(other))
...     def __repr__(self):
...         return f"Shelf({self._books!r})"
...
>>> s = Shelf(["Dune", "Emma"])
>>> len(s), "Dune" in s, s[1], list(s)
(2, True, 'Emma', ['Dune', 'Emma'])
>>> s + ["Ulysses"]
Shelf(['Dune', 'Emma', 'Ulysses'])
>>> bool(Shelf()), bool(s)
(False, True)
```

This is close to how an Odoo recordset behaves: it has a length, iterates to single-record recordsets, supports `in`, indexing, slicing, `+` to concatenate, `|` and `&` for union and intersection, and is falsy when empty. Recordsets are one of the most important objects in Odoo, and their behaviour comes entirely from dunder methods on a Python class.

### Equality and hashing

By default two instances are equal only if they are the same object. Define `__eq__` to compare by value. If you define `__eq__` without `__hash__`, Python makes the class unhashable, because equal objects must have equal hashes:

```pycon
>>> class Isbn:
...     def __init__(self, digits):
...         self.digits = digits
...     def __eq__(self, other):
...         return isinstance(other, Isbn) and self.digits == other.digits
...     def __hash__(self):
...         return hash(self.digits)
...
>>> Isbn("123") == Isbn("123"), len({Isbn("123"), Isbn("123")})
(True, 1)
```

Return `NotImplemented` (not `False`) from `__eq__` when you do not know how to compare with the other type, so Python can try the reflected operation. The `isinstance` check above is the simple version.

## Dataclasses

For classes that mainly hold data, `dataclasses` writes `__init__`, `__repr__`, and `__eq__` for you:

```pycon
>>> from dataclasses import dataclass, field
>>> @dataclass
... class LoanLine:
...     book: str
...     days: int = 14
...     tags: list = field(default_factory=list)
...
>>> line = LoanLine("Dune")
>>> line
LoanLine(book='Dune', days=14, tags=[])
>>> line == LoanLine("Dune", 14)
True
>>> line.tags.append("new")
>>> LoanLine("Emma").tags
[]
```

`field(default_factory=list)` gives each instance its own list. A plain `tags: list = []` is rejected by dataclasses with a `ValueError`, which protects you from the shared-mutable-default bug. Options: `@dataclass(frozen=True)` makes instances immutable and hashable, `@dataclass(slots=True)` (Python 3.10+) restricts attributes. Use dataclasses for helper structures in your own code, for example a result object from a parsing step. Do not use them for Odoo models.

## Inheritance

A class can extend another. The new class (the **subclass**) gets all the attributes and methods of the **base class** (superclass) and can add or replace them:

```pycon
>>> class Item:
...     def __init__(self, title):
...         self.title = title
...     def loan_days(self):
...         return 14
...     def describe(self):
...         return f"{self.title} ({self.loan_days()} days)"
...
>>> class Dvd(Item):
...     def loan_days(self):             # override
...         return 7
...
>>> Item("Dune").describe(), Dvd("Alien").describe()
('Dune (14 days)', 'Alien (7 days)')
```

`Dvd` did not define `__init__` or `describe`, so it inherits them. Note that `describe`, defined in `Item`, calls `self.loan_days()`, and for a `Dvd` object `self.loan_days` finds the **override**. This is what makes inheritance useful: base code calls a method by name, and subclasses change the behaviour without touching the base code. The language feature that gives Odoo its extension model is exactly this.

`isinstance` and `issubclass` test relationships:

```pycon
>>> d = Dvd("Alien")
>>> isinstance(d, Dvd), isinstance(d, Item), isinstance(d, str)
(True, True, False)
>>> issubclass(Dvd, Item)
True
```

### Calling the parent: `super()`

An override often wants to extend the parent's behaviour rather than replace it. `super()` gives access to the parent's version:

```pycon
>>> class Dvd(Item):
...     def __init__(self, title, minutes):
...         super().__init__(title)       # let Item set up title
...         self.minutes = minutes
...     def describe(self):
...         base = super().describe()
...         return f"{base}, {self.minutes} min"
...     def loan_days(self):
...         return 7
...
>>> Dvd("Alien", 117).describe()
'Alien (7 days), 117 min'
```

Forgetting `super().__init__(...)` leaves the parent's attributes unset, and the object fails later with `AttributeError`. That is the single most common inheritance bug. The details of what `super()` resolves to are the subject of [super() explained](super-explained.md); here, read it as "the next class up the chain".

### Abstract-style base classes

Raise `NotImplementedError` in a base method that every subclass must provide:

```pycon
>>> class Fee:
...     def amount(self, days_late):
...         raise NotImplementedError
...
>>> class Flat(Fee):
...     def amount(self, days_late):
...         return 2 if days_late > 0 else 0
...
>>> Flat().amount(3)
2
>>> Fee().amount(3)
Traceback (most recent call last):
    ...
NotImplementedError
```

The `abc` module goes further and forbids instantiating a class with unimplemented abstract methods. Odoo's `models.AbstractModel` is a different thing despite the name: it is a model without its own table, meant to be mixed into others. Read the ORM part for what it does.

## Multiple inheritance and the MRO

A class can have several bases:

```pycon
>>> class Loggable:
...     def log(self, message):
...         return f"[{type(self).__name__}] {message}"
...
>>> class Item:
...     def __init__(self, title):
...         self.title = title
...
>>> class Dvd(Item, Loggable):
...     pass
...
>>> Dvd("Alien").log("created")
'[Dvd] created'
```

`Loggable` is a **mixin**: a class not meant to stand alone, providing a small piece of behaviour for others to combine. The mixin pattern is how Odoo composes features: a model inherits from `mail.thread` to get messaging, `mail.activity.mixin` for activities, and so on. Both of those are real standard mixins, used through the Odoo-level `_inherit` mechanism covered later, but the underlying idea is exactly the Python one above.

When several bases define the same method, Python needs a rule to pick one. That rule is the **method resolution order** (MRO), a linear list of all classes that Python searches in order. Inspect it:

```pycon
>>> Dvd.__mro__
(<class '__main__.Dvd'>, <class '__main__.Item'>, <class '__main__.Loggable'>, <class 'object'>)
>>> [c.__name__ for c in Dvd.__mro__]
['Dvd', 'Item', 'Loggable', 'object']
```

Python computes the MRO with the C3 linearisation algorithm, which gives these guarantees:

1. A class comes before its bases.
2. The order of bases in the `class` statement is preserved.
3. Each class appears once, even when reachable through several paths.

Diamonds show why this matters:

```pycon
>>> class A:
...     def who(self): return "A"
...
>>> class B(A):
...     def who(self): return "B"
...
>>> class C(A):
...     def who(self): return "C"
...
>>> class D(B, C):
...     pass
...
>>> [c.__name__ for c in D.__mro__]
['D', 'B', 'C', 'A', 'object']
>>> D().who()
'B'
```

`A` is the common base. It must come after both `B` and `C`, so its `who` is reached only if neither `B` nor `C` has one. The order of the bases in `class D(B, C)` decides: swap them and `who()` returns `"C"`.

If the constraints cannot be satisfied, Python refuses to create the class:

```pycon
>>> class X(A, B):
...     pass
...
Traceback (most recent call last):
    ...
TypeError: Cannot create a consistent method resolution order (MRO) for bases A, B
```

`A` before `B` contradicts `B` being a subclass of `A`.

### Odoo's model classes

When you write a model class in a module:

```python
class LibraryBook(models.Model):
    _name = "library.book"
    _description = "Book"
```

you are writing a normal Python class that inherits `models.Model`. When another module extends the same model, it writes:

```python
class LibraryBookExtra(models.Model):
    _inherit = "library.book"
```

This second class does not make a new model. At registry build time, Odoo collects every class that contributes to `library.book`, in module load order, and creates the final model class with all of them as base classes. Methods are then resolved through the MRO of that combined class, which is why each override can call `super()` and reach the previous module's version. The practical consequence: **the order of module loading is the order of the inheritance chain**, and an override placed in a module that loads later runs first. The detail of how the registry assembles these classes is in the architecture part of this book; what you need here is the MRO, because it explains everything that follows.

## Composition over inheritance

Inheritance expresses "is a". Composition expresses "has a", by holding another object in an attribute:

```pycon
>>> class Clock:
...     def today(self):
...         from datetime import date
...         return date(2025, 3, 10)
...
>>> class LoanService:
...     def __init__(self, clock=None):
...         self.clock = clock or Clock()
...     def is_overdue(self, due):
...         return due < self.clock.today()
...
>>> from datetime import date
>>> LoanService().is_overdue(date(2025, 3, 1))
True
```

Passing the clock in makes the service testable, since a test can supply a fixed one. When a design feels like a deep inheritance tree, check whether a few small objects composed together would be simpler. Odoo itself leans heavily on inheritance for extensibility, because modules you do not control need a way to alter behaviour, but your own helper code usually does not need it.

## `__slots__`, briefly

`__slots__` declares the allowed attributes and saves memory when you create many small objects. It also turns the "typo creates a new attribute" problem into an error:

```pycon
>>> class Point:
...     __slots__ = ("x", "y")
...     def __init__(self, x, y):
...         self.x, self.y = x, y
...
>>> p = Point(1, 2)
>>> p.z = 3
Traceback (most recent call last):
    ...
AttributeError: 'Point' object has no attribute 'z'
```

Use it only where memory or strictness matters.

## Pitfalls

- **Forgetting `self`.** A method defined as `def total():` fails with `TypeError: total() takes 0 positional arguments but 1 was given` when called on an instance.
- **Forgetting `self.` inside a method.** `title = ...` sets a local that disappears. `self.title = ...` sets the attribute.
- **Mutable class attributes.** A list in the class body is shared by all instances. Create it in `__init__`.
- **Missing `super().__init__()`.** The parent's setup never runs. The failure shows up later as `AttributeError`.
- **Overriding without calling the parent.** In Odoo, replacing `write` or `create` without `super()` skips the framework's own logic and every other module's override. See [super() explained](super-explained.md).
- **Ignoring the return value in overrides.** If the parent returns something and you drop it, every caller gets `None`.
- **Defining `__eq__` and breaking hashing.** Add `__hash__`, or accept that instances cannot be put in sets or used as dict keys.
- **Comparing with `is`.** Use `==` for values. `is` tests identity.
- **Inheriting for code reuse only.** If the subclass is not truly a kind of the base, use composition.
- **Deep or tangled hierarchies.** Every extra layer adds an entry to the MRO that the reader must hold in their head. Prefer shallow trees and small mixins with one responsibility.
- **Mixin order.** `class D(B, C)` and `class D(C, B)` differ when both define a method. Check `D.__mro__` when behaviour surprises you.
- **Name mangling confusion.** A name with two leading underscores (`__x`) is renamed inside the class to `_ClassName__x` and cannot be reached by a subclass under that name. Use one underscore for "internal".
- **Circular imports between class files.** Two modules that import each other's classes at the top fail on load. See [Modules and imports](modules-and-imports.md).

## Try it

1. Write a `Book` class with `title`, `pages`, `__repr__`, and `__eq__` (equal when title and pages match) and `__hash__`. Show that two equal books collapse to one in a set.
2. Write `Item` and `Dvd` as above, then add `Ebook(Item)` whose `loan_days()` returns `21` and whose `describe` adds the file size using `super()`. Print `describe()` for one of each in a loop.
3. Create classes `A`, `B(A)`, `C(A)`, `D(B, C)`, each with a method `chain()` returning a list that starts with its own letter and extends with `super().chain()` if there is a parent. Predict `D().chain()` and `D.__mro__`, then run it.
4. Implement `Shelf` with `__len__`, `__iter__`, `__contains__`, `__getitem__`, and `__bool__`-by-length, and verify `bool(Shelf())` is `False`. Then add `__or__` for union without duplicates, preserving order.
5. Convert `Book` into a dataclass with `frozen=True`, and explain what changes about mutation and hashing.

<details>
<summary>Solution</summary>

1.

```pycon
>>> class Book:
...     def __init__(self, title, pages):
...         self.title, self.pages = title, pages
...     def __repr__(self):
...         return f"Book({self.title!r}, {self.pages!r})"
...     def __eq__(self, other):
...         if not isinstance(other, Book):
...             return NotImplemented
...         return (self.title, self.pages) == (other.title, other.pages)
...     def __hash__(self):
...         return hash((self.title, self.pages))
...
>>> len({Book("Dune", 612), Book("Dune", 612), Book("Emma", 474)})
2
```

2.

```pycon
>>> class Item:
...     def __init__(self, title):
...         self.title = title
...     def loan_days(self):
...         return 14
...     def describe(self):
...         return f"{self.title} ({self.loan_days()} days)"
...
>>> class Dvd(Item):
...     def loan_days(self):
...         return 7
...
>>> class Ebook(Item):
...     def __init__(self, title, mb):
...         super().__init__(title)
...         self.mb = mb
...     def loan_days(self):
...         return 21
...     def describe(self):
...         return super().describe() + f", {self.mb} MB"
...
>>> for item in [Item("Dune"), Dvd("Alien"), Ebook("Emma", 2)]:
...     print(item.describe())
Dune (14 days)
Alien (7 days)
Emma (21 days), 2 MB
```

3.

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
>>> [k.__name__ for k in D.__mro__]
['D', 'B', 'C', 'A', 'object']
```

`B`'s `super()` does not go to `A`; it goes to the next class after `B` in `D`'s MRO, which is `C`. That behaviour is the key idea of the next chapter.

4.

```pycon
>>> class Shelf:
...     def __init__(self, books=()):
...         self._books = list(books)
...     def __len__(self):
...         return len(self._books)
...     def __iter__(self):
...         return iter(self._books)
...     def __contains__(self, item):
...         return item in self._books
...     def __getitem__(self, index):
...         return self._books[index]
...     def __or__(self, other):
...         merged = list(self._books)
...         merged.extend(b for b in other if b not in merged)
...         return Shelf(merged)
...     def __repr__(self):
...         return f"Shelf({self._books!r})"
...
>>> bool(Shelf()), Shelf(["a"]) | Shelf(["a", "b"])
(False, Shelf(['a', 'b']))
```

When `__bool__` is not defined, Python falls back to `__len__`, so an empty shelf is falsy.

5.

```pycon
>>> from dataclasses import dataclass
>>> @dataclass(frozen=True)
... class Book:
...     title: str
...     pages: int
...
>>> b = Book("Dune", 612)
>>> b.pages = 700
Traceback (most recent call last):
    ...
dataclasses.FrozenInstanceError: cannot assign to field 'pages'
>>> hash(b) == hash(Book("Dune", 612))
True
```

Frozen instances reject assignment and, because `eq` and `frozen` are both true, get a generated `__hash__`, so they can be set members and dict keys.

</details>
