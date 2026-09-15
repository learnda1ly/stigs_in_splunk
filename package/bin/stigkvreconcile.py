#!/usr/bin/env python
"""Scheduled search command: reconcile indexed stig:finding events into KV."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import splunk.Intersplunk  # type: ignore
import splunk.rest  # type: ignore


def main() -> None:
    _results, _dummy, settings = splunk.Intersplunk.getOrganizedResults()
    session_key = settings.get("sessionKey") or settings.get("session_key") or ""
    _keywords, argvals = splunk.Intersplunk.getKeywordsAndOptions()
    earliest = argvals.get("earliest") or ""
    body = json.dumps({"earliest": earliest} if earliest else {})
    try:
        response, content = splunk.rest.simpleRequest(
            "/servicesNS/nobody/stigs_in_splunk/stig_imports/reconcile",
            sessionKey=session_key,
            method="POST",
            jsonargs=body,
            raiseAllErrors=False,
        )
        status = int(response.get("status", 200))
        payload = content.decode("utf-8") if isinstance(content, bytes) else (content or "")
        try:
            doc = json.loads(payload)
            if isinstance(doc, dict) and isinstance(doc.get("payload"), str):
                doc = json.loads(doc["payload"])
        except ValueError:
            doc = {"error": payload[:500], "http_status": status}
        if not isinstance(doc, dict):
            doc = {"result": str(doc), "http_status": status}
        doc.setdefault("http_status", status)
        splunk.Intersplunk.outputResults([doc])
    except Exception as exc:
        splunk.Intersplunk.outputResults([{"error": str(exc)}])


if __name__ == "__main__":
    main()
