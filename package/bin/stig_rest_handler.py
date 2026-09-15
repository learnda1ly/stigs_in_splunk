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
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import hosts as hosts_svc
from services import imports as imports_svc
from services import reconcile as reconcile_svc
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
    return str(raw).encode("utf-8")


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
            rec, created = baselines_svc.import_baseline(
                service, body, fmt, username, source_uri
            )
            payload = dict(rec)
            if not created:
                payload["deduplicated"] = True
            return _json_response(payload, status=201 if created else 200)

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

        return _error("not found", status=404)

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
        if not collection_id:
            return _error("stig_collection_id is required")
        source_uri = query.get("source_uri") or ""
        body = _body_bytes(payload)
        if not body:
            return _error("empty import body")
        fmt = (query.get("format") or detect_format(source_uri, body)).lower()
        if fmt not in {"ckl", "cklb"}:
            return _error("format must be ckl or cklb")
        rec = imports_svc.import_checklist_file(
            service,
            body,
            fmt,
            username,
            session,
            collection_id,
            source_uri,
        )
        created = rec.get("host", {}).get("created") or any(
            item.get("created") for item in rec.get("checklists") or []
        )
        return _json_response(rec, status=201 if created else 200)

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
