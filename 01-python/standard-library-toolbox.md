---
description: "datetime, re, json, csv, base64, logging, pathlib, itertools, functools."
---

# Standard library toolbox

Python ships with a large library of ready-made modules, and most integration work in Odoo is a matter of knowing which one to reach for: parse a CSV an accountant sent, decode a base64 attachment, serialise a payload to JSON, pull a reference out of a free-text string with a regular expression, walk a folder of files. Reimplementing these by hand is slower and buggier than using the standard module. This chapter is a working tour of the modules you will use most, with the idioms and the failure modes that matter in Odoo code. Dates and money get their own chapter: [Money, dates, and time zones](working-with-money-and-dates.md).

## Which module for which job

| Job | Module |
|---|---|
| Text patterns | `re` |
| Structured data exchange | `json`, `csv` |
| Binary-to-text encoding | `base64` |
| Hashing, signatures | `hashlib`, `hmac`, `secrets` |
| Files and paths | `pathlib`, `os`, `tempfile`, `shutil` |
| In-memory files | `io` |
| Records and counting | `collections`, `dataclasses` |
| Iteration tools | `itertools` |
| Function tools | `functools`, `operator` |
| Logging | `logging` |
| URLs | `urllib.parse` |
| Dates, time | `datetime`, `zoneinfo` |
| Numbers | `decimal`, `math`, `statistics` |

Check the standard library before installing a package. Check Odoo's own `odoo.tools` before writing a helper; it contains utilities for dates, rounding, files, and mail that already handle Odoo's conventions. Where this chapter names an Odoo helper, it is one that is certain to exist; for others it stays with plain Python.

## re: regular expressions

A regular expression describes a text pattern. Use it when `split`, `startswith`, and `in` are not enough.

```pycon
>>> import re
>>> text = "Loans LIB-2024-0042 and LIB-2025-0007 were returned."
>>> re.findall(r"LIB-\d{4}-\d{4}", text)
['LIB-2024-0042', 'LIB-2025-0007']
>>> m = re.search(r"LIB-(\d{4})-(\d{4})", text)
>>> m.group(0), m.group(1), m.group(2)
('LIB-2024-0042', '2024', '0042')
>>> m.span()
(6, 19)
>>> re.sub(r"\s+", " ", "too    many \n spaces")
'too many spaces'
>>> re.split(r"[;,]\s*", "a, b;c,d")
['a', 'b', 'c', 'd']
```

Always write patterns as **raw strings** (`r"..."`), so backslashes reach the regex engine instead of being consumed by Python's string escapes (see [Values and types](values-and-types.md)).

The syntax you need most:

| Pattern | Matches |
|---|---|
| `.` | any character except newline |
| `\d`, `\w`, `\s` | digit, word character, whitespace |
| `\D`, `\W`, `\S` | the opposites |
| `[abc]`, `[a-z0-9]`, `[^abc]` | one of the set, a range, not in the set |
| `*`, `+`, `?` | zero or more, one or more, zero or one |
| `{n}`, `{n,m}` | exactly `n`, between `n` and `m` |
| `^`, `$` | start and end of the string (or line with `re.MULTILINE`) |
| `(...)` | capture group |
| `(?P<name>...)` | named group |
| `(?:...)` | group without capturing |
| `a\|b` | alternatives |
| `\b` | word boundary |

### Named groups and compiled patterns

Compile a pattern you use repeatedly, and name groups instead of counting them:

```pycon
>>> LOAN_REF = re.compile(r"LIB-(?P<year>\d{4})-(?P<seq>\d{4})")
>>> m = LOAN_REF.fullmatch("LIB-2024-0042")
>>> m.groupdict()
{'year': '2024', 'seq': '0042'}
>>> LOAN_REF.fullmatch("LIB-2024-0042 extra") is None
True
```

`fullmatch` requires the whole string to match. `match` anchors at the start only. `search` finds the pattern anywhere. Choosing among them wrongly is the most common regex bug: `re.match(r"\d+", "abc123")` is `None`, while `re.search` finds `123`.

`re.compile` at module level means the pattern is built once at import. Python caches recently used patterns anyway, so the gain is small, but a named constant documents intent.

### Flags and greediness

```pycon
>>> re.findall(r"^book", "Book one\nbook two", flags=re.IGNORECASE | re.MULTILINE)
['Book', 'book']
>>> re.findall(r"<.+>", "<a><b>")
['<a><b>']
>>> re.findall(r"<.+?>", "<a><b>")
['<a>', '<b>']
```

