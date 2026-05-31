---
icon: compass
---

# The Perfect Module Boilerplate

## 🏗️ The Perfect Module Boilerplate

> Status: CORE INFRASTRUCTURE | Focus: ARCHITECTURAL HYGIENE

When external networks fail and the clock is ticking on a critical production deployment, you do not have the luxury of debugging a missing dependency or a circular import. A structurally flawless boilerplate is your absolute foundation. If the skeleton is weak, the entire ERP ecosystem will collapse under load.

This page dictates the uncompromising standards for scaffolding an Odoo 18 module.

#### 📂 1. The Immutable Directory Structure

An enterprise-grade Odoo module must be predictable. Any developer—or you, reading this during a crisis—should know exactly where business logic, security rules, and interface modifications reside.

Create this exact tree when initializing a new extension:

Plaintext

```
custom_doomsday_module/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── main.py              # Thin webhook routers and API endpoints
├── data/
│   └── scheduled_crons.xml  # Automated actions and system parameters
├── models/
│   ├── __init__.py
│   └── custom_model.py      # Heavy business logic and ORM definitions
├── security/
│   ├── ir.model.access.csv  # Base access rights (Loaded FIRST)
│   └── record_rules.xml     # Multi-company and user-level restrictions
├── static/
│   ├── description/
│   │   └── icon.png         # Module identifier
│   └── src/
│       ├── js/              # OWL components and client-side logic
│       └── xml/             # QWeb frontend templates
├── views/
│   ├── custom_views.xml     # Form, Tree, Kanban structures
│   └── menus.xml            # Action windows and menuitems
└── wizards/
    ├── __init__.py
    └── custom_wizard.py     # TransientModels for interactive pop-ups
```

#### ⚙️ 2. The `__manifest__.py`: The Heartbeat

The manifest is not just a configuration file; it is the execution blueprint. It dictates the load order of your XML files and strict dependencies. A mistake here will cause fatal server crashes upon installation.

Strict Protocol: As an established standard for all production and work-related Odoo environments, inline code comments within the module ecosystem must be written in Italian to maintain consistency across professional codebases.

Python

```python
# __manifest__.py
# Questo manifesto definisce la struttura base e le dipendenze assolute del modulo.
{
    'name': 'Doomsday Core Extension',
    'version': '18.0.1.0.0',
    'category': 'Hidden/Dependency',
    'summary': 'Unbreakable boilerplate for emergency ERP deployments.',
    'description': """
        Provides the foundational architecture for downstream extensions.
        Enforces strict load orders and prevents circular dependencies.
    """,
    'author': 'Senior Architect',
    'depends': [
        'base', 
        'mail', 
        'web'
    ],
    'data': [
        # 1. I file di sicurezza devono SEMPRE essere caricati per primi
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        
        # 2. Struttura del menu e actions
        'views/menus.xml',
        
        # 3. Viste UI (Form, Tree, Search)
        'views/custom_views.xml',
        
        # 4. Dati di base e Crons (caricati con noupdate="1")
        'data/scheduled_crons.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Iniezione di script JS o stili SCSS per il backend
            # 'custom_doomsday_module/static/src/js/core_logic.js',
        ],
    },
    # Hook di sistema per logica complessa post-installazione
    'post_init_hook': '_execute_post_install_routines',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

#### 🔌 3. The `__init__.py`: The Loading Sequence

The root `__init__.py` file must load the Python directories in the correct sequence. Models must be loaded before controllers, as controllers often invoke model logic.

Python

```python
# __init__.py
# Importazione sequenziale dei layer dell'architettura
from . import models
from . import wizards
from . import controllers
from . import hooks
```

Inside your `models/__init__.py`, import your files sequentially based on their internal dependencies:

Python

```python
# models/__init__.py
# I modelli base (mixins/abstract) devono precedere i modelli concreti
from . import abstract_base_model
from . import custom_model
```

#### ⚓ 4. The Post-Init Hook (Advanced Rescue Operations)

Sometimes, simply installing a module isn't enough. You might need to retroactively populate database tables, calculate historical fields, or trigger an external API the moment the module goes live.

We achieve this cleanly without cluttering the models by using a `post_init_hook`.

Create a file named `hooks.py` in your module root:

Python

```python
# hooks.py
from odoo import api, SUPERUSER_ID

def _execute_post_install_routines(env):
    """
    Questo hook viene eseguito automaticamente dal framework 
    immediatamente dopo l'installazione del modulo.
    """
    # Utilizziamo sudo() per garantire i permessi massimi durante il setup
    # Esempio: Inizializzare configurazioni o migrare record storici
    
    # env['custom.model'].sudo()._run_initial_migration()
    pass
```

> The Butterfly Effect Warning: Keep your `post_init_hook` lightweight. If the hook runs complex queries over millions of records without batching, the installation process will time out, rolling back the entire transaction and leaving the database in an inconsistent state.
