#!/usr/bin/env python
"""Scheduled search command: report stale reviews (workspace aging policy)."""

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
    try:
        response, content = splunk.rest.simpleRequest(
            "/servicesNS/nobody/stigs_in_splunk/stig_imports/review_aging_report",
            sessionKey=session_key,
            method="GET",
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
        items = doc.get("items") if isinstance(doc.get("items"), list) else []
        if items:
            splunk.Intersplunk.outputResults(items)
            return
        summary = {
            "stale_count": doc.get("stale_count", 0),
            "workspaces_scanned": doc.get("workspaces_scanned", 0),
            "generated_at": doc.get("generated_at"),
            "http_status": doc.get("http_status", status),
            "note": doc.get("note") or doc.get("error"),
        }
        splunk.Intersplunk.outputResults([summary])
    except Exception as exc:
        splunk.Intersplunk.outputResults([{"error": str(exc)}])


if __name__ == "__main__":
    main()
