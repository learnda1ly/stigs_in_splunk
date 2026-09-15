"""UCC Configuration tab handler: baseline catalog in stig_baselines KV."""

from __future__ import annotations

from splunktaucclib.rest_handler.admin_external import AdminExternalHandler, build_conf_info

import access
from services import baselines as baselines_svc
from stig_ucc_kv import (
    as_conf_entities,
    connect,
    decode_uploaded_file,
    handler_session,
    handler_username,
)


def _fail(message: str) -> None:
    raise Exception(message)


def _baseline_fields(rec) -> dict:
    return {
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


def _baseline_rows(service):
    rows = []
    for rec in baselines_svc.list_baselines(service):
        name = baselines_svc.ucc_name_for(rec)
        if not name:
            continue
        rows.append((name, _baseline_fields(rec)))
    return rows


class BaselineRestHandler(AdminExternalHandler):
    @build_conf_info
    def handleList(self, confInfo):
        rows = _baseline_rows(connect(self))
        want = (self.callerArgs.id or "").strip()
        if want:
            rows = [row for row in rows if row[0] == want]
        return as_conf_entities(self, rows)

    @build_conf_info
    def handleCreate(self, confInfo):
        service = connect(self)
        name = (self.callerArgs.id or "").strip()
        if not name:
            _fail("id is required")
        if baselines_svc.find_baseline_by_ucc_name(service, name):
            _fail("baseline id already exists")
        payload = self.payload or {}
        fmt = (payload.get("format") or "xccdf").strip().lower()
        body = decode_uploaded_file(payload.get("content"))
        if not body:
            _fail("upload an XCCDF, CKL, or CKLB file")
        rec, _created = baselines_svc.import_baseline(
            service,
            body,
            fmt,
            handler_username(self),
            source_uri=name,
            ucc_name=name,
        )
        shown = rec.get("ucc_name") or name
        return as_conf_entities(self, [(shown, _baseline_fields(rec))])

    def handleEdit(self, confInfo):
        _fail("baselines are immutable; delete and import again to replace a revision")

    def handleRemove(self, confInfo):
        service = connect(self)
        session = handler_session(self)
        if not access.user_has_stig_admin(session):
            _fail("stig_admin required to delete a baseline")
        name = (self.callerArgs.id or "").strip()
        rec = baselines_svc.find_baseline_by_ucc_name(service, name)
        if not rec:
            _fail("baseline not found")
        baselines_svc.delete_baseline(service, rec["_key"], handler_username(self))
