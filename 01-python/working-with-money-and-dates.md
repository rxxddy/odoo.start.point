---
description: "Decimal, rounding, UTC storage, and local-time conversion."
---

# Money, dates, and time zones

Two kinds of data cause more production incidents in business software than any others: amounts of money and moments in time. A total off by one cent fails an audit. An order dated tomorrow because someone formatted the time in the wrong zone starts a support thread. Both problems have the same root: the obvious Python type (`float` for money, a bare `datetime` for time) looks fine in testing and is wrong at the edges. This chapter shows the correct types, the rounding rules, and the conversion discipline that Odoo's own data model expects: money is rounded by the currency's rules, datetimes are stored in UTC, and conversion to a user's local time happens at the boundary, and only there.

## Why not float for money

```pycon
>>> 0.1 + 0.2
0.30000000000000004
>>> (0.1 + 0.2) + 0.3 == 0.6
False
>>> 1.1 * 3
3.3000000000000003
>>> round(2.675, 2)
2.67
```

Binary floating point cannot represent most decimal fractions exactly (see [Values and types](values-and-types.md)). For one operation the error is invisible. Across thousands of lines, with tax computed per line and then summed, the error becomes a visible cent, and "the invoice total differs from the sum of the lines" is the classic symptom.

## Decimal

`decimal.Decimal` stores numbers in base 10, so `0.1` is exactly one tenth:

```pycon
>>> from decimal import Decimal
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')
>>> sum([Decimal("0.1")] * 10)
Decimal('1.0')
>>> Decimal("1.10") * 3
Decimal('3.30')
>>> Decimal("10") / Decimal("4")
Decimal('2.5')
```

**Always create a `Decimal` from a string or an integer, never from a float.** A float has already lost the exact value before `Decimal` sees it:

```pycon
>>> str(Decimal(0.1))[:22]
'0.10000000000000000555'
>>> Decimal("0.1")
Decimal('0.1')
>>> Decimal(5), Decimal("5.00") == Decimal("5")
(Decimal('5'), True)
```

`Decimal("5.00")` and `Decimal("5")` are equal in value but keep their own number of decimal places, which shows when you print them. Mixing `Decimal` and `float` in arithmetic raises `TypeError`, which protects you from silently reintroducing the error:

```pycon
>>> Decimal("1.5") + 0.5
Traceback (most recent call last):
    ...
TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'
>>> Decimal("1.5") + 1
Decimal('2.5')
```

### Precision and the context

Decimal arithmetic uses a context with 28 significant digits by default, which is plenty for money. Division is where a repeating result is rounded to that precision:

```pycon
>>> Decimal(1) / Decimal(3)
Decimal('0.3333333333333333333333333333')
```

For money you do not want 28 digits. You want to round to a set number of decimal places, deliberately, using `quantize`.

### quantize: rounding to cents

`quantize` rounds a number to the exponent of its argument and takes a rounding mode:

```pycon
>>> from decimal import ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_DOWN, ROUND_UP
>>> CENT = Decimal("0.01")
>>> Decimal("2.675").quantize(CENT, rounding=ROUND_HALF_UP)
Decimal('2.68')
>>> Decimal("2.675").quantize(CENT, rounding=ROUND_HALF_EVEN)
Decimal('2.68')
>>> Decimal("2.665").quantize(CENT, rounding=ROUND_HALF_EVEN)
Decimal('2.66')
>>> Decimal("2.665").quantize(CENT, rounding=ROUND_HALF_UP)
Decimal('2.67')
>>> Decimal("-2.675").quantize(CENT, rounding=ROUND_HALF_UP)
Decimal('-2.68')
>>> Decimal("2.671").quantize(CENT, rounding=ROUND_DOWN), Decimal("2.671").quantize(CENT, rounding=ROUND_UP)
(Decimal('2.67'), Decimal('2.68'))
```

The modes you need:

