# REST API and Python SDK

Enterprise/Cloud management port is **8089**. Observability Cloud is a different API (`https://api.{realm}.observability.splunkcloud.com/v2`, `X-SF-TOKEN`) — do not mix the two.

REST tutorials — https://docs.splunk.com/Documentation/Splunk/latest/RESTTUT/RESTandCloud
Python SDK — https://dev.splunk.com/enterprise/docs/devtools/python/sdk-python/ (PyPI / GitHub `splunk/splunk-sdk-python`, current developer downloads list 2.1.x)

## Enterprise / Splunk Cloud Platform auth

Session (short-lived)

```bash
curl -k https://localhost:8089/services/auth/login \
  -d username=admin -d password='***'
# <sessionKey>…</sessionKey>
curl -k https://localhost:8089/services/search/jobs \
  -H "Authorization: Splunk <sessionKey>" \
  -d search='search index=_internal | head 1' \
  -d output_mode=json
```

Token (preferred for automation)

```bash
curl -k https://localhost:8089/services/search/jobs \
  -H "Authorization: Bearer <token>" \
  -d search='search index=_internal | head 1' \
  -d output_mode=json
```

Always send `output_mode=json` (or `json_cols` / `csv`). Default XML/Atom is painful.

Cloud extras

- URL `https://<stack>.splunkcloud.com:8089`
- Search-API IP allow list via **ACS** (`search-api/ipallowlists`) or a support case
- `sc_admin` cannot restart, cannot touch indexer/DS config, cannot run debug endpoints
- Restricted to the search tier

From inside an app script, use the `session_key` Splunk already injected and `https://127.0.0.1:8089`. Do not embed user passwords.

## Python SDK

```python
import splunklib.client as client

service = client.connect(
    host="localhost",
    port=8089,
    username="admin",
    password="...",          # or token="...", or splunkToken=
    scheme="https",
    verify=False,            # only for local dev
)

jobs = service.jobs
job = jobs.create("search index=_internal | head 10", **{"exec_mode": "blocking"})
for row in job.results(output_mode="json"):
    pass

saved = service.saved_searches
saved.create("Test Search", "* | head 10")   # no leading 'search' keyword
```

Connect with a token in production. `exec_mode`

- `oneshot` — small, complete payload
- `blocking` — wait until done, then read
- `normal` — poll `isDone`

Collections map to REST resources (`service.indexes`, `service.inputs`, `service.confs["props"]`, `service.storage_passwords`, `service.kvstore`).

## Secrets

Write

```bash
curl -k https://localhost:8089/servicesNS/nobody/<app>/storage/passwords \
  -H "Authorization: Bearer <token>" \
  -d name=api_user \
  -d password='***' \
  -d realm=example_product
```

Stored encrypted in **local** `passwords.conf`

```ini
[credential:example_product:api_user:]
password = <encrypted>
```

Read back via the same endpoint (SDK `service.storage_passwords`). Never ship that file.

## Search jobs (raw)

`POST /services/search/jobs` → sid  
`GET /services/search/jobs/{sid}` → status  
`GET /services/search/jobs/{sid}/results?output_mode=json`

Namespace-aware paths — `/servicesNS/<owner>/<app>/...`. Use `nobody` + app name for app-level objects.

## KV Store

`default/collections.conf`

```ini
[example_coll]
enforceTypes = true
field.id = string
field.count = number
accelerated_fields.by_id = {"id": 1}
```

Data — `/servicesNS/nobody/<app>/storage/collections/data/example_coll`

Cloud users without filesystem access create collections over REST, not by dropping the file (unless the collection ships in the app `default/`).

## HEC (ingest, not management)

`https://<host>:8088/services/collector` with `Authorization: Splunk <hec-token>`. Different port, different token type. Use HEC from external senders; use modular inputs when the collector should live inside Splunk.

## ACS (Cloud admin)

CLI / API for allow lists, private app install, HEC tokens, indexes on Victoria, outbound ports. App install flow

1. Auth to `https://api.splunk.com` with splunk.com credentials → bearer
2. `POST https://appinspect.splunk.com/v1/app/validate` with the package
3. Wait for the request id to succeed
4. `POST` ACS `apps/victoria` with `Authorization: Bearer <stack JWT>` and `X-Splunk-Authorization: <appinspect token>`

Worked handler example — https://github.com/splunk/splunk-app-examples/tree/master/custom_endpoints/hello-world (`[script:]` plus `[admin_external:]` in one app).

## Custom REST endpoints (inside an app)

`restmap.conf` + script in `bin/` inheriting

- `PersistentServerConnectionApplication` — arbitrary JSON APIs
- `MConfigHandler` — EAI wrappers around a custom conf

Expose via `web.conf`. Do not add CherryPy endpoints. Declare `python.version` / `python.required` on the restmap stanza. UCC already generates this pair for account/input CRUD.

## Observability Cloud (do not confuse)

Metrics/detectors/SignalFlow use realm URLs and `X-SF-TOKEN`. Session tokens there expire (~30 days) and cannot ingest datapoints — ingest needs an org token with ingest scope.
