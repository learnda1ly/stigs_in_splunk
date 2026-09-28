# Knowledge objects, CIM, and ES-facing TAs

A technology add-on earns its keep by making raw data searchable and CIM-aligned. Dashboards can live in a separate app that depends on the TA.

## Sourcetype and parsing (props.conf)

Index-time (must be present where parsing happens — HF or indexer, **not** a UF)

```ini
[example:product:log]
SHOULD_LINEMERGE = false
LINE_BREAKER = ([\r\n]+)
TIME_PREFIX = ^
TIME_FORMAT = %Y-%m-%dT%H:%M:%S.%3N%z
MAX_TIMESTAMP_LOOKAHEAD = 32
TRUNCATE = 10000
EVENT_BREAKER_ENABLE = true
EVENT_BREAKER = ([\r\n]+)
```

Search-time (search head)

```ini
[example:product:log]
KV_MODE = json
# or
EXTRACT-user = user=(?<user>[^\s]+)
REPORT-example = example_report
LOOKUP-dest = example_lookup dest AS dest OUTPUT dest_category
EVAL-vendor_product = "Example Product"
FIELDALIAS-src = client_ip AS src
```

JSON — prefer `INDEXED_EXTRACTIONS = json` only when you accept index-time field cost; otherwise `KV_MODE = json` at search time.

Never set `INDEXED_EXTRACTIONS` and `KV_MODE` to fight each other on the same sourcetype without a reason.

## transforms.conf

```ini
[example_report]
REGEX = (\w+)=(\S+)
FORMAT = $1::$2

[example_lookup]
filename = example_lookup.csv

[example_drop]
REGEX = healthcheck
DEST_KEY = queue
FORMAT = nullQueue
```

Lookups go in `lookups/example_lookup.csv`. Wildcard / CIDR lookups need `match_type`. KV Store lookups use `collection` + `external_type = kvstore`.

## CIM

Install `Splunk_SA_CIM` in the dev instance. Map to existing data models (Network Traffic, Authentication, Change, Malware, Web, Endpoint, …). Do not invent a parallel model if CIM already covers the domain.

Minimum for a CIM-compliant sourcetype

1. Field aliases / evals so CIM field names exist (`src`, `dest`, `user`, `action`, `status`, `src_port`, `dest_port`, `vendor_product`, …)
2. `eventtypes.conf` + `tags.conf` so the CIM constraints match

```ini
# eventtypes.conf
[example_auth]
search = sourcetype=example:product:log action=*

# tags.conf
[eventtype=example_auth]
authentication = enabled
authentication-success = enabled
```

Use the CIM add-on's tags as the vocabulary. ES correlation searches bind to those tags and data models — wrong tags means notables never fire.

Validate with `| datamodel Authentication Authentication search | search sourcetype=example:product:log`.

## Macros, saved searches, eventtypes

- Macros in `macros.conf` — definition only, no leading pipe unless the macro is designed that way. Document arguments as `mymacro(2)`.
- Saved searches in `savedsearches.conf`. Scheduled searches on Cloud must stay inside capacity; do not ship a 1-minute search over all time.
- Export KO that other apps need (`export = system` in `default.meta`). Keep reports that are UI-only app-private.

## Data models

Ship a custom datamodel only when CIM cannot represent the data. `default/data/models/<Name>.json` + `datamodels.conf`. Accelerations are an admin decision — do not enable acceleration by default in a Cloud app without a warning.

## Enterprise Security integrations

- Adaptive response actions — `feature=adaptive_response` in `alert_actions.conf` plus an AR-specific stanza. Package as an add-on; do not drop files into `SplunkEnterpriseSecuritySuite`.
- Notable extras — add fields ES already expects (`dest`, `src`, `user`, `url`, `signature`) rather than inventing a new IR workflow.
- Threat intel / lookups — follow ES documentation for `threat_intelligence` collections; do not write straight into ES KV collections from a TA unless the contract says so.
- Add-on Builder / UCC can emit AR actions; still review `alert_actions.conf` by hand.

When targeting ES, develop against a licensed ES sandbox. CIM version must be one ES supports.

## Forwarder placement reminder

| Setting | UF | HF / indexer | Search head |
|---|---|---|---|
| inputs (files, MI that reads files) | yes | yes | rarely |
| index-time props/transforms | no (UF does not parse) | yes | no |
| search-time props, lookups, CIM tags | no | no | yes |
| modular input that calls an API | possible | common | Cloud-limited |

Ship one TA and document where to install it. Splunk Cloud customers often run the input on a self-managed HF and the search-time pieces on Cloud via the packaged app.
