---
description: "Validating and loading a customer file with a preview step."
---

# Spreadsheet import

The built-in import screen is fine for admins who know the field names. It is the wrong tool when a customer sends a file in their own format and expects a clear answer: which rows are wrong, why, and what will be created. This blueprint builds a wizard that uploads a CSV or XLSX, validates every row into a preview with per-row errors, and only then creates records in batches, each batch protected by a savepoint.

The example imports contacts into `res.partner` from columns `name`, `email`, `phone`, `country` (ISO code) and `vat`. Module name: `partner_import`, depending on `base`.

## Design

Two models:

- `partner.import.wizard` (transient): holds the file, the options, and the state (`upload`, `preview`, `done`).
- `partner.import.line` (transient): one row per parsed input row with its values, its error text and its status.

Validation and creation are separate steps. Validation never writes business records, so it is safe to repeat. Creation re-reads the preview lines, not the file, so what the user saw is what gets created.

## Models

```python
# models/import_wizard.py
import base64
import csv
import io
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

COLUMNS = ["name", "email", "phone", "country", "vat"]
BATCH = 100


class PartnerImportWizard(models.TransientModel):
    _name = "partner.import.wizard"
    _description = "Partner import wizard"

    file = fields.Binary(required=True, attachment=False)
    filename = fields.Char()
    state = fields.Selection(
        [("upload", "Upload"), ("preview", "Preview"), ("done", "Done")],
        default="upload")
    line_ids = fields.One2many("partner.import.line", "wizard_id")
    valid_count = fields.Integer(compute="_compute_counts")
    error_count = fields.Integer(compute="_compute_counts")
    created_count = fields.Integer()
    skip_errors = fields.Boolean(
        string="Import valid rows only",
        help="If unchecked, nothing is created while any row has an error.")

    @api.depends("line_ids.error")
    def _compute_counts(self):
        for wiz in self:
            wiz.error_count = len(wiz.line_ids.filtered("error"))
            wiz.valid_count = len(wiz.line_ids) - wiz.error_count

    # -- parsing -----------------------------------------------------------

    def _read_rows(self):
        """Return a list of dicts keyed by lower-cased header."""
        self.ensure_one()
        raw = base64.b64decode(self.file)
        name = (self.filename or "").lower()
        if name.endswith(".xlsx"):
            return self._read_xlsx(raw)
        return self._read_csv(raw)

    def _read_csv(self, raw):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            raise UserError(self.env._("The file is empty."))
        return [
            {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            for row in reader
        ]

    def _read_xlsx(self, raw):
        try:
            import openpyxl
        except ImportError:
            raise UserError(self.env._("XLSX support needs the openpyxl library."))
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = book.active
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            raise UserError(self.env._("The file is empty."))
        keys = [str(h or "").strip().lower() for h in header]
        out = []
        for values in rows:
            if all(v in (None, "") for v in values):
                continue
            out.append({k: ("" if v is None else str(v).strip())
                        for k, v in zip(keys, values)})
        return out

    # -- step 1: validate ---------------------------------------------------

    def action_validate(self):
        self.ensure_one()
        rows = self._read_rows()
        if not rows:
            raise UserError(self.env._("The file has no data rows."))
        missing = [c for c in ("name",) if c not in rows[0]]
        if missing:
            raise UserError(self.env._(
                "Missing required column(s): %s", ", ".join(missing)))

        countries = {c.code: c.id for c in self.env["res.country"].search([])}
        existing = set(self.env["res.partner"].search(
            [("email", "!=", False)]).mapped(lambda p: (p.email or "").lower()))
        seen = set()
        self.line_ids.unlink()
        vals_list = []
        for number, row in enumerate(rows, start=2):   # row 1 is the header
            errors = []
            name = row.get("name", "")
            email = row.get("email", "").lower()
            code = row.get("country", "").upper()
            if not name:
                errors.append(self.env._("Name is required."))
            if email and "@" not in email:
                errors.append(self.env._("Invalid email."))
            if email in seen:
                errors.append(self.env._("Duplicate email in the file."))
            elif email and email in existing:
                errors.append(self.env._("A contact with this email already exists."))
            if code and code not in countries:
                errors.append(self.env._("Unknown country code %s.", code))
            if email:
                seen.add(email)
            vals_list.append({
                "wizard_id": self.id,
                "row_number": number,
                "name": name,
                "email": email,
                "phone": row.get("phone", ""),
                "country_id": countries.get(code),
                "vat": row.get("vat", ""),
                "error": "\n".join(errors) or False,
            })
        self.env["partner.import.line"].create(vals_list)
        self.state = "preview"
        return self._reopen()

    # -- step 2: create -----------------------------------------------------

    def action_import(self):
        self.ensure_one()
        if self.error_count and not self.skip_errors:
            raise UserError(self.env._(
                "%s row(s) have errors. Fix the file, or tick "
                "'Import valid rows only'.", self.error_count))
        lines = self.line_ids.filtered(lambda l: not l.error and not l.partner_id)
        created = 0
        for start in range(0, len(lines), BATCH):
            batch = lines[start:start + BATCH]
            created += self._import_batch(batch)
        self.write({"created_count": created, "state": "done"})
        return self._reopen()

    def _import_batch(self, batch):
        """Create one batch. On failure, retry row by row to isolate the bad one."""
        try:
            with self.env.cr.savepoint():
                self._create_partners(batch)
            return len(batch)
        except Exception:  # noqa: BLE001
            _logger.info("batch failed, falling back to row-by-row", exc_info=True)
        done = 0
        for line in batch:
            try:
                with self.env.cr.savepoint():
                    self._create_partners(line)
                done += 1
            except Exception as exc:  # noqa: BLE001
                line.error = str(exc)
        return done

    def _create_partners(self, lines):
        partners = self.env["res.partner"].create([{
            "name": l.name,
            "email": l.email or False,
            "phone": l.phone or False,
            "country_id": l.country_id.id,
            "vat": l.vat or False,
        } for l in lines])
        for line, partner in zip(lines, partners):
            line.partner_id = partner

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_back(self):
        self.line_ids.unlink()
        self.state = "upload"
        return self._reopen()


class PartnerImportLine(models.TransientModel):
    _name = "partner.import.line"
    _description = "Partner import preview line"
    _order = "row_number"

    wizard_id = fields.Many2one("partner.import.wizard", ondelete="cascade", required=True)
    row_number = fields.Integer()
    name = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    country_id = fields.Many2one("res.country")
    vat = fields.Char()
    error = fields.Text()
    partner_id = fields.Many2one("res.partner")
```

