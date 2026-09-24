"""Custom REST router for STIG KV store PoC."""

from __future__ import annotations

import os
import sys

_BIN = os.path.dirname(os.path.abspath(__file__))
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import json
import logging
import traceback
from typing import Any, Dict, List, Optional, Tuple

from splunk.persistconn.application import PersistentServerConnectionApplication

import access
import audit
import kv_client
from stig_ucc_kv import _context_session, normalize_roles
from importers.ingest import detect_format
from services import baselines as baselines_svc
from services import baseline_library as baseline_library_svc
from services import baseline_jobs as baseline_jobs_svc
from services import checklists as checklists_svc
from services import baseline_defaults as baseline_defaults_svc
from services import review_aging as review_aging_svc
from services import review_requirements as review_requirements_svc
from services import collection_metadata as collection_metadata_svc
from services import collection_clone as collection_clone_svc
from services import collection_jobs as collection_jobs_svc
from services import collection_transfer as collection_transfer_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import labels as labels_svc
from services import host_metadata as host_metadata_svc
from services import hosts as hosts_svc
from services import assignment as assignment_svc
from services import imports as imports_svc
from services import reconcile as reconcile_svc
from services import reporting as reporting_svc
from services import review_history as review_history_svc
from services import review_peers as review_peers_svc
from services import reviews as reviews_svc
from services import revision_upgrade as revision_upgrade_svc
from services import settings as settings_svc

logger = logging.getLogger("stigs_in_splunk.rest")


def _json_response(payload: Any, status: int = 200) -> Dict[str, Any]:
    return {
        "payload": json.dumps(payload),
        "status": int(status),
        "headers": [("Content-Type", "application/json")],
    }


def _error(message: str, status: int = 400) -> Dict[str, Any]:
    return _json_response({"error": message}, status=status)


def _batch_import_http_status(rec: Dict[str, Any]) -> int:
    """Batch/zip import status aligned with single-file POST /stig_imports."""
    summary = rec.get("summary") or {}
    if int(summary.get("failed") or 0):
        return 200
    if int(summary.get("created") or 0):
        return 201
    return 200


def _parse_path(rest_path: str) -> Tuple[str, List[str]]:
    path = (rest_path or "").strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _body_bytes(payload: Dict[str, Any]) -> bytes:
    raw = payload.get("payload")
    if raw is None:
        return b""
    if isinstance(raw, bytes):
        return raw
    text = str(raw)
    if text[:2] == "PK":
        return text.encode("latin-1", errors="replace")
    return text.encode("utf-8")


