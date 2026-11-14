---
description: Outbound calls and inbound webhooks with a mapping layer.
---

# A REST integration

This blueprint connects Odoo to an imaginary external service, "acme-shop", that holds orders and customers. It has four parts: an outbound client with timeouts and retries, an inbound webhook controller that verifies an HMAC signature, a mapping model that links Odoo records to remote ids, and a queue drained by a cron. The queue is what keeps a slow or failing remote from blocking users or rolling back their transactions.

The module is `acme_connector`, depending on `base` and `contacts`.

```
acme_connector/
  __manifest__.py
  __init__.py
  controllers/webhook.py
  models/acme_mapping.py
  models/acme_queue.py
  models/acme_client.py
  models/res_partner.py
  data/cron.xml
  security/ir.model.access.csv
  tests/test_integration.py
```

## Configuration

Keep the base URL, token and webhook secret in `ir.config_parameter`. Never hard-code them, and never put them in a field that ordinary users can read.

```python
# models/acme_client.py
import logging
import time

import requests

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = (3.05, 15)           # (connect, read) seconds
RETRY_STATUS = {429, 502, 503, 504}
MAX_ATTEMPTS = 3


class AcmeClient(models.AbstractModel):
    _name = "acme.client"
    _description = "Acme API client"

    @api.model
    def _conf(self, key):
        return self.env["ir.config_parameter"].sudo().get_param(f"acme.{key}") or ""

    @api.model
    def _request(self, method, path, payload=None):
        base = self._conf("base_url").rstrip("/")
        if not base:
            raise UserError(self.env._("The acme base URL is not configured."))
        headers = {
            "Authorization": f"Bearer {self._conf('token')}",
            "Content-Type": "application/json",
        }
        last_exc = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = requests.request(
                    method, f"{base}/{path.lstrip('/')}",
                    json=payload, headers=headers, timeout=TIMEOUT,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
            else:
                if resp.status_code not in RETRY_STATUS:
                    resp.raise_for_status()
                    return resp.json() if resp.content else {}
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            _logger.warning("acme %s %s attempt %s failed: %s", method, path, attempt, last_exc)
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
        raise last_exc
```

`self.env._()` exists in Odoo 18. In 16 and 17 use `from odoo import _` and `_("...")`.

Three decisions in that function matter. The timeout is always a tuple: `requests` has no default timeout, and a stuck remote holds a worker until the worker's hard limit kills it. Only connection errors, timeouts and transient status codes are retried; a 400 or 404 is a bug in your payload and retrying it three times just triples the noise. The sleep is short (1s, 2s) because this code runs inside a worker. Longer backoff belongs in the queue, below.

## The mapping table

A mapping row says "this Odoo record is that remote object". Do not add `x_acme_id` fields to every model; one table works for any model and keeps the integration removable.

```python
# models/acme_mapping.py
from odoo import fields, models


class AcmeMapping(models.Model):
    _name = "acme.mapping"
    _description = "Acme record mapping"

    model = fields.Char(required=True, index=True)
    res_id = fields.Many2oneReference(model_field="model", required=True, index=True)
    remote_id = fields.Char(required=True, index=True)
    remote_kind = fields.Char(required=True)       # "customer", "order"
    remote_hash = fields.Char()                    # hash of the last synced payload

    _sql_constraints = [
        ("remote_unique", "unique(remote_kind, remote_id)",
         "A remote object can be mapped only once."),
        ("record_unique", "unique(model, res_id, remote_kind)",
         "A record can be mapped only once per kind."),
    ]

    def _lookup(self, remote_kind, remote_id):
        return self.sudo().search(
            [("remote_kind", "=", remote_kind), ("remote_id", "=", remote_id)], limit=1)

    def _for_record(self, record, remote_kind):
        return self.sudo().search([
            ("model", "=", record._name), ("res_id", "=", record.id),
            ("remote_kind", "=", remote_kind)], limit=1)
```