Quantifiers are **greedy**: they match as much as possible. Adding `?` makes them lazy. The second example matches the whole string because `.+` swallowed everything up to the last `>`.

{% hint style="warning" %}
Regular expressions are the wrong tool for HTML, XML, and JSON. Use a real parser (`lxml`, `json`). They are also easy to write with catastrophic backtracking: a pattern like `(a+)+$` against a long string of `a` followed by `b` can run for minutes. Never run a regex you did not write against untrusted input without checking its structure.
{% endhint %}

## json

JSON maps onto Python containers: objects become dicts, arrays become lists, strings stay strings, numbers become int or float, `true`/`false` become `True`/`False`, `null` becomes `None`.

```pycon
>>> import json
>>> payload = {"ref": "SO1", "lines": [{"sku": "A", "qty": 2}], "paid": False, "note": None}
>>> text = json.dumps(payload)
>>> text
'{"ref": "SO1", "lines": [{"sku": "A", "qty": 2}], "paid": false, "note": null}'
>>> json.loads(text) == payload
True
>>> print(json.dumps({"b": [1, 2], "a": None}, indent=2, sort_keys=True))
{
  "a": null,
  "b": [
    1,
    2
  ]
}
```

`dumps` and `loads` work on strings, `dump` and `load` on file objects. Useful options: `indent=2` for readable output, `sort_keys=True` for stable output (useful in tests and diffs), `ensure_ascii=False` to keep non-ASCII characters unescaped, `separators=(",", ":")` for compact output.

JSON has no date, decimal, or set type. Passing one raises `TypeError`:

```pycon
>>> from datetime import date
>>> from decimal import Decimal
>>> json.dumps({"due": date(2025, 3, 1)})
Traceback (most recent call last):
    ...
TypeError: Object of type date is not JSON serializable
```

Convert explicitly, or give `dumps` a `default` function:

```pycon
>>> def encode(obj):
...     if isinstance(obj, (date,)):
...         return obj.isoformat()
...     if isinstance(obj, Decimal):
...         return str(obj)
...     raise TypeError(f"cannot encode {type(obj).__name__}")
...
>>> json.dumps({"due": date(2025, 3, 1), "total": Decimal("10.50")}, default=encode)
'{"due": "2025-03-01", "total": "10.50"}'
```

Money is written as a string here to avoid float rounding on the receiving side. Agree on the convention with whoever consumes the data.

Other facts that cause bugs: tuples come back as lists, dict keys always become strings (`{1: "a"}` returns as `{"1": "a"}`), and `loads` raises `json.JSONDecodeError` (a `ValueError` subclass) on invalid input:

```pycon
>>> json.loads(json.dumps({1: "a"}))
{'1': 'a'}
>>> try:
...     json.loads("{bad json}")
... except json.JSONDecodeError as exc:
...     print("invalid:", exc.msg)
invalid: Expecting property name enclosed in double quotes
```

In Odoo, JSON appears in controllers that return JSON, in webhook payloads, in fields that store structured data as text, and in the HTTP calls you make to other systems. Always wrap `loads` of external data in a `try/except` (see [Errors and exceptions](errors-and-exceptions.md)), and never trust the structure: use `get` with defaults.

## csv

`csv` reads and writes comma-separated (and similar) files, handling quoting for you. Never split lines on commas by hand: a field such as `"Smith, John"` contains a comma.

```pycon
>>> import csv, io
>>> raw = 'title,pages,note\nDune,612,"Epic, long"\nEmma,474,\n'
>>> reader = csv.DictReader(io.StringIO(raw))
>>> rows = list(reader)
>>> rows[0]
{'title': 'Dune', 'pages': '612', 'note': 'Epic, long'}
>>> rows[1]["note"]
''
>>> reader.fieldnames
['title', 'pages', 'note']
```

Every value from a CSV is a **string**. Convert explicitly: `int(row["pages"])`. Empty cells are empty strings, not `None`.

Writing:

```pycon
>>> out = io.StringIO()
>>> writer = csv.DictWriter(out, fieldnames=["title", "pages", "note"], lineterminator="\n")
>>> writer.writeheader()
17
>>> writer.writerow({"title": "Dune", "pages": 612, "note": "Epic, long"})
22
>>> writer.writerow({"title": "Emma", "pages": 474, "note": ""})
10
>>> print(out.getvalue(), end="")
title,pages,note
Dune,612,"Epic, long"
Emma,474,
```

