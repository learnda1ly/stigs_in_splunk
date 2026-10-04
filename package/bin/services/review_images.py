"""Review image attachments (metadata in KV, bytes on disk)."""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import access
import audit
import kv_client
import review_workflow
from models import KV_STIG_REVIEW_IMAGES, kv_record, now_epoch
from services import checklists as checklists_svc
from services import grants as grants_svc
from services import review_history as review_history_svc
from services import reviews as reviews_svc
from services import settings as settings_svc

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    }
)
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _images_root() -> str:
    home = os.environ.get("SPLUNK_HOME")
    if home:
        path = os.path.join(home, "var", "run", "stigs_in_splunk", "review_images")
    else:
        path = os.path.join(tempfile.gettempdir(), "stigs_in_splunk_review_images")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _blob_path(attachment_id: str) -> str:
    if not attachment_id or any(ch in attachment_id for ch in "/\\.") or len(attachment_id) > 64:
        raise ValueError("invalid attachment id")
    return os.path.join(_images_root(), f"{attachment_id}.bin")


def _sanitize_filename(name: str) -> str:
    text = (name or "image").strip() or "image"
    text = _FILENAME_SAFE.sub("_", text)
    return text[:200]


def _normalize_content_type(value: str, filename: str) -> str:
    text = (value or "").strip().lower().split(";")[0].strip()
    if text in ALLOWED_CONTENT_TYPES:
        return text
    guessed, _enc = mimetypes.guess_type(filename)
    if guessed and guessed.lower() in ALLOWED_CONTENT_TYPES:
        return guessed.lower()
    raise ValueError("content_type must be image/png, image/jpeg, image/gif, or image/webp")


def _governance_enabled(service) -> bool:
    return settings_svc.is_governance_enabled(settings_svc.get_settings(service))


