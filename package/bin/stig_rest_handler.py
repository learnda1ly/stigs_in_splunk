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
import kv_client
from importers.ingest import detect_format
from services import baselines as baselines_svc
from services import baseline_jobs as baseline_jobs_svc
from services import checklists as checklists_svc
from services import baseline_defaults as baseline_defaults_svc
from services import collections as collections_svc
from services import hosts as hosts_svc
from services import assignment as assignment_svc
from services import imports as imports_svc
from services import reconcile as reconcile_svc
from services import reporting as reporting_svc
from services import reviews as reviews_svc
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


class StigRestHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line: str, command_arg: str):
        PersistentServerConnectionApplication.__init__(self)

    def handle(self, in_string: str) -> Dict[str, Any]:
        try:
            payload = json.loads(in_string)
            return self._dispatch(payload)
        except Exception as exc:
            logger.error("rest_error %s", traceback.format_exc())
            return _error(str(exc), status=500)

    def _dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        method = (payload.get("method") or "GET").upper()
        session = payload.get("session") or {}
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

        service = kv_client.connect(authtoken)

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

        if len(parts) == 2 and parts[1] == "metrics":
            if method != "GET":
                return _error("method not allowed", status=405)
            try:
                return _json_response(
                    reporting_svc.collection_metrics(service, key, session)
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

        if method == "GET":
            rec = collections_svc.get_collection(service, key)
            if not rec or not access.user_can_read_collection(rec, session):
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            rec = collections_svc.get_collection(service, key)
            if not rec or not access.user_can_write_collection(rec, session):
                return _error("not found", status=404)
            body = _body_json(payload)
            updated = collections_svc.update_collection(service, key, body, username)
            return _json_response(updated)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            collections_svc.delete_collection(service, key, username)
            return _json_response({"deleted": key})
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
                return _json_response(hosts_svc.list_hosts(service, session, cid))
            if method == "POST":
                body = _body_json(payload)
                rec = hosts_svc.create_host(service, body, username, session)
                return _json_response(rec, status=201)
            return _error("method not allowed", status=405)

        key = parts[0]
        if method == "GET":
            rec = hosts_svc.get_host(service, key, session)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method in ("PATCH", "POST", "PUT"):
            body = _body_json(payload)
            updated = hosts_svc.update_host(service, key, body, username, session)
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
            for rec in baselines_svc.list_baselines(service):
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
        if parts == ["import"]:
            if method != "POST":
                return _error("method not allowed", status=405)
            fmt = query.get("format") or "xccdf"
            source_uri = query.get("source_uri") or ""
            body = _body_bytes(payload)
            if not body:
                return _error("empty import body")
            results = baselines_svc.import_baselines_payload(
                service, body, fmt, username, source_uri
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

        if len(parts) == 2 and parts[1] == "rules":
            baseline_id = parts[0]
            if method != "GET":
                return _error("method not allowed", status=405)
            if not baselines_svc.get_baseline(service, baseline_id):
                return _error("not found", status=404)
            rules = baselines_svc.list_baseline_rules(service, baseline_id)
            return _json_response(rules)

        if not parts:
            if method == "GET":
                return _json_response(baselines_svc.list_baselines(service))
            return _error("method not allowed", status=405)

        key = parts[0]
        if method == "GET":
            rec = baselines_svc.get_baseline(service, key)
            if not rec:
                return _error("not found", status=404)
            return _json_response(rec)
        if method == "DELETE":
            if not access.user_has_stig_admin(session):
                return _error("stig_admin required", status=403)
            baselines_svc.delete_baseline(service, key, username)
            return _json_response({"deleted": key})
        return _error("not found", status=404)

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
            return _json_response(
                checklists_svc.export_checklists_bulk(service, ids, fmt, session)
            )

        if parts and parts[0] == "summary":
            if method != "GET":
                return _error("method not allowed", status=405)
            return _json_response(
                checklists_svc.summarize_checklists(
                    service, session, query.get("stig_collection_id")
                )
            )

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
            ctype = (
                "application/json" if fmt.lower() == "cklb" else "application/xml"
            )
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
        if parts == ["batch"]:
            if method not in ("POST", "PATCH", "PUT"):
                return _error("method not allowed", status=405)
            body = _body_json(payload)
            result = reviews_svc.batch_update_reviews(
                service, body, username, session
            )
            return _json_response(result)

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
                    )
                )
            return _error("method not allowed", status=405)

        key = parts[0]
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
        if fmt not in {"ckl", "cklb", "xccdf-results", "xccdf_results", "xccdfresults"}:
            return _error("format must be ckl, cklb, or xccdf-results")
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