`_sql_constraints` works in 16 to 18 (in 19 it is superseded by `models.Constraint`; this book does not cover 19 yet). Two unique constraints give you idempotency for free: a replayed webhook cannot create a second customer, it hits the constraint or finds the existing row. The `remote_hash` column lets you skip writes when nothing changed, which matters for loop prevention.

## The queue

Do not call the remote from `write()` or `create()`. A remote outage would then block saving a partner. Enqueue instead, and let a cron do the call.

```python
# models/acme_queue.py
import hashlib
import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
MAX_TRIES = 6


class AcmeQueue(models.Model):
    _name = "acme.queue"
    _description = "Acme outbound queue"
    _order = "id"

    model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    operation = fields.Selection([("push", "Push")], default="push", required=True)
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("failed", "Failed")],
        default="pending", index=True)
    tries = fields.Integer(default=0)
    next_try = fields.Datetime(default=fields.Datetime.now, index=True)
    last_error = fields.Text()

    @api.model
    def enqueue(self, record):
        domain = [("model", "=", record._name), ("res_id", "=", record.id),
                  ("state", "=", "pending")]
        if not self.search_count(domain):          # collapse duplicates
            self.create({"model": record._name, "res_id": record.id})

    @api.model
    def _cron_process(self, batch=50):
        jobs = self.search(
            [("state", "=", "pending"), ("next_try", "<=", fields.Datetime.now())],
            limit=batch)
        for job in jobs:
            try:
                with self.env.cr.savepoint():
                    job._run()
                job.write({"state": "done", "last_error": False})
            except Exception as exc:  # noqa: BLE001 - queue must survive anything
                tries = job.tries + 1
                _logger.warning("acme job %s failed (%s): %s", job.id, tries, exc)
                job.write({
                    "tries": tries,
                    "last_error": str(exc),
                    "state": "failed" if tries >= MAX_TRIES else "pending",
                    "next_try": fields.Datetime.now() + timedelta(minutes=2 ** tries),
                })
            self.env.cr.commit()   # keep what we finished if a later job kills the worker
        if len(jobs) == batch:
            self.env.ref("acme_connector.ir_cron_acme_queue")._trigger()

    def _run(self):
        self.ensure_one()
        record = self.env[self.model].browse(self.res_id).exists()
        if not record:
            return
        payload = record._acme_payload()
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()).hexdigest()
        mapping = self.env["acme.mapping"]._for_record(record, record._acme_kind)
        if mapping and mapping.remote_hash == digest:
            return                                   # nothing changed, nothing to send
        client = self.env["acme.client"]
        if mapping:
            client._request("PUT", f"{record._acme_kind}s/{mapping.remote_id}", payload)
            mapping.remote_hash = digest
        else:
            data = client._request("POST", f"{record._acme_kind}s", payload)
            self.env["acme.mapping"].sudo().create({
                "model": record._name, "res_id": record.id,
                "remote_id": str(data["id"]), "remote_kind": record._acme_kind,
                "remote_hash": digest,
            })
```

The explicit `commit()` is allowed in cron code and is what you want here: after a successful remote call the mapping must be saved, otherwise the next run creates a duplicate remote object. The remote call itself cannot be rolled back, so keep the window between "remote succeeded" and "commit" as small as possible. `_trigger()` re-schedules the cron for an immediate run when the batch was full (it exists in 16 to 18).

The cron record:

```xml
<!-- data/cron.xml -->
<odoo noupdate="1">
  <record id="ir_cron_acme_queue" model="ir.cron">
    <field name="name">Acme: process outbound queue</field>
    <field name="model_id" ref="model_acme_queue"/>
    <field name="state">code</field>
    <field name="code">model._cron_process()</field>
    <field name="interval_number">5</field>
    <field name="interval_type">minutes</field>
  </record>
</odoo>
```

{% hint style="info" %}
Odoo 16 and 17 cron records usually carry `numbercall` (`-1`) and sometimes `doall`. The Odoo 18 source I checked no longer has those fields on `ir.cron`; drop them there, keep them in older versions.
{% endhint %}

