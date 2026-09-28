# Dashboards, navigation, and UI

Priority for new work

1. **Dashboard Studio** (JSON views) — default for new dashboards in current Enterprise/Cloud
2. **Splunk UI Toolkit (SUIT)** — custom React apps / visualizations used across Splunk's own products
3. **Simple XML** — maintain existing views; do not start large new Simple XML + JS stacks
4. **SplunkJS Web Framework** — frozen. Splunk is not adding features or guidance. Do not choose it for new apps.

Studio and Simple XML both live under `default/data/ui/views/`. Studio files are JSON; Simple XML files are XML. Nav still uses `default/data/ui/nav/default.xml`.

## Navigation

```xml
<nav search_view="search" color="#1A6B8A">
  <view name="overview" default="true" />
  <view name="search" />
  <collection label="Reports">
    <saved source="unclassified" match="example_" />
  </collection>
  <view name="configuration" />
</nav>
```

- `default="true"` marks the landing view. Otherwise the first entry wins.
- `search_view` is the dashboard other apps jump into for "Open in app".
- After edits, `/debug/refresh` then reload the app.

Classic horizontal nav vs modern left-rail nav depends on stack version and `web-features.conf` / `react-page`. If the user asks for "Cisco Splunk modern navigation", follow current `react-page` docs rather than inventing XML icons.

UCC already writes `inputs` and `configuration` views plus nav entries. Do not fight those names.

## Dashboard Studio

- Author in the UI when possible, then copy the JSON into `default/data/ui/views/<name>.json` so it is packaged.
- Data sources are named objects (`type: "ds.search"`) referenced by visualizations. Do not embed ad-hoc SPL in five places — one data source, many viz.
- Tokens work; keep defaults valid so the dashboard loads on first paint.
- Avoid Studio features that require Enterprise-only permissions if the app targets Cloud self-service users.
- Custom visualizations for Studio have a different package contract than Simple XML viz — follow the current Studio custom-viz guide, not the old viz.conf-only path.

## Simple XML (legacy maintenance)

```xml
<dashboard version="1.1" theme="light">
  <label>Overview</label>
  <row>
    <panel>
      <chart>
        <search>
          <query>index=example sourcetype=example:product:log | timechart count</query>
          <earliest>-24h</earliest>
          <latest>now</latest>
        </search>
        <option name="charting.chart">column</option>
      </chart>
    </panel>
  </row>
</dashboard>
```

JS/CSS extensions go in `appserver/static/` and are referenced with `<dashboard script="foo.js" stylesheet="foo.css">`. This path is what AppInspect jQuery checks punish. Prefer Studio over adding more JS to Simple XML.

Form inputs — `<fieldset>` + `<input>` + tokens `$tok$`.

## SUIT / `@splunk/react-ui` (custom UI)

Full package list, bootstrap, fetch helpers, and Dashboard Framework embed live in `references/splunk-ui.md`. Official copy-from repos live in `references/official-examples.md`.

Minimum facts when you stay on this page

- Components come from `@splunk/react-ui/<Component>` (Button, Table, Text, Modal, Heading, ColumnLayout). Peers are `react@^18`, `react-dom@^18`, `styled-components@^5`.
- Mount inside Splunk Web with `import layout from '@splunk/react-page/18'`.
- Theme with `@splunk/themes` + `@splunk/splunk-utils/themes`.
- Talk to splunkd via `@splunk/splunk-utils/fetch` and `/splunkd/__raw/…`, not `:8089`.
- Scaffold with `npx @splunk/create`. Studio custom viz uses `--mode=dashboard-studio-extension`.
- Package the webpack build into `appserver/static`. Source and `node_modules` do not ship.
- UCC already embeds a SUIT admin UI — do not add a second React app for accounts/inputs.

Need Node 20 (Splunk 10). SplunkJS is frozen.

## Setup pages

Classic pattern — `app.conf`

```ini
[install]
is_configured = 0

[ui]
setup_view = setup
```

The setup view writes conf via REST and then sets `is_configured = 1`. UCC's configuration page supersedes this for TAs.

Store credentials with `storage/passwords`, not a custom conf value.

## Icons and static

Reserved names in `static/` or `appserver/static/`

- `appIcon.png`, `appIcon_2x.png`
- `appIconAlt.png`, `appIconAlt_2x.png`
- `appLogo.png`, `appLogo_2x.png`

Keep them small. Cloud packaging rejects surprise binaries.

## Permissions

Views without `export` stay in-app. That is usually correct. Do not export every dashboard to system — you will pollute other apps' menus.