Hints for real files:

- Open files with `newline=""` and an explicit encoding: `open(path, newline="", encoding="utf-8")`. Without `newline=""` embedded newlines in quoted fields and Windows line endings misbehave.
- Spreadsheet programs often write **semicolon**-separated files in regions that use comma as decimal separator, and may prefix UTF-8 files with a byte-order mark. Open those with `encoding="utf-8-sig"` and `delimiter=";"`.
- `csv.Sniffer` can guess the dialect, but an explicit delimiter is more reliable.

```pycon
>>> raw = "title;pages\nDune;612\n"
>>> list(csv.DictReader(io.StringIO(raw), delimiter=";"))
[{'title': 'Dune', 'pages': '612'}]
```

In Odoo you will parse uploaded files from a `Binary` field. The content arrives as base64, so decode it first and wrap it in `io.StringIO` (see the `base64` and `io` sections). For very large files, iterate the reader instead of building a list, so that memory use stays flat (see [Comprehensions and generators](comprehensions-and-generators.md)).

## io: files in memory

`io.StringIO` and `io.BytesIO` behave like files but live in memory. They let you use file-based APIs (`csv`, `json.dump`, image libraries, spreadsheet writers) without touching the disk:

```pycon
>>> buf = io.StringIO()
>>> buf.write("hello\n")
6
>>> buf.write("world\n")
6
>>> buf.getvalue()
'hello\nworld\n'
>>> buf.seek(0)
0
>>> buf.readline()
'hello\n'
>>> data = io.BytesIO(b"\x00\x01\x02")
>>> data.read(2)
b'\x00\x01'
```

After writing to a buffer, call `seek(0)` before reading from it, or the read position is at the end and returns nothing. Report generators in Odoo, for instance, write an Excel or PDF file into a `BytesIO` and then return its bytes for an attachment or an HTTP response.

## base64

`base64` converts bytes to ASCII text and back. It exists because some channels (JSON, XML, email, database text columns) cannot carry raw bytes:

```pycon
>>> import base64
>>> raw = "café".encode("utf-8")
>>> encoded = base64.b64encode(raw)
>>> encoded
b'Y2Fmw6k='
>>> base64.b64decode(encoded).decode("utf-8")
'café'
>>> encoded.decode("ascii")        # as a str, ready for JSON
'Y2Fmw6k='
```

Both functions take and return **bytes**. Convert to `str` with `.decode("ascii")` when you need text. Base64 inflates data by about a third.

Odoo uses this heavily. A `Binary` field exposes its content as base64, and attachments store file content the same way in their `datas` value. The round trip when reading a file from an uploaded field looks like:

```python
raw_bytes = base64.b64decode(self.upload_file)       # bytes of the original file
text = raw_bytes.decode("utf-8")
rows = csv.DictReader(io.StringIO(text))
```

and when producing a download:

```python
buffer = io.BytesIO()
# ... write a spreadsheet or PDF into buffer ...
self.write({"result_file": base64.b64encode(buffer.getvalue())})
```

Mistakes here are common: decoding something that was never encoded (`binascii.Error: Incorrect padding`), or encoding twice so that the user downloads text instead of the file. When a downloaded file is garbage, check the number of encode and decode steps. In recent versions the field value may already be a `bytes` object, and in other cases a `str`; `base64.b64decode` accepts either, and you should not assume more.

URL-safe variants (`urlsafe_b64encode`) use `-` and `_` instead of `+` and `/`, and appear in tokens.

## hashlib, hmac, secrets

```pycon
>>> import hashlib, hmac
>>> hashlib.sha256(b"hello").hexdigest()
'2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
>>> sig = hmac.new(b"shared-secret", b"payload", hashlib.sha256).hexdigest()
>>> len(sig)
64
>>> hmac.compare_digest(sig, sig)
True
```

- Use `hashlib` for checksums and fingerprints (is this the same file?). Do not use it to store passwords; Odoo handles passwords itself.
- Use `hmac` to sign and verify messages with a shared secret, as webhook endpoints do. Compare signatures with `hmac.compare_digest`, never `==`, to avoid timing attacks.
- Use `secrets` (not `random`) for tokens and anything security-relevant: `secrets.token_urlsafe(32)`. `random` is predictable by design.

