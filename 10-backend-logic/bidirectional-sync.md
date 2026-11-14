---
description: "Mapping tables, change detection, and avoiding infinite loops."
---

# Bidirectional synchronisation

Two systems that both edit the same data need a sync that knows what changed, where it came from, and who wins a conflict. The failure mode is always the same: A writes to B, B's change hook writes back to A, and the two ping-pong forever. This chapter covers the mapping, the change detection, and the loop breakers.

## The mapping table

Do not scatter `x_external_id` fields over business models. One mapping model ties a local record to a remote id per system:

```python
class LibrarySyncMap(models.Model):
    _name = "library.sync.map"
    _description = "Local to remote id mapping"

    model = fields.Char(required=True, index=True)
    res_id = fields.Many2oneReference(model_field="model", required=True)
    remote_system = fields.Char(required=True)
    remote_id = fields.Char(required=True)
    remote_hash = fields.Char()      # hash of the last synced payload
    remote_updated = fields.Datetime()
    last_sync = fields.Datetime()

    _sql_constraints = [
        ("remote_uniq", "unique(model, remote_system, remote_id)", "Already mapped."),
        ("local_uniq", "unique(model, res_id, remote_system)", "Already mapped."),
    ]
```

Both constraints matter. The first prevents two local records claiming one remote object; the second prevents one local record being pushed twice as two remote objects. Lookup is by index in both directions.

## Change detection

Never push or pull everything every time. Decide by comparing a fingerprint:

```python
import hashlib, json

def _fingerprint(self, values):
    blob = json.dumps(values, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
```

Build `values` from the mapped fields only, in a canonical form (sorted keys, normalised whitespace and number formats). Compare with `remote_hash` stored at the last sync. If equal, skip. This also stops the loop: after you write the remote's data locally, the local fingerprint equals the stored one, so the write-back finds nothing to send.

When the remote offers a modification timestamp or cursor, use it to fetch only newer records (`updated_since=last_sync`), and still compare fingerprints, since timestamps lie around clock skew and bulk updates. Subtract a small overlap from the cursor and let the fingerprint discard the repeats.

## Breaking the loop

Combine two mechanisms.

**A context flag** for writes you make while applying remote data, so the push hooks on the local side stay quiet:

```python
def write(self, vals):
    res = super().write(vals)
    if not self.env.context.get("library_sync_inbound"):
        self.env["library.export.job"]._enqueue(self)
    return res

def _apply_remote(self, record, values):
    record.with_context(library_sync_inbound=True).write(values)
```

The flag must be passed to every write the inbound path makes, including writes in overrides further down. Context propagates through `with_context` and through recordsets derived from the one you called it on, but not through a fresh `self.env[...]` built from another environment.

**A write-origin marker** for the other direction, where the remote echoes your own change back as an event. Store the id of the change you sent (or the version number the remote returned) in the map. When an inbound event carries a version equal to the one you just wrote, drop it. Many remotes return the new version in the response to your write, so record it immediately.

Use both: the flag protects against local hooks, the fingerprint and version protect against remote echoes. A flag alone fails across processes, since the echo arrives later in a different request where the context is gone.

## Conflicts

Decide the policy per field, not per sync, and write it down:

* One side is the master for a field (prices from the ERP, descriptions from the shop). The other side's edits are overwritten or rejected.
* Last-writer-wins by timestamp, when both sides may edit. Compare remote `updated` with the local `write_date` and accept the newer. Needs reasonably synchronised clocks.
* Field-level merge: compare against the last synced snapshot. A field changed only on one side since the snapshot is taken from that side; changed on both is a conflict to flag for a human.

Keep a snapshot (`remote_hash` is not enough for the merge; store the last synced values, for instance as JSON) if you need field-level merge.

## Deletes

A missing record is ambiguous: deleted, or filtered out, or not yet visible. Prefer soft deletes (archive, `active = False`) mirrored as a status. If the remote only reports absence, delete locally only after a full, successful listing, never after a failed or paginated-out partial one.

## Ordering of creation

Parents before children. Map a partner before the loan that references it. When the child arrives first, either create a placeholder parent and mark it incomplete, or park the event in the queue and retry after the parent syncs.

## Pitfalls

* Loop breaker only in context. Echoes cross process boundaries; store a version or hash.
* Hashing non-canonical data: float formatting, dict order, trailing spaces. A flapping hash looks like constant changes and defeats the whole mechanism.
* `write_date` comparison across systems with different clock settings and time zones. Use UTC, and prefer remote versions where available.
* Creating duplicates because the mapping row is written in a later transaction than the remote call. Commit the map as soon as the remote id is known, and rely on the unique constraint.
* Syncing computed or related fields. Map stored, writable fields only.
* Running initial load and live sync in the same code path with no guard, so the first run floods the queue. Throttle, and load in batches.

## Versions

{% hint style="info" %}
`Many2oneReference` is available in 16, 17 and 18. `_sql_constraints` is the declaration style in all three.
{% endhint %}

## Try it

Find mapping gaps, read-only:

```sql
SELECT b.id FROM library_book b
LEFT JOIN library_sync_map m
  ON m.model = 'library.book' AND m.res_id = b.id AND m.remote_system = 'catalogue'
WHERE m.id IS NULL;
```
