# Modular inputs

Use a modular input when Splunk must pull or receive a custom data stream on a schedule or long-lived process. Prefer UCC-generated inputs when a user-facing setup UI is required. Hand-write the protocol below when you need a minimal TA or to understand what UCC emits.

Docs — https://docs.splunk.com/Documentation/Splunk/latest/AdvancedDev/ModInputsIntro
Worked examples — https://github.com/splunk/splunk-app-examples/tree/master/modularinputs/python (`github_commits`, `github_forks`, `random_numbers`). See `references/official-examples.md`.

## Required pieces

```
<app>/bin/<scheme>.py
<app>/README/inputs.conf.spec
<app>/default/inputs.conf          # scheme defaults only; instances belong in local at runtime
<app>/default/app.conf
```

Scheme name regex — `[0-9a-zA-Z][0-9a-zA-Z_-]*`. Script path is `bin/<scheme>.py` unless `inputs.conf` overrides it.

## inputs.conf.spec

```ini
[<scheme>://<name>]
* Configure <scheme> inputs.

python.version = python3
python.required = 3.9

interval = <integer>
* Collection interval in seconds.

index = <string>
sourcetype = <string>

# custom params
api_url = <value>
account = <value>
```

Do not put `start_by_shell` in the spec. Instances

```ini
[<scheme>://prod]
interval = 60
index = example
sourcetype = example:product:json
api_url = https://api.example.com
disabled = 0
```

Layering is special — `[<scheme>://instance]` inherits from `[<scheme>]` then from `[default]`.

## Protocol

Splunk invokes the script with

- `--scheme` — print introspection XML to stdout and exit 0
- `--validate-arguments` — read validation XML on stdin, exit non-zero on bad config
- no extra args — run, read input definition XML on stdin, stream events

One-instance-per-stanza is the default (`use_single_instance = false`). Set true only when one process should multiplex all stanzas (shared TCP connection, etc.).

### Introspection XML

```xml
<scheme>
  <title>Example Product</title>
  <description>Pull events from Example Product.</description>
  <use_external_validation>true</use_external_validation>
  <use_single_instance>false</use_single_instance>
  <streaming_mode>xml</streaming_mode>
  <endpoint>
    <args>
      <arg name="name">
        <title>Input name</title>
        <required_on_create>true</required_on_create>
      </arg>
      <arg name="api_url">
        <title>API URL</title>
        <required_on_create>true</required_on_create>
      </arg>
    </args>
  </endpoint>
</scheme>
```

`streaming_mode` — `xml` (preferred) or `simple` (plain text, harder to set source/host/index per event).

### Execution XML Splunk sends

Includes `server_host`, `server_uri`, `session_key`, `checkpoint_dir`, and each stanza's params. Debug with

```bash
splunk cmd splunkd print-modinput-config <scheme> <scheme>://<stanza>
```

Use `session_key` + `server_uri` to call REST (`storage/passwords`, KV, conf). Do not prompt for credentials.

### Streaming events (XML mode)

```xml
<stream>
  <event>
    <time>1710000000.000</time>
    <source>example://prod</source>
    <sourcetype>example:product:json</sourcetype>
    <index>example</index>
    <host>collector-1</host>
    <data>{"id":1}</data>
  </event>
</stream>
```

Prefer `splunklib.modularinput.EventWriter`.

## Implementation sketch

```python
import sys
from splunklib.modularinput import Script, Scheme, Argument, Event, EventWriter

class ExampleInput(Script):
    def get_scheme(self):
        scheme = Scheme("Example Product")
        scheme.description = "Pull events from Example Product."
        scheme.use_external_validation = True
        scheme.use_single_instance = False
        scheme.streaming_mode = Scheme.streaming_mode_xml
        url = Argument("api_url")
        url.title = "API URL"
        url.data_type = Argument.data_type_string
        url.required_on_create = True
        scheme.add_argument(url)
        return scheme

    def validate_input(self, definition):
        url = definition.parameters["api_url"]
        if not url.startswith("https://"):
            raise ValueError("api_url must be https")

    def stream_events(self, inputs, ew: EventWriter):
        for name, params in inputs.inputs.items():
            ew.write_event(Event(
                data="{}",
                stanza=name,
                sourcetype="example:product:json",
            ))

if __name__ == "__main__":
    sys.exit(ExampleInput().run(sys.argv))
```

## Checkpoints and behavior

- Write opaque checkpoint files under `checkpoint_dir` only.
- Handle SIGTERM; flush the current event.
- `interval = 0` or a long-running stream — keep the process alive and write events as they arrive. Do not busy-loop.
- Index-time parsing still happens via `props.conf` on the parsing tier (UF does not parse; HF/indexer does). Ship props in the same TA and install that TA wherever parsing occurs.

## Cloud constraints

- No arbitrary sockets inbound on Cloud search heads. Collect from APIs outbound over TLS.
- No indexer-tier modular inputs on Cloud — collection belongs on a customer-managed HF or Ingest Actions, or on Cloud only if the input is supported there.
- Must declare `python.version` / `python.required` on the scheme.
- AppInspect inspects the script for insecure HTTP, subprocess shell=True, and prohibited modules.
