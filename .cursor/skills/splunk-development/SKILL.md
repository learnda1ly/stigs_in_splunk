---
name: splunk-development
description: Build, debug, package, and Cloud-vet Splunk apps and add-ons. Use when writing Splunk apps, TAs, UCC add-ons, modular inputs, custom search commands, REST handlers, conf files (app.conf, props.conf, transforms.conf, inputs.conf, commands.conf, restmap.conf), CIM mappings, Dashboard Studio or Simple XML, Splunk UI Toolkit pages with @splunk/react-ui @splunk/react-page @splunk/create @splunk/visualizations, Splunk REST/SDK clients, AppInspect or slim packaging, ACS private-app installs, or SPL that ships as knowledge objects. Also trigger on Splunkbase packaging, storage/passwords secrets, KV Store collections, Enterprise Security adaptive responses, python.version or python.required settings, and official splunk-app-examples or SUIT gallery repos.
---

# Splunk Development

Author Splunk apps and add-ons the way the current Splunk Developer Program expects them. Prefer shipped templates in `assets/` and details in `references/` over inventing layout or conf keys.

Official sources (prefer these over stale blog posts)

- Developer portal — [https://dev.splunk.com/](https://dev.splunk.com/)

- Enterprise/Cloud app guide — [https://dev.splunk.com/enterprise/docs/developapps/](https://dev.splunk.com/enterprise/docs/developapps/)

- Cloud-ready guidelines — [https://dev.splunk.com/enterprise/docs/planapps/cloudready](https://dev.splunk.com/enterprise/docs/planapps/cloudready)

- AppInspect — [https://dev.splunk.com/enterprise/docs/developapps/testvalidate/appinspect](https://dev.splunk.com/enterprise/docs/developapps/testvalidate/appinspect)

- UCC — [https://splunk.github.io/addonfactory-ucc-generator/](https://splunk.github.io/addonfactory-ucc-generator/)

- Splunk UI / `@splunk/react-ui` — [https://splunkui.splunk.com/Packages/react-ui/Overview](https://splunkui.splunk.com/Packages/react-ui/Overview)

- SUIT overview — [https://splunkui.splunk.com/Toolkits/SUIT/Overview](https://splunkui.splunk.com/Toolkits/SUIT/Overview)

- Official app examples — [https://github.com/splunk/splunk-app-examples](https://github.com/splunk/splunk-app-examples)

- REST tutorials — [https://docs.splunk.com/Documentation/Splunk/latest/RESTTUT/RESTandCloud](https://docs.splunk.com/Documentation/Splunk/latest/RESTTUT/RESTandCloud)

- Conf specs — [https://docs.splunk.com/Documentation/Splunk/latest/Admin/Whatisaconfigurationfile](https://docs.splunk.com/Documentation/Splunk/latest/Admin/Whatisaconfigurationfile)

## Choose the right artifact

| Need | Ship as | Start with |

|---|---|---|

| Ingest + CIM normalize a product | Technology Add-on `TA-*` or `Splunk_TA_*`) | UCC `ucc-gen init`) unless the input is files-only |

| Saved searches, dashboards, macros, nav for a use case | App `*` not starting with `TA-`) | Barebones app + knowledge objects in `default/` |

| Reusable SPL command | Separate command app | `splunklib.searchcommands` + `commands.conf` with `chunked = true` |

| REST/SDK integration from outside Splunk | External client | Python SDK or raw REST — not an app unless it also ships KO |

| ES adaptive response / notable enrichment | Add-on with `adaptive_response` | ES integration guide + AR action conf |

Do not mix a heavy modular input, a custom visualization, and a suite of ES correlation searches in one package unless the user explicitly wants a single app.

## Hard rules (every app)

1. Put shippable conf and views in `default/`. Never package `local/`, `local.meta`, `metadata/local.meta`, or user-level files. `local/` is for runtime overrides only.

2. Folder name equals `[id] name` and `[package] id` in `app.conf`. Use lowercase, digits, underscore. No spaces.

3. Required `app.conf` stanzas for anything that might hit Splunkbase or Cloud — `[id]`, `[launcher]` `author`, `description`, `version`), `[package] id`, `[ui] label`, `[install]`.

4. Version with `major.minor.patch` in both `[id] version` and `[launcher] version`.

5. Python in `bin/` must be Python 3.9-clean. Splunk 10 removed 2.7 and 3.7. On 10.2+ prefer `python.required = 3.9` (add `3.13` only if you tested it). Keep `python.version = python3` for 9.x. Set this on every scripted stanza `commands.conf`, modular `inputs.conf`, `restmap.conf`, scripted `transforms.conf`, `alert_actions.conf`).

6. Secrets go through `storage/passwords` (encrypted `passwords.conf` in **local** at runtime). Never commit plaintext credentials or a packaged `passwords.conf`.

7. Third-party Python deps live in `lib/` (or UCC-managed `lib/`) and are imported via that path. Do not assume site-packages on Cloud.

8. No `.pyc`, `.pyo`, `__pycache__`, `.git`, IDE junk, or nested apps inside the package.

9. `default.meta` ships; `local.meta` does not. Export knowledge objects app-level, not user-level.

10. After editing conf that Splunk already loaded, refresh `/debug/refresh`) or restart. New modular-input schemes and REST maps usually need a restart.

Read `references/app-structure.md` before creating or rearranging files.

## Workflow

### 1. Scaffold

- **TA with UI / accounts / REST inputs** — UCC.

```bash

pip install splunk-add-on-ucc-framework

ucc-gen init --addon-name "TA-example_product" --addon-display-name "Example Product Add-on" --addon-input-name example_input

ucc-gen build --source TA-example_product/package --ta-version 1.0.0

ucc-gen package --path output/TA-example_product

```

Edit `globalConfig.json` and helper modules only. UCC regenerates UI, `restmap.conf`, `web.conf`, input stubs, and the monitoring dashboard. Put collection logic in the helper `validate_input`, `stream_events`) so rebuilds do not wipe it. Details in `references/ucc.md`.

- **Bare app / KO-only app** — copy `assets/barebones-app/` and fill `app.conf`, `default.meta`, nav, views.

- **Custom command app** — copy `assets/custom-command/` and start from `splunk-app-examples/custom_search_commands/python/`*.

- **Hand-written modular input** (no UCC) — start from `splunk-app-examples/modularinputs/python/github_commits`. Prefer UCC when a setup UI is needed.

- **Custom React page inside Splunk Web** — `npx @splunk/create`, then `references/splunk-ui.md`. Bootstrap template in `assets/suit-page/index.jsx`. Copy setup-page wiring from `splunk-app-examples/setup_pages/SUIT-setup-page-example`.

Target a local Splunk Enterprise install for development even if production is Cloud. Set `SPLUNK_HOME`. Developer license is 10 GB/day, 6-month renewable via the Developer Program.

### 2. Implement

Conf files use INI stanzas. Layering and precedence are not optional knowledge — read `references/app-structure.md` before fixing a setting that is being overridden.

Typical files an agent touches

- `default/app.conf` — identity, visibility, setup view, Python

- `default/props.conf` + `transforms.conf` — sourcetype, LINE_BREAKER, TIME_FORMAT, EXTRACT/REPORT, LOOKUP, CIM tags

- `default/inputs.conf` + `README/inputs.conf.spec` — modular / scripted inputs

- `default/commands.conf` — custom SPL

- `default/restmap.conf` + `default/web.conf` — custom endpoints

- `default/collections.conf` — KV Store

- `default/data/ui/nav/default.xml` + `views/*.xml` — classic nav / Simple XML

- `default/data/ui/views/*.json` — Dashboard Studio

- `metadata/default.meta` — export and RBAC defaults

- `bin/*.py` — commands, inputs, handlers, alert actions

Knowledge-object and CIM patterns live in `references/knowledge-objects.md`. Dashboards and SUIT notes live in `references/dashboards-ui.md`. REST and SDK patterns live in `references/rest-sdk.md`.

### 3. Validate

```bash

# packaging + manifest

pip install splunk-packaging-toolkit

slim validate <app-dir-or-package>

# static AppInspect (offline). Use the tag that matches the destination.

pip install splunk-appinspect

splunk-appinspect inspect <package.tgz> --included-tags cloud

splunk-appinspect inspect <package.tgz> --included-tags private_victoria

splunk-appinspect inspect <package.tgz> --included-tags future

# fast local layout check bundled with this skill

bash scripts/[package-check.sh](http://package-check.sh) <app-dir>

# conf merge view

$SPLUNK_HOME/bin/splunk btool props list --debug

$SPLUNK_HOME/bin/splunk btool check

```

AppInspect CLI is static. Cloud/Splunkbase submission also runs the hosted API (dynamic). Both must be clean for `cloud`. See `references/appinspect-packaging.md`.

### 4. Package

```bash

# UCC

ucc-gen package --path output/<app_id>

# Packaging Toolkit (preferred over `splunk package app` — that command merges local into default)

slim package <app-dir>

# Last resort CLI (strip local/ first)

$SPLUNK_HOME/bin/splunk package app <app_id>

```

Output a single-root `.tgz` / `.spl` named `{app_id}-{version}.tgz`.

### 5. Install on Cloud

Victoria/Classic private apps go through AppInspect then ACS `apps/victoria` or the Cloud UI). REST to Cloud search heads needs the search-api IP allow list via ACS. Details in `references/appinspect-packaging.md` and `references/rest-sdk.md`.

## Coding conventions for `bin/`

- Shebang `#!/usr/bin/env python3` or rely on Splunk's interpreter via conf. Do not vendor a custom interpreter.

- Import `splunklib` from the app `lib/` (SDK 2.1.x current on the developer downloads page). Pin and vendor it; do not expect it on Cloud.

- Modular inputs — use `splunklib.modularinput` `Script`, `Scheme`, `Argument`, `EventWriter`). Stream XML events. Checkpoint under the provided `checkpoint_dir`.

- Custom commands — use `splunklib.searchcommands` with `@Configuration()` and `chunked = true` in `commands.conf` (chunked protocol). Mark `is_risky = true` if the command can send data out or run code.

- REST handlers — prefer `PersistentServerConnectionApplication` (script) or `MConfigHandler` (EAI/conf). Do not add CherryPy endpoints; they fail Cloud vetting and Python compatibility checks.

- Log with the SDK logger or Splunk's logging helpers. Never print secrets. Never write debug lines to stdout from a custom command (it corrupts the chunked protocol).

- HTTP from scripts — TLS 1.2+ only. AppInspect flags insecure requests and old `sslVersions`.

- Handle session keys from modular-input XML `session_key`) or REST. Talk to `https://127.0.0.1:8089` from inside Splunk; do not hardcode management URIs for Cloud.