def _normalize_query(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        out: Dict[str, Any] = {}
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out[str(item[0])] = item[1]
        return out
    return {}


def _body_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("payload")
    if isinstance(raw, dict):
        return raw
    data = _body_bytes(payload)
    if not data:
        return {}
    try:
        return json.loads(data.decode("utf-8"))
    except (TypeError, ValueError):
        return {}


def _enrich_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Merge Splunk roles from current-context; passSession often omits role list."""
    token = session.get("authtoken")
    if not token:
        return session
    merged_roles = normalize_roles(session.get("roles"))
    try:
        extra = _context_session(token)
    except Exception:
        session["roles"] = merged_roles
        return session
    if extra.get("user"):
        session["user"] = extra["user"]
    for role in normalize_roles(extra.get("roles")):
        if role not in merged_roles:
            merged_roles.append(role)
    session["roles"] = merged_roles
    if extra.get("capabilities") and not session.get("capabilities"):
        session["capabilities"] = extra["capabilities"]
    return session


def _kv_connect(session: Dict[str, Any]):
    """KV collections are app-owner scoped; workspace ACL is enforced in services."""
    token = session.get("authtoken")
    username = (session.get("user") or "").strip()
    roles = access.user_roles(session)
    if token and roles & access.ADMIN_ROLES:
        return kv_client.connect(token)
    try:
        import splunk.auth as splunk_auth

        if username:
            trusted = splunk_auth.getSessionKeyForTrustedUser(username)
            if trusted:
                return kv_client.connect(trusted)
        trusted_admin = splunk_auth.getSessionKeyForTrustedUser("admin")
        if trusted_admin:
            return kv_client.connect(trusted_admin)
    except Exception:
        logger.debug("privileged KV session unavailable", exc_info=True)
    if token:
        return kv_client.connect(token)
    raise PermissionError("authentication required")


class StigRestHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line: str, command_arg: str):
        PersistentServerConnectionApplication.__init__(self)

    def handle(self, in_string: str) -> Dict[str, Any]:
        try:
            payload = json.loads(in_string)
            session = payload.get("session") or {}
            audit.set_indexing_context(session.get("authtoken") or "")
            try:
                return self._dispatch(payload)
            finally:
                audit.clear_indexing_context()
        except Exception as exc:
            logger.error("rest_error %s", traceback.format_exc())
            return _error(str(exc), status=500)

    def _dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        method = (payload.get("method") or "GET").upper()
        session = _enrich_session(dict(payload.get("session") or {}))
        authtoken = session.get("authtoken")
        if not authtoken:
            return _error("authentication required", status=401)

        username = session.get("user") or "unknown"
        query = _normalize_query(payload.get("query"))
        rest_path = (
            payload.get("rest_path")
            or payload.get("path_info")
            or payload.get("path")
            or ""
        )
        resource, parts = _parse_path(rest_path)

        service = _kv_connect(session)

        try:
            if resource == "stig_collections":
                return self._collections(method, parts, query, payload, service, session, username)
            if resource == "stig_findings":
                return self._findings(method, parts, query, service, session)
            if resource == "stig_hosts":
                return self._hosts(method, parts, query, payload, service, session, username)
            if resource == "stig_baselines":
                return self._baselines(method, parts, query, payload, service, session, username)
            if resource == "stig_checklists":
                return self._checklists(method, parts, query, payload, service, session, username)
            if resource == "stig_reviews":
                return self._reviews(method, parts, query, payload, service, session, username)
            if resource == "stig_settings":
                return self._settings(method, parts, payload, service, username)
            if resource == "stig_imports":
                return self._imports(method, parts, query, payload, service, session, username)
            if resource == "stig_assignment_rules":
                return self._assignment_rules(
                    method, parts, query, payload, service, session, username
                )
            if resource == "stig_host_baseline_assignments":
                return self._host_baseline_assignments(
                    method, parts, query, payload, service, session, username
                )
            if resource == "stig_assignment":
                return self._assignment_preview(
                    method, parts, query, payload, service, session, username
                )
            if resource == "stigs_in_splunk_baseline":
                return self._ucc_baselines(
                    method, parts, query, payload, service, session, username
                )
            return _error(f"unknown resource: {resource}", status=404)
        except PermissionError as exc:
            return _error(str(exc), status=403)
        except KeyError:
            return _error("not found", status=404)
        except ValueError as exc:
            return _error(str(exc), status=400)
        except kv_client.KvError as exc:
            return _error(str(exc), status=int(exc.status or 500))

    def _collections(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                return _json_response(collections_svc.list_collections(service, session))
            if method == "POST":
                body = _body_json(payload)
                rec = collections_svc.create_collection(service, body, username)
                return _json_response(rec, status=201)
            return _error("method not allowed", status=405)

        if parts[0] == "meta":
            if len(parts) == 2 and parts[1] == "metrics":
                if method != "GET":
                    return _error("method not allowed", status=405)
                return _json_response(
                    reporting_svc.meta_collection_metrics(service, session, query)
                )
            if len(parts) == 3 and parts[1] == "metrics" and parts[2] == "summary":
                if method != "GET":
                    return _error("method not allowed", status=405)
                return _json_response(
                    reporting_svc.meta_collection_metrics_summary(
                        service, session, query
                    )
                )
            return _error("not found", status=404)

        key = parts[0]
        if len(parts) >= 2 and parts[1] == "baseline_defaults":
            if method == "GET" and len(parts) == 2:
                try:
                    return _json_response(
                        baseline_defaults_svc.list_defaults(service, key, session)
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            if method in ("POST", "PUT", "PATCH") and len(parts) == 2:
                body = _body_json(payload)
                try:
                    rec = baseline_defaults_svc.set_default(
                        service,
                        key,
                        body.get("stig_id") or body.get("benchmark_id") or "",
                        body.get("baseline_id") or "",
                        username,
                        session,
                    )
                    return _json_response(rec)
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            if method == "DELETE" and len(parts) == 3:
                try:
                    return _json_response(
                        baseline_defaults_svc.delete_default(
                            service, key, parts[2], username, session
                        )
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            return _error("method not allowed", status=405)

        if len(parts) >= 2 and parts[1] == "review_requirements":
            if method == "GET" and len(parts) == 2:
                try:
                    return _json_response(
                        review_requirements_svc.get_requirements(service, key, session)
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            if method in ("POST", "PUT", "PATCH") and len(parts) == 2:
                body = _body_json(payload)
                try:
                    return _json_response(
                        review_requirements_svc.patch_requirements(
                            service, key, body, username, session
                        )
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            return _error("method not allowed", status=405)

        if len(parts) >= 2 and parts[1] in ("review_aging", "review-aging"):
            if len(parts) == 2:
                if method == "GET":
                    try:
                        return _json_response(
                            review_aging_svc.get_config(service, key, session)
                        )
                    except KeyError:
                        return _error("not found", status=404)
                    except PermissionError as exc:
                        return _error(str(exc), status=403)
                if method in ("POST", "PUT", "PATCH"):
                    body = _body_json(payload)
                    try:
                        return _json_response(
                            review_aging_svc.patch_config(
                                service, key, body, username, session
                            )
                        )
                    except KeyError:
                        return _error("not found", status=404)
                    except PermissionError as exc:
                        return _error(str(exc), status=403)
                    except ValueError as exc:
                        return _error(str(exc), status=400)
                return _error("method not allowed", status=405)
            if len(parts) == 3 and parts[2] == "stale":
                if method != "GET":
                    return _error("method not allowed", status=405)
                try:
                    return _json_response(
                        review_aging_svc.list_stale_reviews(
                            service, key, session, query
                        )
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            return _error("not found", status=404)

        if len(parts) >= 2 and parts[1] == "metadata":
            if method == "GET" and len(parts) == 2:
                try:
                    return _json_response(
                        collection_metadata_svc.get_metadata(service, key, session)
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
                except ValueError as exc:
                    return _error(str(exc), status=400)
            if method in ("POST", "PUT", "PATCH") and len(parts) == 2:
                body = _body_json(payload)
                try:
                    return _json_response(
                        collection_metadata_svc.patch_metadata(
                            service, key, body, username, session
                        )
                    )
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
                except ValueError as exc:
                    return _error(str(exc), status=400)
            return _error("method not allowed", status=405)

        if len(parts) >= 2 and parts[1] == "grants":
            return self._collection_grants(
                method, key, parts[2:], payload, service, session, username
            )

        if len(parts) >= 2 and parts[1] == "labels":
            return self._collection_labels(
                method, key, parts[2:], payload, service, session, username
            )

        if len(parts) == 2 and parts[1] == "clone":
            if method not in ("POST", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                result = collection_clone_svc.clone_collection(
                    service, key, body, username, session
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            return _json_response(result, status=201)

        if len(parts) == 3 and parts[1] == "export-to":
            if method not in ("POST", "PUT"):
                return _error("method not allowed", status=405)
            dest_id = parts[2]
            body = _body_json(payload)
            try:
                result = collection_transfer_svc.export_hosts_to_collection(
                    service, key, dest_id, body, username, session
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            status = 201 if int((result.get("summary") or {}).get("moved") or 0) else 200
            return _json_response(result, status=status)

        if len(parts) == 2 and parts[1] == "upgrade_checklists":
            if method not in ("POST", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                return _json_response(
                    revision_upgrade_svc.upgrade_collection_checklists(
                        service,
                        key,
                        body.get("baseline_id") or "",
                        username,
                        session,
                        from_baseline_id=body.get("from_baseline_id") or "",
                        stig_id=body.get("stig_id")
                        or body.get("benchmark_id")
                        or "",
                    )
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)

        if len(parts) == 2 and parts[1] == "metrics":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    reporting_svc.collection_metrics(service, key, session)
                )
            except KeyError:
                return _error("not found", status=404)
        if len(parts) == 3 and parts[1] == "findings" and parts[2] == "aggregate":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    reporting_svc.collection_findings_aggregate(
                        service, key, session, query
                    )
                )
            except KeyError:
                return _error("not found", status=404)
        if len(parts) == 2 and parts[1] == "findings":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    reporting_svc.collection_findings(service, key, session, query)
                )
            except KeyError:
                return _error("not found", status=404)
        if len(parts) == 3 and parts[1] == "unreviewed" and parts[2] == "rules":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    reporting_svc.collection_unreviewed_rules(
                        service, key, session, query
                    )
                )
            except KeyError:
                return _error("not found", status=404)
            except ValueError as exc:
                return _error(str(exc), status=400)
        if len(parts) == 3 and parts[1] == "unreviewed" and parts[2] == "assets":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    reporting_svc.collection_unreviewed_assets(
                        service, key, session, query
                    )
                )
            except KeyError:
                return _error("not found", status=404)
            except ValueError as exc:
                return _error(str(exc), status=400)

        if len(parts) == 2 and parts[1] == "review-history":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    review_history_svc.list_collection_review_history(
                        service, key, session, query
                    )
                )
            except KeyError:
                return _error("not found", status=404)

        if len(parts) >= 2 and parts[1] == "jobs":
            return self._collection_jobs(
                method, key, parts[2:], query, payload, service, session, username
            )

        if len(parts) == 2 and parts[1] == "imports":
            if method != "POST":
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            entries = body.get("files") or body.get("entries")
            zip_body = _body_bytes(payload)
            try:
                if entries is not None:
                    rec = imports_svc.import_checklist_batch(
                        service, session, username, key, entries
                    )
                elif zip_body and (
                    (body.get("format") or "").lower() == "zip"
                    or zip_body[:2] == b"PK"
                ):
                    rec = imports_svc.import_checklist_zip(
                        service,
                        session,
                        username,
                        key,
                        zip_body,
                        source_uri=body.get("source_uri")
                        or query.get("source_uri")
                        or "archive.zip",
                    )
                else:
                    return _error(
                        "JSON body requires files[] or a zip payload with format=zip",
                        status=400,
                    )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            return _json_response(rec, status=_batch_import_http_status(rec))

        archive_fmt = parts[2].lower().replace("_", "-") if len(parts) > 2 else ""
        archive_formats = {"ckl", "cklb", "xccdf", "xccdf-results", "xccdfresults"}
        if len(parts) == 3 and parts[1] == "archive" and archive_fmt in archive_formats:
            if method not in ("POST", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                result = checklists_svc.export_collection_archive(
                    service,
                    key,
                    parts[2],
                    session,
                    host_id=body.get("host_id") or query.get("host_id"),
                    baseline_id=body.get("baseline_id") or query.get("baseline_id"),
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            return _json_response(result)

        if len(parts) == 2 and parts[1] == "poam":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                result = reporting_svc.collection_poam(service, key, session, query)
            except KeyError:
                return _error("not found", status=404)
            if result.get("format") == "csv":
                filename = result.get("filename") or "stig_poam.csv"
                headers = [
                    ("Content-Type", "text/csv; charset=utf-8"),
                    (
                        "Content-Disposition",
                        f'attachment; filename="{filename}"',
                    ),
                ]
                row_count = result.get("row_count")
                if row_count is not None:
                    headers.append(("X-Stig-Row-Count", str(row_count)))
                return {
                    "payload": result.get("content") or "",
                    "status": 200,
                    "headers": headers,
                }
            return _json_response(result)

        if method == "GET":
            rec = collections_svc.get_collection(service, key)
            grants = grants_svc.query_grants(service, key)
            if not rec or not access.user_can_read_collection(rec, session, grants):
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            rec = collections_svc.get_collection(service, key)
            if not rec:
                return _error("not found", status=404)
            grants = grants_svc.query_grants(service, key)
            ctx = access.resolve_workspace_access(rec, session, grants)
            if not ctx.edit_collection and not ctx.edit_access_principals:
                return _error("not found", status=404)
            body = _body_json(payload)
            if "access_principals" in body and not ctx.edit_access_principals:
                if not access.user_has_stig_admin(session):
                    return _error("owner or stig_admin required to change access_principals", status=403)
            updated = collections_svc.update_collection(service, key, body, username)
            return _json_response(updated)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            body = _body_json(payload)
            cascade = collections_svc.parse_cascade_flag(
                query.get("cascade"), body.get("cascade")
            )
            try:
                result = collections_svc.delete_collection(
                    service, key, username, cascade=cascade, source="rest"
                )
            except KeyError:
                return _error("not found", status=404)
            except collections_svc.CollectionDeleteBlockedError as exc:
                return _json_response(
                    {
                        "error": str(exc),
                        "children": exc.counts,
                        "cascade_required": True,
                    },
                    status=409,
                )
            return _json_response(result)
        return _error("method not allowed", status=405)

    def _collection_grants(
        self,
        method: str,
        collection_id: str,
        parts: List[str],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                try:
                    rows = grants_svc.list_grants(service, collection_id, session)
                    return _json_response(rows)
                except KeyError:
                    return _error("not found", status=404)
            if method == "POST":
                body = _body_json(payload)
                try:
                    rec = grants_svc.create_grant(
                        service, collection_id, body, username, session
                    )
                    return _json_response(rec, status=201)
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            return _error("method not allowed", status=405)

        grant_id = parts[0]
        if len(parts) == 2 and parts[1] == "acl":
            if method not in ("PUT", "PATCH", "POST"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                rec = grants_svc.update_grant_acl(
                    service, collection_id, grant_id, body, username, session
                )
                return _json_response(rec)
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)

        if method == "GET":
            rec = grants_svc.get_grant(service, collection_id, grant_id, session)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "PUT", "POST"):
            body = _body_json(payload)
            try:
                rec = grants_svc.update_grant(
                    service, collection_id, grant_id, body, username, session
                )
                return _json_response(rec)
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
        if method == "DELETE":
            try:
                grants_svc.delete_grant(
                    service, collection_id, grant_id, username, session
                )
                return _json_response({"deleted": grant_id})
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
        return _error("method not allowed", status=405)

    def _collection_labels(
        self,
        method: str,
        collection_id: str,
        parts: List[str],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                try:
                    rows = labels_svc.list_labels(service, collection_id, session)
                    return _json_response(rows)
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            if method == "POST":
                body = _body_json(payload)
                try:
                    rec = labels_svc.create_label(
                        service, collection_id, body, username, session
                    )
                    return _json_response(rec, status=201)
                except ValueError as exc:
                    return _error(str(exc), status=400)
                except KeyError:
                    return _error("not found", status=404)
                except PermissionError as exc:
                    return _error(str(exc), status=403)
            return _error("method not allowed", status=405)

        label_id = parts[0]
        if len(parts) == 2 and parts[1] == "assets":
            if method not in ("POST", "PUT", "PATCH"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                result = labels_svc.assign_label_to_hosts(
                    service, collection_id, label_id, body, username, session
                )
                return _json_response(result)
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)

        if method == "GET":
            rec = labels_svc.get_label(service, collection_id, label_id, session)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "PUT", "POST"):
            body = _body_json(payload)
            try:
                rec = labels_svc.update_label(
                    service, collection_id, label_id, body, username, session
                )
                return _json_response(rec)
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
        if method == "DELETE":
            try:
                labels_svc.delete_label(
                    service, collection_id, label_id, username, session
                )
                return _json_response({"deleted": label_id})
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
        return _error("method not allowed", status=405)

    def _findings(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        service,
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        if parts:
            return _error("not found", status=404)
        if method != "GET":
            return _error("method not allowed", status=405)
        collection_id = (query.get("stig_collection_id") or "").strip()
        if not collection_id:
            return _error("stig_collection_id is required")
        try:
            return _json_response(
                reporting_svc.collection_findings(service, collection_id, session, query)
            )
        except KeyError:
            return _error("not found", status=404)

    def _hosts(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                cid = query.get("stig_collection_id")
                label_id = (query.get("label_id") or "").strip() or None
                return _json_response(
                    hosts_svc.list_hosts(service, session, cid, label_id=label_id)
                )
            if method == "POST":
                body = _body_json(payload)
                rec = hosts_svc.create_host(service, body, username, session)
                return _json_response(rec, status=201)
            return _error("method not allowed", status=405)

        key = parts[0]
        if len(parts) >= 2:
            sub = parts[1]
            if sub == "metadata":
                if method == "GET" and len(parts) == 2:
                    try:
                        return _json_response(
                            host_metadata_svc.get_metadata(service, key, session)
                        )
                    except KeyError:
                        return _error("not found", status=404)
                    except PermissionError as exc:
                        return _error(str(exc), status=403)
                    except ValueError as exc:
                        return _error(str(exc), status=400)
                if method in ("POST", "PUT", "PATCH") and len(parts) == 2:
                    body = _body_json(payload)
                    try:
                        return _json_response(
                            host_metadata_svc.patch_metadata(
                                service, key, body, username, session
                            )
                        )
                    except KeyError:
                        return _error("not found", status=404)
                    except PermissionError as exc:
                        return _error(str(exc), status=403)
                    except ValueError as exc:
                        return _error(str(exc), status=400)
                return _error("method not allowed", status=405)
            if sub == "checklists" and method == "GET":
                try:
                    rows = checklists_svc.list_checklists_for_host(
                        service, key, session
                    )
                except KeyError:
                    return _error("not found", status=404)
                return _json_response(rows)
            if sub == "stigs":
                if method == "POST" and len(parts) == 2:
                    body = _body_json(payload)
                    try:
                        checklist, created = checklists_svc.assign_stig_to_host(
                            service, key, body, username, session
                        )
                    except KeyError:
                        return _error("not found", status=404)
                    except PermissionError as exc:
                        return _error(str(exc), status=403)
                    except ValueError as exc:
                        return _error(str(exc), status=400)
                    out = dict(checklist)
                    out["created"] = created
                    return _json_response(out, status=201 if created else 200)
                if method == "DELETE" and len(parts) == 3:
                    baseline_ref = parts[2]
                    try:
                        result = checklists_svc.unassign_stig_from_host(
                            service, key, baseline_ref, username, session
                        )
                    except KeyError:
                        return _error("not found", status=404)
                    except PermissionError as exc:
                        return _error(str(exc), status=403)
                    except ValueError as exc:
                        return _error(str(exc), status=400)
                    return _json_response(result)
                return _error("method not allowed", status=405)

        if method == "GET":
            rec = hosts_svc.get_host(service, key, session)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            try:
                updated = hosts_svc.update_host(
                    service, key, body, username, session
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            return _json_response(updated)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            hosts_svc.delete_host(service, key, username, session)
            return _json_response({"deleted": key})
        return _error("method not allowed", status=405)

    def _ucc_baselines(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        """Persist stand-in for UCC /stigs_in_splunk_baseline (not EAI XML)."""
        if method == "GET":
            want = (parts[0] if parts else "") or str(query.get("id") or "").strip()
            entries = []
            acl = {
                "app": "stigs_in_splunk",
                "can_change_perms": False,
                "can_list": True,
                "can_share_app": True,
                "can_share_global": False,
                "can_share_user": False,
                "can_write": True,
                "modifiable": True,
                "owner": "nobody",
                "perms": {"read": ["*"], "write": ["*"]},
                "sharing": "app",
            }
            for rec in baselines_svc.list_baselines_for_user(service, session):
                name = baselines_svc.ucc_name_for(rec)
                if not name:
                    continue
                if want and name != want:
                    continue
                content = {
                    "disabled": False,
                    "eai:acl": acl,
                    "name": name,
                    "stig_id": rec.get("stig_id") or "",
                    "title": rec.get("title") or rec.get("stig_name") or "",
                    "version": rec.get("version") or "",
                    "release_info": rec.get("release_info") or "",
                    "rule_count": rec.get("rule_count") or 0,
                    "source_type": rec.get("source_type") or "",
                    "source_uri": rec.get("source_uri") or "",
                    "content_fingerprint": rec.get("content_fingerprint") or "",
                    "format": rec.get("source_type") or "",
                    "content": "",
                }
                entries.append(
                    {
                        "name": name,
                        "id": name,
                        "acl": acl,
                        "content": content,
                    }
                )
            return _json_response({"entry": entries})

        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            name = (parts[0] if parts else "").strip()
            if not name:
                return _error("baseline id required")
            rec = baselines_svc.find_baseline_by_ucc_name(service, name)
            if not rec:
                return _error("not found", status=404)
            baselines_svc.delete_baseline(service, rec["_key"], username)
            return _json_response({"deleted": name})

        if method in ("POST", "PUT", "PATCH"):
            # UCC reads messages[0].text; {error: "..."} becomes "An unknown error occurred".
            msg = (
                "Configuration cannot import a DISA library zip. Splunk used to wrap "
                "that file in EAI XML and fail with Unable to xml-parse. Open Import "
                "and drop the zip there — it is uploaded in 4MB persist chunks and "
                "every Manual-xccdf STIG is imported automatically."
            )
            return _json_response(
                {
                    "messages": [{"type": "ERROR", "text": msg}],
                    "error": msg,
                },
                status=400,
            )
        return _error("method not allowed", status=405)

    def _baselines(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        scope_filter = (query.get("stig_collection_id") or "").strip() or None
        visible_ids = baselines_svc.visible_baseline_id_set(
            service, session, stig_collection_id=scope_filter
        )

        if parts == ["import"]:
            if method != "POST":
                return _error("method not allowed", status=405)
            fmt = query.get("format") or "xccdf"
            source_uri = query.get("source_uri") or ""
            body_json = _body_json(payload)
            scope = (
                body_json.get("stig_collection_id")
                or query.get("stig_collection_id")
                or ""
            ).strip()
            if scope:
                grants_svc.require_workspace_write(service, scope, session)
            body = _body_bytes(payload)
            if not body:
                return _error("empty import body")
            results = baselines_svc.import_baselines_payload(
                service,
                body,
                fmt,
                username,
                source_uri,
                stig_collection_id=scope,
            )
            created_any = any(item.get("created") for item in results)
            payload_out = {
                "imported": len(results),
                "created": sum(1 for item in results if item.get("created")),
                "deduplicated": sum(1 for item in results if not item.get("created")),
                "baselines": [item["record"] for item in results],
            }
            if len(results) == 1:
                payload_out.update(results[0]["record"])
                payload_out["created"] = bool(results[0].get("created"))
                payload_out["deduplicated"] = not results[0].get("created")
            return _json_response(payload_out, status=201 if created_any else 200)

        if parts and parts[0] == "jobs":
            return self._baseline_jobs(
                method, parts[1:], query, payload, service, username
            )

        if parts == ["gc_orphan_rules"]:
            if method not in ("GET", "POST"):
                return _error("method not allowed", status=405)
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            body = _body_json(payload)
            execute = False
            if method == "POST":
                execute = baselines_svc.parse_orphan_gc_execute_flag(query, body)
            report = baselines_svc.gc_orphan_baseline_rules(
                service, username, execute=execute
            )
            return _json_response(report)

        if parts == ["hierarchy"]:
            if method != "GET":
                return _error("method not allowed", status=405)
            return _json_response(
                baseline_library_svc.list_hierarchy(
                    service,
                    session,
                    stig_collection_id=scope_filter,
                )
            )

        if len(parts) >= 2 and parts[0] == "by_stig":
            if method != "GET":
                return _error("method not allowed", status=405)
            stig_id = "/".join(parts[1:])
            entry = baseline_library_svc.get_benchmark(
                service,
                stig_id,
                session,
                stig_collection_id=scope_filter,
            )
            if not entry:
                return _error("not found", status=404)
            return _json_response(entry)

        if len(parts) == 2 and parts[0] == "rules":
            if method != "GET":
                return _error("method not allowed", status=405)
            rule_ref = parts[1]
            stig_filter = (query.get("stig_id") or "").strip()
            matches = baselines_svc.find_catalog_rules_by_ref(
                service,
                rule_ref,
                stig_id=stig_filter,
                visible_baseline_ids=visible_ids,
            )
            if not matches:
                return _error("not found", status=404)
            return _json_response(
                {
                    "rule_ref": rule_ref,
                    "stig_id": stig_filter or None,
                    "match_count": len(matches),
                    "matches": matches,
                }
            )

        if len(parts) == 2 and parts[0] == "ccis":
            if method != "GET":
                return _error("method not allowed", status=405)
            cci = parts[1]
            stig_filter = (query.get("stig_id") or "").strip()
            matches = baselines_svc.find_catalog_rules_by_cci(
                service,
                cci,
                stig_id=stig_filter,
                visible_baseline_ids=visible_ids,
            )
            return _json_response(
                {
                    "cci": baselines_svc.normalize_cci(cci),
                    "stig_id": stig_filter or None,
                    "match_count": len(matches),
                    "matches": matches,
                }
            )

        if len(parts) == 2 and parts[0] == "groups":
            if method != "GET":
                return _error("method not allowed", status=405)
            group_id = parts[1]
            stig_filter = (query.get("stig_id") or "").strip()
            matches = baselines_svc.find_catalog_rules_by_group_id(
                service,
                group_id,
                stig_id=stig_filter,
                visible_baseline_ids=visible_ids,
            )
            return _json_response(
                {
                    "group_id": group_id,
                    "stig_id": stig_filter or None,
                    "match_count": len(matches),
                    "matches": matches,
                }
            )

        if len(parts) == 2 and parts[0] == "rule":
            if method != "GET":
                return _error("method not allowed", status=405)
            detail = baseline_library_svc.get_rule_by_key(service, parts[1])
            if not detail:
                return _error("not found", status=404)
            if str(detail.get("baseline_id") or "") not in visible_ids:
                return _error("not found", status=404)
            return _json_response(detail)

        if len(parts) == 3 and parts[1] == "rules":
            baseline_id = parts[0]
            rule_ref = parts[2]
            if method != "GET":
                return _error("method not allowed", status=405)
            if baseline_id not in visible_ids:
                return _error("not found", status=404)
            detail = baseline_library_svc.get_baseline_rule(
                service,
                baseline_id,
                rule_ref,
                group_id=str(query.get("group_id") or ""),
            )
            if not detail:
                return _error("not found", status=404)
            return _json_response(detail)

        if len(parts) == 2 and parts[1] == "rules":
            baseline_id = parts[0]
            if method != "GET":
                return _error("method not allowed", status=405)
            if baseline_id not in visible_ids:
                return _error("not found", status=404)
            rules = baselines_svc.list_baseline_rules(service, baseline_id)
            return _json_response(rules)

        if not parts:
            if method == "GET":
                return _json_response(
                    baselines_svc.list_baselines_for_user(
                        service, session, stig_collection_id=scope_filter
                    )
                )
            return _error("method not allowed", status=405)

        key = parts[0]
        if method == "GET":
            rec = baselines_svc.get_baseline_for_user(service, session, key)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            baselines_svc.delete_baseline(service, key, username)
            return _json_response({"deleted": key})
        return _error("not found", status=404)

    def _collection_jobs(
        self,
        method: str,
        collection_id: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method != "POST":
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            operation = (body.get("operation") or "archive_export").strip().lower()
            if operation != "archive_export":
                return _error("operation must be archive_export", status=400)
            try:
                rec = collection_jobs_svc.create_archive_export_job(
                    service,
                    collection_id,
                    session,
                    username,
                    body.get("format") or query.get("format") or "",
                    host_id=body.get("host_id") or query.get("host_id"),
                    baseline_id=body.get("baseline_id") or query.get("baseline_id"),
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            return _json_response(rec, status=201)

        job_id = parts[0]
        if len(parts) == 2 and parts[1] == "download":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    collection_jobs_svc.download_job_result(
                        job_id, collection_id, username
                    )
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)

        if len(parts) != 1:
            return _error("not found", status=404)

        if method == "GET":
            try:
                return _json_response(
                    collection_jobs_svc.get_job(job_id, collection_id, username)
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
        if method == "DELETE":
            try:
                collection_jobs_svc.delete_job(job_id, collection_id, username)
                return _json_response({"deleted": job_id})
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
        return _error("method not allowed", status=405)

    def _baseline_jobs(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method != "POST":
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            rec = baseline_jobs_svc.create_job(
                body.get("filename") or "",
                int(body.get("size") or 0),
                username,
            )
            return _json_response(rec, status=201)
        job_id = parts[0]
        if method == "GET":
            return _json_response(baseline_jobs_svc.get_job(job_id, username))
        if method == "DELETE":
            baseline_jobs_svc.delete_job(job_id, username)
            return _json_response({"deleted": job_id})
        if method != "POST":
            return _error("method not allowed", status=405)
        body = _body_json(payload)
        action = (body.get("action") or query.get("action") or "").strip().lower()
        if action == "chunk":
            data = baseline_jobs_svc.decode_chunk(body.get("data"))
            rec = baseline_jobs_svc.append_chunk(
                job_id, username, int(body.get("offset") or 0), data
            )
            return _json_response(rec)
        if action == "finalize":
            rec = baseline_jobs_svc.finalize_job(job_id, username)
            return _json_response(rec)
        if action == "import":
            rec = baseline_jobs_svc.import_member(
                service, job_id, username, body.get("path") or ""
            )
            payload_out = dict(rec.get("record") or {})
            payload_out["created"] = bool(rec.get("created"))
            payload_out["deduplicated"] = not rec.get("created")
            payload_out["path"] = rec.get("path")
            return _json_response(payload_out, status=201 if rec.get("created") else 200)
        return _error("action must be chunk, finalize, or import")

    def _checklists(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if parts and parts[0] == "export_bulk":
            if method not in ("POST", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            ids = body.get("checklist_ids") or body.get("ids") or []
            if isinstance(ids, str):
                ids = [part.strip() for part in ids.split(",") if part.strip()]
            fmt = body.get("format") or query.get("format") or "cklb"
            collection_id = (
                body.get("stig_collection_id") or query.get("stig_collection_id") or ""
            ).strip()
            try:
                return _json_response(
                    checklists_svc.export_checklists_bulk(
                        service,
                        ids if not collection_id else None,
                        fmt,
                        session,
                        stig_collection_id=collection_id or None,
                        host_id=body.get("host_id") or query.get("host_id"),
                        baseline_id=body.get("baseline_id") or query.get("baseline_id"),
                    )
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)

        if parts and parts[0] == "summary":
            if method != "GET":
                return _error("method not allowed", status=405)
            return _json_response(
                checklists_svc.summarize_checklists(
                    service, session, query.get("stig_collection_id")
                )
            )

        if len(parts) == 2 and parts[1] == "upgrade":
            checklist_id = parts[0]
            if method not in ("POST", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                return _json_response(
                    revision_upgrade_svc.upgrade_checklist(
                        service,
                        checklist_id,
                        body.get("baseline_id") or "",
                        username,
                        session,
                    )
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)

        if len(parts) == 2 and parts[1] == "validate":
            checklist_id = parts[0]
            if method == "GET":
                return _json_response(
                    reviews_svc.validate_checklist(
                        service, checklist_id, session, persist=False
                    )
                )
            if method in ("POST", "PUT", "PATCH"):
                return _json_response(
                    reviews_svc.validate_checklist(
                        service, checklist_id, session, persist=True
                    )
                )
            return _error("method not allowed", status=405)

        if len(parts) == 2 and parts[1] == "export":
            checklist_id = parts[0]
            if method != "GET":
                return _error("method not allowed", status=405)
            fmt = query.get("format") or "cklb"
            content = checklists_svc.export_checklist(service, checklist_id, fmt, session)
            fmt_lower = (fmt or "").lower().replace("_", "-")
            if fmt_lower == "cklb":
                ctype = "application/json"
            else:
                ctype = "application/xml"
            return {
                "payload": content,
                "status": 200,
                "headers": [("Content-Type", ctype)],
            }

        if not parts:
            if method == "GET":
                cid = query.get("stig_collection_id")
                summary = str(query.get("summary") or "").lower() in {
                    "1",
                    "true",
                    "yes",
                }
                if summary:
                    return _json_response(
                        checklists_svc.summarize_checklists(service, session, cid)
                    )
                return _json_response(checklists_svc.list_checklists(service, session, cid))
            if method == "POST":
                body = _body_json(payload)
                rec = checklists_svc.create_checklist(service, body, username, session)
                return _json_response(rec, status=201)
            return _error("method not allowed", status=405)

        key = parts[0]
        if method == "GET":
            rec = checklists_svc.get_checklist(service, key, session)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            updated = checklists_svc.update_checklist(service, key, body, username, session)
            return _json_response(updated)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            checklists_svc.delete_checklist(service, key, username, session)
            return _json_response({"deleted": key})
        return _error("method not allowed", status=405)

    def _reviews(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                return _json_response(
                    reviews_svc.list_reviews(
                        service,
                        session,
                        checklist_id=query.get("checklist_id"),
                        status=query.get("status"),
                        stig_collection_id=query.get("stig_collection_id"),
                        rule_id=query.get("rule_id"),
                        rule_version=query.get("rule_version"),
                        valid=query.get("valid"),
                        workflow_state=query.get("workflow_state"),
                    )
                )
            return _error("method not allowed", status=405)

        if parts == ["batch"] and method in ("POST", "PATCH", "PUT"):
            body = _body_json(payload)
            action = (body.get("action") or "").strip().lower()
            has_field_batch = body.get("reviews") is not None or body.get("updates") is not None
            if action in ("submit", "accept", "reject"):
                if has_field_batch:
                    return _error(
                        "batch body cannot combine action with reviews/updates; "
                        "send governance (action + review_ids) or field batch (reviews) only",
                        status=400,
                    )
                review_ids = body.get("review_ids") or body.get("ids") or []
                if not isinstance(review_ids, list):
                    return _error("review_ids must be a list")
                result = reviews_svc.batch_workflow(
                    service,
                    action,
                    [str(r) for r in review_ids],
                    username,
                    session,
                    reject_feedback=body.get("reject_feedback"),
                )
                return _json_response(result)
            result = reviews_svc.batch_update_reviews(
                service, body, username, session
            )
            return _json_response(result)

        key = parts[0]
        if len(parts) == 2 and parts[1] == "history":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    review_history_svc.list_review_history(
                        service, key, session, query
                    )
                )
            except KeyError:
                return _error("not found", status=404)

        if len(parts) == 2 and parts[1] == "peers":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    review_peers_svc.list_review_peers(service, key, session)
                )
            except KeyError:
                return _error("not found", status=404)

        if len(parts) == 3 and parts[1] == "copy_from":
            peer_id = parts[2]
            if method != "POST":
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            try:
                result = review_peers_svc.copy_from_peer(
                    service, key, peer_id, username, session, body
                )
                return _json_response(result)
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)

        if len(parts) == 2 and parts[1] in ("submit", "accept", "reject"):
            action = parts[1]
            if method not in ("POST", "PATCH", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            if action == "submit":
                updated = reviews_svc.submit_review(service, key, username, session)
            elif action == "accept":
                updated = reviews_svc.accept_review(service, key, username, session)
            else:
                updated = reviews_svc.reject_review(
                    service,
                    key,
                    username,
                    session,
                    reject_feedback=body.get("reject_feedback"),
                )
            return _json_response(updated)

        if method == "GET":
            rec = reviews_svc.get_review(service, key, session)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            updated = reviews_svc.update_review(service, key, body, username, session)
            return _json_response(updated)
        return _error("method not allowed", status=405)

    def _imports(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if parts == ["reconcile"]:
            if method not in ("GET", "POST"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            earliest = query.get("earliest") or body.get("earliest") or None
            rec = reconcile_svc.reconcile_from_index(
                service, session, username, earliest=earliest
            )
            return _json_response(rec)
        if parts == ["review_aging_report"]:
            if method not in ("GET", "POST"):
                return _error("method not allowed", status=405)
            rec = review_aging_svc.report_stale_all_workspaces(
                service, session, query
            )
            return _json_response(rec)
        if parts:
            return _error("not found", status=404)
        if method != "POST":
            return _error("method not allowed", status=405)
        collection_id = query.get("stig_collection_id") or ""
        source_uri = query.get("source_uri") or ""
        body = _body_bytes(payload)
        if not body:
            return _error("empty import body")
        fmt = (query.get("format") or detect_format(source_uri, body)).lower()
        if fmt in {
            "zip",
            "xccdf-results-zip",
            "xccdf_results_zip",
            "xccdfresultszip",
        }:
            try:
                cid = collection_id
                if not cid:
                    cid = imports_svc.resolve_import_workspace(
                        service, session, username, ""
                    )
                if fmt == "zip":
                    importer = imports_svc.import_checklist_zip
                else:
                    importer = imports_svc.import_xccdf_results_zip
                rec = importer(
                    service,
                    session,
                    username,
                    cid,
                    body,
                    source_uri=source_uri or "archive.zip",
                )
            except KeyError:
                return _error("not found", status=404)
            except PermissionError as exc:
                return _error(str(exc), status=403)
            except ValueError as exc:
                return _error(str(exc), status=400)
            return _json_response(rec, status=_batch_import_http_status(rec))
        if fmt not in {"ckl", "cklb", "xccdf-results", "xccdf_results", "xccdfresults"}:
            return _error(
                "format must be ckl, cklb, zip, xccdf-results-zip, or xccdf-results"
            )
        rec = imports_svc.import_checklist_file(
            service,
            body,
            fmt,
            username,
            session,
            collection_id,
            source_uri,
            operator_collection_id=collection_id,
        )
        created = rec.get("host", {}).get("created") or any(
            item.get("created") for item in rec.get("checklists") or []
        )
        return _json_response(rec, status=201 if created else 200)

    def _assignment_rules(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                return _json_response(assignment_svc.list_rules(service))
            if method == "POST":
                body = _body_json(payload)
                rec = assignment_svc.create_rule(service, body, username)
                return _json_response(rec, status=201)
            return _error("method not allowed", status=405)
        key = parts[0]
        if method == "GET":
            rec = assignment_svc.get_rule(service, key)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            updated = assignment_svc.update_rule(service, key, body, username)
            return _json_response(updated)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            assignment_svc.delete_rule(service, key, username)
            return _json_response({"deleted": key})
        return _error("method not allowed", status=405)

    def _host_baseline_assignments(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if not parts:
            if method == "GET":
                return _json_response(assignment_svc.list_overrides(service))
            if method == "POST":
                body = _body_json(payload)
                rec = assignment_svc.create_override(service, body, username)
                return _json_response(rec, status=201)
            return _error("method not allowed", status=405)
        key = parts[0]
        if method == "GET":
            rec = assignment_svc.get_override(service, key)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            updated = assignment_svc.update_override(service, key, body, username)
            return _json_response(updated)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            assignment_svc.delete_override(service, key, username)
            return _json_response({"deleted": key})
        return _error("method not allowed", status=405)

    def _assignment_preview(
        self,
        method: str,
        parts: List[str],
        query: Dict[str, Any],
        payload: Dict[str, Any],
        service,
        session: Dict[str, Any],
        username: str,
    ) -> Dict[str, Any]:
        if parts != ["preview"]:
            return _error("not found", status=404)
        if method not in ("GET", "POST"):
            return _error("method not allowed", status=405)
        body = _body_json(payload)
        event = body.get("event") if body else {}
        if not event and query.get("event"):
            try:
                event = json.loads(query.get("event") or "{}")
            except (TypeError, ValueError):
                event = {}
        if not event:
            return _error("event body required")
        from importers.events import normalize_finding_event

        try:
            normalized = normalize_finding_event(event)
        except ValueError as exc:
            return _error(str(exc))
        forced = (body.get("forced_collection_id") or query.get("forced_collection_id") or "").strip()
        if forced:
            result = assignment_svc.resolve_collection_id(
                normalized,
                service,
                session,
                forced_collection_id=forced,
                username=username,
                audit_resolve=False,
            )
        else:
            result = assignment_svc.preview_resolution(
                service, normalized, session, username=username
            )
        return _json_response(result)

    def _settings(
        self,
        method: str,
        parts: List[str],
        payload: Dict[str, Any],
        service,
        username: str,
    ) -> Dict[str, Any]:
        if parts:
            return _error("not found", status=404)
        if method == "GET":
            return _json_response(settings_svc.get_settings(service))
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            return _json_response(settings_svc.save_settings(service, body, username))
        return _error("method not allowed", status=405)
