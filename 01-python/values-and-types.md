---
description: "Numbers, strings, booleans, None, truthiness, and the traps in each."
---

# Values and types

Every piece of data in a program is a **value**, and every value has a **type** that decides what you can do with it. You can add two numbers, join two strings, and not add a number to a string. Odoo field values map directly onto a handful of these types: `Char` fields hold strings, `Integer` fields hold ints, `Boolean` fields hold booleans, `Float` and `Monetary` fields hold numbers, and an empty field often arrives as `False` or `None`. Knowing exactly how these types behave, including where they surprise you, removes a large share of everyday bugs. This chapter covers the built-in scalar types, variables, conversion, and truthiness.

## Variables are names

```pycon
>>> title = "Dune"
>>> pages = 612
>>> price = 12.5
>>> available = True
>>> note = None
```

`title = "Dune"` does not put a string inside a box called `title`. It makes the name `title` refer to a string object. The name is a label; the object exists independently. You can ask an object for its type and identity:

```pycon
>>> type(title)
<class 'str'>
>>> type(pages), type(price), type(available), type(note)
(<class 'int'>, <class 'float'>, <class 'bool'>, <class 'NoneType'>)
```

Two names can refer to the same object:

```pycon
>>> a = "Dune"
>>> b = a
>>> a is b
True
```

This matters for **mutable** objects (lists, dicts, and sets) and is revisited in [Lists, tuples, dicts, sets](collections.md). Numbers, strings, booleans, `None`, and tuples are **immutable**: operations create new objects rather than changing the old one.

Rebinding a name changes only that name:

```pycon
>>> pages = pages + 1
>>> pages
613
>>> pages += 1          # shorthand for pages = pages + 1
>>> pages
614
```

### Naming rules and conventions

A name may contain letters, digits, and underscores, and cannot start with a digit. Names are case-sensitive (`Pages` and `pages` are different). The conventions Odoo code follows (PEP 8, the Python style guide):

| Kind | Style | Example |
|---|---|---|
| Variable, function, method, module | `snake_case` | `loan_count`, `compute_total` |
| Class | `CapWords` | `LibraryBook` |
| Constant | `UPPER_CASE` | `MAX_RENEWALS` |
| Internal use | leading underscore | `_cache`, `_compute_total` |

Words reserved by the language cannot be names: `if`, `for`, `class`, `def`, `return`, `None`, `True`, `False`, `import`, `in`, `is`, `not`, `and`, `or`, and a few others. You can accidentally overwrite built-in names such as `list`, `id`, `type`, `sum`, `max`, `filter`, and `str`, because they are ordinary names that Python looks up when your own scope has nothing by that name. Odoo code is full of variables called `id`; they shadow the built-in `id()` only inside that scope, which is harmless until you need the built-in there.

## Integers

`int` has no size limit. Python switches to arbitrary precision automatically.

```pycon
>>> 7 + 3, 7 - 3, 7 * 3
(10, 4, 21)
>>> 7 / 2           # true division always gives a float
3.5
>>> 7 // 2          # floor division
3
>>> 7 % 2           # remainder
1
>>> 2 ** 10
1024
>>> 2 ** 100
1267650600228229401496703205376
```

Division has two operators, and the difference matters. `/` always returns a float, even when the result is whole (`6 / 3` is `2.0`). `//` rounds toward negative infinity, which differs from "chop off the decimals" for negative numbers:

```pycon
>>> -7 // 2
-4
>>> int(-7 / 2)     # truncates toward zero
-3
>>> -7 % 2          # remainder takes the sign of the divisor
1
>>> divmod(17, 5)   # quotient and remainder together
(3, 2)
```

Underscores make large literals readable: `1_000_000`. Hexadecimal and binary literals exist (`0xFF`, `0b1010`) but are rare in business code.

Integer ids are everywhere in Odoo (`record.id`, foreign keys in raw SQL), and the type is `int` all the way down. A recordset's `id` for a record not yet saved is not an int; it is a special "new id" object, covered when we meet the ORM.

## Floats

`float` is a 64-bit binary floating-point number. It represents most decimals only approximately, because computers store numbers in base 2 and `0.1` has no finite base-2 expansion.