```python
# models/__init__.py
from . import import_wizard
```

## The view

```xml
<!-- views/import_wizard_views.xml -->
<odoo>
  <record id="partner_import_wizard_form" model="ir.ui.view">
    <field name="name">partner.import.wizard.form</field>
    <field name="model">partner.import.wizard</field>
    <field name="arch" type="xml">
      <form>
        <field name="state" invisible="1"/>
        <group invisible="state != 'upload'">
          <field name="file" filename="filename"/>
          <field name="filename" invisible="1"/>
        </group>
        <group invisible="state != 'preview'">
          <field name="valid_count"/>
          <field name="error_count"/>
          <field name="skip_errors" invisible="error_count == 0"/>
        </group>
        <group invisible="state != 'done'">
          <field name="created_count"/>
        </group>
        <field name="line_ids" invisible="state == 'upload'" readonly="1">
          <list decoration-danger="error" decoration-success="partner_id">
            <field name="row_number"/>
            <field name="name"/>
            <field name="email"/>
            <field name="country_id"/>
            <field name="error"/>
            <field name="partner_id" optional="hide"/>
          </list>
        </field>
        <footer>
          <button string="Validate" type="object" name="action_validate"
                  class="btn-primary" invisible="state != 'upload'"/>
          <button string="Import" type="object" name="action_import"
                  class="btn-primary" invisible="state != 'preview'"/>
          <button string="Back" type="object" name="action_back"
                  invisible="state != 'preview'"/>
          <button string="Close" special="cancel"/>
        </footer>
      </form>
    </field>
  </record>

  <record id="partner_import_wizard_action" model="ir.actions.act_window">
    <field name="name">Import contacts</field>
    <field name="res_model">partner.import.wizard</field>
    <field name="view_mode">form</field>
    <field name="target">new</field>
  </record>

  <menuitem id="menu_partner_import" name="Import contacts"
            parent="contacts.menu_contacts" action="partner_import_wizard_action"/>
</odoo>
```

{% hint style="info" %}
The `<list>` tag and bare `invisible="state != 'upload'"` expressions are Odoo 17 and 18 syntax. In Odoo 16 the tag is `<tree>` and conditions are written `attrs="{'invisible': [('state', '!=', 'upload')]}"`. Add `contacts` to the manifest depends for the menu parent.
{% endhint %}

