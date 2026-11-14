---
description: "Breakpoints, stepping, and attaching an IDE."
---

# Debugging with pdb and debugpy

A print statement tells you what you thought to print. A debugger lets you inspect everything at the moment of failure. Odoo runs normal Python, so both the standard `pdb` and an IDE debugger through `debugpy` work, with a few constraints about workers and threads.

## Run single-process first

Breakpoints are only useful in a process you can see. Start the server with no workers, so one process handles every request:

```bash
./odoo-bin -c odoo.conf -d mydb --workers=0 --dev=all
```

`--dev=all` enables reload and the post-mortem debugger. The values are comma-separated and include `reload` (restart on Python change), `qweb`, `xml` (read views from disk) and `pdb` (drop into the debugger on exception). In recent versions `--dev=all` implies all of them; check `./odoo-bin --help` in your version.

## pdb: breakpoints in code

```python
def action_confirm(self):
    for loan in self:
        breakpoint()          # or: import pdb; pdb.set_trace()
        loan._check_availability()
```

The server stops on that line and the prompt appears in the terminal that started it. This does not work under systemd, in Docker without `-it`, or when output is piped. Run it in the foreground.

Commands you need:

| Command | Effect |
| --- | --- |
| `n` | Next line |
| `s` | Step into |
| `c` | Continue |
| `r` | Run until the current function returns |
| `l` / `ll` | Show code around the line / the whole function |
| `p expr` / `pp expr` | Print / pretty-print |
| `w` | Show the stack |
| `u` / `d` | Move up / down the stack |
| `b file:line` | Set a breakpoint |
| `q` | Quit (raises, so the request fails) |

Inside the prompt, `self`, `self.env` and the local variables are live:

```
(Pdb) self.env['library.loan'].search_count([])
(Pdb) pp self.read(['state'])
(Pdb) self.env.cr.execute("select 1"); self.env.cr.fetchall()
```

Do not call `self.env.cr.commit()` from a debugger session unless you mean it.

## Post-mortem: stop where it crashes

```bash
./odoo-bin -c odoo.conf -d mydb --workers=0 --dev=pdb
```

On an unhandled exception the process drops into `pdb` at the failing frame, with the exception state intact. Use `w` to see the stack and `u` to climb to the frame whose variables you need. This is usually quicker than guessing a breakpoint position.

## debugpy: attach an IDE

```bash
pip install debugpy
```

Add near the start of the code you want to debug, or in a small local addon:

```python
import debugpy
debugpy.listen(("127.0.0.1", 5678))
print("waiting for debugger")
debugpy.wait_for_client()
```

Or start the server through debugpy without touching code:

```bash
python -m debugpy --listen 127.0.0.1:5678 --wait-for-client ./odoo-bin -c odoo.conf -d mydb --workers=0
```

In VS Code add an "attach" configuration:

```json
{
  "name": "Attach to Odoo",
  "type": "debugpy",
  "request": "attach",
  "connect": {"host": "127.0.0.1", "port": 5678},
  "justMyCode": false
}
```

Older VS Code versions use `"type": "python"`. Set `justMyCode` to false to step into Odoo's own code. PyCharm uses a "Python Debug Server" or attaches by process.

### Debugging a remote or containerised server

Bind to `0.0.0.0` only in a private network, and prefer an SSH tunnel:

```bash
ssh -L 5678:127.0.0.1:5678 user@devserver
```

`debugpy` has no authentication. Never expose it to the internet. In Docker publish the port and map source paths with `pathMappings` so breakpoints line up.

## Debugging the shell and tests

```bash
./odoo-bin shell -d mydb --no-http          # then call breakpoint() in your own code
./odoo-bin -d mytest -i library --test-tags=/library:TestLoan --stop-after-init --workers=0
```

A test stops at `breakpoint()` the same way. Use `--test-tags` to run only the test you debug.

## Pitfalls

- **Workers.** With `--workers>0` requests run in child processes without a terminal; the breakpoint hangs or is skipped. Use `--workers=0`.
- **Request timeouts.** A request paused in a debugger can hit `--limit-time-real`. Raise it for the session.
- **Leftover breakpoints.** A `breakpoint()` committed to production blocks a worker forever. Set `PYTHONBREAKPOINT=0` in production environments as a safety net.
- **Locks.** A stopped transaction holds row locks. Others wait.
- **Reload during debugging.** `--dev=reload` restarts on file save and drops your session. Disable it when stepping.