```pycon
>>> 0.1 + 0.2
0.30000000000000004
>>> 0.1 + 0.2 == 0.3
False
>>> round(2.675, 2)
2.67
>>> 1e3, 1.5e-3
(1000.0, 0.0015)
```

`round(2.675, 2)` gives `2.67`, not `2.68`, because the float closest to 2.675 is slightly below it. This is not a Python bug; every language using IEEE 754 doubles behaves identically. Two rules follow:

1. Never compare floats with `==` when they come from arithmetic. Compare with a tolerance (`math.isclose`) or, in Odoo, with the helper functions designed for it (`float_compare`, `float_is_zero`, `float_round` from `odoo.tools`), which compare to a given number of decimal digits. See [Money, dates, and time zones](working-with-money-and-dates.md).
2. Never store money in floats. Use `Decimal` or integers of the smallest currency unit in your own code. Odoo's `Monetary` field is backed by a float in the database column but rounds using the currency's rules, which is why it is used with a currency, not on its own.

```pycon
>>> import math
>>> math.isclose(0.1 + 0.2, 0.3)
True
```

Special values exist: `float("inf")`, `float("-inf")`, and `float("nan")`. `nan` is not equal to anything, including itself:

```pycon
>>> nan = float("nan")
>>> nan == nan
False
>>> nan != nan
True
>>> math.isnan(nan)
True
```

A float `nan` leaking into a total silently poisons every sum it touches. Check input at the boundary.

### Mixing int and float

An operation on an int and a float gives a float:

```pycon
>>> 3 + 0.5
3.5
>>> 4 / 2
2.0
>>> type(4 / 2)
<class 'float'>
```

This is a common source of a surprising `2.0` where `2` was expected, for example when building a string such as `"%d items" % qty` (fine) versus `str(qty)` (gives `'2.0'`).

### Converting

```pycon
>>> int("42"), int(3.9), int(-3.9)
(42, 3, -3)
>>> float("3.14"), float(2)
(3.14, 2.0)
>>> int("3.14")
Traceback (most recent call last):
    ...
ValueError: invalid literal for int() with base 10: '3.14'
>>> int(float("3.14"))
3
```

`int()` on a float truncates toward zero; it does not round. `int()` on a string accepts only integer text (surrounding whitespace is fine, `" 42 "` works). Converting user input is where `ValueError` appears; see [Errors and exceptions](errors-and-exceptions.md).

## Strings

A `str` is an immutable sequence of Unicode characters. Use single or double quotes, interchangeably:

```pycon
>>> 'library'
'library'
>>> "it's fine"
"it's fine"
>>> 'say "hi"'
'say "hi"'
>>> "line one\nline two"
'line one\nline two'
>>> print("line one\nline two")
line one
line two
>>> print("a\tb")
a	b
```

The REPL shows the `repr` (a form meant for programmers, with quotes and escapes), while `print` shows the text. `\n` is a newline, `\t` a tab, `\\` a backslash. Triple quotes span lines:

```pycon
>>> text = """first
... second"""
>>> text
'first\nsecond'
```

Raw strings, prefixed with `r`, keep backslashes as typed. They are essential for regular expressions and Windows paths:

```pycon
>>> print(r"C:\temp\new")
C:\temp\new
>>> len(r"\n"), len("\n")
(2, 1)
```

### Indexing and slicing

Strings are sequences. Positions start at 0, and negative positions count from the end:

```pycon
>>> code = "LIB-2024-0042"
>>> code[0], code[-1]
('L', '2')
>>> code[:3]
'LIB'
>>> code[4:8]
'2024'
>>> code[-4:]
'0042'
>>> code[::-1]
'2400-4202-BIL'
>>> len(code)
13
```

A slice `s[start:stop]` includes `start` and excludes `stop`. Omitted ends mean "from the beginning" and "to the end". `s[::step]` takes every step-th character; a step of -1 reverses. Slicing never raises an error for out-of-range ends, while indexing does:

```pycon
>>> code[100:]
''
>>> code[100]
Traceback (most recent call last):
    ...
IndexError: string index out of range
```

### Strings are immutable

```pycon
>>> code[0] = "X"
Traceback (most recent call last):
    ...
TypeError: 'str' object does not support item assignment
>>> "X" + code[1:]
'XIB-2024-0042'
```

Every "modification" builds a new string. Methods never change the original:

```pycon
>>> name = "  Ada Lovelace  "
>>> name.strip()
'Ada Lovelace'
>>> name
'  Ada Lovelace  '
```

Forgetting to use the return value (`name.strip()` on its own line, expecting `name` to change) is a classic beginner bug.

### Common methods

```pycon
>>> s = "Library Book, first edition"
>>> s.lower(), s.upper()
('library book, first edition', 'LIBRARY BOOK, FIRST EDITION')
>>> s.title()
'Library Book, First Edition'
>>> s.startswith("Library"), s.endswith("edition")
(True, True)
>>> s.find("Book"), s.find("zzz")
(8, -1)
>>> s.replace("first", "second")
'Library Book, second edition'
>>> s.split(", ")
['Library Book', 'first edition']
>>> "a,b,,c".split(",")
['a', 'b', '', 'c']
>>> "  many   spaces  here ".split()
['many', 'spaces', 'here']
>>> "-".join(["2024", "05", "17"])
'2024-05-17'
>>> "abc".center(9, "*")
'***abc***'
>>> "42".zfill(6)
'000042'
>>> "Book" in s
True
```

Note two behaviours of `split`. With an explicit separator, consecutive separators produce empty strings. With no argument, it splits on any run of whitespace and discards empties. Use `join` to build a string from pieces; it is the inverse of `split` and far faster than repeated `+` in a loop.

`s.find()` returns `-1` for "not found"; `s.index()` raises `ValueError`. Use `in` for a plain membership test, because the `-1` return value is truthy and has caused many bugs: `if s.find("x"):` is true when the text is absent.

### Formatting

You will build strings constantly: log messages, error messages for users, file names, domains. Three mechanisms exist.

**f-strings** (Python 3.6+) evaluate expressions inline and are the default choice:

```pycon
>>> title, qty, price = "Dune", 3, 12.5
>>> f"{title}: {qty} x {price} = {qty * price}"
'Dune: 3 x 12.5 = 37.5'
>>> f"{price:.2f}"
'12.50'
>>> f"{1234567.891:,.2f}"
'1,234,567.89'
>>> f"{qty:05d}"
'00003'
>>> f"{title:>10}|{title:<10}|{title:^10}|"
'      Dune|Dune      |   Dune   |'
>>> f"{0.256:.1%}"
'25.6%'
>>> f"{title!r}"
"'Dune'"
>>> f"{qty=}"
'qty=3'
```

After the colon comes a format specification: `.2f` is two decimals, `,` adds thousands separators, `05d` pads an integer to width 5 with zeros, `>` `<` `^` align. `!r` uses `repr`. The `{name=}` form (Python 3.8+) prints the expression and its value, handy when debugging.

**`str.format`** is the older equivalent, still common in Odoo core where strings are built separately from their values:

```pycon
>>> "{} has {} copies".format("Dune", 3)
'Dune has 3 copies'
>>> "{name} has {n} copies".format(name="Dune", n=3)
'Dune has 3 copies'
```

**`%` formatting** is the oldest. It remains important for one reason: logging and Odoo's translation function `_()` use `%`-style placeholders so that the message template can be translated or deferred before values are inserted.

```pycon
>>> "%s has %d copies" % ("Dune", 3)
'Dune has 3 copies'
>>> "%(name)s has %(n)d copies" % {"name": "Dune", "n": 3}
'Dune has 3 copies'
>>> "%.2f" % 12.5
'12.50'
```

{% hint style="warning" %}
Do not use an f-string inside a translated message. The text passed to the translation function is looked up as a whole; if you interpolate first, every distinct value creates a distinct, untranslatable key. Pass the template with placeholders, then insert values after translation. The rule and the exact call are covered where `_()` is introduced; the Python habit to form now is "template first, values second".
{% endhint %}

### Unicode and bytes

`str` holds text. `bytes` holds raw bytes. Converting between them requires naming an encoding:

```pycon
>>> "café".encode("utf-8")
b'caf\xc3\xa9'
>>> b'caf\xc3\xa9'.decode("utf-8")
'café'
>>> len("café"), len("café".encode("utf-8"))
(4, 5)
```

