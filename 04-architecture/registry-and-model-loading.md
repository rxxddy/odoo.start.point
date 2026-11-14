---
description: How classes become one model, and what happens at startup.
---

# Registry and model loading

An Odoo model is not a single Python class. It is the result of combining every class that declares or extends the same `_name`, across every installed module, into one class built at runtime. That combined set of models, one per database, is the registry. Most "my override is ignored" and "field not found" problems are explained by how the registry is built, so this chapter walks through it.

## One registry per database

Each database served by a process has its own `Registry` object (`odoo.modules.registry.Registry`). It holds the final model classes, the field definitions, the SQL constraints, the cache, and signals for cross-process invalidation. Two databases on the same server can have different modules installed, so `env['library.book']` is a different class in each.

Consequences you will meet:

- Code at module import time cannot know which database it is for. Never read the database at import. Do it in methods or in `_register_hook`.
- Memory grows with the number of loaded databases. Multi-database servers with many large registries need an eye on `--limit-memory-*` and on `--db-filter`.

## From classes to a model

When Odoo loads a module, importing its Python files defines classes. A metaclass records each one in the module's list. Then, for each model in the module, the registry runs `_build_model`:

```python
class LibraryBook(models.Model):            # defines
    _name = 'library.book'
    name = fields.Char()

class LibraryBookExt(models.Model):         # extends in place
    _inherit = 'library.book'
    isbn = fields.Char()

class LibraryBookMixin(models.Model):       # inherits another model by copy
    _name = 'library.rare.book'
    _inherit = ['library.book', 'mail.thread']
```

- A class with `_name` only defines a new model.
- A class with `_inherit` and no `_name`, or with `_name` equal to one of the parents, extends that model in place.
- A class with a new `_name` and `_inherit` creates a new model that copies the parents' fields and methods (prototype inheritance). The new table is separate.
- `_inherits = {'parent.model': 'parent_id'}` is delegation: the child has its own table and exposes the parent's fields through a many2one. It is a different mechanism, rarely what you want.

The final class is built by creating a new Python class whose bases are all the extension classes in load order, followed by the original definition. That is why `super()` in an override reaches the code from modules loaded earlier: the MRO is the module load order, reversed.

## Load order decides override order

Modules are loaded in dependency order. Among modules at the same depth, the order is by sequence and then by name; it is deterministic but you should not depend on it. If module A and B both override `library.book.write` and neither depends on the other, which runs first is unspecified.

```python
class LibraryBook(models.Model):
    _inherit = 'library.book'

    def write(self, vals):
        # runs before the code of every module loaded earlier
        res = super().write(vals)
        # runs after
        return res
```

Rule: if you need to run after or before another module's override, depend on that module in `depends`. Do not rely on alphabetical order.

## What happens at startup

The loader in `odoo/modules/loading.py` does this for each database, in simplified order:

1. Load `base` and set up the registry.
2. For each module in dependency order: import Python package, build its models, create or update tables and columns (`_auto_init`), load data files, run hooks.
3. After all modules of the batch are loaded, finalize: `_setup_complete`, add constraints, create indexes, compute stored fields that were added, and call `_register_hook` on every model.
4. Run post-install tests if enabled.
5. When the registry is ready, the server starts serving requests for the database.

Schema changes are made during step 2, per module. A field added in your module gets its column on update, not at ordinary startup. That is why Python code changes need only a restart, while model changes need `-u`.

{% hint style="info" %}
Versions: from 17 on, many tables and column definitions follow the same flow but index creation and some constraint handling moved into dedicated steps (for example, `_sql_constraints` is still honoured in 17 and 18; check your branch if you are touching the schema code itself). The registry-building idea is identical across 16, 17 and 18.
{% endhint %}

## Lazy loading and reload

On first request after startup, registries are created lazily per database. If a request arrives for a database whose registry is not loaded, it is loaded then and the user waits. On large installations, this means the first request after a restart can take tens of seconds.

When a module is installed, updated or uninstalled in a running multi-process server, the process that did it reloads its own registry and records a signal in the database (the `ir_sequence` rows named `base_registry_signaling` and `base_cache_signaling`). Other workers check those sequences at the start of each request and reload when they changed. This is how a running pool converges after an update without restarts. It is also why a long-running worker can briefly use stale code or stale cache after another process changed the database.

## Registry hooks you can use

| Hook | When | Use |
|---|---|---|
| `_register_hook` | After the registry is complete, every time it is loaded | Patching methods dynamically, setting up one-time per-registry state |
| `_auto_init` | During schema update | Rarely overridden; use `init()` to create SQL views |
| `init()` | After table creation | Create database views or indexes for `_auto = False` models |
| `post_init_hook` (manifest) | After install, once | Data fixups |

## Pitfalls

{% hint style="warning" %}
Never import another module's models in a way that creates a hard dependency without declaring it in `depends`. The import works when the module is installed, and crashes the registry build when it is not.
{% endhint %}

- **Class-level state.** Mutable class attributes are shared by every database in the process. Keep state on the environment or in the database, not on the class.
- **Overriding without `super()`.** The extension chain is a chain only if everyone calls `super()`. Skipping it silently disables every module loaded earlier.
- **Field type change in an extension.** Redefining a field with a different type is allowed and rebuilds the column on update; for large tables this is a long, locking migration.
- **`_inherit` typo.** An unknown `_inherit` name raises at load: `Model 'library.bok' does not exist in registry`. A correct name from a module you forgot to put in `depends` raises the same.
- **Computed stored fields on update.** Adding a stored computed field recomputes it for all rows during `-u`. On large tables, set the column first in a migration, or compute in batches.

## Try it

```bash
odoo-bin shell -d dev <<'PY'
Book = env['library.book']
print(type(Book).__mro__)           # the combined class and its bases
print(env.registry.models.keys() & {'library.book', 'library.loan'})
print([c.__module__ for c in type(Book).__mro__ if c.__module__.startswith('odoo.addons')])
PY
```

The last line lists the modules contributing to the model, in override order.
