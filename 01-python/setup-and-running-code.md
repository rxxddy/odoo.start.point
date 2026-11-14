---
description: "Interpreter, virtual environments, running scripts, the REPL."
---

# Setup and running code

Odoo is a Python program. Every model, every button handler, every scheduled job you will write is Python executed by an interpreter on a server. Before you write a line of business logic you need three things: a working interpreter, an isolated place to install libraries, and a feedback loop that tells you within seconds whether a line of code does what you think. This chapter builds those three things and introduces the vocabulary used for the rest of Part 1. It assumes you have never programmed.

## What "running Python" means

A computer executes machine instructions. Python source code is text, so something has to translate it. That something is the **interpreter**: a program called `python` (or `python3`) that reads your text file, converts it to an internal form, and executes it step by step. When you "run a script", you start the interpreter and hand it a file.

Python code lives in files ending in `.py`. A file is a **script** when you run it directly and a **module** when another file imports it (see [Modules and imports](modules-and-imports.md)). The distinction is about how the file is used, not about its content.

Odoo is started by running the interpreter on its entry point, conceptually `python odoo-bin ...`. The server reads your module files, loads them as Python modules, and calls your code when users click things. Everything in this part of the book applies to those files.

### Which version

Each Odoo release states a minimum Python version, and the supported range moves with the release. Read the `requirements.txt` and the installation documentation of the release you target, then install an interpreter inside that range. This book uses syntax that needs Python 3.10 in a few places (`match`, `X | Y` in type hints) and says so each time. If your server runs an older interpreter, those snippets will not work there, and the text names the older equivalent.

{% hint style="info" %}
Test on the same major.minor version your production server uses. A feature that exists on your laptop's interpreter and not on the server is a common way to break a deployment.
{% endhint %}

## Installing Python

### Windows

Download the installer from python.org. On the first screen tick **Add python.exe to PATH**. PATH is the list of folders the shell searches when you type a command name; without the tick, typing `python` finds nothing.

Open PowerShell and check:

```text
> python --version
Python 3.12.4
```

Windows also ships a launcher called `py` that can choose between several installed versions:

```text
> py -3.12 --version
Python 3.12.4
> py -0
 -V:3.12 *        Python 3.12 (64-bit)
 -V:3.10          Python 3.10 (64-bit)
```

`py -0` lists installed versions and marks the default with `*`. With several Pythons installed, use `py -3.10` to be explicit.

{% hint style="warning" %}
Windows has "App execution aliases" that make `python` open the Microsoft Store when no interpreter is installed. If `python` opens the Store, install from python.org and disable the alias under Settings, Apps, Advanced app settings, App execution aliases.
{% endhint %}

### Linux

Most distributions ship Python. Check first:

```text
$ python3 --version
Python 3.10.12
```

On Debian and Ubuntu you also need the venv module and the build tools that Odoo's dependencies need:

```text
$ sudo apt install python3-venv python3-pip python3-dev build-essential
```

On Linux the command is `python3`. A bare `python` may not exist, or may point to something old. Inside a virtual environment (next section) `python` always exists and always means the right one.

### macOS

Install with Homebrew (`brew install python@3.12`) or from python.org. The command is `python3`.

## Running code: three ways

### 1. The REPL

REPL means Read-Evaluate-Print Loop. Start the interpreter with no arguments:

```text
$ python3
Python 3.12.4 (main, Jun  6 2024, 18:26:44) [GCC 13.2.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>>
```

`>>>` is the prompt. You type an expression, press Enter, and Python prints the result:

```pycon
>>> 2 + 3
5
>>> "library" + " " + "book"
'library book'
>>> len("library.book")
12
```

Lines starting with `>>>` are what you type. Lines without a prefix are what Python prints. The book uses this format throughout; paste the `>>>` lines into a REPL and you see the same output.

A statement that needs more than one line shows the continuation prompt `...`:

```pycon
>>> for n in range(3):
...     print(n)
...
0
1
2
```

Press Enter on the empty `...` line to finish the block. Leave the REPL with `exit()`, or Ctrl+D on Linux and macOS, or Ctrl+Z then Enter on Windows.

The REPL is the fastest way to answer "what does this expression do?". Use it constantly. Two built-ins make it better:

- `help(thing)` shows documentation (press `q` to leave the pager). Try `help(str.split)`.
- `dir(thing)` lists the names an object offers.