Encoding an `é` takes two bytes in UTF-8, so the byte length is not the character count. Files, network sockets, and base64 deal in bytes; fields, labels, and messages deal in strings. Odoo binary fields (attachments, images) are stored as base64-encoded content; the standard library chapter shows the conversions. The rule: decode bytes to `str` at the input boundary, work in `str`, encode at the output boundary.

Combining a `str` and a `bytes` raises `TypeError`:

```pycon
>>> "abc" + b"def"
Traceback (most recent call last):
    ...
TypeError: can only concatenate str (not "bytes") to str
```

## Booleans

`bool` has two values, `True` and `False`. Comparisons produce them:

```pycon
>>> 3 < 5, 3 == 3, 3 != 3, "a" < "b"
(True, True, False, True)
>>> 1 < 3 < 5          # chained comparison
True
```

Python lets you chain comparisons the way mathematics does: `1 < x < 5` means `1 < x and x < 5`, with `x` evaluated once.

Combine conditions with `and`, `or`, and `not`:

```pycon
>>> True and False, True or False, not True
(False, True, False)
```

`bool` is a subclass of `int`: `True` equals 1 and `False` equals 0, so `sum([True, True, False])` is `2`. That is a useful counting idiom, and also the reason `True + True` works without complaint.

```pycon
>>> sum([True, True, False])
2
>>> True + True
2
```

### `==` versus `is`

`==` asks whether two values are equal. `is` asks whether two names refer to the exact same object. Use `==` for values. Use `is` only for `None`, `True`, and `False` singletons, and then prefer plain truthiness checks (below) except where `None` must be told apart from `0` or empty.

```pycon
>>> a = [1, 2]
>>> b = [1, 2]
>>> a == b, a is b
(True, False)
>>> x = None
>>> x is None, x is not None
(True, False)
```

Comparing small ints or short strings with `is` sometimes works because CPython reuses some objects. That is an implementation detail, and code relying on it breaks without notice.

## None

`None` is the single value meaning "nothing here". Functions that do not return anything return `None`. It is the standard sentinel for an optional argument or a missing value.

```pycon
>>> result = print("hi")
hi
>>> result is None
True
```

In Odoo, an unset field on a record is not uniformly `None`. A `Char` field with no value reads as `False`, an unset `Many2one` reads as an empty recordset, a `Date` with no value reads as `False`. Code that tests `if record.date_due is None` will therefore never match a record read from the database. Test truthiness instead, or compare against `False` deliberately. This quirk is old and widespread, and you must know it before reading any real Odoo code.

## Truthiness

Every value is either truthy or falsy when used in a condition (`if x:`). The falsy values:

| Type | Falsy value |
|---|---|
| bool | `False` |
| None | `None` |
| int / float | `0`, `0.0` |
| str | `""` |
| list / tuple / dict / set | empty |
| Decimal | `Decimal("0")` |
| Odoo recordset | empty recordset |

Everything else is truthy:

```pycon
>>> for v in [0, 0.0, "", [], {}, None, False, "0", "False", [0], " "]:
...     print(repr(v), bool(v))
0 False
0.0 False
'' False
[] False
{} False
None False
False False
'0' True
'False' True
[0] True
' ' True
```

Note the last four: a non-empty string is truthy even if its content is `"0"` or `"False"`, a list containing a falsy value is truthy, and a string with one space is truthy.

Truthiness makes code short:

```python
if not records:
    return
```

It also hides distinctions. `if not qty:` is true for `0`, `0.0`, `None`, and `False` alike. When `0` is a legitimate value and `None` means "not provided", write `if qty is None:`.

### Short-circuit evaluation and `or` defaults

`and` and `or` do not return `True` or `False`. They return one of their operands, and stop evaluating as soon as the result is known:

```pycon
>>> 0 or "default"
'default'
>>> "value" or "default"
'value'
>>> "" and "never"
''
>>> [] or [1]
[1]
```

`x or default` is a well-known idiom for "use `x` unless it is falsy". It is correct for strings and collections where empty means missing. It is wrong when `0` or `False` is a valid value:

```pycon
>>> discount = 0
>>> discount or 10      # the user explicitly chose 0, and gets 10
10
>>> discount if discount is not None else 10
0
```

Short-circuiting also lets you guard an expression:

```pycon
>>> user = None
>>> user and user.upper()
>>> user = "ada"
>>> user and user.upper()
'ADA'
```

The first call prints nothing because the REPL does not display `None`.

