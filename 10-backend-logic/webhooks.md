---
description: Verification, idempotency, and fast acknowledgement.
---

# Receiving webhooks

A webhook is an HTTP request someone else sends to you when something happens. The sender expects a fast answer, retries when it does not get one, and may deliver the same event twice. A reliable receiver does three things: verifies the sender, acknowledges quickly, and processes each event exactly once.

## Verify the signature

Anyone can post to a public URL. Senders prove who they are by signing the raw body with a shared secret, typically HMAC-SHA256 in a header. Verify against the raw bytes, before parsing:

```python
import hashlib
import hmac
import json

import psycopg2

from odoo import http
from odoo.http import request
from odoo.tools import consteq


class LibraryWebhook(http.Controller):

    @http.route("/library/webhook", type="http", auth="public",
                methods=["POST"], csrf=False)
    def receive(self):
        body = request.httprequest.get_data()  # raw bytes
        secret = request.env["ir.config_parameter"].sudo().get_param(
            "library_sync.webhook_secret", ""
        ).encode()
        sent = request.httprequest.headers.get("X-Signature", "")
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not secret or not consteq(sent, expected):
            return request.make_response("", status=401)
        # ... store the event, see below
```

Points that matter:

* Compare in constant time (`odoo.tools.consteq`, an alias of `hmac.compare_digest`) so response timing leaks nothing.
* Sign the raw body. Re-serialising parsed JSON changes whitespace and key order, and the signature no longer matches.
* Refuse when no secret is configured. With an empty secret anyone can compute a valid signature.
* If the sender signs a timestamp, reject events older than a few minutes to stop replay.
* `type="http"` with `csrf=False` is right here: the caller is a server, not a browser, and the HMAC replaces the CSRF token. `type="json"` expects a JSON-RPC envelope that third parties do not send.

## Acknowledge fast, work later

Senders time out after a few seconds and then resend. Do not process inside the request. Store the event, answer 200, and let a cron do the work:

```python
        payload = json.loads(body)
        Event = request.env["library.webhook.event"].sudo()
        try:
            with request.env.cr.savepoint():
                Event.create({
                    "external_id": payload["id"],
                    "kind": payload["type"],
                    "payload": body.decode(),
                })
        except psycopg2.errors.UniqueViolation:
            pass  # duplicate delivery, already stored
        request.env.ref("library_sync.cron_webhook_events").sudo()._trigger()
        return request.make_response("ok", status=200)
```

## Idempotency

Delivery is at least once. The same event arrives twice after a timeout, a retry or a manual replay. Make that harmless with a unique constraint on the sender's event id:

```python
class LibraryWebhookEvent(models.Model):
    _name = "library.webhook.event"
    _description = "Inbound webhook event"

    external_id = fields.Char(required=True, index=True)
    kind = fields.Char(required=True)
    payload = fields.Text()
    state = fields.Selection(
        [("new", "New"), ("done", "Done"), ("error", "Error")], default="new"
    )

    _sql_constraints = [
        ("external_id_uniq", "unique(external_id)", "Duplicate event."),
    ]
```

The constraint, not a prior `search`, is the guard: two simultaneous deliveries both pass a search and both insert. The database decides. The savepoint keeps the unique violation from poisoning the request's transaction.

Processing must be idempotent too. "Set the loan to returned" is safe to repeat; "add one to the stock counter" is not. Prefer handlers that set state from the event over handlers that apply deltas, and check current state first.

## Ordering

Events can arrive out of order. If order matters, carry a version or timestamp in the payload and ignore anything older than what you have stored. Never rely on arrival order.

## Status codes

401 for a bad signature, 400 for an unparseable body, 200 for anything stored. Do not answer 5xx for business-processing problems: the event is safely stored, and a 5xx only makes the sender retry something you already have. Keep the error on the event record (`state = "error"`) for a human.

## Outbound webhooks

Sending mirrors this: sign the body, send with a timeout from a queue, retry with backoff, include a unique event id so the receiver can deduplicate. See External APIs for the client side.

## Pitfalls

* Verifying a signature over parsed params instead of the raw body.
* Comparing signatures with `==`.
* Processing inline, so the sender gives up and retries, creating the duplicate you then have to handle.
* `auth="public"` and no `sudo()`: the public user cannot write. Use `sudo()` narrowly, on the event model only.
* Leaking the secret in logs or views.
* No unique constraint, then finding duplicate orders in production.
* Trusting the payload for amounts or permissions. Treat it as a hint and refetch from the API when it matters.

## Versions

{% hint style="info" %}
`odoo.tools.consteq` exists in 16, 17 and 18 (verified in 18). `_sql_constraints` is the declaration style in all three; check your build if you migrate to a later release.
{% endhint %}

## Try it

Compute a signature locally and call your endpoint:

```
BODY='{"id":"evt_1","type":"loan.returned"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -i -X POST http://localhost:8069/library/webhook -H "X-Signature: $SIG" -d "$BODY"
```

Send it twice. The second call must also return 200 and create no new row.
