# dev-settings (Splunk technical add-on)

Optional **development-only** app that turns off splunkd’s in-memory cache for static web assets under `appserver/static`, so UI and dashboard JavaScript changes show up without relying on bump/refresh as often.

## Settings (`default/web.conf` → `[settings]`)

| Setting | Value | Effect |
|---------|-------|--------|
| `js_no_cache` | `true` | Disables Splunk Web JavaScript cache control (see `web.conf` spec; marked deprecated but still used in dev workflows). |
| `cacheEntriesLimit` | `0` | Disables the static-asset entry cache in splunkd. |
| `cacheBytesLimit` | `0` | Disables the static-asset byte cache in splunkd. |

Splunk documents `cacheEntriesLimit=0` for **development only**, not production ([Customization options and caching](https://help.splunk.com/en/splunk-cloud-platform/developing-views-and-apps-for-splunk-web/10.5.2605/customize-splunk-web/customization-options-and-caching)).

You still need a **browser hard refresh** (or disabled cache in devtools) for client-side caching.

## Install

```bash
cp -a dev-settings /opt/splunk/etc/apps/dev-settings
chown -R splunk:splunk /opt/splunk/etc/apps/dev-settings
/opt/splunk/bin/splunk restart
```

Disable for production: `splunk disable app dev-settings` or remove the directory, then restart.

## Verify

```bash
/opt/splunk/bin/splunk btool web list settings --debug=false | egrep 'js_no_cache|cacheEntriesLimit|cacheBytesLimit'
```

Expected: all three non-default values from this app’s `web.conf`.