### Conditional expressions

```pycon
>>> qty = 0
>>> "none left" if qty == 0 else "in stock"
'none left'
```

`A if condition else B` is an expression, so it can sit inside a larger expression, an argument, or a string.

## Checking and converting types

```pycon
>>> isinstance(3, int), isinstance(3, (int, float)), isinstance(True, int)
(True, True, True)
>>> isinstance("3", int)
False
```

`isinstance(x, T)` is the correct check; avoid `type(x) == T`, which rejects subclasses. Note that `isinstance(True, int)` is `True`, so a function that accepts "any int" also accepts `True`.

Conversion functions are named after the type: `int()`, `float()`, `str()`, `bool()`. They do not guess:

```pycon
>>> str(12), str(None), str(3.0)
('12', 'None', '3.0')
>>> bool("False")
True
```

`bool("False")` is `True` because the string is non-empty. To parse a text flag, compare explicitly:

```pycon
>>> value = "False"
>>> value.strip().lower() in ("1", "true", "yes", "y")
False
```

### No implicit conversion between text and numbers

```pycon
>>> "5" + 3
Traceback (most recent call last):
    ...
TypeError: can only concatenate str (not "int") to str
>>> "5" * 3
'555'
>>> int("5") + 3
8
```

Python refuses to guess whether you meant `"53"` or `8`. Notice that `"5" * 3` is legal and repeats the string, which can mask a bug when a numeric string sneaks in from a form or an import.

## A worked example: validating a loan code

Combine the pieces. A function that checks a code of the form `LIB-YYYY-NNNN` and returns the year and sequence number:

```pycon
>>> def parse_code(code):
...     code = code.strip().upper()
...     parts = code.split("-")
...     if len(parts) != 3 or parts[0] != "LIB":
...         return None
...     year, seq = parts[1], parts[2]
...     if not (year.isdigit() and seq.isdigit()):
...         return None
...     return int(year), int(seq)
...
>>> parse_code(" lib-2024-0042 ")
(2024, 42)
>>> parse_code("LIB-2024-00x2") is None
True
>>> parse_code("BOOK-1-2") is None
True
```

`isdigit()` returns `True` when the string is non-empty and consists of digits. Note that for some non-ASCII digits (for instance superscripts) `isdigit()` is true yet `int()` fails; `str.isdecimal()` is stricter, and for external input a regular expression is safer (see the [Standard library toolbox](standard-library-toolbox.md)). Functions are introduced properly in [Functions](functions.md).

## Odoo-flavoured values

The types above appear in field definitions and field values:

| Odoo field | Python value you read |
|---|---|
| `Char`, `Text`, `Html`, `Selection` | `str`, or `False` when empty |
| `Integer` | `int` |
| `Float` | `float` |
| `Boolean` | `bool` |
| `Date`, `Datetime` | `datetime.date`, `datetime.datetime`, or `False` |
| `Many2one` | a recordset of at most one record |
| `One2many`, `Many2many` | a recordset |

A defensive helper for the "False when empty" quirk:

```pycon
>>> def clean(value):
...     """Return a stripped string, or '' for False/None/empty."""
...     return value.strip() if isinstance(value, str) else ""
...
>>> clean("  Ada  "), clean(False), clean(None)
('Ada', '', '')
```

Another common pattern is building a display label from optional parts:

```pycon
>>> def label(title, author=None, year=None):
...     parts = [title]
...     if author:
...         parts.append(f"by {author}")
...     if year:
...         parts.append(f"({year})")
...     return " ".join(parts)
...
>>> label("Dune"), label("Dune", "F. Herbert"), label("Dune", "F. Herbert", 1965)
('Dune', 'Dune by F. Herbert', 'Dune by F. Herbert (1965)')
```

## Pitfalls

