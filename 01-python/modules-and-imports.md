---
description: "Packages, __init__.py, import order, and circular imports."
---

# Modules and imports

A program that fits in one file stops fitting quickly. Python splits code into **modules** (files) and **packages** (folders of modules), and connects them with `import`. Odoo takes this literally: an Odoo "module" is a Python package, its `__init__.py` files decide which model files get loaded and in what order, and cross-module code reuse is an ordinary import. Import mistakes, especially circular imports and missing `__init__.py` entries, are among the most common reasons a freshly written Odoo model does not appear. This chapter explains how imports work, how Python finds code, how packages are structured, and what that means for an Odoo addon.

## Modules

Any `.py` file is a module. Its name is the file name without the extension. Create `fees.py`:

```python
RATE = 0.5

def late_fee(days_late):
    return max(days_late, 0) * RATE
```

Another file, in the same folder, can use it:

```pycon
>>> import fees
>>> fees.late_fee(4)
2.0
>>> fees.RATE
0.5
```

`import fees` runs the file once, from top to bottom, and binds the name `fees` to a **module object**. The names defined in the file (`RATE`, `late_fee`) become attributes of that object.

### Import forms

```python
import fees                       # use as fees.late_fee(...)
import fees as f                  # alias: f.late_fee(...)
from fees import late_fee         # bring one name in: late_fee(...)
from fees import late_fee, RATE   # several names
from fees import late_fee as fee  # alias for a name
from fees import *                # all public names: avoid
```

Which to use:

- `import module` keeps the origin visible at the call site (`fees.late_fee`), avoids name clashes, and makes it obvious where something comes from. The standard library is usually imported this way: `import os`, `import json`.
- `from module import name` is shorter and is the norm for frameworks: Odoo files begin with `from odoo import api, fields, models, _`.
- `from module import *` pulls in everything not starting with an underscore (or everything listed in `__all__`), so a reader cannot tell where a name came from, and it can overwrite names you already defined. Do not use it in your code.

The PEP 8 convention is to put imports at the top of the file, in three groups separated by blank lines: standard library, third-party packages, then your own code. Odoo core follows it, in this order (standard library, `odoo` itself, then other addons):

```python
import logging
from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
```

### Modules run once, then are cached

Python stores every imported module in `sys.modules`, keyed by name. A second `import fees` anywhere in the program returns the same module object without re-running the file:

```pycon
>>> import sys
>>> import fees
>>> sys.modules["fees"] is fees
True
```

This is why module-level code is a single-run initialisation, and why module-level variables are shared state across the whole process. In an Odoo server the process handles many requests, and often many databases, so a mutable module-level variable is global to all of them. See [Functions](functions.md) on scope.

### Code runs at import time

Everything at module level executes during import: assignments, function and class definitions, and any statement you leave there.

```python
# fees.py
print("fees loaded")          # runs on first import
RATE = 0.5
```

Keep module-level code to definitions and cheap constants. Do not open connections, read files, or call services at import time. A failure there breaks the import of every file that depends on it, and in Odoo it breaks the registry load for the whole database.

### `__name__` and `if __name__ == "__main__"`

Every module has a `__name__`. When imported it is the module's name. When run as a script it is `"__main__"`:

```text
$ python3 mod.py          # mod.py contains: print(__name__)
__main__
$ python3 -c "import mod"
mod
```

So a file can serve both purposes:

```python
def main():
    print("running")

if __name__ == "__main__":
    main()
```

The guarded block runs only when the file is executed directly, not when another file imports it. Odoo module files do not use this; Odoo imports them. You use it in standalone helper scripts that also expose reusable functions.

## How Python finds a module

When you write `import fees`, Python looks, in order, at:

1. `sys.modules`, the cache of already imported modules.
2. Built-in modules (compiled into the interpreter).
3. Each folder in `sys.path`, in order, for `fees.py` or a `fees` package folder.

`sys.path` is a list of strings:

```pycon
>>> import sys
>>> type(sys.path), isinstance(sys.path[0], str)
(<class 'list'>, True)
```

It starts with the script's folder (or an empty string in the REPL, meaning the current directory), followed by entries from the `PYTHONPATH` environment variable, then the standard library and the `site-packages` folder of the active environment (see [Setup and running code](setup-and-running-code.md)).

The practical rules that follow:

- A file named like a standard module (`json.py`, `random.py`, `logging.py`) placed next to your script **shadows** the real one, because the script's folder comes first.
- `ModuleNotFoundError: No module named 'x'` means no folder in `sys.path` contains `x`. Either it is not installed in the interpreter you are running, or your own folder is not on the path.
- To use code from another folder, put the folder on the path (`PYTHONPATH`, or a package install), not by editing `sys.path` inside your files.