## pathlib and the file system

`pathlib.Path` represents file paths as objects and replaces most of `os.path`:

```pycon
>>> from pathlib import Path
>>> p = Path("exports") / "2025" / "loans.csv"
>>> p.name, p.stem, p.suffix, p.parent
('loans.csv', 'loans', '.csv', PosixPath('exports/2025'))
>>> p.with_suffix(".json").as_posix()
'exports/2025/loans.json'
```

(On Windows the parent displays as `WindowsPath('exports/2025')`.) The `/` operator joins parts with the right separator for the platform, so never build paths with string concatenation or hard-coded backslashes.

Reading, writing, and listing, in a temporary folder so the example cleans up after itself:

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as tmp:
...     folder = Path(tmp)
...     (folder / "a.txt").write_text("one\n", encoding="utf-8")
...     (folder / "b.txt").write_text("two\n", encoding="utf-8")
...     (folder / "data").mkdir()
...     (folder / "data" / "c.csv").write_text("x,y\n", encoding="utf-8")
...     print(sorted(p.name for p in folder.glob("*.txt")))
...     print(sorted(str(p.relative_to(folder).as_posix()) for p in folder.rglob("*") if p.is_file()))
...     print((folder / "a.txt").read_text(encoding="utf-8").strip())
...     print((folder / "missing.txt").exists())
4
4
4
['a.txt', 'b.txt']
['a.txt', 'b.txt', 'data/c.csv']
one
False
```

The three 4s are the return values of `write_text` (characters written) echoed by the REPL for the three file writes. `glob("*.txt")` matches in one folder, `rglob("*")` recurses.

Important details:

- Always pass `encoding="utf-8"` to `read_text`, `write_text`, and `open`.
- `Path.exists()` followed by an action has a race: the file can change in between. For files, prefer to just try and catch `FileNotFoundError`.
- `tempfile` creates temporary files and folders that are cleaned up, and avoids collisions between concurrent requests. Never write temporary files to a fixed name like `/tmp/export.csv` in a server that handles several requests at once.
- `shutil` copies, moves, and deletes trees: `shutil.copy`, `shutil.move`, `shutil.rmtree`. `rmtree` deletes recursively and without confirmation; double-check the path.
- In a long-running Odoo process, do not rely on the current working directory: it is whatever the server was started from. Build paths from a known base.
- Never build a path from user input without validating it. A file name of `../../etc/passwd` escapes the intended folder. Take only `Path(name).name`, and check that the resolved path stays inside the base folder.

## itertools

`itertools` provides building blocks for iteration that work lazily:

```pycon
>>> from itertools import chain, islice, groupby, accumulate, product, combinations, zip_longest, takewhile, count
>>> list(chain([1, 2], [3, 4]))
[1, 2, 3, 4]
>>> list(chain.from_iterable([[1, 2], [3], []]))
[1, 2, 3]
>>> list(islice(count(10), 3))
[10, 11, 12]
>>> list(accumulate([1, 2, 3, 4]))
[1, 3, 6, 10]
>>> list(product("ab", [1, 2]))
[('a', 1), ('a', 2), ('b', 1), ('b', 2)]
>>> list(combinations([1, 2, 3], 2))
[(1, 2), (1, 3), (2, 3)]
>>> list(zip_longest([1, 2, 3], ["a"], fillvalue="-"))
[(1, 'a'), (2, '-'), (3, '-')]
>>> list(takewhile(lambda n: n < 3, [1, 2, 3, 1]))
[1, 2]
```

`chain.from_iterable` flattens one level of nesting; it is the usual way to flatten the lines of several orders. `accumulate` gives running totals. `groupby` needs input sorted by the key, as covered in [Comprehensions and generators](comprehensions-and-generators.md).

A batching helper (`itertools.batched` exists in Python 3.12+; for older versions write your own):

```pycon
>>> from itertools import islice
>>> def batched(iterable, n):
...     it = iter(iterable)
...     while batch := list(islice(it, n)):
...         yield batch
...
>>> list(batched(range(7), 3))
[[0, 1, 2], [3, 4, 5], [6]]
```

Unlike the slicing version in the generators chapter, this works on any iterable, including a generator or a database cursor.

## functools and operator

Beyond `wraps` and `lru_cache` from [Decorators](decorators.md):

```pycon
>>> from functools import reduce, partial, cmp_to_key
>>> reduce(lambda acc, n: acc * n, [1, 2, 3, 4], 1)
24
>>> from operator import itemgetter, attrgetter, add
>>> rows = [{"name": "b", "n": 2}, {"name": "a", "n": 2}, {"name": "c", "n": 1}]
>>> sorted(rows, key=itemgetter("n", "name"))
[{'name': 'c', 'n': 1}, {'name': 'a', 'n': 2}, {'name': 'b', 'n': 2}]
>>> reduce(add, [[1], [2, 3]], [])
[1, 2, 3]
```

`itemgetter("n", "name")` builds the key function `lambda r: (r["n"], r["name"])`. `attrgetter("partner_id.name")` does the same for attributes and supports dotted paths, which is the plain-Python analogue of walking relations on records. `reduce` folds a sequence into one value. Use it rarely: `sum`, `max`, `"".join`, and `any` cover most needs, and an explicit loop is often clearer.

`functools.cached_property` computes a value once per instance on first access, which suits helper objects (not Odoo models, whose cache is managed by the ORM).

## logging, briefly

Covered with exceptions in [Errors and exceptions](errors-and-exceptions.md). The rules to keep: `_logger = logging.getLogger(__name__)` at the top of each module, `%s` arguments instead of f-strings, `_logger.exception` inside `except` blocks, and levels used meaningfully. In Odoo the server configures handlers and formatting, so your code never calls `basicConfig`. In standalone scripts, call `logging.basicConfig(level=logging.INFO)` once, at the entry point.

## urllib.parse

Build and take apart URLs without string slicing:

```pycon
>>> from urllib.parse import urlparse, urlencode, quote, parse_qs, urljoin
>>> u = urlparse("https://example.org/api/v1/loans?state=open&page=2")
>>> u.scheme, u.netloc, u.path
('https', 'example.org', '/api/v1/loans')
>>> parse_qs(u.query)
{'state': ['open'], 'page': ['2']}
>>> urlencode({"q": "dune & co", "page": 2})
'q=dune+%26+co&page=2'
>>> quote("a b/c")
'a%20b/c'
>>> urljoin("https://example.org/api/", "v1/loans")
'https://example.org/api/v1/loans'
```

Always encode query parameters with `urlencode` (or pass `params=` to your HTTP library). Concatenating user input into a URL breaks on `&`, `#`, spaces, and non-ASCII text, and opens injection problems.