## What not to do

- Do not author new features on the legacy SplunkJS / Simple XML JS stack. Splunk is not adding guidance there; use Dashboard Studio or Splunk UI Toolkit (SUIT / `@splunk/react-ui`) for new UI.

- Do not put index-time `TRANSFORMS` that require a custom Python command on Cloud search heads and expect them to run on indexers you do not control.

- Do not use `runshellscript`, start-by-shell tricks, or ship binaries without declaring them — Cloud tags fail these.

- Do not edit files under `$SPLUNK_HOME/etc/system/local` as part of an app. That is not portable.

- Do not invent CIM extra fields without `tags.conf` + `eventtypes.conf` (or equivalent automatic lookups). ES/CIM consumers will not see them.

## Decision shortcuts

- User says "add-on for vendor API" → UCC + helper module + CIM in props/transforms.

- User says "custom SPL command" → chunked `searchcommands` app, not a script in `bin/` referenced ad-hoc.

- User says "dashboard" → Dashboard Studio JSON unless they already have Simple XML or need a custom React viz `@splunk/dashboard-core` + `@splunk/visualizations`).

- User says "React page / SUIT / look like Splunk Web" → `@splunk/create` + `@splunk/react-ui` + `@splunk/react-page/18`. Load `references/splunk-ui.md`.

