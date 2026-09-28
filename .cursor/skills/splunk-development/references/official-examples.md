# Official example repositories

Prefer these over blog snippets. Clone, copy the pattern, adapt names — do not paste the whole app.

## `splunk/splunk-app-examples`

https://github.com/splunk/splunk-app-examples

Canonical Enterprise app examples used by the Developer Program and the JS/Python SDKs. Run locally with Docker from the repo root (`make up`) or copy one subdirectory into `$SPLUNK_HOME/etc/apps`.

| Path | What to steal |
|---|---|
| `custom_search_commands/python/streamingsearchcommands_app` | `@Configuration` `StreamingCommand`, `chunked = true`, `python.version = python3`. Field-in / field-out (`celsius` → `fahrenheit`). |
| `custom_search_commands/python/generatingsearchcommands_app` | Generating command + matching `commands.conf` stanza. |
| `custom_search_commands/python/eventingsearchcommands_app` | Eventing command. |
| `custom_search_commands/python/reportingsearchcommands_app` | Reporting / reduce command. |
| `custom_search_commands/python/customsearchcommands_app` | Several commands in one app (`countmatches`, `filter`, `generatetext`, `simulate`, `sum`) — how `commands.conf` lists many `filename` + `chunked` stanzas. |
| `custom_search_commands/python/customsearchcommands_template` | Template including `commands-scpv1.conf` vs `commands-scpv2.conf`. New work uses v2 / `chunked = true`. |
| `modularinputs/python/github_commits` | Real modular input — `Scheme`, `Argument`, `use_external_validation`, `use_single_instance = False`, checkpoint-friendly GitHub API pull. Vendors `splunklib` next to `bin/`. |
| `modularinputs/python/github_forks` | Sibling input. |
| `modularinputs/python/random_numbers` | Minimal scheme + streaming. |
| `custom_endpoints/hello-world` | Both handler styles in one app — `PersistentServerConnectionApplication` (`[script:hello-world]`) and EAI (`[admin_external:…]`). |
| `custom_alert_actions/slack_alerts` | `alert_actions.conf` with `is_custom = 1`, `python.version = python3`, payload params, setup view, `restmap.conf`. |
| `setup_pages/SUIT-setup-page-example` | **Current** setup UI — Lerna monorepo, `@splunk/react-ui`, `@splunk/react-page`, `@splunk/themes`, `@splunk/splunk-utils/fetch` posting to `storage/passwords` then flipping `configured=true`. |
| `setup_pages/react_setup_page_example` | Older React-on-Simple-XML setup (vendored react in `appserver/static`). Use the SUIT example instead for new apps. |
| `setup_pages/setup_page_simple` | Minimal non-React setup. |
| `setup_pages/weather_app_example` | Setup that stores an external API secret, referenced from the Developer Guide secret-storage page. |
| `setup_pages/dependency_checking_app_example` | Gate setup on a required add-on being installed. |
| `setup_pages/developer_guidance_setup_page` | Documented walkthrough companion. |
| `javascript/browser/create-splunk-react-app` | Standalone CRA talking to Splunk (historical). Prefer `@splunk/create` / `react_search_example` today. |
| `javascript/browser/helloworld`, `ui`, `viz`, `minisplunk` | JS SDK browser samples. |
| `javascript/node/helloworld` | JS SDK on Node. |
| `python/explorer`, `analytics`, `dashboard`, `twitted` | Python SDK sample apps (search jobs, simple UI). |
| `spl2-sample-apps/sample_spl2_buttercup` | SPL2 module app. |
| `spl2-sample-apps/sample_spl2_pii_masking` | SPL2 PII masking sample. |
| `tutorials/Module-01_GetStarted` … `Module-04_Validate` | Dev-tutorial app (`devtutorial`) matching the portal "Get started developing apps" modules. |

Notes when copying

- Official `commands.conf` examples set `chunked = true` and `python.version = python3` and nothing else. Add `python.required = 3.9` for Splunk 10.2+.
- Modular input examples document that `splunklib` must sit in `bin/` (or `lib/` on `sys.path`). The Docker `make up` flow mounts the SDK for you; a shipped app must vendor it.
- `custom_endpoints/hello-world` contains a `local/` tree in the repo — strip it before packaging.

## SUIT / Examples Gallery repos

Gallery is pointed at from https://splunkui.splunk.com/Toolkits/SUIT/Overview and the `@splunk/create` README.

| Repo | What to steal |
|---|---|
| https://github.com/splunk/SUIT-setup-page-example | Same setup-page app as above (also vendored under `splunk-app-examples/setup_pages/`). |
| https://github.com/splunk/SUIT-example-for-visualizations | `@splunk/visualizations` + in-Web `@splunk/search-job` wiring. Yarn workspaces / `yarn run setup`. |
| https://github.com/splunk/SUIT-example-for-logins | Login to Splunk **outside** Splunk Web with SUIT packages. |
| https://github.com/splunk/react_search_example | Standalone React app; query string `username`, `password`, `serverURL`; `@splunk/splunk-utils` search from outside Web. |
| https://github.com/splunk/dashboard-simple-table-component | `@splunk/create` app + custom table viz (`@splunk/react-ui/Table` + `@splunk/react-sparkline`) registered into Dashboard Framework. |
| https://github.com/splunk/dashboard-interactivity-modal | Click a viz → `@splunk/react-ui/Modal`. |
| https://github.com/splunk/dashboard-react-google-maps | Third-party map inside `@splunk/dashboard-core`. |
| https://github.com/splunk/dashboard-conf19-examples | Multi-page Dashboard Framework app; each view is `src/pages/<name>/index.jsx` bootstrapped with `@splunk/react-page`. |
| https://github.com/splunk/conf25_drones_real_time_monitoring | .conf25 custom + built-in viz, live data, Dashboard Framework. |
| https://github.com/splunk/conf25_building_dynamic_dashboards_3dviz | .conf25 3D / external library embed. |

## How the agent should use them

1. Identify the closest example from the tables.
2. Read that example's `commands.conf` / `inputs.conf.spec` / `package.json` / page `index.jsx` before writing new files.
3. Keep our hard rules (no packaged `local/`, `python.required`, secrets via `storage/passwords`). Examples are older than Splunk 10 in places — update Python metadata and React 18 imports (`@splunk/react-page/18`, `react@^18`) when copying.
4. Do not vendor the entire monorepo into an app tarball. Ship only the built Splunk app package (`stage/` / `appserver/static` + `default/` + `bin/`).
