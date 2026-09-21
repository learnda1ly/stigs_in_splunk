"""UCC Configuration tab handler: workspaces in stig_collections KV."""

from __future__ import annotations

from splunktaucclib.rest_handler.admin_external import AdminExternalHandler, build_conf_info

import access
from models import as_bool
from services import collections as collections_svc
from services import grants as grants_svc
from stig_ucc_kv import (
    as_conf_entities,
    connect,
    handler_session,
    handler_username,
    parse_principals,
    principals_to_text,
)


def _fail(message: str) -> None:
    raise Exception(message)


def _workspace_fields(rec) -> dict:
    return {
        "description": rec.get("description") or "",
        "access_principals": principals_to_text(rec.get("access_principals")),
        "is_default": bool(as_bool(rec.get("is_default"))),
    }


def _workspace_rows(service):
    collections_svc.ensure_default_collection(service, "system")
    rows = []
    for rec in collections_svc.list_all_collections(service):
        name = (rec.get("name") or rec.get("_key") or "").strip()
        if not name:
            continue
        rows.append((name, _workspace_fields(rec)))
    return rows


class WorkspaceRestHandler(AdminExternalHandler):
    @build_conf_info
    def handleList(self, confInfo):
        # Configuration lists every workspace. Persist /stig_collections still
        # filters by access_principals for the editor.
        rows = _workspace_rows(connect(self))
        want = (self.callerArgs.id or "").strip()
        if want:
            rows = [row for row in rows if row[0] == want]
        return as_conf_entities(self, rows)

    @build_conf_info
    def handleCreate(self, confInfo):
        service = connect(self)
        name = (self.callerArgs.id or "").strip()
        if not name:
            _fail("name is required")
        if collections_svc.find_collection_by_name(service, name):
            _fail("workspace name already exists")
        payload = self.payload or {}
        body = {
            "name": name,
            "description": payload.get("description") or "",
        }
        principals = parse_principals(payload.get("access_principals"))
        if principals is not None:
            body["access_principals"] = principals
        if "is_default" in payload:
            body["is_default"] = as_bool(payload.get("is_default"))
        stored = collections_svc.create_collection(service, body, handler_username(self))
        return as_conf_entities(
            self, [(stored.get("name") or name, _workspace_fields(stored))]
        )

    @build_conf_info
    def handleEdit(self, confInfo):
        service = connect(self)
        name = (self.callerArgs.id or "").strip()
        rec = collections_svc.find_collection_by_name(service, name)
        if not rec:
            _fail("workspace not found")
        session = handler_session(self)
        grants = grants_svc.query_grants(service, rec["_key"])
        ctx = access.resolve_workspace_access(rec, session, grants)
        if not ctx.edit_collection and not access.user_can_write_collection(rec, session, grants):
            _fail("not allowed to update this workspace")
        payload = self.payload or {}
        patch = {}
        if "description" in payload:
            patch["description"] = payload.get("description") or ""
        if "access_principals" in payload:
            principals = parse_principals(payload.get("access_principals"))
            patch["access_principals"] = principals if principals is not None else []
        if "is_default" in payload:
            patch["is_default"] = as_bool(payload.get("is_default"))
        stored = rec
        if patch:
            stored = collections_svc.update_collection(
                service, rec["_key"], patch, handler_username(self)
            )
        return as_conf_entities(
            self, [(stored.get("name") or name, _workspace_fields(stored))]
        )

    def handleRemove(self, confInfo):
        service = connect(self)
        name = (self.callerArgs.id or "").strip()
        rec = collections_svc.find_collection_by_name(service, name)
        if not rec:
            _fail("workspace not found")
        session = handler_session(self)
        if not access.user_has_stig_admin(session):
            _fail("stig_admin required to delete a workspace")
        collections_svc.delete_collection(service, rec["_key"], handler_username(self))