```pycon
>>> dir("abc")[-3:]
['title', 'translate', 'upper']
```

Both work on anything, including Odoo objects, which is why they matter later when you stand in front of an unfamiliar recordset.

The underscore `_` holds the last printed result:

```pycon
>>> 6 * 7
42
>>> _ + 1
43
```

### 2. Running a script file

Create a file `hello.py`:

```python
name = "library"
count = 3
print("Module:", name)
print("Books:", count)
```

Run it from the folder that contains it:

```text
$ python3 hello.py
Module: library
Books: 3
```

`print()` writes text to the terminal. A script that computes something and does not print it appears to do nothing. In the REPL the value of the last expression is printed automatically; in a script it is not.

A script is read top to bottom, once, and the interpreter exits at the end. Variables disappear. This is the main difference from the REPL, where state stays until you exit.

### 3. `python -c` for one-liners

`-c` runs a string as code:

```text
$ python3 -c "print(sum(range(1, 101)))"
5050
```

This is useful for quick checks and for shell scripts. Quoting differs between shells; double quotes outside and single quotes inside works in Bash, PowerShell, and cmd:

```text
$ python3 -c "print('a' * 3)"
aaa
```

### Running a module with `-m`

`python -m name` runs an installed module as a program. You will use these:

```text
$ python3 -m venv .venv            # create a virtual environment
$ python3 -m pip install lxml      # run the pip that belongs to THIS interpreter
$ python3 -m json.tool data.json   # pretty-print a JSON file
$ python3 -m http.server 8000      # serve the current folder
```

`python -m pip` is better than a bare `pip`. A bare `pip` belongs to whichever Python appears first on PATH, which may not be the one you think. `python -m pip` installs into the interpreter you named.

## Virtual environments

Python libraries are installed into the interpreter's own folder, called `site-packages`. If every project installs there, two projects that need different versions of the same library collide. Odoo makes this concrete: different Odoo releases pin different versions of libraries such as `lxml`, `Pillow`, `psycopg2`, and `Werkzeug`. You cannot satisfy both in one folder.

A **virtual environment** (venv) is a self-contained folder holding a link to (or copy of) the interpreter plus its own empty `site-packages`. Install into it and nothing else on the machine changes. Give each Odoo version its own venv.

### Create and activate

```text
$ cd ~/work/odoo-16
$ python3 -m venv .venv
```

Activation changes your shell's PATH for the current session so that `python` and `pip` resolve inside `.venv`:

```text
# Linux / macOS
$ source .venv/bin/activate
(.venv) $ which python
/home/me/work/odoo-16/.venv/bin/python

# Windows PowerShell
> .venv\Scripts\Activate.ps1
(.venv) > (Get-Command python).Source
C:\work\odoo-16\.venv\Scripts\python.exe
```

The `(.venv)` prefix tells you it is active. Leave with `deactivate`.

{% hint style="warning" %}
On Windows PowerShell, activation can fail with "running scripts is disabled on this system". Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip activation and call the interpreter by its path: `.venv\Scripts\python.exe script.py`.
{% endhint %}

Activation is a convenience for humans. Services and cron jobs call the venv's interpreter by full path: `/opt/odoo/.venv/bin/python /opt/odoo/odoo-bin -c /etc/odoo.conf`.

### Installing packages with pip

`pip` downloads libraries from the Python Package Index (PyPI) and installs them in the active environment:

```text
(.venv) $ python -m pip install --upgrade pip
(.venv) $ python -m pip install requests
(.venv) $ python -m pip list
Package            Version
------------------ ---------
certifi            2024.7.4
charset-normalizer 3.3.2
idna               3.7
pip                24.1.2
requests           2.32.3
urllib3            2.2.2
```

Pin versions in a text file. Odoo ships its own `requirements.txt`:

```text
(.venv) $ python -m pip install -r requirements.txt
```

Each line names a package and optionally a version constraint, like `lxml==4.9.3` or `Pillow>=9.0,<11`. If a package fails to build, the error usually names a missing system library (`libpq-dev`, `libxml2-dev`, `libldap2-dev`, `libsasl2-dev` on Debian-family systems). Install it with the system package manager and retry.

To record what you have installed:

```text
(.venv) $ python -m pip freeze > frozen.txt
```

### Checking which Python is running

When something behaves oddly, ask the interpreter about itself:

```pycon
>>> import sys
>>> sys.version_info[:2]
(3, 12)
>>> sys.executable
'/home/me/work/odoo-16/.venv/bin/python'
>>> sys.prefix != sys.base_prefix   # True inside a venv
True
>>> import lxml
>>> lxml.__file__
'/home/me/work/odoo-16/.venv/lib/python3.12/site-packages/lxml/__init__.py'
```

`sys.executable` answers "which interpreter am I?". `module.__file__` answers "which copy of this library did I import?". Those two questions resolve most "it works on my machine" confusion.

## Shadowing and isolated mode

When you run a script, Python searches the script's own folder first when resolving imports. A file named `random.py` or `json.py` next to your script therefore shadows the standard library module of the same name. Two defenses:

- Never name your files after standard modules (`json.py`, `random.py`, `logging.py`, `email.py`, `datetime.py`).
- Run throwaway code with `python -I` (isolated mode), which ignores the current directory and the `PYTHON*` environment variables:

```text
$ python3 -I -c "import json; print(json.__file__)"
/usr/lib/python3.12/json/__init__.py
```

Keep a scratch folder outside any project for experiments, so stray files never end up on an addons path.

## Reading error messages

You will see errors every day. They describe what went wrong and where. Learn to read them bottom-up.

```python
def total(prices):
    return sum(prices)

def report(data):
    return total(data["prices"])

print(report({"price": [1, 2, 3]}))
```

```text
$ python3 report.py
Traceback (most recent call last):
  File "report.py", line 7, in <module>
    print(report({"price": [1, 2, 3]}))
  File "report.py", line 5, in report
    return total(data["prices"])
KeyError: 'prices'
```

Read from the last line up. `KeyError: 'prices'` says what happened: a dictionary was asked for a key it does not have. The line above it shows the exact line of code. Lines above that show who called whom to get there, outermost call first. The last frame is where the error was raised, which is not always where the mistake was made. Here the typo is `"price"` in the data on line 7; the error surfaces at line 5.

Odoo prints this same traceback in its server log and, for errors the user can see, summarises it in a dialog. The skill is identical.

### Syntax errors versus runtime errors

A `SyntaxError` happens before any code runs, because the interpreter cannot parse the file:

```text
  File "x.py", line 2
    if count > 3
                ^
SyntaxError: expected ':'
```

Everything else (`NameError`, `TypeError`, `KeyError`, ...) happens while running, so code before the faulty line has already executed. In Odoo a syntax error in a module file means the module fails to load at server start, and the log names the file and line. A runtime error inside a method appears only when a user triggers that method.

## Editors and tooling

You can write Python in any text editor, but three features save hours:

1. **Syntax highlighting and indentation handling.** Python uses indentation as structure (see [Control flow](control-flow.md)), so mixing tabs and spaces breaks code. Configure your editor to insert 4 spaces when you press Tab.
2. **A linter.** `flake8`, `pylint`, or `ruff` flag undefined names, unused imports, and many bugs without running the code.
3. **A debugger.** Covered in the Shell and debugging part of this book. For now `print()` is enough.

Install tools in the venv, not globally:

```text
(.venv) $ python -m pip install ruff
(.venv) $ python -m ruff check hello.py
All checks passed!
```

## Your first useful script

A script that reads a text file and counts lines per state. Create `loans.txt`:

```text
book-001 returned
book-002 open
book-003 open
book-004 returned
book-005 open
```

And `count_loans.py`:

```python
from collections import Counter

counts = Counter()
with open("loans.txt", encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        book, state = line.split()
        counts[state] += 1

for state, number in counts.items():
    print(state, number)
```

```text
$ python3 count_loans.py
returned 2
open 3
```

You do not need to understand every line yet. Notice the shape: read input, loop, compute, print. The next chapters explain each part until the whole script is obvious: `import` in [Modules and imports](modules-and-imports.md), `Counter` and `.items()` in [Lists, tuples, dicts, sets](collections.md), `for` and `continue` in [Control flow](control-flow.md), and `with open` in [Errors and exceptions](errors-and-exceptions.md) and the [Standard library toolbox](standard-library-toolbox.md).

## Where Odoo's Python runs

When you later start Odoo, several execution contexts exist, all using the same interpreter:

| Context | How it starts | Typical use |
|---|---|---|
| Server | `python odoo-bin -c config` | The long-running process that serves users. |
| Shell | `python odoo-bin shell -d dbname` | An interactive REPL with a database environment loaded. |
| Module install or update | `odoo-bin -d db -i module` or `-u module` | Runs your data files and migration scripts. |
| Tests | `odoo-bin` with test options | Runs test classes. |

