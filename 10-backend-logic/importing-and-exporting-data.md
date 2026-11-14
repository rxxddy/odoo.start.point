---
description: The import engine, CSV and Excel, and large files.
---

# Importing and exporting data

Moving data in and out of Odoo is mostly the import engine, a single method that does name resolution, validation and create-or-update. Use it from code instead of writing your own loader, and learn its quirks once.

## The engine: `load()`

`Model.load(fields, data)` takes a list of column names and a matrix of string values and returns `{"ids": [...], "messages": [...]}`. It is what the web import screen calls (verified in `odoo/models.py`: "Attempts to load the data matrix, and returns a list of ids ... and a list of messages").

```python
fields_ = ["id", "title", "isbn", "author_id", "tag_ids"]
rows = [
    ["__import__.book_1", "Dune", "9780000000001", "Herbert", "Fiction,Classic"],
    ["__import__.book_2", "Emma", "9780000000002", "Austen", "Classic"],
]
result = self.env["library.book"].load(fields_, rows)
if result["messages"]:
    for m in result["messages"]:
        _logger.warning("row %s: %s", m.get("rows"), m["message"])
```

What it gives you over `create`:

* **External ids.** The `id` column is an XML id. If it exists, the record is updated; if not, created. This makes imports repeatable. Without `id` you always create.
* **Name resolution.** Many2one columns take a display name (`author_id`) or an external id (`author_id/id`), many2many take comma-separated names. Selection fields accept the label as well as the key.
* **Per-row messages.** Errors carry row numbers and field names instead of aborting on the first exception. Rows are processed inside savepoints, and if any row has an error with `ids` set to `False`, nothing is saved.
* **Onchange and defaults** are applied as for the UI.

Use `id` columns with your own module prefix, so reruns update instead of duplicating. Never invent ids that look like `base.` or another module's namespace.

## The pitfalls of name lookup

Name resolution uses `name_search`. A duplicate name makes the import fail with an ambiguity message, a missing one fails with "no matching record". For big imports use external ids for relations (`author_id/id`) and import in dependency order: authors, then books, then loans. Do not rely on a name being unique just because it is today.

## CSV and Excel

Python's `csv` module and `openpyxl` (shipped with Odoo, since it reads xlsx for the UI) cover input:

```python
import base64, csv, io

def _rows_from_csv(self, content_b64):
    text = base64.b64decode(content_b64).decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header = next(reader)
    return header, list(reader)
```

Details that bite:

* **Encoding.** Excel writes CSV in a legacy code page unless told otherwise. `utf-8-sig` removes a BOM; fall back or ask for UTF-8 explicitly.
* **Delimiter and decimals.** Locales that use a comma decimal use a semicolon delimiter. Detect with `csv.Sniffer` or make it a wizard option; do not guess silently.
* **Leading zeros and long numbers.** A spreadsheet turns `00123` into `123` and `9780000000001` into scientific notation. Read cells as text or tell users to format the column as text.
* **Dates.** Pass ISO `YYYY-MM-DD`. Ambiguous `03/04/2025` is parsed by the user's language settings in the UI import, but your code must pick a format.
* **Excel files.** `openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)` streams rows and reads cached formula values. Convert every cell to string, empty cells to `""`, before `load()`.

## Batches and progress

`load()` on 100,000 rows in one call holds one transaction and a lot of memory. Split:

```python
for start in range(0, len(rows), 500):
    result = Model.load(header, rows[start:start + 500])
    if not result["ids"]:
        errors.extend(result["messages"])
    self.env.cr.commit()   # only in a cron or script, not in a user request
```

For large imports, upload the file as an attachment, create a job, and let a cron process chunks (see Queues and background work). The user gets a status record with error counts and downloadable rejects.


Mail tracking dominates import time on mail-thread models. Import with `with_context(tracking_disable=True, mail_notrack=True, mail_create_nolog=True)` when notifications are not wanted.

## Exporting

For code, `export_data` mirrors the UI export:

```python
data = books.export_data(["id", "title", "author_id/name"])["datas"]
```

The UI export (`/web/export`) uses the same mechanism. Field paths with a slash traverse relations, `id` gives the external id (created on demand for records without one). For simple dumps, `read` or `search_read` plus `csv.writer` is clearer and faster:

```python
out = io.StringIO()
w = csv.writer(out, delimiter=",", quoting=csv.QUOTE_MINIMAL)
w.writerow(["title", "isbn"])
for b in books.read(["title", "isbn"]):
    w.writerow([b["title"], b["isbn"]])
```

Prefer streaming and chunks for large sets, and mind CSV injection: a cell starting with `=`, `+`, `-` or `@` runs as a formula when opened in a spreadsheet. Prefix such text values with an apostrophe or a space when the data comes from outside.

## Idempotent imports

Design so a rerun is safe: stable external ids, `load()` for upserts, a natural-key uniqueness constraint behind it. When data has no stable key, create one from the source (file name plus row hash) and store it, rather than matching on a name.

## Pitfalls

* Importing without external ids, then importing again and doubling everything.
* Matching by name where names repeat.
* Committing inside `load()` callers reachable from the UI.
* Ignoring `messages` and trusting `ids`: a partial failure leaves `ids` False and the data unsaved.
* Mail tracking left on: each row sends notifications.
* Spreadsheets silently altering codes, dates and long numbers.
* Importing as superuser for convenience, bypassing access rules the real user should hit.

## Versions

{% hint style="info" %}
`load(fields, data)` has the same signature in 16, 17 and 18 (verified in 18). In 18 the helpers live in `odoo/models.py` (`_load_records`, `_load_records_create`, `_load_records_write`). Context keys and message structure have changed between releases, so inspect `result["messages"]` on your build rather than parsing text.
{% endhint %}

## Try it

Dry-run an import in a test database and read what the engine says before committing:

```python
res = env["library.book"].load(["id", "title"], [["__import__.t1", "Test"]])
print(res)
env.cr.rollback()
```