For Odoo, the **addons path** (set in the configuration file or with `--addons-path`) is how the server finds addons, and Odoo arranges the Python import side so that each addon in those folders is importable as `odoo.addons.<module_name>`. You do not edit `sys.path` yourself.

Inspect where something comes from:

```pycon
>>> import json
>>> json.__name__, json.__file__.endswith("__init__.py")
('json', True)
```

## Packages

A **package** is a folder that contains modules and, normally, a file named `__init__.py`. The folder name is the package name:

```text
library/
    __init__.py
    models/
        __init__.py
        book.py
        loan.py
```

You import from it with dotted names:

```python
import library.models.book
from library.models import loan
from library.models.book import register
```

`__init__.py` runs when the package is imported. It may be empty, or it may import the package's submodules. Whatever names it defines or imports become attributes of the package, which makes `__init__.py` the place to define the package's public face.

Since Python 3.3, a folder without `__init__.py` can still be imported as an implicit **namespace package**. It works until you need package-level initialisation, and for Odoo addons the file is required. A missing `__init__.py` is a classic cause of "my new folder is ignored".

### Relative imports

Inside a package you can refer to siblings relative to the current module:

```python
# library/models/loan.py
from . import book              # sibling module: library.models.book
from .book import register      # a name from a sibling
from .. import wizard           # a module one level up: library.wizard
from ..tools import helpers     # a module in a sibling package
```

One dot means the current package, two dots the parent. Relative imports work only inside a package, not in a script run directly. They survive renaming the top-level package. Odoo code uses them heavily: `from . import models` in the addon's root `__init__.py`.

### Example: observing import order

With the package layout above, where `models/__init__.py` contains `from . import book` then `from . import loan`, and each file prints a line when loaded:

```pycon
>>> import library
loading book
loading loan
```

`import library` ran `library/__init__.py`, which ran `from . import models`, which ran `models/__init__.py`, which imported `book` and then `loan` in the written order. Each module appears in `sys.modules` under its dotted name:

```pycon
>>> sorted(m for m in sys.modules if m.startswith("library"))
['library', 'library.models', 'library.models.book', 'library.models.loan']
```

Import order is **execution order**, and execution order is what matters in Odoo, as the next section shows.

## Anatomy of an Odoo addon, as Python

An addon is a folder on the addons path containing a `__manifest__.py` and, for Python code, an `__init__.py`:

```text
library/
    __manifest__.py
    __init__.py
    models/
        __init__.py
        book.py
        loan.py
    wizard/
        __init__.py
        return_wizard.py
    controllers/
        __init__.py
        main.py
    views/
        book_views.xml
    security/
        ir.model.access.csv
```

The root `__init__.py` is the entry point Odoo imports when it loads the addon, and it lists which subpackages to load:

```python
# library/__init__.py
from . import models
from . import wizard
from . import controllers
```

```python
# library/models/__init__.py
from . import book
from . import loan
```

Each model file defines classes inheriting `models.Model`. **A model class exists in Odoo only if its file is imported.** If you create `models/fine.py` and forget the line `from . import fine` in `models/__init__.py`, the file is never executed, the class is never defined, and nothing tells you: no error, and the model is simply absent. Views that reference its fields later fail with errors about unknown fields or models, which sends people looking in the wrong place. When a new model does not show up, check the `__init__.py` chain first.

The order of imports is also meaningful:

- Inside one addon, classes are collected in the order in which their modules were imported. When two classes in the same addon extend one model, the order of `from . import ...` lines decides which is earlier in the chain (see [super() explained](super-explained.md)).
- A file that uses a class or constant from a sibling can import it, and Python will load the sibling first if it has not been loaded already.

The manifest, `__manifest__.py`, contains a single dictionary literal. Odoo reads it without importing the addon's code, to find the name, dependencies, data files, and so on. The fields that matter at this point:

```python
{
    "name": "Library",
    "version": "1.0.0",
    "depends": ["base", "mail"],
    "data": ["security/ir.model.access.csv", "views/book_views.xml"],
    "external_dependencies": {"python": ["lxml"]},
    "license": "LGPL-3",
}
```

`depends` lists other addons that must be loaded first, which is what decides module load order and therefore the order of the model chain. `external_dependencies` lists Python packages, and Odoo checks they are importable at install time and refuses to install the addon otherwise, with a message naming the missing library. The manifest keys are covered in the architecture part of this book.

### Importing from another addon

An addon that depends on another can import from it using the `odoo.addons` namespace:

```python
from odoo.addons.library.models.book import SOME_CONSTANT
```