The Odoo shell is a normal REPL with an extra variable (`env`) bound to a database environment. Everything you practise in a plain REPL transfers directly. Part 4 covers the command line in detail; the point here is that "Python for Odoo" is plain Python, run by a plain interpreter, inside a venv you control.

## Pitfalls

- **Wrong interpreter.** `pip install` into the system Python, then running Odoo from a venv (or the reverse), gives `ModuleNotFoundError` for a package you "just installed". Use `python -m pip` and verify with `sys.executable`.
- **Forgetting to activate.** A new terminal tab uses the system Python. The prompt prefix `(.venv)` is your confirmation.
- **Moving or renaming a venv folder.** Venvs store absolute paths. Renaming the parent folder breaks the scripts inside `.venv`. Recreate the venv and reinstall from `requirements.txt`; venvs are disposable by design.
- **Committing the venv.** Add `.venv/` to `.gitignore`. Share `requirements.txt`, not the environment.
- **Shadowing standard modules.** A local `json.py` or `logging.py` makes `import json` load your file. The error then looks unrelated (`AttributeError: module 'json' has no attribute 'loads'`). Rename the file and delete the `__pycache__` folder next to it.
- **Mixed tabs and spaces.** Python 3 raises `TabError` when they are mixed in a way it cannot interpret consistently. Configure the editor to use spaces.
- **Missing system libraries.** `pip install` of `psycopg2` or `python-ldap` fails with compiler errors when headers are absent. The fix is a system package, not a different pip command.
- **Different Python on the server.** Developing on 3.12 and deploying on 3.10 means `match` works in both, while a newer standard library function may not exist on the server. Pin the same minor version.
- **File encoding on Windows.** `open("file.txt")` without `encoding=` uses the system code page, so the same script reads a file differently on two machines. Always pass `encoding="utf-8"`.
- **Print-less scripts.** A script that computes and prints nothing looks broken. In a script, use `print()`.

## Try it

1. Create a folder `scratch`, a virtual environment inside it, activate it, and print `sys.prefix` and `sys.executable` from the REPL. Confirm that they point inside the folder.
2. Write `squares.py` that prints the squares of 1 to 5, one per line, then run it from the shell. Then do the same as a one-liner with `-c`.
3. Deliberately cause a `NameError`, a `KeyError`, and a `SyntaxError`. For each, read the message bottom-up and state what the interpreter is telling you.
4. In the scratch folder create `json.py` containing `print("mine")`. Run `python -c "import json; print(json.__file__)"`, then `python -I -c "import json; print(json.__file__)"`. Explain the difference, then delete the file.
5. Install `requests` into the venv, then run `python -m pip freeze`. Create a second venv and check that `requests` is absent there.

<details>
<summary>Solution</summary>

1. Typical commands:

```text
$ mkdir scratch && cd scratch
$ python3 -m venv .venv
$ source .venv/bin/activate
(.venv) $ python
>>> import sys
>>> sys.prefix
'/home/me/scratch/.venv'
>>> sys.executable
'/home/me/scratch/.venv/bin/python'
```

2. File:

```python
for n in range(1, 6):
    print(n * n)
```

One-liner: `python -c "print(*[n * n for n in range(1, 6)], sep=chr(10))"` prints 1, 4, 9, 16, 25 on separate lines. (The `for` statement form does not fit after `-c` on one line when combined with other statements, which is why the list comprehension form is used; comprehensions are covered in [Comprehensions and generators](comprehensions-and-generators.md).)

3. `print(undefined_name)` gives `NameError: name 'undefined_name' is not defined`: a name was used that was never assigned. `{"a": 1}["b"]` gives `KeyError: 'b'`: the dictionary has no such key. `if True print(1)` gives `SyntaxError`, raised before anything runs. The last line names the type; the lines above give location.

4. Without `-I`, the current directory comes first on the import path, so `json.__file__` shows `.../scratch/json.py` (and importing it prints `mine`). With `-I` the standard library module is loaded and `json.__file__` shows a path inside the Python installation. Remove the file and the `__pycache__` folder afterwards.

5. After installation, `python -m pip freeze` lists `requests` with its dependencies. In the second venv `python -m pip freeze` prints nothing, because each venv has its own `site-packages`.

</details>
