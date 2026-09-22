# STIG app audit index

Structured mutation audit events are emitted by `package/bin/audit.py` on REST/KV changes (create, update, delete, import, transfer, and related actions). Each event is:

1. **Always** written to the Splunk app logger `stigs_in_splunk.audit` (splunkd log), and  
2. **Best-effort** indexed into Splunk when the `stig_audit` index and ingest path are available.

If indexing fails (missing index, HTTP input disabled, no HEC token), mutations still succeed; only the searchable copy is skipped.

**Splunkd log vs index:** Lines in `splunkd.log` still use JSON `null` for `entity_id` when the caller omits an id. Indexed events normalize omitted ids to `""` for consistent SPL/dashboard fields.

## Event shape

Indexed events use **sourcetype** `stig:audit` with JSON field extraction (`props.conf`). Top-level fields:

| Field | Description |
|-------|-------------|
| `action` | Mutation type (`create`, `update`, `delete`, `import`, `transfer`, …) |
| `user` | Splunk username from the REST session |
| `entity_type` | KV entity (`stig_host`, `stig_collection`, `stig_review`, …) |
| `entity_id` | Entity `_key` when applicable (empty string in the index when omitted) |
| `object` | `entity_type:entity_id` for dashboard display |
| `workspace_id` | Workspace `_key` when known (from `stig_collection_id` in details or collection entity id) |
| `details` | Optional JSON bag (same as splunkd log payload) |
| `time` | Epoch seconds (event time) |

Example SPL:

```spl
index=stig_audit sourcetype=stig:audit action=create entity_type=stig_host
| table _time user workspace_id object
```

## Shipped defaults

The app tarball includes:

| File | Purpose |
|------|---------|
| `default/indexes.conf` | `[stig_audit]` index definition |
| `default/inputs.conf` | `[http://stig_audit]` HEC-style input → `stig_audit` / `stig:audit` |
| `default/props.conf` | `[stig:audit]` JSON timestamp and extraction |
| `default/data/ui/views/stig_audit_dashboard.xml` | Simple XML dashboard **STIG audit** (nav **Audit**) |

After install or upgrade, **restart Splunk** (or reload indexes/inputs) so `stig_audit` and the HTTP input are created.

## Admin enablement

1. **Index** — On indexers/search heads, confirm `stig_audit` exists (`index=stig_audit | head 1` or Settings → Indexes). The app ships the stanza; clustered deployments may require pushing `indexes.conf` via deployer.
2. **HTTP input** — Requires the Splunk **HTTP Event Collector** / `splunk_httpinput` app (same as finding ingest). The shipped stanza sets `disabled = 0`; after restart, confirm the `stig_audit` input is present and enabled under **Settings → Data inputs → HTTP Event Collector** (app context `stigs_in_splunk`). Splunk generates a **token** at runtime; the REST handler reads it server-side only (never exposed in Configuration UI).
3. **Fallback** — During authenticated REST calls, the app may index via `/services/receivers/simple` when a user session is present but HEC is unavailable.
4. **Retention** — Adjust `frozenTimePeriodInSecs` on `[stig_audit]` in `local/indexes.conf` if you need longer retention than the shipped one-year default.

## Review history vs audit

| Mechanism | Store | Use |
|-----------|--------|-----|
| **Audit** (`stig_audit` index) | Operational security log of API mutations | Compliance, forensics, admin dashboard |
| **Review history** (`stig_review_history` KV) | Per-rule assessor field changes | STIG Editor timeline |

They are intentionally separate.
