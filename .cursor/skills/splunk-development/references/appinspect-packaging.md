# Packaging, AppInspect, and Cloud

## Package shape

- One root directory named the app id
- Extension `.tgz` / `.tar.gz` / `.spl`
- Filename `{app_id}-{version}.tgz`
- No `local/`, no `local.meta`, no `__pycache__`, no `.git`, no nested apps
- `default/app.conf` present with `[id]`, `[launcher]`, `[package] id`, `[ui] label`
- Icons if visible — `static/appIcon.png`, `appIcon_2x.png` (reserved names)

```bash
pip install splunk-packaging-toolkit
slim validate <app-or-package>
slim package <app-dir>
```

`splunk package app <id>` works only if the app already lives in `$SPLUNK_HOME/etc/apps` and **merges local into default**. Strip `local/` first or do not use it.

UCC

```bash
ucc-gen build --source <src>/package --ta-version 1.0.0
ucc-gen package --path output/<app_id>
```

## Python on current Splunk

| Platform | Interpreter |
|---|---|
| Enterprise / Cloud 9.2–9.4 | 3.7 still present on some trains; 3.9 default from 9.3 |
| Enterprise / Cloud 10.0–10.1 | **3.9 only** (2.7 and 3.7 removed). OpenSSL 3, Node 20 |
| Enterprise / Cloud 10.2+ | `python.required` selects the highest available (3.9, and 3.13 when present). `python.version` is deprecated but honored if `python.required` is absent |

Ship both for a while

```ini
python.version = python3
python.required = 3.9
```

Add `3.13` only after running the script on 3.13. Splunk 10.2 picks the newest listed that exists on the host.

Force 3.9 on a 9.3+ test box with `server.conf` `[general] python.version = force_python3`.

## AppInspect

CLI 4.2.x (developer portal listed 4.2.1 in 2026-05). PyPI `splunk-appinspect`.

```bash
splunk-appinspect inspect myapp-1.0.0.tgz --included-tags cloud
splunk-appinspect inspect myapp-1.0.0.tgz --included-tags private_victoria
splunk-appinspect inspect myapp-1.0.0.tgz --included-tags future
splunk-appinspect list tags
splunk-appinspect list checks --included-tags cloud
```

Hosted (dynamic + latest checks)

```bash
# token from splunk.com login against api.splunk.com
curl -X POST https://appinspect.splunk.com/v1/app/validate \
  -H "Authorization: Bearer $TOKEN" \
  -F app_package=@myapp-1.0.0.tgz \
  -F included_tags=cloud
```

### Tags that matter

| Tag | Use |
|---|---|
| `cloud` | Splunkbase / public Cloud vetting (strictest common set) |
| `private_victoria` | Private app on Victoria Experience |
| `private_classic` | Private app on Classic Experience |
| `private_app` | Older combined private-app set; more restrictive union |
| `future` | Checks that will become failures — treat as failures now |
| `packaging_standards` | Tarball layout |
| `splunk_appinspect` | Every check |

CLI is static. Do not claim "Cloud-ready" from CLI alone if the destination is Splunkbase — run the API.

### Failures you will actually hit

- Missing `python.version = python3` on scripted stanzas
- Packaged `local/` or passwords
- `.pyc` files
- Insecure `http://` in Python (`check_for_insecure_http_calls_in_python`)
- Old TLS (`sslVersions` without `tls1.2`; 10.4+ wants `tls1.2,tls1.3`)
- Stale Python SDK / httplib2
- Overriding stdlib module names
- `runshellscript`, start-by-shell, custom interpreters
- Disallowed file types in `default/`
- App id ≠ directory name ≠ `[package] id`
- jQuery / unsafe JS patterns on leftover Simple XML extensions
- Compiled binaries without source or a documented exception

Result states — `success`, `failure`, `manual_check`, `not_applicable`, `error`, `future_failure`. `manual_check` still blocks Splunkbase until a human signs off.

## Cloud-ready behavior

From the Cloud-ready app guidelines

- Only allowed conf files in `default/`
- ASCII/UTF-8 text; no unexpected binaries
- No nested apps
- Setup must work without filesystem writes outside the app `local/`
- Outbound network only; no bind-on-port collectors on Cloud SH
- Do not require a restart to become useful if you can avoid it
- Index-time settings in a TA must be documented for HF/UF install — they will not run on Cloud indexers you cannot reach

## Private app install (Victoria)

1. AppInspect API validate (private_victoria / private_app)
2. ACS `POST apps/victoria` with stack JWT + AppInspect token
3. Or use the Cloud UI "App management" self-service if the stack allows it

`sc_admin` cannot sideload via `$SPLUNK_HOME`. There is no "just copy to etc/apps" on Cloud.

## Test matrix before you ship

- Install on a local Enterprise 10.x instance from the tarball (not from the working tree)
- `btool check` clean
- AppInspect `cloud` + `future` clean
- Create one input, restart/reload, confirm events land with the intended sourcetype
- Confirm secrets survive a restart (encrypted passwords)
- Confirm the app does not own objects that collide with `search` or CIM extras (`Splunk_SA_CIM`)
