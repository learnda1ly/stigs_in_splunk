"""Validation for ingest settings and reconcile SPL literals (SSRF / injection hardening)."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from models import DEFAULT_HEC_URL

_ALLOWED_HEC_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_HEC_PATH_PREFIX = "/services/collector/"
_INDEX_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SOURCETYPE_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_EARLIEST_RE = re.compile(r"^[A-Za-z0-9._:@/+\-]+$")
_MAX_EARLIEST_LEN = 128


def _is_loopback_host(hostname: str) -> bool:
    return (hostname or "").lower() in _ALLOWED_HEC_HOSTS


def validate_hec_url_admin(url: str) -> str:
    """Validate HEC URL saved by Splunk admin (any host; HTTPS off loopback)."""
    text = (url or "").strip()
    if not text:
        raise ValueError("hec_url is required")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("hec_url must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("hec_url must not include credentials")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("hec_url must include a host")
    if not _is_loopback_host(host) and parsed.scheme != "https":
        raise ValueError("hec_url must use https for non-loopback hosts")
    path = parsed.path or ""
    if not path.startswith(_HEC_PATH_PREFIX):
        raise ValueError("hec_url path must start with /services/collector/")
    if parsed.query or parsed.fragment:
        raise ValueError("hec_url must not include query or fragment")
    return text


def hec_url_for_emit(url: Optional[str]) -> str:
    """Return stored admin-configured collector URL, or default when missing/invalid."""
    text = (url or "").strip()
    if not text:
        return DEFAULT_HEC_URL
    try:
        return validate_hec_url_admin(text)
    except ValueError:
        return DEFAULT_HEC_URL


def validate_ingest_index(index: str) -> str:
    name = (index or "").strip()
    if not name or not _INDEX_RE.match(name):
        raise ValueError("ingest_index must be a simple index name (letters, digits, ._-)")
    return name


def validate_ingest_sourcetype(sourcetype: str) -> str:
    st = (sourcetype or "").strip()
    if not st or not _SOURCETYPE_RE.match(st):
        raise ValueError(
            "ingest_sourcetype must be a simple sourcetype name (letters, digits, ._:-)"
        )
    return st


def validate_reconcile_earliest(earliest: str) -> str:
    text = (earliest or "").strip()
    if not text:
        raise ValueError("reconcile_earliest is required")
    if len(text) > _MAX_EARLIEST_LEN:
        raise ValueError("reconcile_earliest is too long")
    if not _EARLIEST_RE.match(text):
        raise ValueError("reconcile_earliest contains invalid characters")
    if "|" in text or ";" in text:
        raise ValueError("reconcile_earliest must not contain SPL command separators")
    return text


def validate_ingest_settings_record(record: dict) -> None:
    """Raise ValueError when ingest-related settings are unsafe."""
    if "hec_url" in record or record.get("hec_url"):
        validate_hec_url_admin(record.get("hec_url") or DEFAULT_HEC_URL)
    if "ingest_index" in record or record.get("ingest_index"):
        validate_ingest_index(record.get("ingest_index") or "")
    if "ingest_sourcetype" in record or record.get("ingest_sourcetype"):
        validate_ingest_sourcetype(record.get("ingest_sourcetype") or "")
    if "reconcile_earliest" in record or record.get("reconcile_earliest"):
        validate_reconcile_earliest(record.get("reconcile_earliest") or "")