def _attachment_allowed(
    row: Dict[str, Any],
    access_ctx: access.WorkspaceAccess,
    host_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    if access_ctx.admin_bypass:
        return True
    host_id = row.get("host_id") or ""
    baseline_id = row.get("baseline_id") or ""
    if access_ctx.acl_host_ids and host_id not in access_ctx.acl_host_ids:
        return False
    if access_ctx.acl_baseline_ids and baseline_id not in access_ctx.acl_baseline_ids:
        return False
    if access_ctx.acl_label_ids:
        host_by_id = host_by_id or {}
        host = host_by_id.get(host_id)
        if not host:
            return False
        if not access.host_allowed(host, access_ctx):
            return False
    return True


def _host_by_id_for_labels(
    service, collection_id: str, access_ctx: access.WorkspaceAccess
) -> Dict[str, Dict[str, Any]]:
    from models import KV_STIG_HOSTS

    host_by_id: Dict[str, Dict[str, Any]] = {}
    if not access_ctx.acl_label_ids:
        return host_by_id
    host_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    for host in kv_client.query_all(host_coll, {"stig_collection_id": collection_id}):
        key = host.get("_key")
        if key:
            host_by_id[str(key)] = host
    return host_by_id


def _access_for_review(
    service,
    review: Dict[str, Any],
    session: Dict[str, Any],
) -> Tuple[Dict[str, Any], access.WorkspaceAccess, List[Dict[str, Any]]]:
    checklist_id = review.get("checklist_id")
    if not checklist_id:
        raise KeyError(review.get("_key"))
    checklist = checklists_svc.get_checklist(service, str(checklist_id), session)
    if not checklist:
        raise KeyError(review.get("_key"))
    collection_id = checklist.get("stig_collection_id") or ""
    if not collection_id:
        raise KeyError(review.get("_key"))
    workspace, access_ctx, grants = grants_svc.workspace_context(
        service, collection_id, session
    )
    if not access_ctx.can_read:
        raise KeyError(review.get("_key"))
    ctx = review_history_svc._context_for_review(service, review, checklist=checklist)
    host_by_id = _host_by_id_for_labels(service, collection_id, access_ctx)
    if not _attachment_allowed(ctx, access_ctx, host_by_id):
        raise KeyError(review.get("_key"))
    return workspace, access_ctx, grants


def _require_writable_review(
    service,
    review_id: str,
    session: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    review = review_history_svc.require_visible_review(service, review_id, session)
    workspace, _access_ctx, grants = _access_for_review(service, review, session)
    if not access.user_can_write_collection(workspace, session, grants):
        raise PermissionError("stig_write required")
    if _governance_enabled(service):
        reviews_svc._ensure_editable(
            review, session, governance_enabled=True
        )
    return review, workspace, grants


def _public_row(rec: Dict[str, Any], *, include_download_path: bool = True) -> Dict[str, Any]:
    out = {
        "_key": rec.get("_key"),
        "review_id": rec.get("review_id"),
        "filename": rec.get("filename"),
        "content_type": rec.get("content_type"),
        "byte_size": rec.get("byte_size"),
        "created_at": rec.get("created_at"),
        "created_by": rec.get("created_by"),
    }
    if include_download_path and rec.get("_key") and rec.get("review_id"):
        rid = rec.get("review_id")
        aid = rec.get("_key")
        out["download_path"] = f"stig_reviews/{rid}/images/{aid}"
    return out


def list_review_images(
    service,
    review_id: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    review = review_history_svc.require_visible_review(service, review_id, session)
    _access_for_review(service, review, session)
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_IMAGES)
    rows = kv_client.query_all(coll, {"review_id": review_id})
    rows.sort(key=lambda r: float(r.get("created_at") or 0))
    return {
        "review_id": review_id,
        "images": [_public_row(r) for r in rows],
    }


def get_review_image(
    service,
    review_id: str,
    attachment_id: str,
    session: Dict[str, Any],
    *,
    include_bytes: bool = True,
) -> Dict[str, Any]:
    review = review_history_svc.require_visible_review(service, review_id, session)
    _access_for_review(service, review, session)
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_IMAGES)
    rec = kv_client.get_by_key(coll, attachment_id)
    if not rec or rec.get("review_id") != review_id:
        raise KeyError(attachment_id)
    out = _public_row(rec)
    if include_bytes:
        path = _blob_path(attachment_id)
        if not os.path.isfile(path):
            raise KeyError(attachment_id)
        with open(path, "rb") as handle:
            raw = handle.read()
        out["content_base64"] = base64.b64encode(raw).decode("ascii")
    return out


def create_review_image(
    service,
    review_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
    *,
    raw_body: Optional[bytes] = None,
) -> Dict[str, Any]:
    review, _workspace, _grants = _require_writable_review(service, review_id, session)
    filename = _sanitize_filename(str(body.get("filename") or "image"))
    content_type = _normalize_content_type(
        str(body.get("content_type") or ""), filename
    )
    raw: bytes
    if raw_body:
        raw = raw_body
    else:
        b64 = body.get("content_base64")
        if not b64:
            raise ValueError("content_base64 or binary body is required")
        try:
            raw = base64.b64decode(str(b64), validate=True)
        except (ValueError, TypeError) as err:
            raise ValueError("invalid content_base64") from err
    if not raw:
        raise ValueError("empty image body")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds maximum size of {MAX_IMAGE_BYTES} bytes")

    ctx = review_history_svc._context_for_review(service, review)
    row = {
        "review_id": review_id,
        "stig_collection_id": ctx["stig_collection_id"],
        "checklist_id": ctx["checklist_id"],
        "host_id": ctx["host_id"],
        "baseline_id": ctx["baseline_id"],
        "filename": filename,
        "content_type": content_type,
        "byte_size": len(raw),
        "created_at": now_epoch(),
        "created_by": username or "unknown",
    }
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_IMAGES)
    stored = kv_client.insert_record(coll, kv_record(row))
    attachment_id = str(stored.get("_key") or "")
    if not attachment_id:
        raise kv_client.KvError("insert succeeded but attachment id missing")
    path = _blob_path(attachment_id)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(raw)
        os.replace(tmp, path)
    except Exception:
        kv_client.delete_record(coll, attachment_id)
        if os.path.isfile(tmp):
            os.remove(tmp)
        if os.path.isfile(path):
            os.remove(path)
        raise
    audit.log_event(
        "create",
        "stig_review_image",
        attachment_id,
        username,
        {"review_id": review_id, "filename": filename, "byte_size": len(raw)},
    )
    return _public_row(stored)


def delete_review_image(
    service,
    review_id: str,
    attachment_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_writable_review(service, review_id, session)
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_IMAGES)
    rec = kv_client.get_by_key(coll, attachment_id)
    if not rec or rec.get("review_id") != review_id:
        raise KeyError(attachment_id)
    kv_client.delete_record(coll, attachment_id)
    path = _blob_path(attachment_id)
    if os.path.isfile(path):
        os.remove(path)
    audit.log_event(
        "delete",
        "stig_review_image",
        attachment_id,
        username,
        {"review_id": review_id, "filename": rec.get("filename")},
    )
    return {"deleted": True, "_key": attachment_id, "review_id": review_id}


def delete_images_for_review(service, review_id: str) -> int:
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_IMAGES)
    removed = 0
    for rec in kv_client.query_all(coll, {"review_id": review_id}):
        key = rec.get("_key")
        if key:
            kv_client.delete_record(coll, key)
            path = _blob_path(str(key))
            if os.path.isfile(path):
                os.remove(path)
            removed += 1
    return removed


def delete_images_for_collection(service, collection_id: str) -> int:
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_IMAGES)
    removed = 0
    for rec in kv_client.query_all(coll, {"stig_collection_id": collection_id}):
        key = rec.get("_key")
        if key:
            kv_client.delete_record(coll, key)
            path = _blob_path(str(key))
            if os.path.isfile(path):
                os.remove(path)
            removed += 1
    return removed
