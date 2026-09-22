"""Async collection import/export jobs (pollable; artifacts on disk).

Workers never reuse the parent persist ``service`` handle across threads. Each
background run calls ``kv_client.connect(session_key)`` with the request
``authtoken`` captured at job creation (same pattern as a new REST round-trip).

Job directories use lazy TTL expiry on read (``_load_meta``), like
``baseline_jobs``: abandoned jobs remain on disk until TTL plus the next GET
poll; there is no global sweeper.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, Optional

import kv_client
from services import checklists as checklists_svc

JOB_TTL_SECONDS = 6 * 3600
SYNC_ENV = "STIG_COLLECTION_JOBS_SYNC"

_LOCK = threading.Lock()
_ACTIVE: Dict[str, threading.Thread] = {}


def _jobs_root() -> str:
    home = os.environ.get("SPLUNK_HOME")
    if home:
        path = os.path.join(home, "var", "run", "stigs_in_splunk", "collection_jobs")
    else:
        path = os.path.join(tempfile.gettempdir(), "stigs_in_splunk_collection_jobs")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _job_dir(job_id: str) -> str:
    if not job_id or any(ch in job_id for ch in "/\\.") or len(job_id) > 64:
        raise ValueError("invalid job id")
    return os.path.join(_jobs_root(), job_id)


def _meta_path(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), "meta.json")


def _artifact_path(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), "artifact.zip")


def _load_meta(job_id: str, username: str, collection_id: str) -> Dict[str, Any]:
    path = _meta_path(job_id)
    if not os.path.isfile(path):
        raise KeyError(job_id)
    with open(path, encoding="utf-8") as handle:
        meta = json.load(handle)
    if meta.get("stig_collection_id") != collection_id:
        raise KeyError(job_id)
    if meta.get("created_by") and meta.get("created_by") != username:
        raise PermissionError("access denied to collection job")
    created = float(meta.get("created_at") or 0)
    if created and (time.time() - created) > JOB_TTL_SECONDS:
        shutil.rmtree(_job_dir(job_id), ignore_errors=True)
        raise KeyError(job_id)
    return meta


def _save_meta(meta: Dict[str, Any]) -> None:
    path = _meta_path(meta["job_id"])
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(meta, handle)
    os.replace(tmp, path)


def _public(meta: Dict[str, Any], collection_id: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "job_id": meta.get("job_id"),
        "stig_collection_id": meta.get("stig_collection_id"),
        "operation": meta.get("operation"),
        "status": meta.get("status"),
        "format": meta.get("format"),
        "filters": meta.get("filters") or {},
        "created_by": meta.get("created_by"),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "error": meta.get("error"),
    }
    result = meta.get("result")
    if result and meta.get("status") == "succeeded":
        job_id = meta.get("job_id")
        out["result"] = {
            **result,
            "download_path": f"stig_collections/{collection_id}/jobs/{job_id}/download",
        }
    else:
        out["result"] = None
    return out


def _normalize_format(fmt: str) -> str:
    text = (fmt or "").strip().lower().replace("_", "-")
    if text in ("xccdfresults", "xccdf-results"):
        return "xccdf"
    if text not in ("ckl", "cklb", "xccdf"):
        raise ValueError("format must be ckl, cklb, or xccdf")
    return text


def _execute_job(
    session_key: str,
    session: Dict[str, Any],
    job_id: str,
    collection_id: str,
    username: str,
) -> None:
    try:
        meta = _load_meta(job_id, username, collection_id)
    except (KeyError, PermissionError):
        return
    if meta.get("status") not in ("pending", "running"):
        return
    meta["status"] = "running"
    meta["updated_at"] = time.time()
    _save_meta(meta)
    try:
        service = kv_client.connect(session_key)
        export_fmt = meta.get("format") or "cklb"
        filters = meta.get("filters") or {}
        payload = checklists_svc.export_collection_archive(
            service,
            collection_id,
            export_fmt,
            session,
            host_id=filters.get("host_id"),
            baseline_id=filters.get("baseline_id"),
        )
        raw = base64.b64decode(payload.get("content_base64") or "")
        with open(_artifact_path(job_id), "wb") as handle:
            handle.write(raw)
        meta["result"] = {
            "filename": payload.get("filename"),
            "format": payload.get("format"),
            "count": payload.get("count"),
            "files": payload.get("files"),
        }
        meta["status"] = "succeeded"
        meta["error"] = None
    except Exception as exc:  # noqa: BLE001 — job failure surface
        meta["status"] = "failed"
        meta["error"] = str(exc)
        meta["result"] = None
    meta["updated_at"] = time.time()
    _save_meta(meta)


def _start_worker(
    session_key: str,
    session: Dict[str, Any],
    job_id: str,
    collection_id: str,
    username: str,
) -> None:
    session_snap = dict(session or {})
    if os.environ.get(SYNC_ENV) == "1":
        _execute_job(session_key, session_snap, job_id, collection_id, username)
        return

    def _run() -> None:
        _execute_job(session_key, session_snap, job_id, collection_id, username)
        with _LOCK:
            _ACTIVE.pop(job_id, None)

    thread = threading.Thread(target=_run, name=f"stig-collection-job-{job_id}", daemon=True)
    with _LOCK:
        _ACTIVE[job_id] = thread
    thread.start()


def create_archive_export_job(
    service,
    collection_id: str,
    session: Dict[str, Any],
    username: str,
    fmt: str,
    host_id: Optional[str] = None,
    baseline_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate workspace export ACL and queue async archive zip job."""
    export_fmt = _normalize_format(fmt)
    collection_id = (collection_id or "").strip()
    if not collection_id:
        raise ValueError("stig_collection_id is required")
    checklists_svc._require_workspace_export_access(service, collection_id, session)
    session_key = (session or {}).get("authtoken") or ""
    if not str(session_key).strip():
        raise ValueError("session authtoken required for export job")
    job_id = uuid.uuid4().hex
    os.makedirs(_job_dir(job_id), mode=0o700)
    now = time.time()
    meta = {
        "job_id": job_id,
        "stig_collection_id": collection_id,
        "operation": "archive_export",
        "format": export_fmt,
        "filters": {
            "host_id": (host_id or "").strip() or None,
            "baseline_id": (baseline_id or "").strip() or None,
        },
        "status": "pending",
        "created_by": username,
        "created_at": now,
        "updated_at": now,
        "error": None,
        "result": None,
    }
    _save_meta(meta)
    _start_worker(session_key, session, job_id, collection_id, username)
    return get_job(job_id, collection_id, username)


def get_job(
    job_id: str, collection_id: str, username: str
) -> Dict[str, Any]:
    meta = _load_meta(job_id, username, collection_id)
    return _public(meta, collection_id)


def delete_job(job_id: str, collection_id: str, username: str) -> None:
    meta_path = _meta_path(job_id)
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        if meta.get("stig_collection_id") != collection_id:
            raise KeyError(job_id)
        if meta.get("created_by") and meta.get("created_by") != username:
            raise PermissionError("access denied to collection job")
    shutil.rmtree(_job_dir(job_id), ignore_errors=True)
    with _LOCK:
        _ACTIVE.pop(job_id, None)


def download_job_result(
    job_id: str, collection_id: str, username: str
) -> Dict[str, Any]:
    meta = _load_meta(job_id, username, collection_id)
    if meta.get("status") != "succeeded":
        raise ValueError("job is not ready for download")
    path = _artifact_path(job_id)
    if not os.path.isfile(path):
        raise KeyError(job_id)
    with open(path, "rb") as handle:
        raw = handle.read()
    result = dict(meta.get("result") or {})
    result["stig_collection_id"] = collection_id
    result["content_base64"] = base64.b64encode(raw).decode("ascii")
    result["filters"] = meta.get("filters") or {}
    return result