## Hooking the model

```python
# models/res_partner.py
from odoo import api, models

SYNC_FIELDS = {"name", "email", "phone", "street", "city", "zip", "country_id"}


class ResPartner(models.Model):
    _inherit = "res.partner"
    _acme_kind = "customer"

    def _acme_payload(self):
        self.ensure_one()
        return {"name": self.name, "email": self.email or None,
                "phone": self.phone or None, "city": self.city or None}

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        if not self.env.context.get("acme_no_sync"):
            for partner in partners:
                self.env["acme.queue"].sudo().enqueue(partner)
        return partners

    def write(self, vals):
        res = super().write(vals)
        if SYNC_FIELDS & set(vals) and not self.env.context.get("acme_no_sync"):
            for partner in self:
                self.env["acme.queue"].sudo().enqueue(partner)
        return res
```

## Inbound webhook with HMAC

The remote signs the raw body with a shared secret and sends the hex digest in a header. Verify against the raw bytes, not against re-serialised JSON: key order and whitespace would change the digest.

```python
# controllers/webhook.py
import hmac
import hashlib
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AcmeWebhook(http.Controller):

    @http.route("/acme/webhook", type="http", auth="public", methods=["POST"],
                csrf=False)
    def webhook(self):
        body = request.httprequest.get_data()
        secret = request.env["acme.client"].sudo()._conf("webhook_secret")
        given = request.httprequest.headers.get("X-Acme-Signature", "")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(given, expected):
            return request.make_response("forbidden", status=403)
        try:
            event = json.loads(body)
        except ValueError:
            return request.make_response("bad json", status=400)
        self._handle(event)
        return request.make_response("ok", status=200)

    def _handle(self, event):
        env = request.env(su=True)
        env = env(context=dict(env.context, acme_no_sync=True))
        if event.get("type") != "customer.updated":
            return
        data = event["data"]
        mapping = env["acme.mapping"]._lookup("customer", str(data["id"]))
        vals = {"name": data["name"], "email": data.get("email")}
        if mapping:
            env["res.partner"].browse(mapping.res_id).write(vals)
        else:
            partner = env["res.partner"].create(vals)
            env["acme.mapping"].create({
                "model": "res.partner", "res_id": partner.id,
                "remote_id": str(data["id"]), "remote_kind": "customer"})
```

`auth="public"` is correct here: the signature is the authentication. `request.env(su=True)` is the Odoo 16 to 18 spelling for a superuser environment. Use `hmac.compare_digest`, never `==`, to avoid timing leaks.

Return quickly. If the event needs heavy work, create a queue row of another operation and answer 200; remote senders retry on timeouts and you will receive the same event twice.

## Loop prevention

Without care, the flow is: remote update, webhook writes the partner, `write()` enqueues, cron pushes back, remote fires another webhook. Three layers stop it:

1. The webhook writes with `acme_no_sync=True`, so it never enqueues.
2. The queue compares the payload hash with `mapping.remote_hash` and skips unchanged data. After an inbound write, also store the hash so the next outbound run is a no-op.
3. `enqueue` collapses duplicate pending jobs.

Layer 1 alone is not enough if the remote echoes changes caused by your own PUT; layer 2 is the one that ends the loop.

## Tests with mocked HTTP

Never let tests reach the network. Patch `requests.request` where the client uses it.

