---
description: TransactionCase, tags, fixtures, and running tests.
---

# Writing tests

Odoo's test framework is `unittest` with a database-backed base class. Each test method runs inside a transaction that is rolled back, so tests are isolated and fast. This chapter covers the classes you will use, how to set up data, how to test as a specific user, and how to run only what you need.

## The base classes

All live in `odoo/tests/common.py`, re-exported from `odoo.tests`:

| Class | Use |
|---|---|
| `TransactionCase` | Default. One transaction per test method, rolled back afterwards. `setUpClass` data is shared and also rolled back at the end of the class. |
| `SingleTransactionCase` | One transaction for the whole class; tests depend on order. Rarely a good idea. |
| `HttpCase` | Adds `url_open`, `authenticate`, and browser tours. See the next chapter. |
| `BaseCase` | The parent of those; you do not subclass it directly. |

## A first test

```python
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestLibraryLoan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.book = cls.env['library.book'].create({'name': 'Test Book'})
        cls.member = cls.env['res.partner'].create({'name': 'Test Member'})

    def test_loan_sets_due_date(self):
        loan = self.env['library.loan'].create({
            'book_id': self.book.id,
            'borrower_id': self.member.id,
        })
        self.assertTrue(loan.due_date)

    def test_cannot_loan_twice(self):
        vals = {'book_id': self.book.id, 'borrower_id': self.member.id}
        self.env['library.loan'].create(vals)
        with self.assertRaises(ValidationError):
            self.env['library.loan'].create(vals)
```

Use `setUpClass` for data that tests only read. Anything a test mutates should be created inside the test, or the tests will depend on each other. Never forget `super().setUpClass()`: it sets up `cls.env` and the registry cleanup.

## Tags

`@tagged` selects when and under what label a test runs. By default, tests are `standard` and `at_install`: they run right after their module is installed, before other modules. For tests that need the whole registry (inherits from other modules, HTTP), use `post_install` and remove `at_install`:

```python
@tagged('post_install', '-at_install')
```

You can add custom tags (`@tagged('library_slow')`) and select with `--test-tags`. The default set is `standard`, so untagged tests always run.

{% hint style="info" %}
Versions: `@tagged`, `post_install`, `at_install` and the `-tag` exclusion syntax are the same in 16, 17 and 18. `HttpCase` logs a warning if it is not `post_install` (from `common.py`).
{% endhint %}

## Running tests

Run a module's tests on a throwaway database, never on production:

```bash
odoo-bin -d test_db -i library --test-enable --stop-after-init
odoo-bin -d test_db -u library --test-tags /library --stop-after-init
odoo-bin -d test_db --test-tags /library:TestLibraryLoan.test_cannot_loan_twice -u library --stop-after-init
```

The tag selector format is `[-][tag][/module][:class][.method]`. `--test-enable` is implied by `--test-tags` in recent versions; keeping it is harmless. Use `--log-level=test` for more test output. On Odoo.sh the test run happens in the build; read the build log's "Tests" section.

## Testing as a user

```python
def test_employee_cannot_delete(self):
    employee = self.env['res.users'].create({
        'name': 'Plain Employee', 'login': 'plain_emp',
        'groups_id': [(6, 0, [self.env.ref('library.group_library_user').id])],
    })
    loan = self.env['library.loan'].create({...})
    with self.assertRaises(AccessError):
        loan.with_user(employee).unlink()
```

`with_user` accepts a user record or id; `self.env['x'].with_user(self.env.ref('base.user_demo'))` also works if demo data is loaded, but don't depend on demo. Create your users in `setUpClass`.

If you create users, use `new_test_user` from `odoo.addons.mail.tests.common` where mail is a dependency: it handles groups and avoids notification side effects. Otherwise, set `no_reset_password=True` in the context to prevent invitation mails.

## Assertions worth knowing

- `assertRecordValues(records, [{'field': value}, ...])` compares recordsets against dicts and reports diffs clearly. Order matters unless you sort.
- `assertQueryCount(admin=3)` fixes the SQL query count for a block, a cheap regression guard against N+1.
- `with self.assertRaises(...)` is wrapped by Odoo to use a savepoint, so the transaction stays usable after the exception. Plain `unittest` doesn't do this.
- `Form(record)` from `odoo.tests` simulates the form view: onchanges, defaults, required fields, readonly rules.

```python
from odoo.tests import Form

with Form(self.env['library.loan']) as f:
    f.book_id = self.book
    f.borrower_id = self.member
loan = f.save()
```

`Form` fails if a field is not in the view or is readonly, which makes it useful for testing that the view is usable, not just the model.

## Time and mail

Freeze time with `freezegun` when the dependency exists (`from freezegun import freeze_time`), or use the Odoo helpers in `odoo.tests.common` (`freeze_time` is re-exported in recent versions). Mail sent in tests is not delivered; the mail queue is mocked in the framework, and `mail.mail` records can be inspected. Crons are not run automatically: call `self.env.ref('library.cron_overdue')._trigger()` is not enough, call the method directly.

## Pitfalls

{% hint style="warning" %}
A test that passes alone and fails in the suite is almost always shared state: a record created in `setUpClass` and mutated, a cached `ir.config_parameter`, or a registry-level change. Make tests independent first.
{% endhint %}

- **`cr.commit()` in code under test.** In tests the cursor is wrapped, so the commit is a no-op; code that relies on committed data in a second cursor will behave differently.
- **Testing as admin only.** The superuser skips ACLs and rules. A test that never switches user proves nothing about security.
- **Relying on demo data.** The test database may be created without demo. Create what you need.
- **`at_install` tests that depend on other modules.** They run before later modules install. Use `post_install`.
- **Too many assertions on dates.** `fields.Date.today()` changes at midnight. Fix the date explicitly.

## Try it

Run only one test class and see its SQL count on a scratch database:

```bash
odoo-bin -d scratch -u library --test-tags /library:TestLibraryLoan --stop-after-init --log-level=test
```
