---
icon: meetup
---

# Environment & Setup

## 🛠️ Environment & Setup (Odoo 18)

> Status: CRITICAL PATH | Focus: LOCAL RESILIENCE

When the cloud goes dark and remote servers are unreachable, your local machine becomes your only sanctuary. A misconfigured development environment will mask critical errors, hide PostgreSQL deadlocks, and inevitably lead to catastrophic deployment failures when systems come back online.

You must forge a local environment that strictly mirrors production stress while remaining deeply transparent for debugging. This section dictates the absolute baseline for a resilient Odoo 18 local setup.

#### 🎛️ 1. The Doomsday `odoo.conf`

Never rely on default parameters. The default Odoo configuration is designed for basic testing, not enterprise-grade module development. Your `odoo.conf` must explicitly control memory limits, enforce debug logging, and manage worker threads.

Architectural Rule: During active development, set `workers = 0`. This forces Odoo into single-threaded mode, allowing your IDE debugger (VSCode/PyCharm) to reliably attach to breakpoints without getting lost across multiple core processes.

Ini, TOML

```python
[options]
; Credenziali di accesso al database locale PostgreSQL
db_host = localhost
db_port = 5432
db_user = odoo
db_password = super_secure_password

; Percorsi assoluti (separati da virgola, senza spazi)
addons_path = /opt/odoo/odoo/addons,/opt/odoo/custom_addons

; Attivazione della modalità sviluppatore profonda con auto-reload
dev_mode = reload
log_level = debug

; Limiti di memoria e timeout (Cruciali per testare i batch processing)
; In caso di loop infiniti, il server ucciderà il processo per proteggere la CPU
limit_time_cpu = 600
limit_time_real = 1200
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648

; Single-thread mode per permettere al debugger di intercettare le chiamate
workers = 0
```

#### 💻 2. The Command Line Arsenal

When the graphical user interface (UI) crashes due to a corrupted XML view, you cannot rely on the browser to fix it. You must control the server directly from the terminal.

Navigate to your Odoo core directory and utilize these precise execution flags:

The Standard Development Boot:

Bash

```bash
# Avvio del server puntando a un database specifico
python3 odoo-bin -c /etc/odoo.conf -d my_doomsday_db
```

The Surgical Module Update:

Never restart the server and hope the UI updates. Force the framework to reload your specific XML and Python logic directly.

Bash

```bash
# L'opzione -u forza l'aggiornamento del modulo scavalcando la cache
python3 odoo-bin -c /etc/odoo.conf -d my_doomsday_db -u custom_doomsday_module
```

#### 🐚 3. The Odoo Shell: Your Offline Oracle

If the AI is dead and StackOverflow is unreachable, how do you test ORM queries or debug `self.env` variables? You use the Odoo Interactive Shell. This bypasses the web interface entirely, connecting a Python terminal directly to your live PostgreSQL database with a fully loaded Odoo environment.

Execute this in your terminal:

Bash

```bash
python3 odoo-bin shell -c /etc/odoo.conf -d my_doomsday_db
```

Once inside, you have absolute power over the ORM. You can test your logic safely before hardcoding it into your models:

Python

```python
# Esempio di utilizzo della shell per verificare i dati senza interfaccia UI
# 1. Ottenere l'ambiente utente
env.user.name

# 2. Testare una query complessa sui partner
partners = env['res.partner'].search([('is_company', '=', True)], limit=5)
for p in partners:
    print(p.display_name)

# 3. Forzare un commit manuale se si alterano i dati (usare con cautela estrema)
# env.cr.commit()
```

#### 🐞 4. IDE Debugging (VSCode `launch.json`)

`print()` statements are an amateur's tool. When diagnosing bidirectional sync failures or infinite data loops, you need to freeze time, inspect the execution stack, and evaluate `self.env.context` on the fly.

Place this configuration in your `.vscode/launch.json` file. It binds Visual Studio Code directly to the Odoo binary.

JSON

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Odoo 18 - Doomsday Debugger",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/odoo/odoo-bin",
            "args": [
                "-c",
                "${workspaceFolder}/odoo.conf",
                "-d",
                "my_doomsday_db",
                "-u",
                "custom_doomsday_module"
            ],
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}",
            "justMyCode": false
        }
    ]
}
```

_Note: Setting `"justMyCode": false` is critical. It allows your debugger to step down into Odoo's core framework files (like `models.py` or `fields.py`) so you can understand exactly how the system is behaving under the hood._