```python
# tests/test_integration.py
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from odoo.tests import HttpCase, TransactionCase, tagged


def _response(status=200, data=None):
    resp = MagicMock()
    resp.status_code = status
    resp.content = b"x"
    resp.json.return_value = data or {}
    resp.raise_for_status.side_effect = None
    return resp


@tagged("post_install", "-at_install")
class TestAcmeQueue(TransactionCase):

    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("acme.base_url", "https://acme.invalid/api")
        params.set_param("acme.token", "t")

    @patch("odoo.addons.acme_connector.models.acme_client.requests.request")
    def test_push_creates_mapping(self, mock_req):
        mock_req.return_value = _response(201, {"id": 42})
        partner = self.env["res.partner"].create({"name": "Test Customer"})
        self.env["acme.queue"]._cron_process()
        mapping = self.env["acme.mapping"]._for_record(partner, "customer")
        self.assertEqual(mapping.remote_id, "42")
        mock_req.assert_called_once()

    @patch("odoo.addons.acme_connector.models.acme_client.time.sleep")
    @patch("odoo.addons.acme_connector.models.acme_client.requests.request")
    def test_transient_error_is_retried(self, mock_req, _sleep):
        mock_req.side_effect = [_response(503), _response(200, {"id": 7})]
        data = self.env["acme.client"]._request("POST", "customers", {})
        self.assertEqual(data["id"], 7)
        self.assertEqual(mock_req.call_count, 2)

    @patch("odoo.addons.acme_connector.models.acme_client.requests.request")
    def test_unchanged_payload_is_not_resent(self, mock_req):
        mock_req.return_value = _response(201, {"id": 1})
        partner = self.env["res.partner"].create({"name": "Test Customer"})
        self.env["acme.queue"]._cron_process()
        self.env["acme.queue"].enqueue(partner)
        self.env["acme.queue"]._cron_process()
        self.assertEqual(mock_req.call_count, 1)


@tagged("post_install", "-at_install")
class TestAcmeWebhook(HttpCase):

    def _post(self, payload, secret="s3cret", sign=True):
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if sign:
            headers["X-Acme-Signature"] = hmac.new(
                secret.encode(), body, hashlib.sha256).hexdigest()
        return self.url_open("/acme/webhook", data=body, headers=headers)

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param("acme.webhook_secret", "s3cret")

    def test_rejects_bad_signature(self):
        self.assertEqual(self._post({"type": "x"}, secret="wrong").status_code, 403)

    def test_creates_partner_without_enqueue(self):
        event = {"type": "customer.updated", "data": {"id": 9, "name": "Webhook Customer"}}
        self.assertEqual(self._post(event).status_code, 200)
        partner = self.env["res.partner"].search([("name", "=", "Webhook Customer")])
        self.assertEqual(len(partner), 1)
        self.assertFalse(self.env["acme.queue"].search([("res_id", "=", partner.id)]))
```

Note one catch: a `TransactionCase` test calls `_cron_process`, which calls `self.env.cr.commit()`. In tests the cursor is a test cursor and `commit()` is neutralised, so this is safe. Keep it that way: do not open your own cursors in this code.

## Pitfalls

- **No timeout.** The most common integration bug. A hung socket holds a worker until the limit kills the request and everything it did.
- **Calling the remote inside `write()`.** Outage on their side becomes "cannot save" on yours, and a rollback after a successful call leaves the remote ahead of Odoo.
- **Verifying the signature on parsed JSON.** The digest will not match reliably. Hash the raw bytes.
- **Comparing signatures with `==`.** Use `hmac.compare_digest`.
- **Trusting remote ids as unique per kind.** Different kinds can reuse the same id; that is why the mapping key includes `remote_kind`.
- **Webhook handlers that are not idempotent.** Senders retry. Look up the mapping first.
- **Retrying non-transient errors.** A 422 will never succeed; mark the job failed and surface `last_error` to a human.
- **Forgetting multi-worker races.** Two cron runs cannot overlap on the same job because `ir.cron` locks its own row, but a webhook and the cron can touch the same partner; the unique constraints turn that race into an error rather than a duplicate.

## Try it

Run the module tests from the shell, then watch the queue:

```bash
odoo-bin -d testdb -i acme_connector --test-tags /acme_connector --stop-after-init
psql testdb -c "select state, count(*) from acme_queue group by state"
```

Related: [cron jobs and the queue pattern](../10-backend-logic/) and the [ORM chapters](../06-orm/).
