# HEC simulator (routing tests)

When testing **workspace assignment rules**, omit `collection_id` / `collectionId` from
`hosts.yaml` (or leave it blank). The reconcile resolver routes by assignment rules,
host×baseline overrides, and the Default workspace.

Optional: pass `--collection-id` only when validating legacy senders with
`trust_event_collection_id` enabled in Configuration.
