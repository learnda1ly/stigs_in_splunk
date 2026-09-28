# UCC add-on development

Universal Configuration Console is the current way to build UI-backed technology add-ons. Add-on Builder itself now generates UCC projects. Do not start new TAs with hand-rolled setup JS or legacy AoB-only layouts unless converting an existing AoB app (`ucc-gen import-from-aob`).

Docs — https://splunk.github.io/addonfactory-ucc-generator/

## Install and commands

```bash
pip install splunk-add-on-ucc-framework

ucc-gen init --addon-name "TA-example_product" \
  --addon-display-name "Example Product Add-on" \
  --addon-input-name example_input

ucc-gen build --source TA-example_product/package --ta-version 1.0.0
ucc-gen package --path output/TA-example_product
```

`init` writes a source tree. `build` emits an installable app under `output/`. `package` writes the `.tar.gz` next to `globalConfig.json`.

## Source vs generated

Treat as **source** (edit these)

- `globalConfig.json` (or `.yaml`) — UI, accounts, inputs, alerts, dashboard tabs
- `package/bin/<helper>.py` — `validate_input` and `stream_events`
- `package/lib/` requirements via UCC `meta.requirements` / additional packaging
- `package/default/props.conf`, `transforms.conf`, `tags.conf`, lookups
- `additional_packaging.py` — build hooks
- custom JS hooks under the documented custom path

Treat as **generated** (do not hand-edit; UCC overwrites on build)

- `appserver/` UI
- `restmap.conf`, `web.conf`, most of `inputs.conf` / specs
- generated input wrapper `.py` in `bin/` (the file that imports the helper)
- OpenAPI at `appserver/static/openapi.json`
- default monitoring dashboard

If you edit a generated input script, the next `ucc-gen build` will wipe it. Put logic in the helper module and set `inputHelperModule` on the service.

## Helper module

```json
"services": [
  {
    "name": "example_input",
    "title": "Example Input",
    "inputHelperModule": "example_input_helper",
    "entity": [ ]
  }
]
```

```python
from splunklib import modularinput as smi

def validate_input(definition: smi.ValidationDefinition):
    interval = definition.parameters.get("interval")
    if interval is not None and int(interval) < 10:
        raise ValueError("interval must be >= 10 seconds")

def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    for input_name, input_item in inputs.inputs.items():
        event = smi.Event(
            data='{"ok": true}',
            sourcetype="example:product:json",
            index=input_item.get("index") or "main",
        )
        event_writer.write_event(event)
```

Checkpoint state under the checkpoint dir Splunk provides. Do not write into `etc/apps`.

## globalConfig shape (mental model)

```json
{
  "pages": {
    "configuration": {
      "title": "Configuration",
      "tabs": [
        { "name": "account", "title": "Account", "entity": [] }
      ]
    },
    "inputs": {
      "title": "Inputs",
      "services": [],
      "table": { "header": [], "actions": ["edit", "delete", "clone"] }
    },
    "dashboard": { "panels": [{ "name": "default" }] }
  },
  "meta": {
    "name": "TA-example_product",
    "restRoot": "ta_example_product",
    "version": "1.0.0",
    "displayName": "Example Product Add-on",
    "schemaVersion": "0.0.3"
  }
}
```

Entity field types you will actually use — `text`, `textarea`, `number`, `checkbox`, `singleSelect`, `multipleSelect`, `oauth`, `file`, `interval`, `index`, `custom`.

Validators — `required`, `regex`, `number`, `string`. Always give `errorMsg`.

Auth — use the built-in account tab + OAuth entity when the vendor is OAuth2. UCC generates the redirect view and secret handling. Never store client secrets in `default/`.

Alerts — define alert actions in `globalConfig`; UCC writes `alert_actions.conf` and the Python stub. Implement the stub the same way as helpers (do not fight the generator).

## Build-time Python deps

Declare requirements so UCC installs them into `lib/`. Cloud has no pip. If a wheel is not pure-Python, Cloud vetting will fail or the addon will crash on the search head OS.

## Custom UI

UCC is not a free-form React app. For fields it cannot express, use `type: "custom"` + `hook.src` with `type: "external"` (ESM). Files live under `appserver/static/js/build/custom/` after build conventions — follow the current UCC "Custom hook" page rather than inventing a webpack stack.

For a fully custom React experience, SUIT is the right tool, not a UCC hook.

## Conversion

Existing Add-on Builder projects — `ucc-gen import-from-aob`. Review generated `globalConfig.json` and re-test modular inputs; helper extraction is the first cleanup step.

## What UCC does not replace

CIM mappings, index-time props, lookups, eventtypes/tags, and datamodels are still hand-authored in `package/default/`. See `knowledge-objects.md`.