## A compact example: import a CSV of loans

Putting several modules together, a function that parses a CSV, validates each row with a regular expression, groups by member, and reports problems with logging. It runs as shown:

```pycon
>>> import csv, io, logging, re, sys
>>> from collections import defaultdict
>>> logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(levelname)s %(message)s", force=True)
>>> _logger = logging.getLogger("library.import")
>>> REF = re.compile(r"LIB-\d{4}-\d{4}")
>>> def import_loans(text):
...     by_member = defaultdict(list)
...     errors = []
...     for number, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
...         ref = (row.get("ref") or "").strip().upper()
...         if not REF.fullmatch(ref):
...             errors.append(number)
...             _logger.warning("row %d: bad reference %r", number, row.get("ref"))
...             continue
...         by_member[row["member"].strip()].append(ref)
...     return dict(by_member), errors
...
>>> data = "ref,member\nlib-2025-0001,ada\nLIB-2025-0002, bob\nBAD,cy\nLIB-2025-0003,ada\n"
>>> import_loans(data)
WARNING row 4: bad reference 'BAD'
({'ada': ['LIB-2025-0001', 'LIB-2025-0003'], 'bob': ['LIB-2025-0002']}, [4])
```

Row numbers start at 2 because line 1 is the header. The same function body, with `base64.b64decode(...)` in front of it, is how an Odoo wizard that imports an uploaded CSV starts.

## Pitfalls

