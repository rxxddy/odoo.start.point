# How to Handle External Modules

## 📦 How to Handle External Modules

> Status: DEPENDENCY MANAGEMENT | Focus: ECOSYSTEM SURVIVAL

In a true isolated environment, your greatest vulnerability is not the code you wrote, but the code you _didn't_ write.

Relying on external Odoo apps (like OCA modules) or third-party Python libraries (like `requests` or `zeep`) introduces fatal points of failure. If an external library is missing when the Odoo server boots, the entire instance will crash with a traceback, taking all other functional modules down with it.

To survive, you must manage external dependencies with absolute defensive precision. Here is how to bind your module to the outside world without letting it drag you down.

#### 🪢 1. Odoo Module Dependencies (The `depends` Array)

If your custom module modifies a view or a model from another Odoo app (e.g., you are adding a field to `sale.order`), you must explicitly declare that app as a dependency.

If you do not, Odoo might load your module _before_ the Sales module, resulting in a fatal `Model not found` error.

In your `__manifest__.py`:

Python

```python
    # The 'depends' array dictates the exact loading sequence.
    # Odoo will ensure all these modules are fully installed and loaded BEFORE yours.
    'depends': [
        'base',           # The core framework (always required)
        'sale_management', # Required if you inherit 'sale.order'
        'stock',          # Required if you inherit 'stock.picking'
        # 'delivery_dhl'  # Example of a third-party or OCA module dependency
    ],
```

The Doomsday Rule: Keep your `depends` array as small as mathematically possible. Every module you add here is a module that _must_ exist and function perfectly for your code to run.

#### 🐍 2. Python Library Dependencies (`external_dependencies`)

If your module requires a specialized Python library (for example, `paramiko` for SFTP transfers, or `phonenumbers` for validation), you must warn the Odoo framework.

Do not just `import` it in your Python files and hope the server admin ran `pip install`.

Declare it in your `__manifest__.py` using the `external_dependencies` dictionary. If the library is missing from the host machine, Odoo will gracefully refuse to install the module and will show a clear UI warning instead of crashing the server loop.

Python

```python
    # __manifest__.py
    
    # Instructs the Odoo framework to check the host machine's Python environment
    # before attempting to install or upgrade this module.
    'external_dependencies': {
        'python': [
            'requests',      # Used for REST API calls
            'zeep',          # Used for SOAP API calls (e.g., Courier integrations)
            'cryptography'   # Used for payload encryption
        ],
        'bin': [
            'ffmpeg'         # Checks for system-level binary dependencies (rare but powerful)
        ]
    },
```

#### 🛡️ 3. Defensive Imports (The Architect's Way)

Even with manifest declarations, a Senior Architect never assumes an external Python library will load perfectly.

When writing the actual Python code, you must use Defensive Importing. This means wrapping your imports in a `try/except` block. This prevents the `.py` file from crashing the Odoo registry during the initial compile phase.

Python

```python
import logging
from odoo import models, fields, exceptions, _

_logger = logging.getLogger(__name__)

# 1. DEFENSIVE IMPORT BLOCK
# Attempt to import the external library. 
try:
    import zeep
    ZEEP_INSTALLED = True
except ImportError:
    # If it fails, do not crash. Flag it, log it, and continue loading the model.
    ZEEP_INSTALLED = False
    _logger.warning("The 'zeep' Python library is missing. SOAP integrations will fail.")


class CourierIntegration(models.Model):
    _name = 'courier.integration'
    _description = "External API Dispatcher"

    name = fields.Char(string="Connection Name", required=True)

    def action_ping_courier_api(self):
        # 2. RUNTIME VALIDATION
        # Block the user gracefully at runtime if the dependency is missing,
        # rather than letting the code crash deep inside a transaction.
        if not ZEEP_INSTALLED:
            raise exceptions.UserError(
                _("Critical Dependency Missing: Please contact the system administrator to install the 'zeep' Python library.")
            )
            
        # 3. SAFE EXECUTION
        # If we reach this point, we know the library is safe to use.
        try:
            client = zeep.Client(wsdl="https://ws.dhl.com/soap?wsdl")
            # ... execute API logic ...
            
        except Exception as e:
            _logger.exception("SOAP API connection failed: %s", str(e))
            raise exceptions.UserError(_("Failed to connect to the external courier API."))
```

#### 🧩 Summary of Survival

1. Odoo Apps: Put them in `depends`.
2. Python `pip` Packages: Put them in `external_dependencies['python']`.
3. Execution Safety: Wrap your imports in `try/except ImportError` and block the execution gracefully in the method, not at the top of the file.
