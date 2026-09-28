# Custom search commands

Ship a custom command as its own app (or a clearly named sub-feature of an app). Implement it with `splunklib.searchcommands` and the **chunked** protocol.

Docs — https://dev.splunk.com/enterprise/docs/devtools/customsearchcommands
`commands.conf` spec — https://docs.splunk.com/Documentation/Splunk/latest/Admin/Commandsconf
Worked examples — https://github.com/splunk/splunk-app-examples/tree/master/custom_search_commands/python (streaming, generating, eventing, reporting, multi-command app). See `references/official-examples.md`.

## Command types vs SDK classes

| Need | SDK class | notes |
|---|---|---|
| Map 1 event → 0..n events, can run on indexers | `StreamingCommand` | Set streaming; keep it distributable if possible |
| Produce events from scratch (`| mycmd`) | `GeneratingCommand` | Usually search-head only |
| Reduce a result set (stats-like) | `ReportingCommand` | Two-phase map/reduce if you implement it |
| Need the whole event set then emit events | `EventingCommand` | Search-head; expensive |

A command that calls REST for secrets or app conf must run on the search head (not distributable).

## Files

```
<app>/bin/mycmd.py
<app>/default/commands.conf
<app>/default/searchbnf.conf          # optional, drives the search UI help
<app>/default/app.conf
<app>/lib/splunklib/...               # vendor the SDK
```

### commands.conf

```ini
[mycmd]
filename = mycmd.py
chunked = true
is_risky = false
python.version = python3
python.required = 3.9
# run_in_preview = true
# maxchunksize = 65536
# maxwait = 0
```

When `chunked = true`, most legacy keys (`streaming`, `retainsevents`, `enableheader`, `supports_getinfo`, `supports_rawargs`) are ignored. Only chunked-relevant keys apply.

Set `is_risky = true` if the command sends data off-box, executes code, or can be used to exfiltrate. Risky commands require `require_risk_acknowledgement` / explicit ad-hoc enablement.

### searchbnf.conf (short)

```ini
[mycmd-command]
syntax = mycmd
shortdesc = Does the thing.
description = Longer help shown in the search UI.
```

## Implementation

```python
#!/usr/bin/env python3
from splunklib.searchcommands import (
    dispatch, StreamingCommand, Configuration, Option, validators
)

@Configuration()
class MyCommand(StreamingCommand):
    field = Option(require=True, validate=validators.Fieldname())

    def stream(self, records):
        for record in records:
            record["copied"] = record.get(self.field, "")
            yield record

dispatch(MyCommand, sys.argv, sys.stdin, sys.stdout, __name__)
```

Generating

```python
@Configuration(retainsevents=False, type="reporting")
class MyGen(GeneratingCommand):
    def generate(self):
        yield {"_time": time.time(), "_raw": "hello"}
```

Match the decorator/`@Configuration` flags to the class. Read the SDK examples in `splunk-sdk-python` before inventing new flags.

## Runtime facts

- Invoked as `| mycmd field=foo` (generating) or `... | mycmd field=foo` (streaming/reporting).
- Chunked protocol speaks length-prefixed metadata + CSV/JSON bodies on stdin/stdout. Do not `print()` debug lines to stdout — you will corrupt the protocol. Log with `self.logger`.
- Prefer passing field names as options, not raw `sys.argv`.
- If the command must read `storage/passwords` or a custom conf, use the service from `self.service` (SDK binds the session).

## Cloud / AppInspect

- `python.version` must be explicit (`check_command_scripts_python_version`).
- No `subprocess` to arbitrary shell, no shipping a second interpreter.
- Keep imported third-party libs inside `lib/` and pure-Python if Cloud-bound.
- Custom commands in other languages are possible but fight Cloud vetting; do not choose that on Cloud.

## When not to write a command

- The job is a lookup — use `transforms.conf` + CSV/KV/external lookup first.
- The job is field extraction — `props.conf` / `INGEST_EVAL` / `EVAL-`.
- The job is a one-off — a macro or saved search is cheaper to maintain.
