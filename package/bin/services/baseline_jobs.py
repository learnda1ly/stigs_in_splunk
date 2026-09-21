"""Chunked DISA library zip staging for persist REST (not EAI)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, Optional

from importers.stig_zip import explore_baseline_zip, extract_baseline_xccdf
from services import baselines as baselines_svc


MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024
MAX_CHUNK_BYTES = 4 * 1024 * 1024
JOB_TTL_SECONDS = 6 * 3600


def _jobs_root() -> str:
    home = os.environ.get("SPLUNK_HOME")
    if home:
        path = os.path.join(home, "var", "run", "stigs_in_splunk", "baseline_jobs")
    else:
        path = os.path.join(tempfile.gettempdir(), "stigs_in_splunk_baseline_jobs")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _job_dir(job_id: str) -> str:
    if not job_id or any(ch in job_id for ch in "/\\.") or len(job_id) > 64:
        raise ValueError("invalid job id")
    return os.path.join(_jobs_root(), job_id)


def _meta_path(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), "meta.json")


def _zip_path(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), "upload.zip")


def _load_meta(job_id: str, username: str) -> Dict[str, Any]:
    path = _meta_path(job_id)
    if not os.path.isfile(path):
        raise KeyError(job_id)
    with open(path, encoding="utf-8") as handle:
        meta = json.load(handle)
    if meta.get("created_by") and meta.get("created_by") != username:
        raise PermissionError("access denied to zip job")
    created = float(meta.get("created_at") or 0)
    if created and (time.time() - created) > JOB_TTL_SECONDS:
        shutil.rmtree(_job_dir(job_id), ignore_errors=True)
        raise KeyError(job_id)
    return meta


def _save_meta(meta: Dict[str, Any]) -> None:
    path = _meta_path(meta["job_id"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(meta, handle)
    os.replace(tmp, path)


def _public(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": meta.get("job_id"),
        "filename": meta.get("filename"),
        "size": meta.get("size"),
        "received": meta.get("received"),
        "status": meta.get("status"),
        "found": meta.get("found") or [],
        "skipped": meta.get("skipped") or {"srg": 0, "scap": 0, "other": 0},
    }


def create_job(filename: str, size: int, username: str) -> Dict[str, Any]:
    size = int(size or 0)
    if size <= 0 or size > MAX_ZIP_BYTES:
        raise ValueError(f"zip size must be between 1 and {MAX_ZIP_BYTES} bytes")
    job_id = uuid.uuid4().hex
    os.makedirs(_job_dir(job_id), mode=0o700)
    meta = {
        "job_id": job_id,
        "filename": os.path.basename(filename or "library.zip") or "library.zip",
        "size": size,
        "received": 0,
        "status": "uploading",
        "created_by": username,
        "created_at": time.time(),
        "found": [],
        "skipped": {"srg": 0, "scap": 0, "other": 0},
    }
    _save_meta(meta)
    open(_zip_path(job_id), "wb").close()
    return _public(meta)


def get_job(job_id: str, username: str) -> Dict[str, Any]:
    return _public(_load_meta(job_id, username))


def append_chunk(
    job_id: str, username: str, offset: int, data: bytes
) -> Dict[str, Any]:
    meta = _load_meta(job_id, username)
    if meta.get("status") != "uploading":
        raise ValueError("job is not accepting chunks")
    if not data:
        raise ValueError("empty chunk")
    if len(data) > MAX_CHUNK_BYTES:
        raise ValueError(f"chunk larger than {MAX_CHUNK_BYTES} bytes")
    offset = int(offset)
    if offset != int(meta.get("received") or 0):
        raise ValueError("chunk offset does not match received bytes")
    if offset + len(data) > int(meta["size"]):
        raise ValueError("chunk exceeds declared zip size")
    with open(_zip_path(job_id), "ab") as handle:
        handle.write(data)
    meta["received"] = offset + len(data)
    _save_meta(meta)
    return _public(meta)


def decode_chunk(raw: Any) -> bytes:
    if raw is None:
        return b""
    if isinstance(raw, bytes):
        return raw
    text = str(raw).strip()
    if not text:
        return b""
    try:
        return base64.b64decode(text, validate=False)
    except (ValueError, TypeError) as err:
        raise ValueError("chunk is not valid base64") from err


def finalize_job(job_id: str, username: str) -> Dict[str, Any]:
    meta = _load_meta(job_id, username)
    if int(meta.get("received") or 0) != int(meta.get("size") or 0):
        raise ValueError("upload incomplete")
    explored = explore_baseline_zip(_zip_path(job_id))
    meta["found"] = explored["found"]
    meta["skipped"] = explored["skipped"]
    meta["status"] = "ready"
    _save_meta(meta)
    return _public(meta)


def import_member(
    service, job_id: str, username: str, member_path: str
) -> Dict[str, Any]:
    meta = _load_meta(job_id, username)
    if meta.get("status") != "ready":
        raise ValueError("zip job is not ready")
    xml = extract_baseline_xccdf(_zip_path(job_id), member_path)
    rec, created = baselines_svc.import_baseline(
        service,
        xml,
        "xccdf",
        username,
        source_uri=member_path,
    )
    return {"record": rec, "created": created, "path": member_path}


def delete_job(job_id: str, username: str) -> None:
    path = _job_dir(job_id)
    meta_path = _meta_path(job_id)
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        if meta.get("created_by") and meta.get("created_by") != username:
            raise PermissionError("access denied to zip job")
    shutil.rmtree(path, ignore_errors=True)