- **Float equality.** `0.1 + 0.2 == 0.3` is false. Compare with tolerance, or with Odoo's `float_compare` and a precision.
- **Float for money.** Sums of floats drift by fractions of a cent and totals stop matching invoices. Use `Decimal` or Odoo's currency rounding. See [Money, dates, and time zones](working-with-money-and-dates.md).
- **`/` versus `//`.** `total / count` returns a float, and `//` floors negative numbers downward. Use the one you mean.
- **`int()` truncates.** `int(2.99)` is `2`. Use `round()` when rounding is intended, and remember that `round()` uses banker's rounding for exact halves: `round(0.5)` is `0`, `round(1.5)` is `2`, `round(2.5)` is `2`.
- **Discarding the return value of a string method.** `name.strip()` alone does nothing useful.
- **`if x:` when 0 is valid.** A quantity of zero is falsy and gets treated as "missing". Use `is None` for the real missing case.
- **`x or default` with legitimate falsy values.** A discount of `0` becomes the default.
- **`is` on values.** `if state is "done":` may appear to work and then fails on some strings. Use `==`. Recent Python versions emit a `SyntaxWarning` for `is` against a literal.
- **`find()` in a condition.** `-1` is truthy. Use `in` or compare with `-1`.
- **`bool("False")`.** Non-empty strings are true. Parse flags explicitly.
- **Odoo `False` versus `None`.** A `Char` field that is empty is `False`, and `.strip()` on it raises `AttributeError: 'bool' object has no attribute 'strip'`.
- **Mixing `str` and `bytes`.** Raises `TypeError`. Decode at the boundary.
- **Shadowing built-ins.** Assigning `list = [...]` or `sum = 0` makes later `list(...)` calls fail with `TypeError: 'list' object is not callable`.
- **Numeric strings from forms and imports.** `"10" < "9"` is `True` because strings compare character by character. Convert to numbers before comparing.

## Try it

1. Predict, then verify in the REPL: `7 // -2`, `-7 % 3`, `round(3.5)`, `round(4.5)`, `0.1 * 3 == 0.3`.
2. Write a function `format_isbn(raw)` that removes spaces and hyphens from a string, checks that the result is exactly 13 digits, and returns it grouped as `978-0-306-40615-7` style (3-1-3-5-1 digit groups), or returns `None` when invalid.
3. Write `to_bool(text)` that returns `True` for `"1"`, `"true"`, `"yes"` (case-insensitive, whitespace ignored), `False` for `"0"`, `"false"`, `"no"`, and `None` for anything else.
4. Explain why `total = 0; for p in prices: total += p` can produce `0.30000000000000004` for `prices = [0.1, 0.2]`, and show the integer-cents version that does not.
5. Format the number `1234567.5` as `1,234,567.50`, as `1.234.567,50` (continental European style), and as a percentage when the number is `0.0725`.

<details>
<summary>Solution</summary>

1.

```pycon
>>> 7 // -2, -7 % 3, round(3.5), round(4.5), 0.1 * 3 == 0.3
(-4, 2, 4, 4, False)
```

`7 // -2` floors `-3.5` to `-4`. `-7 % 3` is `2` because the remainder takes the sign of the divisor. Round-half-to-even gives `4` for both `3.5` and `4.5`. `0.1 * 3` is `0.30000000000000004`.

2.

```pycon
>>> def format_isbn(raw):
...     digits = raw.replace(" ", "").replace("-", "")
...     if len(digits) != 13 or not digits.isdigit():
...         return None
...     groups = (digits[:3], digits[3:4], digits[4:7], digits[7:12], digits[12:])
...     return "-".join(groups)
...
>>> format_isbn("978 0 306 40615 7")
'978-0-306-40615-7'
>>> format_isbn("123") is None
True
```

3.

```pycon
>>> def to_bool(text):
...     value = text.strip().lower()
...     if value in ("1", "true", "yes"):
...         return True
...     if value in ("0", "false", "no"):
...         return False
...     return None
...
>>> to_bool(" Yes "), to_bool("0"), to_bool("maybe")
(True, False, None)
```

4. `0.1` and `0.2` are not exactly representable in binary, so each addition carries a tiny error and the result is the nearest float to the true sum, which is not the nearest float to `0.3`. With cents:

```pycon
>>> prices_cents = [10, 20]
>>> sum(prices_cents)
30
>>> f"{sum(prices_cents) / 100:.2f}"
'0.30'
```

5.

```pycon
>>> n = 1234567.5
>>> f"{n:,.2f}"
'1,234,567.50'
>>> f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
'1.234.567,50'
>>> f"{0.0725:.2%}"
'7.25%'
```

For real localisation do not swap characters by hand; use the language's formatting rules (Odoo provides locale-aware formatting helpers, and Python has the `locale` module).

</details>
