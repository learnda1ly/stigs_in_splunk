"""POA&M-style export rows (eMASS template reference; not a certified eMASS export)."""

from __future__ import annotations

import base64
import csv
import io
import re
import zipfile
from typing import Any, Dict, Iterable, List, Sequence
from xml.sax.saxutils import escape

# Column keys (stable for JSON/REST) and human labels (CSV/XLSX header row).
POAM_COLUMNS: List[Dict[str, str]] = [
    {"key": "poam_id", "label": "POAM ID"},
    {"key": "weakness_id", "label": "Weakness ID"},
    {"key": "control_vulnerability_description", "label": "Control Vulnerability Description"},
    {"key": "security_checks", "label": "Security Checks"},
    {"key": "severity", "label": "Severity"},
    {"key": "cci", "label": "CCI"},
    {"key": "resources_affected", "label": "Resources Affected"},
    {"key": "stig_id", "label": "STIG ID"},
    {"key": "rule_id", "label": "Rule ID"},
    {"key": "status", "label": "Status"},
    {"key": "finding_details", "label": "Raw Finding Details"},
    {"key": "comments", "label": "Comments"},
    {"key": "office_org", "label": "Office/Org"},
    {"key": "resources_required", "label": "Resources Required"},
    {"key": "scheduled_completion_date", "label": "Scheduled Completion Date"},
    {"key": "milestone_changes", "label": "Milestone Changes"},
    {
        "key": "source_identifying_vulnerability",
        "label": "Source Identifying Vulnerability",
    },
    {"key": "updated_at", "label": "Last Updated (epoch)"},
    {"key": "updated_by", "label": "Updated By"},
    {"key": "checklist_id", "label": "Checklist ID"},
    {"key": "host_id", "label": "Host ID"},
    {"key": "baseline_id", "label": "Baseline ID"},
    {"key": "review_key", "label": "Review Key"},
]

POAM_COLUMN_KEYS = [col["key"] for col in POAM_COLUMNS]
POAM_COLUMN_LABELS = [col["label"] for col in POAM_COLUMNS]


def _cci_text(ccis: Any) -> str:
    if not ccis:
        return ""
    if isinstance(ccis, str):
        return ccis.strip()
    if isinstance(ccis, (list, tuple)):
        return "; ".join(str(c).strip() for c in ccis if str(c).strip())
    return str(ccis)


def finding_to_poam_row(
    finding: Dict[str, Any],
    rule_meta: Dict[str, Any],
    *,
    poam_id: str = "",
) -> Dict[str, Any]:
    """Map one governance-open finding row to a POA&M template line."""
    group_id = finding.get("group_id") or ""
    rule_version = finding.get("rule_version") or ""
    rule_title = rule_meta.get("rule_title") or finding.get("rule_title") or ""
    ccis = rule_meta.get("ccis") or finding.get("ccis") or []
    stig_id = finding.get("stig_id") or ""
    baseline_title = finding.get("baseline_title") or ""
    security_checks = rule_version or finding.get("rule_id") or group_id
    source = stig_id
    if baseline_title:
        source = f"{stig_id} — {baseline_title}" if stig_id else baseline_title

    return {
        "poam_id": poam_id,
        "weakness_id": group_id,
        "control_vulnerability_description": rule_title,
        "security_checks": security_checks,
        "severity": (finding.get("severity") or "unknown").lower(),
        "cci": _cci_text(ccis),
        "resources_affected": finding.get("hostname") or "",
        "stig_id": stig_id,
        "rule_id": finding.get("rule_id") or "",
        "status": finding.get("status") or "open",
        "finding_details": finding.get("finding_details") or "",
        "comments": finding.get("comments") or "",
        "office_org": "",
        "resources_required": "",
        "scheduled_completion_date": "",
        "milestone_changes": "",
        "source_identifying_vulnerability": source,
        "updated_at": finding.get("updated_at"),
        "updated_by": finding.get("updated_by") or "",
        "checklist_id": finding.get("checklist_id") or "",
        "host_id": finding.get("host_id") or "",
        "baseline_id": finding.get("baseline_id") or "",
        "review_key": finding.get("_key") or "",
    }


def findings_to_poam_rows(
    findings: Sequence[Dict[str, Any]],
    rule_index: Dict[tuple, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, finding in enumerate(findings, start=1):
        baseline_id = str(finding.get("baseline_id") or "")
        rule_id = str(finding.get("rule_id") or "")
        group_id = str(finding.get("group_id") or "")
        meta = {}
        for key in (
            (baseline_id, rule_id, group_id),
            (baseline_id, rule_id, ""),
            (baseline_id, "", group_id),
        ):
            if key in rule_index:
                meta = rule_index[key]
                break
        rows.append(
            finding_to_poam_row(finding, meta, poam_id=str(idx))
        )
    return rows


def poam_to_csv(rows: Iterable[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(POAM_COLUMN_LABELS)
    for row in rows:
        writer.writerow([row.get(key, "") for key in POAM_COLUMN_KEYS])
    return buf.getvalue()


def _col_name(index: int) -> str:
    """1-based column index to Excel column letters."""
    name = ""
    n = index
    while n:
        n, rem = divmod(n - 1, 26)
        name = chr(65 + rem) + name
    return name


def _sheet_xml(headers: Sequence[str], data_rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    all_rows = [headers] + [list(r) for r in data_rows]
    for r_idx, row in enumerate(all_rows, start=1):
        lines.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row, start=1):
            ref = f"{_col_name(c_idx)}{r_idx}"
            text = "" if value is None else str(value)
            lines.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
            )
        lines.append("</row>")
    lines.extend(["</sheetData>", "</worksheet>"])
    return "".join(lines)


def poam_to_xlsx_bytes(rows: Iterable[Dict[str, Any]]) -> bytes:
    """Minimal Office Open XML workbook (one sheet) without external dependencies."""
    data = [[row.get(key, "") for key in POAM_COLUMN_KEYS] for row in rows]
    sheet = _sheet_xml(POAM_COLUMN_LABELS, data)
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="POAM" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def poam_xlsx_payload(rows: Iterable[Dict[str, Any]], filename: str) -> Dict[str, Any]:
    raw = poam_to_xlsx_bytes(rows)
    return {
        "filename": filename,
        "format": "xlsx",
        "content_base64": base64.b64encode(raw).decode("ascii"),
    }


def safe_poam_filename(collection_id: str, ext: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (collection_id or "workspace")[:24])
    return f"stig_poam_{slug}.{ext}"