| Mode | Rule |
|---|---|
| `ROUND_HALF_UP` | exact halves round away from zero (the "school" rule, usual for invoices) |
| `ROUND_HALF_EVEN` | exact halves round to the even neighbour ("banker's rounding", the default of `Decimal` and of Python's `round()`) |
| `ROUND_DOWN` | toward zero (truncate) |
| `ROUND_UP` | away from zero |
| `ROUND_FLOOR`, `ROUND_CEILING` | toward negative or positive infinity |

Python's built-in `round()` on a `Decimal` uses half-even, and on an `int` result it differs from what accountants expect:

```pycon
>>> round(Decimal("2.5")), round(Decimal("3.5"))
(2, 4)
>>> round(2.5), round(3.5)
(2, 4)
```

Which mode is right is a business decision, usually set by law or by the accounting policy: invoices commonly use half-up. Odoo's currency rounding is half-up by default. Use one explicit helper in your code, so the rule exists in one place:

```pycon
>>> def money(value, places="0.01"):
...     return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)
...
>>> money("2.675"), money(Decimal("10")), money(3)
(Decimal('2.68'), Decimal('10.00'), Decimal('3.00'))
```

### Rounding per line or per total

Rounding at different points gives different totals. Three lines at 3.33 with 20% tax:

```pycon
>>> prices = [Decimal("3.33")] * 3
>>> rate = Decimal("0.20")
>>> per_line = sum(money(p * rate) for p in prices)
>>> on_total = money(sum(prices) * rate)
>>> per_line, on_total
(Decimal('2.01'), Decimal('2.00'))
```

Neither is wrong; they are different policies, and the choice must match your jurisdiction and what your accounting software does. Odoo lets a company choose between rounding tax per line and rounding on the total (a company-level setting for how taxes are rounded globally). The Python lesson is to decide on the policy, implement it in one place, and test it with figures like these.

### Allocating a remainder

Splitting an amount into parts that must sum to the total (for instance, an instalment plan) cannot be done by dividing and rounding each part. Allocate the rounding remainder explicitly:

```pycon
>>> def split_amount(total, parts):
...     total = Decimal(total)
...     base = (total / parts).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
...     amounts = [base] * parts
...     remainder = total - base * parts
...     index = 0
...     while remainder > 0:
...         amounts[index] += Decimal("0.01")
...         remainder -= Decimal("0.01")
...         index += 1
...     return amounts
...
>>> split_amount("100.00", 3)
[Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]
>>> sum(split_amount("100.00", 3))
Decimal('100.00')
>>> sum([Decimal("33.33")] * 3)
Decimal('99.99')
```

The naive version loses a cent. Odoo does equivalent work when it distributes payment terms or splits invoice lines, and when you generate such splits yourself, the sum-equals-total test is the test to write.

### Comparing and formatting

```pycon
>>> Decimal("2.50") == Decimal("2.5"), Decimal("2.50") > Decimal("2.4")
(True, True)
>>> f"{Decimal('1234567.891'):,.2f}"
'1,234,567.89'
>>> str(Decimal("10.50")), float(Decimal("10.50"))
('10.50', 10.5)
```

Convert with `str` when sending to other systems (JSON, CSV), and parse with `Decimal(text)`. Convert to `float` only at the boundary where a float is required, and never convert back and forth in the middle of a calculation.

## Money in Odoo

Odoo does not use `Decimal` in its model layer. A `Monetary` field is a float stored with a currency, and the correctness of the amount depends on rounding with the **currency's rounding rules** and comparing with a precision, not with `==`. The pieces to know:

- **`Float` fields** accept a `digits` precision and the ORM rounds to it on write.
- **`Monetary` fields** reference a currency field (`currency_field`, defaulting to `currency_id`), and the client displays and rounds using that currency.
- **Rounding helpers** live in `odoo.tools`: `float_round`, `float_compare`, `float_is_zero`. They take `precision_digits` or `precision_rounding`.
- **Currency methods:** the currency record offers `round(amount)`, `compare_amounts(a, b)`, `is_zero(amount)`, and conversion helpers. They apply the currency's own rounding (two decimals for many currencies, zero for some, three for others).

Usage, in Odoo code:

```python
from odoo.tools import float_compare, float_is_zero, float_round

rounded = float_round(12.3456, precision_digits=2)                 # 12.35
same = float_compare(0.1 + 0.2, 0.3, precision_digits=2) == 0      # True
nothing = float_is_zero(0.004, precision_digits=2)                 # True

currency = record.currency_id
total = currency.round(record.amount_untaxed * 1.2)
if currency.is_zero(record.amount_due):
    ...
```

`float_compare` returns `-1`, `0`, or `1`, like a comparison function, treating values equal when they round to the same number at the given precision. That is the correct way to ask "are these two amounts equal?" for float-typed values, replacing `==`.

To see what these functions do without Odoo, here is a plain-Python equivalent of the behaviour (written for understanding; use the Odoo functions in modules because they handle edge cases around binary representation that this simplified version does not):

```pycon
>>> def float_round_demo(value, precision_digits=2):
...     return float(Decimal(repr(value)).quantize(Decimal(1).scaleb(-precision_digits), rounding=ROUND_HALF_UP))
...
>>> float_round_demo(2.675), float_round_demo(12.3456), float_round_demo(0.125, 2)
(2.68, 12.35, 0.13)
>>> def float_compare_demo(a, b, precision_digits=2):
...     ra, rb = float_round_demo(a, precision_digits), float_round_demo(b, precision_digits)
...     return (ra > rb) - (ra < rb)
...
>>> float_compare_demo(0.1 + 0.2, 0.3), float_compare_demo(1.005, 1.0), float_compare_demo(1.2, 1.3)
(0, 1, -1)
```

Notice `round(2.675, 2)` gave `2.67` at the start of this chapter, and the helper gives `2.68`: the helper goes through the shortest decimal representation of the float (`repr`), which is what a person would write. That is the behaviour money code wants, and it is why a dedicated rounding helper exists rather than the built-in.

When you need exact arithmetic inside your own business logic (allocations, large totals), converting field values to `Decimal` through `str` or `repr`, computing, and rounding at the end is a sound approach, as long as you round with the currency before writing back.

### Rules of thumb

1. Round at defined points, using the currency (or the field precision), not ad hoc.
2. Compare floats with `float_compare` or `currency.compare_amounts`, never `==`.
3. Do not sum rounded floats and unrounded floats in the same expression without thinking about what the totals should be.
4. Keep conversions (`currency` to `currency`) in one step, using the framework's conversion with a rate date, not by multiplying by a rate you fetched yourself.
5. Test with amounts that expose the problem: 0.005, 2.675, 1.005, three-way splits of 100.

## Dates and times

### The three types

```pycon
>>> from datetime import date, datetime, time, timedelta, timezone
>>> d = date(2025, 3, 14)
>>> t = time(9, 30)
>>> dt = datetime(2025, 3, 14, 9, 30, 15)
>>> d, t, dt
(datetime.date(2025, 3, 14), datetime.time(9, 30), datetime.datetime(2025, 3, 14, 9, 30, 15))
>>> dt.date(), dt.time(), dt.year, dt.month, dt.day, dt.hour
(datetime.date(2025, 3, 14), datetime.time(9, 30, 15), 2025, 3, 14, 9)
>>> d.weekday(), d.isoweekday()        # Monday is 0 / Sunday is 7
(4, 5)
```

`date` is a calendar day, `time` a time of day, `datetime` both. Odoo has matching field types: `Date` holds a `date`, `Datetime` holds a `datetime`. Use `Date` when the business concept is a day (a due date, a birthday), and `Datetime` when it is a moment (a timestamp of an event). Storing a day as midnight in a `Datetime` invites time zone trouble: midnight UTC is yesterday evening in the Americas.

### Arithmetic with timedelta

```pycon
>>> d + timedelta(days=30)
datetime.date(2025, 4, 13)
>>> date(2025, 4, 1) - date(2025, 3, 1)
datetime.timedelta(days=31)
>>> (date(2025, 4, 1) - date(2025, 3, 1)).days
31
>>> dt + timedelta(hours=36)
datetime.datetime(2025, 3, 15, 21, 30, 15)
>>> td = timedelta(days=1, hours=3)
>>> td.total_seconds(), td.days, td.seconds
(97200.0, 1, 10800)
```

`timedelta` has no months or years, since they have no fixed length. `td.seconds` is only the seconds part (0 to 86399) that remains after the days; `total_seconds()` is the whole duration. Mixing them up is a common bug.

For calendar arithmetic use `dateutil.relativedelta`, which is bundled with Odoo's dependencies:

```pycon
>>> from dateutil.relativedelta import relativedelta
>>> date(2025, 1, 31) + relativedelta(months=1)
datetime.date(2025, 2, 28)
>>> date(2025, 3, 14) + relativedelta(months=-2, day=1)
datetime.date(2025, 1, 1)
>>> date(2025, 2, 10) + relativedelta(day=31)
datetime.date(2025, 2, 28)
>>> date(2025, 3, 14) + relativedelta(years=1, weekday=0)
datetime.date(2026, 3, 16)
```

`relativedelta(months=1)` on January 31 clamps to the last day of February. Singular arguments (`day=1`, `day=31`, `weekday=0`) set the value instead of adding; `day=31` clamps to the month's real last day, which is the usual way to get the end of a month. Month-based business rules (monthly billing, "30 days end of month" payment terms) should use `relativedelta` and be tested with the 28th to 31st.

### Parsing and formatting

```pycon
>>> d.isoformat(), dt.isoformat()
('2025-03-14', '2025-03-14T09:30:15')
>>> date.fromisoformat("2025-03-14"), datetime.fromisoformat("2025-03-14T09:30:15")
(datetime.date(2025, 3, 14), datetime.datetime(2025, 3, 14, 9, 30, 15))
>>> dt.strftime("%d/%m/%Y %H:%M")
'14/03/2025 09:30'
>>> datetime.strptime("14/03/2025 09:30", "%d/%m/%Y %H:%M")
datetime.datetime(2025, 3, 14, 9, 30)
>>> dt.strftime("%A %B")       # names depend on the locale
'Friday March'
```

The common format codes: `%Y` year, `%m` month, `%d` day, `%H` hour (24h), `%M` minute, `%S` second, `%A` weekday name, `%B` month name, `%z` UTC offset. `strptime` raises `ValueError` when the text does not match:

```pycon
>>> datetime.strptime("2025-13-01", "%Y-%m-%d")
Traceback (most recent call last):
    ...
ValueError: time data '2025-13-01' does not match format '%Y-%m-%d'
```

Prefer ISO 8601 (`YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SS`) for any data exchange, files, and logs. It is unambiguous and sorts correctly as text. Avoid `%d/%m` versus `%m/%d` ambiguity: `03/04/2025` is March 4th in one country and April 3rd in another.

Odoo accepts and returns date and datetime values as ISO-like strings in its server-side formats (`%Y-%m-%d` and `%Y-%m-%d %H:%M:%S`) in domains, XML-RPC and JSON. The `fields.Date` and `fields.Datetime` classes provide converters (`to_date`, `to_datetime`, `to_string`) between strings and Python objects, so use them instead of formatting by hand.

### Month and week helpers

```pycon
>>> import calendar
>>> calendar.monthrange(2025, 2)[1]        # number of days in the month
28
>>> calendar.isleap(2024)
True
>>> date(2025, 3, 14).isocalendar()[:2]    # ISO year, ISO week
(2025, 11)
>>> start_of_week = d - timedelta(days=d.weekday())
>>> start_of_week
datetime.date(2025, 3, 10)
```

Be careful with ISO weeks: December 30 can belong to week 1 of the next year, and January 1 can belong to week 52 or 53 of the previous one. Pair `isocalendar()[0]` with `[1]`, never `date.year` with the week number.

## Time zones

### The problem

A moment in time happens once, but its wall-clock reading differs around the world. "2025-03-14 09:30" means nothing without a zone. Python has two kinds of `datetime`:

- **Naive**: no zone information. `datetime(2025, 3, 14, 9, 30)`.
- **Aware**: carries a `tzinfo` and therefore denotes one exact moment.

```pycon
>>> naive = datetime(2025, 3, 14, 9, 30)
>>> naive.tzinfo is None
True
>>> aware = datetime(2025, 3, 14, 9, 30, tzinfo=timezone.utc)
>>> aware.isoformat()
'2025-03-14T09:30:00+00:00'
>>> naive < aware
Traceback (most recent call last):
    ...
TypeError: can't compare offset-naive and offset-aware datetimes
```

Mixing naive and aware raises `TypeError`, which is a useful alarm.

### The Odoo convention: store UTC, convert at the edge

Odoo stores every `Datetime` as **naive UTC**: the database column holds a timestamp with no zone, and by convention it always means UTC. In Python, reading a `Datetime` field gives a naive `datetime` whose wall-clock fields are the UTC time. The user's browser converts to and from the user's time zone when displaying and editing. Your Python code works in UTC, and converts only when it produces text or logic meant for a person in a specific zone: an email body, a report, "is it before 5pm for this user?".

This design has the advantage that arithmetic, sorting, and comparisons are all consistent and independent of anyone's zone. The cost is that you must never mistake a naive UTC value for local time.

### Getting "now" and "today"

```pycon
>>> now_aware = datetime.now(timezone.utc)
>>> now_aware.tzinfo
datetime.timezone.utc
>>> naive_utc_now = now_aware.replace(tzinfo=None)
>>> naive_utc_now.tzinfo is None
True
```

`datetime.now()` without an argument returns the **server's local time**, naive, which is neither UTC nor the user's zone: avoid it. `datetime.utcnow()` returns naive UTC but is deprecated from Python 3.12 because naive datetimes are error-prone; the aware form followed by `.replace(tzinfo=None)` is the replacement when you need a naive value.

In Odoo, use the field helpers:

- `fields.Datetime.now()` returns the current time as a naive UTC datetime, ready to be written into a `Datetime` field.
- `fields.Date.today()` returns today's date according to the server's clock, which can be the wrong day for a user far from the server.
- `fields.Date.context_today(record)` returns today's date in the **user's** time zone (taken from the context or the user), which is the right one for "today" as the user sees it.
- `fields.Datetime.context_timestamp(record, timestamp)` converts a naive UTC datetime into an aware one in the user's zone, for display logic.

### zoneinfo

Python 3.9+ ships `zoneinfo`, which uses the IANA time zone database (names like `Europe/Rome` or `America/New_York`). Odoo code you read may use the older `pytz` library for the same job. The idea is identical. On Windows, `zoneinfo` needs the `tzdata` package (`pip install tzdata`) because the operating system does not supply the database.

```pycon
>>> from zoneinfo import ZoneInfo
>>> rome = ZoneInfo("Europe/Rome")
>>> utc = timezone.utc
>>> stored = datetime(2025, 3, 14, 23, 30)              # naive UTC, as Odoo stores it
>>> as_utc = stored.replace(tzinfo=utc)                 # label it as UTC
>>> as_rome = as_utc.astimezone(rome)                   # convert to local time
>>> as_rome.isoformat()
'2025-03-15T00:30:00+01:00'
>>> as_rome.date(), as_utc.date()
(datetime.date(2025, 3, 15), datetime.date(2025, 3, 14))
```

At 23:30 UTC on the 14th it is already the 15th in Rome. A report that groups events "by day" using the UTC date would put this event on a different day from the one the user in Rome sees. The fix is to convert first, then take `.date()`.

Two operations, and the difference matters:

- `replace(tzinfo=...)` **labels** a naive value with a zone without changing its numbers. Use it when you know which zone the naive value is in (UTC for stored values).
- `astimezone(zone)` **converts** an aware value to the same moment in another zone and changes the numbers.

Calling `astimezone` on a naive datetime treats it as the **system local time**, which silently depends on the server configuration. Always label first.

### From a user's local input to stored UTC

The reverse trip: the user types "2025-03-15 09:00" meaning Rome time. Label it with the user's zone, convert to UTC, drop the zone for storage:

```pycon
>>> local = datetime(2025, 3, 15, 9, 0, tzinfo=rome)
>>> to_store = local.astimezone(utc).replace(tzinfo=None)
>>> to_store
datetime.datetime(2025, 3, 15, 8, 0)
```

In the summer the offset is +2 and the same wall-clock reading maps to 07:00 UTC. That is why a fixed offset ("Rome is UTC+1") is not enough: use named zones.

### Day boundaries: searching "today" in local time

A user asks for "all events today". In UTC storage, "today in Rome" is a range that does not start at UTC midnight:

```pycon
>>> day = date(2025, 3, 15)
>>> start_local = datetime.combine(day, time.min, tzinfo=rome)
>>> end_local = start_local + timedelta(days=1)
>>> start_utc = start_local.astimezone(utc).replace(tzinfo=None)
>>> end_utc = end_local.astimezone(utc).replace(tzinfo=None)
>>> start_utc, end_utc
(datetime.datetime(2025, 3, 14, 23, 0), datetime.datetime(2025, 3, 15, 23, 0))
```

The domain is then `[("date_event", ">=", start_utc), ("date_event", "<", end_utc)]`, with a half-open range (inclusive start, exclusive end) so nothing is counted twice or lost at midnight. Filtering on the date part of a UTC value gives the wrong answer for any user not in UTC.

### Daylight saving time

Wall-clock time in a zone with daylight saving has two awkward days a year. In Rome, on 2025-03-30 the clock jumps from 02:00 to 03:00, so that day has 23 hours, and 02:30 does not exist. On 2025-10-26 it falls back from 03:00 to 02:00, so that day has 25 hours, and 02:30 happens twice.

```pycon
>>> before = datetime(2025, 3, 29, 12, 0, tzinfo=rome)
>>> after = before + timedelta(days=1)         # wall-clock arithmetic
>>> after.isoformat()
'2025-03-30T12:00:00+02:00'
>>> (after - before).total_seconds() / 3600    # same tzinfo: wall-clock difference
24.0
>>> (after.astimezone(utc) - before.astimezone(utc)).total_seconds() / 3600
23.0
```

Subtracting two aware datetimes that share the same `tzinfo` object compares their wall-clock readings and ignores offsets, so the first subtraction reports 24 hours although only 23 real hours passed. Convert both to UTC before measuring an elapsed duration, as the second line does.

Adding `timedelta(days=1)` to an aware datetime keeps the same wall-clock time, so the real elapsed time is 23 hours that day. If you need an exact duration of 24 hours, convert to UTC first, add, and convert back:

```pycon
>>> exact = (before.astimezone(utc) + timedelta(hours=24)).astimezone(rome)
>>> exact.isoformat()
'2025-03-30T13:00:00+02:00'
```

Ambiguous times are resolved by the `fold` attribute:

```pycon
>>> first = datetime(2025, 10, 26, 2, 30, tzinfo=rome)            # fold=0: first occurrence
>>> second = datetime(2025, 10, 26, 2, 30, fold=1, tzinfo=rome)   # second occurrence
>>> first.isoformat(), second.isoformat()
('2025-10-26T02:30:00+02:00', '2025-10-26T02:30:00+01:00')
```

Storing UTC avoids all of this for data at rest. These cases matter when you convert user input and when you do recurring-schedule arithmetic ("every day at 02:30 local").

### Date versus datetime fields and zones

A `Date` field has no zone and no conversion: 2025-03-15 is 2025-03-15 for everyone. Prefer it for business days. When you need to turn a moment into a business day, convert to the relevant zone first (the user's, or the company's, as the requirement says) and then take the date, as in the Rome example above. State which zone you mean in the code and in the field's help text.

## Putting it together: a small, verifiable helper set

```pycon
>>> from dateutil.relativedelta import relativedelta
>>> def end_of_month(day):
...     return day + relativedelta(day=31)
...
>>> def utc_day_range(day, tz):
...     """Return naive-UTC [start, end) covering the calendar `day` in zone `tz`."""
...     start = datetime.combine(day, time.min, tzinfo=tz)
...     end = start + relativedelta(days=1)
...     to_utc = lambda v: v.astimezone(timezone.utc).replace(tzinfo=None)
...     return to_utc(start), to_utc(end)
...
>>> end_of_month(date(2024, 2, 10)), end_of_month(date(2025, 4, 1))
(datetime.date(2024, 2, 29), datetime.date(2025, 4, 30))
>>> utc_day_range(date(2025, 3, 30), rome)
(datetime.datetime(2025, 3, 29, 23, 0), datetime.datetime(2025, 3, 30, 22, 0))
>>> utc_day_range(date(2025, 10, 26), rome)
(datetime.datetime(2025, 10, 25, 22, 0), datetime.datetime(2025, 10, 26, 23, 0))
```

On 2025-03-30 the range is 23 hours long, on 2025-10-26 it is 25 hours, which is exactly right for those days, and which a hand-written "midnight to midnight plus 24 hours in UTC" would get wrong.

## Pitfalls

- **Floats for money.** Sums drift. Use `Decimal` in plain code, and currency rounding plus `float_compare` in Odoo.
- **`Decimal(0.1)`.** Builds from a float and keeps its error. Pass a string.
- **Comparing amounts with `==`.** Use `float_compare`, `currency.compare_amounts`, or `currency.is_zero`.
- **Python's `round()` on money.** Half-even and float representation produce `2.67` for `2.675`. Use an explicit rounding helper.
- **Rounding policy drift.** Rounding per line in one place and on the total in another gives totals that disagree. Pick one, centralise it.
- **Splitting by division.** Parts that are rounded independently do not sum to the total. Allocate the remainder.
- **Mixing `Decimal` and `float`.** Raises `TypeError` for good reason. Convert through `str` deliberately.
- **`datetime.now()` and `datetime.utcnow()`.** The first is server-local and naive, the second is naive and deprecated. Use `fields.Datetime.now()` in Odoo and `datetime.now(timezone.utc)` elsewhere.
- **`fields.Date.today()` for user-facing "today".** It follows the server clock. Use `context_today` for the user's day.
- **Treating stored datetimes as local time.** They are naive UTC. Label as UTC, then convert.
- **`astimezone` on a naive value.** Assumes the system's local zone. Label with `replace(tzinfo=...)` first.
- **Taking `.date()` of a UTC value to group by day.** It groups by the UTC day, which differs from the user's day. Convert first.
- **Searching a day as UTC midnight to midnight.** Compute the local day's bounds and convert them to UTC, using a half-open range.
- **Fixed offsets instead of zone names.** "UTC+1" ignores daylight saving. Use `Europe/Rome` style names.
- **`timedelta(days=1)` across a DST change.** It is wall-clock arithmetic for aware values. Convert to UTC for exact durations.
- **`timedelta.seconds`.** Returns the seconds component, not the total. Use `total_seconds()`.
- **Month arithmetic with `timedelta`.** There is no month. Use `relativedelta`, and test the 29th to 31st.
- **ISO week and year mismatch.** Use `isocalendar()` for both parts.
- **Ambiguous date formats.** `03/04/2025` means different days in different countries. Exchange ISO 8601 strings.
- **`zoneinfo` on Windows without `tzdata`.** Raises `ZoneInfoNotFoundError`. Install the package.
- **Storing a day as midnight in a `Datetime`.** Use a `Date` field for days.

## Try it

1. Write `split_amount(total, parts)` (as above) and a test that checks, for totals `"0.01"`, `"100.00"`, `"99.99"` and parts `2`, `3`, `7`, that the parts sum to the total and differ by at most one cent from each other.
2. Compute VAT at 22% for three lines priced `"9.99"`, `"19.95"`, and `"0.45"` per line and on the total, using half-up rounding, and show whether the two policies give the same total.
3. Given the naive UTC datetime `2025-07-01 22:30`, show the local date and time in `America/New_York` and in `Asia/Tokyo`, and explain the date in each.
4. Write `local_day_bounds_utc(day, zone_name)` that returns the half-open UTC range for a local calendar day, and use it to find the length in hours of the day `2025-11-02` in `America/New_York` (the end of daylight saving in the United States).
5. Write `add_months(d, n)` with `relativedelta` and verify with `date(2025, 1, 31)` for `n` from 1 to 4.

<details>
<summary>Solution</summary>

1.

```pycon
>>> from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
>>> def split_amount(total, parts):
...     total = Decimal(total)
...     cent = Decimal("0.01")
...     base = (total / parts).quantize(cent, rounding=ROUND_DOWN)
...     amounts = [base] * parts
...     remainder = total - base * parts
...     index = 0
...     while remainder > 0:
...         amounts[index] += cent
...         remainder -= cent
...         index += 1
...     return amounts
...
>>> ok = True
>>> for total in ("0.01", "100.00", "99.99"):
...     for parts in (2, 3, 7):
...         a = split_amount(total, parts)
...         ok = ok and sum(a) == Decimal(total) and max(a) - min(a) <= Decimal("0.01")
...
>>> ok
True
```

2.

```pycon
>>> money = lambda v: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
>>> prices = [Decimal("9.99"), Decimal("19.95"), Decimal("0.45")]
>>> rate = Decimal("0.22")
>>> per_line = sum(money(p * rate) for p in prices)
>>> on_total = money(sum(prices) * rate)
>>> per_line, on_total
(Decimal('6.69'), Decimal('6.69'))
```

The two policies agree for these figures. Try three lines of `3.33` at `0.20` (earlier in the chapter) to see them disagree. The exercise is a reminder that agreement for one data set proves nothing, and the test should include figures that expose the difference.

3.

```pycon
>>> from datetime import datetime, timezone
>>> from zoneinfo import ZoneInfo
>>> stored = datetime(2025, 7, 1, 22, 30).replace(tzinfo=timezone.utc)
>>> stored.astimezone(ZoneInfo("America/New_York")).isoformat()
'2025-07-01T18:30:00-04:00'
>>> stored.astimezone(ZoneInfo("Asia/Tokyo")).isoformat()
'2025-07-02T07:30:00+09:00'
```

New York is four hours behind UTC in July (daylight saving), so the date stays the 1st. Tokyo is nine hours ahead, so it is already the next morning.

4.

```pycon
>>> from datetime import date, time, timedelta
>>> def local_day_bounds_utc(day, zone_name):
...     zone = ZoneInfo(zone_name)
...     start = datetime.combine(day, time.min, tzinfo=zone)
...     end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
...     return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
...
>>> start, end = local_day_bounds_utc(date(2025, 11, 2), "America/New_York")
>>> (end - start).total_seconds() / 3600
25.0
```

The end of daylight saving gives a 25-hour day. Note that the end bound is built from the next day's local midnight, not by adding 24 hours to the start.

5.

```pycon
>>> from dateutil.relativedelta import relativedelta
>>> def add_months(d, n):
...     return d + relativedelta(months=n)
...
>>> [add_months(date(2025, 1, 31), n).isoformat() for n in range(1, 5)]
['2025-02-28', '2025-03-31', '2025-04-30', '2025-05-31']
```

Each result is computed from the original date. Applying `add_months(..., 1)` repeatedly would produce `02-28`, `03-28`, `04-28`, because the day of month is lost after the first clamp. For a monthly schedule, compute each date from the start date and the count.

</details>
