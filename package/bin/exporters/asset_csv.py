"""STIG Manager–compatible asset CSV columns (user guide §2.9.2.2–2.9.2.3)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

ASSET_CSV_COLUMNS: List[str] = [
    "Name",
    "Description",
    "IP",
    "FQDN",
    "MAC",
    "Non-Computing",
    "STIGs",
    "Labels",
    "Metadata",
]

_HEADER_MAP = {name.casefold(): name for name in ASSET_CSV_COLUMNS}


def normalize_header_row(fieldnames: Optional[Sequence[str]]) -> Dict[str, str]:
    """Map lower-case header tokens to canonical column names."""
    out: Dict[str, str] = {}
    for raw in fieldnames or []:
        key = (raw or "").strip().casefold()
        canon = _HEADER_MAP.get(key)
        if canon:
            out[raw] = canon
    return out


def _truncate(value: str, limit: int = 255) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return text[:limit]


def parse_bool_non_computing(value: str) -> bool:
    text = (value or "").strip().casefold()
    if not text:
        return False
    if text in ("true", "1", "yes", "y"):
        return True
    if text in ("false", "0", "no", "n"):
        return False
    raise ValueError("Non-Computing must be TRUE or FALSE")


def parse_metadata_cell(value: str) -> Dict[str, str]:
    raw = (value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Metadata must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Metadata must be a JSON object")
    out: Dict[str, str] = {}
    for key, val in parsed.items():
        key_str = str(key).strip()
        if not key_str:
            raise ValueError("Metadata keys must be non-empty strings")
        if not isinstance(val, str):
            raise ValueError(f"Metadata value for {key_str!r} must be a string")
        out[key_str] = val
    return out


def split_multiline_cell(value: str) -> List[str]:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [line.strip() for line in text.split("\n")]
    return [p for p in parts if p]


def parse_asset_csv(text: str) -> List[Dict[str, Any]]:
    """Parse CSV text into row dicts keyed by canonical column names."""
    if not (text or "").strip():
        return []
    reader = csv.DictReader(io.StringIO(text), dialect=csv.excel)
    header_map = normalize_header_row(reader.fieldnames)
    if "Name" not in header_map.values():
        raise ValueError("CSV must include a Name column")
    rows: List[Dict[str, Any]] = []
    for idx, raw in enumerate(reader, start=2):
        row: Dict[str, Any] = {"_row": idx}
        for src_key, canon in header_map.items():
            row[canon] = raw.get(src_key, "")
        rows.append(row)
    return rows


def asset_row_to_csv_dict(row: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "Name": str(row.get("Name") or ""),
        "Description": str(row.get("Description") or ""),
        "IP": str(row.get("IP") or ""),
        "FQDN": str(row.get("FQDN") or ""),
        "MAC": str(row.get("MAC") or ""),
        "Non-Computing": str(row.get("Non-Computing") or "FALSE"),
        "STIGs": str(row.get("STIGs") or ""),
        "Labels": str(row.get("Labels") or ""),
        "Metadata": str(row.get("Metadata") or ""),
    }


def assets_to_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=ASSET_CSV_COLUMNS,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(asset_row_to_csv_dict(row))
    return buf.getvalue()


def safe_asset_csv_filename(collection_id: str) -> str:
    slug = (collection_id or "workspace").strip() or "workspace"
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug)
    return f"stig_assets_{slug}.csv"
