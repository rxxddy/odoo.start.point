---
description: The built-in profiler and what its output tells you.
---

# Profiling

Logging queries shows what the database did. Profiling shows where the time went in Python and SQL together, per call stack. Use it when a screen or method is slow and you do not yet know why.

## The profiler in the UI

In developer mode, the debug menu has a profiling entry (a bug icon with a stopwatch in recent versions). Open it, enable recording, optionally select options, then reproduce the slow action. Disable it again. The recordings are stored in the model `ir.profile` and listed under Settings, Technical, Profiling.

Options you can toggle:

- **Memory**: sample allocations (heavier).
- **Sync** and **Async** collectors: stack sampling of the running code, and sampling of asynchronous work.
- **SQL**: record every query with its stack.
- **Traces**: full call tracing, very slow, for short actions.

Open a recording and choose "Open in Speedscope" to browse flame graphs in the browser. The SQL view lists queries by the line of Python that issued them.

## Profiling from code

```python
from odoo.tools import profiler

def heavy(self):
    with profiler.Profiler(description="heavy export", db=self.env.cr.dbname):
        self._build_export()
```

The recording ends up in `ir.profile`. In the shell:

```python
>>> from odoo.tools.profiler import Profiler
>>> with Profiler(description="loans listing", db=env.cr.dbname):
...     env['library.loan'].search([]).mapped('book_id.name')
```

Without a database, `Profiler` can write to the log or to a file depending on options. The module and arguments changed over versions; read `odoo/tools/profiler.py` in your release.

## Command-line profiling with cProfile

Works on any version, and is good for scripts:

```bash
python -m cProfile -o /tmp/run.prof ./odoo-bin shell -d mydb --no-http < scripts/export.py
python - <<'PY'
import pstats
pstats.Stats("/tmp/run.prof").sort_stats("cumulative").print_stats(30)
PY
```

Or inside code, for a block:

```python
import cProfile, pstats, io
pr = cProfile.Profile()
pr.enable()
records._compute_totals()
pr.disable()
out = io.StringIO()
pstats.Stats(pr, stream=out).sort_stats("cumulative").print_stats(25)
print(out.getvalue())
```

`cumulative` shows where time is spent including callees; `tottime` shows the cost of the function itself. Look at `cumulative` to find the area, `tottime` to find the culprit.

## Reading the output

- A wide flame graph block around `cr.execute` or `psycopg2`: database time. Go to [Inspecting SQL](inspecting-sql.md).
- Many narrow repeated blocks under one parent: a loop issuing small queries (N+1), or a compute running per record.
- Time in `fields.py` `__get__` and `_fetch`: reading fields in a way that defeats the prefetch.
- Time in `_recompute_*` or `modified`: write triggered recomputes of stored dependants.
- Time in `ir_qweb` or `_render`: template cost; check the number of records rendered.
- Time in `safe_eval`: rules and automations evaluated per record.

## Measuring method

1. Fix one scenario and data set. Profile it before changing anything.
2. Change one thing. Profile again, with the same data.
3. Compare totals, not feelings. Keep the numbers in the commit message.

A quick wall-clock check beats a profiler for before and after:

```python
import time
t = time.perf_counter()
...
print(round(time.perf_counter() - t, 3))
```

## Pitfalls

- **Profiling with debug logging on.** The logging overhead distorts the result.
- **Cold cache.** The first run reads from disk; run twice and measure the second.
- **Profiler overhead.** Tracing and memory options slow the code several times; relative shapes stay useful, absolute times do not.
- **Production recordings.** A profile contains code paths and, with SQL collection, query text with data. Delete recordings when finished and do not share them.
- **Optimising the wrong layer.** If one query takes 90 percent of the time, no Python change matters.