Access rights: transient models need no `ir.model.access.csv` rows in 16 to 18, but the user opening the wizard needs create rights on `res.partner`. Restrict the menu with `groups="base.group_system"` or a dedicated group if only some users may import.

## Test

```python
# tests/test_import.py
import base64

from odoo.tests import TransactionCase, tagged

CSV = (
    "name,email,phone,country,vat\n"
    "Test One,one@example.test,111,BE,\n"
    ",missing@example.test,,BE,\n"
    "Test Three,bad-email,,XX,\n"
    "Test Four,one@example.test,,,\n"
)


@tagged("post_install", "-at_install")
class TestPartnerImport(TransactionCase):

    def _wizard(self, text=CSV):
        return self.env["partner.import.wizard"].create({
            "file": base64.b64encode(text.encode()),
            "filename": "contacts.csv",
        })

    def test_validation_reports_each_error(self):
        wiz = self._wizard()
        wiz.action_validate()
        self.assertEqual(wiz.valid_count, 1)
        self.assertEqual(wiz.error_count, 3)
        by_row = {l.row_number: l.error for l in wiz.line_ids}
        self.assertIn("Name is required", by_row[3])
        self.assertIn("Unknown country", by_row[4])
        self.assertIn("Duplicate email", by_row[5])

    def test_blocks_when_errors_unless_skipping(self):
        wiz = self._wizard()
        wiz.action_validate()
        with self.assertRaises(Exception):
            wiz.action_import()
        wiz.skip_errors = True
        wiz.action_import()
        self.assertEqual(wiz.created_count, 1)
        self.assertTrue(self.env["res.partner"].search([("email", "=", "one@example.test")]))

    def test_bad_row_does_not_lose_batch(self):
        wiz = self._wizard("name,email\nTest A,a@example.test\nTest B,b@example.test\n")
        wiz.action_validate()
        original = type(wiz)._create_partners

        def flaky(self_, lines):
            if lines[:1].name == "Test B" or len(lines) > 1:
                raise ValueError("boom")
            return original(self_, lines)

        type(wiz)._create_partners = flaky
        try:
            wiz.action_import()
        finally:
            type(wiz)._create_partners = original
        self.assertEqual(wiz.created_count, 1)
        self.assertEqual(wiz.line_ids.filtered("error").mapped("name"), ["Test B"])
```

## Pitfalls

- **Encoding.** Spreadsheet exports from desktop tools are often cp1252 or UTF-8 with a BOM. `utf-8-sig` strips the BOM; the latin-1 fallback never fails, so check names visually in the preview.
- **Delimiter.** Many locales export `;`. `csv.Sniffer` can guess wrong on tiny files; fall back to `csv.excel` as above and show the preview so a wrong split is visible.
- **XLSX types.** `str(v)` turns the number 1234 into `1234` but a float cell into `1234.0`, and dates into datetime strings. Format-sensitive columns (phone, VAT, codes) should be text cells, or parse them explicitly.
- **Validating against a stale state.** The preview is computed at one moment. The import step creates rows later; a unique constraint may still fire. That is why the batch falls back to row-by-row inside savepoints.
- **A savepoint is not a commit.** If the whole request fails after the loop, everything rolls back, including batches that "succeeded". For very large files, commit between batches in a cron or a queue ([see the REST blueprint](blueprint-rest-integration.md)) rather than in the wizard.
- **Memory and time.** A request has a time limit. Beyond a few thousand rows, store the file in an attachment and process it from a cron, reporting progress on a record.
- **Transient cleanup.** Wizard and line records are vacuumed by `ir.autovacuum`; do not keep anything you need as an audit trail in them. Log the result to the chatter or a real model if you must.
- **Open-ended `except Exception`.** Acceptable around a savepoint where you record the message per row; never elsewhere.
- **`mapped(lambda ...)` on all partners with an email** loads every partner. For a big database, query only the emails present in the file with `search_read([("email", "in", emails)], ["email"])`.

## Try it

Create `contacts.csv` with a good row, a row with no name and one with an unknown country. Open the wizard, upload, press Validate and confirm the three rows are coloured and annotated. Then check what was created:

```bash
psql testdb -c "select id, name, email from res_partner order by id desc limit 5"
```

Related: [ORM batch creation](../06-orm/) and [backend logic](../10-backend-logic/).