- **Non-raw regex strings.** `"\d+"` works by accident, `"\b"` becomes a backspace character. Always use `r"..."`.
- **`match` versus `search` versus `fullmatch`.** `match` anchors only at the start. Validating a whole value needs `fullmatch`.
- **Greedy quantifiers.** `.+` over-matches. Use `.+?`, or a negated class like `[^>]+`.
- **Regex against markup.** Use a parser for HTML, XML, and JSON.
- **JSON types.** Dates, decimals, and sets are not serialisable. Tuples become lists, integer keys become strings.
- **Trusting decoded JSON.** Missing keys and wrong types are normal in external data. Use `get` and validate.
- **CSV by hand.** `line.split(",")` breaks on quoted commas and newlines. Use `csv`.
- **CSV values are strings.** Convert and validate. Empty cells are `""`, not `None`.
- **Wrong delimiter or encoding.** Semicolon-separated, BOM-prefixed files from spreadsheets need `delimiter=";"` and `encoding="utf-8-sig"`.
- **Reading a buffer you did not rewind.** After writing to `StringIO` or `BytesIO`, call `seek(0)` before reading.
- **Base64 off by one.** Decoding data that was not encoded gives `Incorrect padding`; encoding twice gives a corrupted download. Count the steps.
- **`bytes` versus `str`.** `b64encode` returns bytes. `json.dumps` of bytes raises `TypeError`. Decode to ASCII first.
- **Comparing signatures with `==`.** Use `hmac.compare_digest`.
- **`random` for tokens.** Use `secrets`.
- **Hard-coded path separators and fixed temp names.** Use `pathlib` and `tempfile`.
- **Relying on the working directory.** In a server process it is not what you expect.
- **Path traversal.** Never join user-supplied file names onto a base folder without taking `.name` and checking the result.
- **Missing `encoding=`.** Behaviour then depends on the machine's locale.

## Try it

1. Write `extract_refs(text)` that returns all references of the form `LIB-YYYY-NNNN` in a string, uppercase and without duplicates, preserving first-seen order.
2. Parse the CSV text `"member,amount\nada,10.50\nbob,3\nada,2.25\n"`, and return a dict from member to total as `Decimal`. (Import `Decimal` from `decimal`.)
3. Serialise `{"due": date(2025, 3, 1), "total": Decimal("10.50"), "tags": {"a", "b"}}` to JSON using a `default` function, producing stable output for the set.
4. Round trip a UTF-8 string containing `é` through base64 and back, and show the byte lengths before and after encoding.
5. Using `pathlib` and `tempfile`, create three `.csv` files and one `.txt` file in a temporary folder, and list only the CSV files sorted by name.

<details>
<summary>Solution</summary>

1.

```pycon
>>> import re
>>> def extract_refs(text):
...     found = re.findall(r"lib-\d{4}-\d{4}", text, flags=re.IGNORECASE)
...     return list(dict.fromkeys(r.upper() for r in found))
...
>>> extract_refs("lib-2025-0001, LIB-2025-0002 and lib-2025-0001 again")
['LIB-2025-0001', 'LIB-2025-0002']
```

2.

```pycon
>>> import csv, io
>>> from collections import defaultdict
>>> from decimal import Decimal
>>> raw = "member,amount\nada,10.50\nbob,3\nada,2.25\n"
>>> totals = defaultdict(Decimal)
>>> for row in csv.DictReader(io.StringIO(raw)):
...     totals[row["member"]] += Decimal(row["amount"])
...
>>> dict(totals)
{'ada': Decimal('12.75'), 'bob': Decimal('3')}
```

3.

```pycon
>>> import json
>>> from datetime import date
>>> from decimal import Decimal
>>> def encode(obj):
...     if isinstance(obj, date):
...         return obj.isoformat()
...     if isinstance(obj, Decimal):
...         return str(obj)
...     if isinstance(obj, (set, frozenset)):
...         return sorted(obj)
...     raise TypeError(type(obj).__name__)
...
>>> json.dumps({"due": date(2025, 3, 1), "total": Decimal("10.50"), "tags": {"a", "b"}}, default=encode, sort_keys=True)
'{"due": "2025-03-01", "tags": ["a", "b"], "total": "10.50"}'
```

4.

```pycon
>>> import base64
>>> raw = "café".encode("utf-8")
>>> enc = base64.b64encode(raw)
>>> len(raw), len(enc), base64.b64decode(enc).decode("utf-8")
(5, 8, 'café')
```

5.

```pycon
>>> import tempfile
>>> from pathlib import Path
>>> with tempfile.TemporaryDirectory() as tmp:
...     folder = Path(tmp)
...     for name in ("b.csv", "a.csv", "c.csv", "notes.txt"):
...         _ = (folder / name).write_text("x\n", encoding="utf-8")
...     print([p.name for p in sorted(folder.glob("*.csv"))])
['a.csv', 'b.csv', 'c.csv']
```

</details>
