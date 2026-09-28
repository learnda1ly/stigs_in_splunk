# Splunk UI Toolkit and `@splunk/react-ui`

New custom UI for Splunk apps is React + the Splunk UI Toolkit (SUIT). Do not start new work on SplunkJS.

Docs

- Design system / packages — https://splunkui.splunk.com/Packages
- SUIT overview — https://splunkui.splunk.com/Toolkits/SUIT/Overview
- `@splunk/react-ui` — https://splunkui.splunk.com/Packages/react-ui/Overview and https://www.npmjs.com/package/@splunk/react-ui
- `@splunk/react-page` — https://www.npmjs.com/package/@splunk/react-page
- `@splunk/visualizations` — https://www.npmjs.com/package/@splunk/visualizations
- `@splunk/create` — https://www.npmjs.com/package/@splunk/create
- Theme support in apps — https://dev.splunk.com/enterprise/docs/developapps/createapps/buildapps/adduithemes

Examples that show the real wiring live in `references/official-examples.md`. Copy patterns from those repos rather than inventing a webpack stack.

## Package map (install these, do not invent names)

| npm package | Use for |
|---|---|
| `@splunk/react-ui` | Buttons, Table, Text, Modal, Heading, Link, List, ColumnLayout, Switch, Select, … Splunk design-language components |
| `@splunk/react-icons` | Icons that match Splunk Web |
| `@splunk/react-page` | Mount a React tree inside Splunk Web chrome (app bar, footer). React 18 entry is `@splunk/react-page/18` |
| `@splunk/themes` | `SplunkThemeProvider` (enterprise / prisma) |
| `@splunk/splunk-utils` | In-Web REST helpers (`fetch` with CSRF cookies), theme detection (`themes`) |
| `@splunk/ui-utils` | i18n `_()`, ids, format helpers |
| `@splunk/search-job` | Run searches from React **inside** Splunk Web |
| `@splunk/react-search` | Search input / job UI |
| `@splunk/react-time-range` | Time-range picker |
| `@splunk/visualizations` | Studio-class charts (`Line`, `SingleValue`, `Table`, …) with a `dataSources.primary` shape |
| `@splunk/visualization-context` | Peer of `@splunk/visualizations` |
| `@splunk/dashboard-core` | Render a Dashboard Studio JSON definition as React |
| `@splunk/dashboard-context` | `DashboardContextProvider`, geo providers |
| `@splunk/dashboard-presets` | `EnterpriseViewOnlyPreset` |
| `@splunk/create` | Scaffold a monorepo app + page, standalone app, or Dashboard Studio custom viz |
| `@splunk/webpack-configs` | Official webpack/babel pieces (`@splunk/babel-preset`) |
| `@splunk/react-toast-notifications` | Toasts |

Peers for current `@splunk/react-ui` (5.x on npm as of 2026-09)

```bash
npm install react@^18 react-dom@^18 styled-components@^5
npm install @splunk/react-ui @splunk/themes @splunk/react-page @splunk/splunk-utils
```

Splunk 10 ships Node 20. Pin `styled-components@5` (not 6) unless the package page says otherwise. Bundle **one** copy of `@splunk/react-ui` — two copies on a page break Layer/Modal.

## When to use what

| Goal | Tool |
|---|---|
| TA setup / accounts / inputs | UCC (already SUIT under the hood). Do not add a second React app. |
| Custom app page inside Splunk Web | `@splunk/create` default mode, or hand-roll `@splunk/react-page` + `@splunk/react-ui` |
| Dashboard that is mostly Studio | Dashboard Studio JSON in `default/data/ui/views/` |
| Dashboard that needs custom React viz, click-to-modal, 3rd-party maps | `@splunk/dashboard-core` + custom preset + `@splunk/visualizations` |
| Custom viz in Studio's picker | `npx @splunk/create --mode=dashboard-studio-extension` |
| App **outside** Splunk Web talking to 8089 | `@splunk/splunk-utils` + `@splunk/visualizations` (see `react_search_example`, `SUIT-example-for-logins`) |

## Scaffold

```bash
mkdir my-ui-app && cd my-ui-app
npx @splunk/create
# prompts: app name, page name, page type (Basic Page)

yarn && yarn build
```

Modes

- default — monorepo `packages/<page>` + `packages/<app>`
- `--mode=standalone` — React app without the Splunk app tree
- `--mode=dashboard-studio-extension` — custom Studio visualization project

`@splunk/create` links `@splunk/react-ui`, `@splunk/dashboard-core`, and `@splunk/visualizations` for you.