- User says "store API token" → setup page or UCC account tab → `storage/passwords`.

- User says "works on my Enterprise box but Cloud install fails" → package contains `local/`, missing `python.version`, or AppInspect `cloud` tag failures. Run the Cloud tag first.

## Progressive disclosure

Load only what the current task needs

- App layout, precedence, `app.conf`, `default.meta` → `references/app-structure.md`

- UCC / `globalConfig.json` / helpers → `references/ucc.md`

- Modular inputs protocol → `references/modular-inputs.md`

- Custom search commands → `references/custom-commands.md`

- REST, tokens, Python SDK, HEC → `references/rest-sdk.md`

- AppInspect tags, slim, Cloud/ACS → `references/appinspect-packaging.md`

- CIM, props/transforms, lookups, ES → `references/knowledge-objects.md`

- Nav, Studio, Simple XML → `references/dashboards-ui.md`

- `@splunk/react-ui`, `@splunk/react-page`, `@splunk/create`, Dashboard Framework → `references/splunk-ui.md`

- Official GitHub examples to copy → `references/official-examples.md`

Starter trees

- `assets/barebones-app/`

- `assets/custom-command/`

- `assets/modular-input/`

- `assets/suit-page/index.jsx`

## Cursor install

This folder is a portable Agent Skill `SKILL.md` + `references/` + `assets/` + `scripts/`). Copy it to one of

- `.cursor/skills/splunk-development/` (this repo)

- `~/.cursor/skills/splunk-development/` (all repos)

- `.agents/skills/splunk-development/` (shared with other agents)

Invoke with `/splunk-development` or let the agent pick it up from the description. Optional Cursor-only frontmatter you may add locally (not required here) — `paths` globs such as `**/*.conf`, `**/globalConfig.json`, `**/bin/*.py`, `**/default/data/ui/**`.

