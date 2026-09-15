#!/usr/bin/env python3
"""Chunk-upload a DISA library zip through persist /stig_baselines/jobs."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import ssl
import urllib.error
import urllib.parse
import urllib.request

ZIP_PATH = os.path.expanduser(
    os.environ.get("STIG_ZIP", "~/U_Rev_4_SRG-STIG_Sunset_Compilation.zip")
)
HOST = os.environ.get("SPLUNK_HOST", "127.0.0.1")
PORT = int(os.environ.get("SPLUNK_PORT", "8089"))
USER = os.environ.get("SPLUNK_USERNAME", "admin")
PASSWORD = os.environ.get("SPLUNK_PASSWORD", "")
APP = os.environ.get("SPLUNK_APP", "stigs_in_splunk")
CHUNK = 4 * 1024 * 1024
IMPORT_LIMIT = int(os.environ.get("STIG_IMPORT_LIMIT", "2"))


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str, code: int = 1) -> None:
    log("ERROR: " + msg)
    sys.exit(code)


def session_key() -> str:
    if not PASSWORD:
        fail(
            "SPLUNK_PASSWORD is not set. Export it and re-run this probe.",
            2,
        )
    ctx = ssl._create_unverified_context()
    data = urllib.parse.urlencode(
        {"username": USER, "password": PASSWORD}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://{HOST}:{PORT}/services/auth/login",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        fail(f"login HTTP {err.code}")
    except urllib.error.URLError as err:
        fail(f"cannot reach Splunk management port {HOST}:{PORT}: {err}")
    start = body.find("<sessionKey>")
    end = body.find("</sessionKey>")
    if start < 0 or end < 0:
        fail("login did not return a session key")
    return body[start + 12 : end].strip()


def call(key: str, method: str, resource: str, payload=None, timeout: int = 120):
    import urllib.parse

    url = f"https://{HOST}:{PORT}/servicesNS/nobody/{APP}/{resource}"
    body = None
    headers = {
        "Authorization": f"Splunk {key}",
        "Content-Type": "application/json",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as err:
        raw = err.read()
        status = err.code
        text = raw.decode("utf-8", errors="replace")
        fail(f"{method} {resource} HTTP {status}: {text[:800]}")
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return status, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return status, text
    if isinstance(parsed, dict) and "payload" in parsed and len(parsed) <= 3:
        inner = parsed.get("payload")
        if isinstance(inner, str):
            try:
                parsed = json.loads(inner)
            except json.JSONDecodeError:
                pass
    return status, parsed


def main() -> None:

    if not os.path.isfile(ZIP_PATH):
        fail(f"zip not found: {ZIP_PATH}")
    size = os.path.getsize(ZIP_PATH)
    log(f"zip={ZIP_PATH}")
    log(f"size={size} ({size / (1024 * 1024):.1f} MiB)")

    t0 = time.time()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
    from importers.stig_zip import explore_baseline_zip

    local = explore_baseline_zip(ZIP_PATH)
    log(
        "local_explore found=%s skipped=%s elapsed=%.2fs"
        % (len(local["found"]), local["skipped"], time.time() - t0)
    )
    for item in local["found"][:3]:
        log("  " + item["path"])

    key = session_key()
    log("logged in")

    st, ping = call(key, "GET", "stig_baselines")
    n = len(ping) if isinstance(ping, list) else ping
    log(f"GET stig_baselines HTTP {st} count={n if isinstance(n, int) else type(ping).__name__}")

    filename = os.path.basename(ZIP_PATH)
    st, job = call(
        key,
        "POST",
        "stig_baselines/jobs",
        {"filename": filename, "size": size},
    )
    job_id = (job or {}).get("job_id")
    if not job_id:
        fail(f"create job HTTP {st} body={job}")
    log(f"job_id={job_id} HTTP {st}")

    sent = 0
    with open(ZIP_PATH, "rb") as handle:
        while sent < size:
            chunk = handle.read(CHUNK)
            b64 = base64.b64encode(chunk).decode("ascii")
            st, rec = call(
                key,
                "POST",
                f"stig_baselines/jobs/{job_id}",
                {"action": "chunk", "offset": sent, "data": b64},
                timeout=180,
            )
            sent += len(chunk)
            pct = round(100.0 * sent / size)
            log(
                f"chunk offset={sent - len(chunk)} bytes={len(chunk)} "
                f"received={(rec or {}).get('received')} {pct}% HTTP {st}"
            )

    t1 = time.time()
    st, listed = call(
        key,
        "POST",
        f"stig_baselines/jobs/{job_id}",
        {"action": "finalize"},
        timeout=300,
    )
    found = (listed or {}).get("found") or []
    skipped = (listed or {}).get("skipped") or {}
    log(
        f"finalize HTTP {st} found={len(found)} skipped={skipped} "
        f"elapsed={time.time() - t1:.2f}s"
    )
    if len(found) != len(local["found"]):
        log(
            f"WARN found count mismatch local={len(local['found'])} api={len(found)}"
        )

    imported = []
    for item in found[:IMPORT_LIMIT]:
        t2 = time.time()
        st, rec = call(
            key,
            "POST",
            f"stig_baselines/jobs/{job_id}",
            {"action": "import", "path": item["path"]},
            timeout=300,
        )
        imported.append(
            {
                "http": st,
                "path": item["path"],
                "key": (rec or {}).get("_key"),
                "stig_id": (rec or {}).get("stig_id"),
                "title": (rec or {}).get("title"),
                "rules": (rec or {}).get("rule_count"),
                "created": (rec or {}).get("created"),
                "deduplicated": (rec or {}).get("deduplicated"),
                "elapsed": round(time.time() - t2, 2),
            }
        )
        log(
            "import {path} HTTP {http} key={key} stig_id={stig_id} "
            "rules={rules} created={created} dedup={deduplicated} {elapsed}s".format(
                **imported[-1]
            )
        )

    log(f"done job_id={job_id} imported={len(imported)} total={time.time() - t0:.1f}s")
    log(json.dumps({"job_id": job_id, "imported": imported}, indent=2))


if __name__ == "__main__":
    main()
