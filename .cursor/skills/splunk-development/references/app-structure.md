# App structure, conf, and precedence

Canonical layout lives under `$SPLUNK_HOME/etc/apps/<app_id>/`. The packaged tarball must contain exactly one root folder named `<app_id>`.

```
<app_id>/
├── default/                  # SHIP THIS. Original conf and views.
│   ├── app.conf              # required
│   ├── props.conf
│   ├── transforms.conf
│   ├── inputs.conf
│   ├── commands.conf
│   ├── restmap.conf
│   ├── web.conf
│   ├── collections.conf
│   ├── savedsearches.conf
│   ├── macros.conf
│   ├── tags.conf
│   ├── eventtypes.conf
│   ├── datamodels.conf
│   ├── alert_actions.conf
│   ├── workflow_actions.conf
│   ├── server.conf           # only when you must (e.g. custom conf via restmap)
│   └── data/ui/
│       ├── nav/default.xml
│       └── views/
├── local/                    # DO NOT PACKAGE. Runtime / UI edits land here.
├── metadata/
│   ├── default.meta          # SHIP THIS
│   └── local.meta            # DO NOT PACKAGE
├── README/
│   └── inputs.conf.spec      # required to register a modular-input scheme
├── bin/                      # scripts (commands, inputs, handlers, alerts)
├── lib/                      # vendored Python deps (splunk-sdk, requests, …)
├── lookups/                  # CSV / KV lookup files shipped with the app
├── appserver/static/         # JS, CSS, images, SUIT build, UCC UI
├── static/                   # app icons (appIcon.png, appIcon_2x.png, appLogo.png)
└── README.md                 # optional; not loaded by Splunk
```

`splunk create app` / the Web "Create app" flow builds this tree. Template `barebones` is the right starting point for KO-only apps.

## default vs local

- `default/` is what you author and ship.
- Splunk Web and REST writes go to `local/` (app-level) or `$SPLUNK_HOME/etc/users/<user>/<app>/local` (user-level).
- `local` wins over `default` in the same app.
- Packaging with `splunk package app` **merges local into default**. That is why slim/UCC packaging is safer — they will not quietly bake a developer's test stanza into the release.

## File precedence (user/app context — searches, views, most KO)

Highest wins when values conflict. Splunk still merges files; only colliding keys are replaced.

1. `$SPLUNK_HOME/etc/users/<user>/<app>/local/`
2. `$SPLUNK_HOME/etc/users/<user>/<app>/default/`
3. `$SPLUNK_HOME/etc/apps/<app>/local/`
4. `$SPLUNK_HOME/etc/apps/<app>/default/`
5. `$SPLUNK_HOME/etc/system/local/`
6. `$SPLUNK_HOME/etc/system/default/`  (lowest)

Global context (indexing, inputs on a forwarder) ignores user dirs and uses system + apps. When two apps disagree, lexicographic app name is the last resort after directory priority — do not rely on it. Use explicit `priority` in props or put index-time settings in a well-named TA installed on forwarders/indexers.

Debug with:

```bash
splunk btool props list <sourcetype> --debug
splunk btool inputs list --debug
```

## app.conf (minimum Cloud / Splunkbase-ready)

```ini
[install]
is_configured = 0
state = enabled
build = 1

[id]
name = ta_example_product
version = 1.0.0

[launcher]
author = Example Corp
description = Collects and CIM-normalizes Example Product logs.
version = 1.0.0

[package]
id = ta_example_product

[ui]
is_visible = true
label = Example Product
# setup_view = setup_page_xml_name   # only if you ship a setup dashboard

[triggers]
reload.inputs = simple
```

- `[id] name` and `[package] id` must equal the directory name.
- `[ui] label` is 5–80 characters for Splunkbase.
- `is_visible = false` for a pure TA that should not appear in the app picker.
- `setup_view` + `[install] is_configured = 0` redirects first launch to that view. UCC handles this for you.

## default.meta

```ini
[]
access = read : [ * ], write : [ admin, sc_admin ]
export = system

[inputs]
export = system

[props]
export = system

[transforms]
export = system

[lookups]
export = system
```

- `export = system` makes sourcetypes/props visible outside the app (required for a TA).
- `export = none` keeps dashboards/searches app-private.
- Never ship `local.meta`.

Owner/perms set in Web write to `local.meta`. If a KO "disappears" after packaging, it was left in a user directory or `local.meta` was omitted from the source tree incorrectly — check both.

## Conf syntax

```ini
[stanza]
# comment
key = value
```

- No quotation gymnastics unless the value needs them. Leading/trailing spaces on values are trimmed.
- Repeatable keys (e.g. multiple `REPORT-`) use a unique suffix (`REPORT-foo`, `REPORT-bar`).
- `.conf.spec` files in `README/` document custom keys so the UI and btool know they exist.

## Reload vs restart

Needs restart — new modular-input scheme, new REST map, many `server.conf` changes, new custom command on some versions.

Often reloadable — props/transforms (index-time still needs pipeline restart on forwarders), views, nav, saved searches. Hitting `https://<host>:8000/debug/refresh` reloads a subset. Do not tell Cloud customers to restart; they cannot.

## Naming

- Apps — short, unique, match Splunkbase id rules (`A-Za-z0-9_.-`).
- TAs — `TA-<vendor>_<product>` or `Splunk_TA_<product>` (Splunk-supported convention).
- Sourcetypes — `vendor:product:type` (colon-separated), not free-form.
- Indexes — do not create indexes in a Cloud-bound TA unless the user owns that policy; prefer documenting a required index and using `index =` in inputs as a default the admin can override.