## Page bootstrap (inside Splunk Web)

React 18 (current `@splunk/react-page`):

```jsx
import React from 'react';
import layout from '@splunk/react-page/18';
import { SplunkThemeProvider } from '@splunk/themes';
import { defaultTheme, getThemeOptions } from '@splunk/splunk-utils/themes';
import Button from '@splunk/react-ui/Button';
import Heading from '@splunk/react-ui/Heading';

const theme = getThemeOptions(defaultTheme() || 'enterprise');

layout(
    <SplunkThemeProvider {...theme}>
        <Heading level={1}>Example</Heading>
        <Button label="Save" appearance="primary" />
    </SplunkThemeProvider>,
    { pageTitle: 'Example', hideFooter: true, layout: 'fixed' }
);
```

`layout` options used in official examples — `pageTitle`, `hideFooter`, `layout: 'fixed'`, plus `theme` from `getUserTheme()` when supporting light/dark.

`app.conf` must declare theme support if you honor the user theme:

```ini
[ui]
supported_themes = light,dark
```

Light is required.

## Component import rules

Import **one component per path**. Do not barrel-import the package root.

```jsx
import Button from '@splunk/react-ui/Button';
import Table from '@splunk/react-ui/Table';
import Text from '@splunk/react-ui/Text';
import Modal from '@splunk/react-ui/Modal';
import Heading from '@splunk/react-ui/Heading';
import ColumnLayout from '@splunk/react-ui/ColumnLayout';
```

Styling

- Prefer the `style` prop and the `inline` boolean. Do not fight Splunk CSS with `className` or global overrides — specificity is not a public API.
- Fonts — "Splunk Platform Sans" / "Splunk Platform Mono". `@splunk/react-page` loads them inside Splunk Web; standalone apps must load `@font-face` themselves.
- Production builds — `NODE_ENV=production` via webpack `DefinePlugin` so react-ui strips dev warnings.

## Talk to splunkd from the browser

Inside Splunk Web, use `@splunk/splunk-utils/fetch` so CSRF cookies ride along. Official setup-page example:

```jsx
import { defaultFetchInit, handleResponse } from '@splunk/splunk-utils/fetch';

const endpoint =
    '/en-US/splunkd/__raw/servicesNS/nobody/<app_id>/storage/passwords';

await fetch(endpoint, {
    ...defaultFetchInit,
    method: 'POST',
    body: `name=${user}&password=${password}&realm=${realm}`,
});
```

Same pattern to flip `[install] is_configured` via `/servicesNS/nobody/system/apps/local/<app_id>` with `body: 'configured=true'`.

Do not call `:8089` from browser JS inside Splunk Web — use the `/splunkd/__raw/` proxy. Outside Splunk Web, use `@splunk/splunk-utils` against the management port with explicit credentials (see login example repo).

## Dashboard Framework embed

```jsx
import DashboardCore from '@splunk/dashboard-core';
import { DashboardContextProvider } from '@splunk/dashboard-context';
import EnterpriseViewOnlyPreset from '@splunk/dashboard-presets/EnterpriseViewOnlyPreset';
import definition from './definition.json';

<DashboardContextProvider preset={customPreset}>
    <DashboardCore width="100%" height="100%" definition={definition} />
</DashboardContextProvider>
```

Register extra viz in the preset (`visualizations: { 'splunk.line': Line, 'acme.map': MyMap }`). Official .conf25 samples — `splunk/conf25_drones_real_time_monitoring`, `splunk/conf25_building_dynamic_dashboards_3dviz`.

## What gets shipped

Webpack production output lands in the Splunk app's `appserver/static/` (or the `stage/` folder `@splunk/create` produces). Pair each page with a Simple XML or HTML view that loads that bundle, plus a `nav/default.xml` entry. Source (`src/`, `packages/`, `node_modules/`) does **not** belong in the `.tgz`.

`link:app` scripts in official examples symlink the staged app into `$SPLUNK_HOME/etc/apps`. Restart once after the first link.

## Anti-patterns

- Mixing SplunkJS MVC `require([ 'splunkjs/mvc', ...])` with SUIT on the same view.
- Vendoring React 16 and React 18 on one page.
- Importing `@splunk/react-ui` as a namespace (`import * as SUI`) — tree-shaking dies and AppInspect size checks suffer.
- Writing setup UI by hand when UCC already covers accounts/inputs.
- Calling `storage/passwords` with a hardcoded locale prefix other than the user's (`en-US` in examples is a shortcut; prefer relative `/splunkd/__raw/...` or `getAppData` helpers).
