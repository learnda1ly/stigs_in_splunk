# STIG in Splunk — persist REST (catalog reference)

Base URL (management port):

`https://<host>:8089/servicesNS/nobody/stigs_in_splunk`

Authentication: Splunk session key (`Authorization: Bearer <token>`) or equivalent; same as other `stig_*` resources.

Full resource list: [spec.md](../spec.md) §11.

## Baseline catalog reference (CCI / group / rule)

Global baseline rules live in KV `stig_baseline_rules`. These endpoints search **across all imported baselines** (not workspace-scoped). CCI coverage depends on DISA XCCDF / CKL / CKLB import: only CCIs present on imported rule rows are searchable.

**Reserved segments:** `rules`, `ccis`, `groups`, and `rule` are catalog path literals (not baseline `_key` values) for `GET /stig_baselines/{id}` — see [spec.md](../spec.md) §11.3.

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_baselines/rules/{ruleRef}` | Match `rule_id`, `rule_id_src`, `rule_version`, or `group_id`. Optional query `stig_id`. **404** if no matches. |
| GET | `/stig_baselines/ccis/{cci}` | Rules referencing CCI (e.g. `CCI-000366`). Optional `stig_id`. **200** with `matches: []` when none. |
| GET | `/stig_baselines/groups/{groupId}` | Rules with V-id `group_id`. Optional `stig_id`. |
| GET | `/stig_baselines/rule/{ruleKey}` | Single rule by KV `_key` (`rule_key` in assignment APIs). **404** if missing. |

### Response shape (list endpoints)

```json
{
  "rule_ref": "SV-000001",
  "stig_id": null,
  "match_count": 2,
  "matches": [
    {
      "rule_key": "…",
      "group_id": "V-000001",
      "rule_id": "SV-000001",
      "rule_version": "EX-00-000001",
      "severity": "high",
      "rule_title": "…",
      "ccis": ["CCI-000366"],
      "check_content_hash": "…",
      "baseline": {
        "baseline_id": "…",
        "stig_id": "Example_STIG",
        "version": "1",
        "title": "…",
        "benchmark_date": "…",
        "content_fingerprint": "…"
      }
    }
  ]
}
```

`GET /stig_baselines/rule/{ruleKey}` returns one object in the same `matches[]` field shape (without the list wrapper).

OpenAPI fragment: [openapi.yaml](./openapi.yaml).