Use it for constants, helpers, and exceptions, not to bypass the ORM. Models of other addons are reached through the environment (`self.env["library.book"]`), not by importing the class. Importing an addon you do not list in `depends` may work on your machine, because it is on the addons path, and then fail on a database where it is not installed.

### Importing external libraries

A third-party package used only by some features should not break the whole addon when it is absent. The standard guarded import:

```python
import logging

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    _logger.warning("xlsxwriter is not installed; Excel export is disabled")
    xlsxwriter = None
```

and later:

```python
def export_xlsx(self):
    if xlsxwriter is None:
        raise UserError(_("The xlsxwriter library is required for this export."))
```

For a hard requirement, list the package in `external_dependencies` so that installation fails clearly, rather than the failure happening at the first click.

## Circular imports

Module `a` imports `b`, and `b` imports `a`. Python starts loading `a`, hits `import b`, starts loading `b`, hits `import a`, finds `a` **partially initialised** in `sys.modules` (its remaining lines have not run yet), and the result depends on what `b` asks of it.

```python
# circ/a.py
from circ.b import B_VALUE
A_VALUE = 1
```

```python
# circ/b.py
from circ.a import A_VALUE
B_VALUE = 2
```

```text
$ python3 -c "import circ.a"
  File ".../circ/b.py", line 1, in <module>
    from circ.a import A_VALUE
ImportError: cannot import name 'A_VALUE' from partially initialized module 'circ.a' (most likely due to a circular import)
```

`from circ.a import A_VALUE` needs the **name** `A_VALUE` to exist right now, but `a` has not reached the line that defines it. Note the traceback shows the error in `b.py`, though the design problem spans both files.

If the two files use `import module` and access attributes later, at call time rather than at import time, the same cycle works:

```python
# circ/c.py
import circ.d

def c_value():
    return circ.d.D_VALUE + 1
C_VALUE = 1
```

```python
# circ/d.py
import circ.c
D_VALUE = 10

def d_value():
    return circ.c.C_VALUE + D_VALUE
```

```text
$ python3 -c "import circ.c, circ.d; print(circ.c.c_value(), circ.d.d_value())"
11 11
```

Here, nobody touches an attribute of the partially loaded module at import time, only inside functions that run later, when both modules are complete. This works, but it is fragile, and relying on it is a smell.

### Ways out

1. **Move the shared piece to a third module** that both import. This is almost always the right fix. If `a` and `b` both need a constant, a function, or a base class, put it in `common.py` and have both import from it. The dependency graph becomes a tree.
2. **Import inside the function** that needs it (a *deferred* or local import):

```python
def confirm(self):
    from .wizard import ConfirmWizard      # imported on first call, not at load
    return ConfirmWizard.run(self)
```

   Works, and is acceptable for rare code paths. The cost is a hidden dependency and a tiny lookup on every call.
3. **Use `import module` style** and reference attributes lazily, as in the `c`/`d` example.
4. **Reference by name, not by class.** In Odoo you almost never need to import a model class from a sibling file, because `self.env["library.book"]` retrieves it by its model name at runtime. Many circular imports in addons come from importing a class that could have been looked up through `env`. Many-to-one fields reference other models by string (`fields.Many2one("library.book")`), which is exactly to avoid the import.
5. **Type checking only:** for type hints, `from __future__ import annotations` plus `if TYPE_CHECKING:` imports the name for editors without importing it at runtime.

## Reloading and `importlib`

Importing a name twice does not re-run the module. `importlib.reload(module)` forces it, and is useful in the REPL while developing a helper file, with caveats: objects created before the reload still refer to the old classes. Do not use it in production code. In Odoo, changes to Python files take effect after the server restarts, or in development when the server runs with auto-reload enabled.

`importlib.import_module("library.models.book")` imports a module by a name held in a string:

```pycon
>>> import importlib
>>> mod = importlib.import_module("json")
>>> mod.dumps({"a": 1})
'{"a": 1}'
```

This is the building block for plugin systems and for code that picks an implementation at runtime from configuration.

## `__all__`

A module may define `__all__`, a list of the names that `from module import *` exports and that documentation tools treat as public:

```python
__all__ = ["late_fee", "RATE"]
```

Names that begin with an underscore are also treated as private by convention. Python does not enforce privacy: anyone can `import fees; fees._helper`. The convention tells readers what is safe to depend on.

## Organising your own code

A few conventions that keep imports healthy:

- **One direction of dependency.** If `models` imports from `tools`, then `tools` must not import from `models`. Draw the arrows; they should have no cycles.
- **Small, named modules.** `tools/dates.py` and `tools/money.py` beat `utils.py` with 40 unrelated functions.
- **Pure helpers in their own modules.** Functions that do not touch the ORM (parsing, formatting, calculations) go in plain Python modules. They can be tested without a database, and they import nothing from Odoo.
- **Explicit public names.** Re-export what other files should use from `__init__.py`, so internal files can move.
- **Absolute imports in scripts, relative inside packages.**
- **No work at import time.** Module-level code defines things; functions do things.

## Pitfalls

- **Missing line in `__init__.py`.** A new model or wizard file that is not imported does nothing, with no error. When something you wrote does not exist at runtime, check the import chain from the addon root.
- **Missing `__init__.py` in a new folder.** The subpackage is not importable or not loaded.
- **Circular imports.** Fix by extracting shared code, not by sprinkling local imports around.
- **Shadowing a standard module.** `json.py`, `logging.py`, `email.py`, or `types.py` in your folder breaks unrelated imports. Delete `__pycache__` after renaming.
- **`from x import *`.** Hides origins and overwrites names silently.
- **Importing a class from another addon without declaring the dependency.** Works locally where both are installed, fails elsewhere. Use `depends`, and prefer `self.env[...]`.
- **Work at import time.** Network calls or database access in module-level code slow down and can break server startup.
- **Mutable module-level state.** Shared by all requests, and across databases in one process.
- **Optional library imports without a guard.** A missing optional package breaks the whole addon load. Use the `try/except ImportError` pattern, or list a hard requirement in `external_dependencies`.
- **Relative import in a script.** `ImportError: attempted relative import with no known parent package` when the file is run directly. Run it as a module (`python -m package.module`) or use absolute imports.
- **Stale `.pyc` or reload confusion.** After moving files, stale `__pycache__` folders can mask the change. Restarting the process is the reliable fix.
- **Different import paths for one file.** Importing the same file as `library.models.book` in one place and as `models.book` in another creates two module objects with two copies of every class. Always import through the one canonical dotted path.
- **Assuming import order across addons.** Do not rely on one addon being loaded before another unless the dependency is declared.

## Try it

1. Create a package `shop` with `__init__.py`, `prices.py` (a function `with_tax(amount, rate=0.2)`), and `report.py` that imports `with_tax` with a relative import and defines `line(label, amount)` returning a formatted string. Import `shop.report` from a script one level above, and print a line.
2. Add a `print("loading prices")` to `prices.py`. Import `shop.report` and `shop.prices` in the same script, and count how many times the message prints. Explain.
3. Make a deliberate circular import with `from ... import name` in both modules, read the error, and fix it by moving the shared constant to a third module.
4. Write a script `tool.py` with a function `main()` and the `__main__` guard. Run it directly, then import it from the REPL, and observe the difference.
5. Sketch the `__init__.py` files for an addon with `models/book.py`, `models/loan.py`, `wizard/return_wizard.py`, and `controllers/main.py`. Which line, if missing, hides a model silently, and which one hides a controller route?

<details>
<summary>Solution</summary>

1. Layout and files:

```text
project/
    main.py
    shop/
        __init__.py        (empty)
        prices.py
        report.py
```

```python
# shop/prices.py
def with_tax(amount, rate=0.2):
    return round(amount * (1 + rate), 2)
```

```python
# shop/report.py
from .prices import with_tax

def line(label, amount):
    return f"{label:<10}{with_tax(amount):>8.2f}"
```

```python
# main.py
from shop.report import line
print(line("Book", 10))
```

```text
$ python3 main.py
Book          12.00
```

2. The message prints once. `import shop.report` loads `shop.prices` as a side effect of the relative import, and `sys.modules` caches it, so the later `import shop.prices` finds it already loaded and does not run the file again.

3. With `a.py` doing `from b import X` and `b.py` doing `from a import Y`, the second import fails with `ImportError: cannot import name ... from partially initialized module`. Move `X` and `Y` to `common.py` and have both modules import from it; the dependency graph then has no cycle.

4. Run directly, `__name__` is `"__main__"` and the guarded block executes. Imported from the REPL, `__name__` is `"tool"`, the guarded block does not run, and `main()` is available to call by hand.

5.

```python
# addon/__init__.py
from . import models
from . import wizard
from . import controllers
```

```python
# addon/models/__init__.py
from . import book
from . import loan
```

```python
# addon/wizard/__init__.py
from . import return_wizard
```

```python
# addon/controllers/__init__.py
from . import main
```

Missing `from . import loan` in `models/__init__.py` hides the loan model silently. Missing `from . import controllers` in the root `__init__.py` (or `from . import main` in the controllers package) leaves the routes unregistered, and requests to them return a not-found response.

</details>
