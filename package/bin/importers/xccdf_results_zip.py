"""Walk zip archives for OpenSCAP / Evaluate-STIG XCCDF TestResult XML files."""

from __future__ import annotations

import io
import zipfile
from typing import Iterator, List, Optional, Tuple, Union

from importers.checklist_zip import (
    MAX_CHECKLIST_FILES,
    MAX_TOTAL_UNCOMPRESSED,
    _open_zip,
    _read_member_bytes,
)
from importers.stig_zip import MAX_DEPTH, looks_like_zip, _norm

# Same cap as checklist archive ingest (shared batch limit).
MAX_RESULT_FILES = MAX_CHECKLIST_FILES

_SKIP_SUBSTR = (
    "/__macosx/",
    "manual-xccdf",
    "_srg_",
    "-srg-",
    "/srg_",
    "srg_v",
    "_scap_",
    "-scap-",
    "/scap/",
    "datastream",
    "-ds.xml",
    "_ds.xml",
)

ZipSource = Union[bytes, bytearray]


def _looks_like_test_result_xml(raw: bytes) -> bool:
    sample = raw[:16384].lstrip()
    if b"TestResult" not in sample:
        return False
    if b"rule-result" not in sample:
        return False
    # DISA Manual STIG benchmark XML (no scan results).
    if b"Manual-xccdf" in sample or b"manual-xccdf" in sample.lower():
        if b"<TestResult" not in sample:
            return False
    return True


def is_xccdf_results_member(name: str, raw: bytes) -> bool:
    path = _norm(name)
    base = path.rsplit("/", 1)[-1]
    if base.startswith(".") or any(part in path for part in _SKIP_SUBSTR):
        return False
    if not base.endswith(".xml"):
        return False
    if base.endswith("-results.xml") or base.endswith("_results.xml"):
        return _looks_like_test_result_xml(raw)
    return _looks_like_test_result_xml(raw)


def iter_xccdf_results_files(
    data: bytes,
    *,
    source_prefix: str = "",
    depth: int = 0,
    _count: Optional[List[int]] = None,
    _total_uncompressed: Optional[List[int]] = None,
) -> Iterator[Tuple[str, bytes]]:
    if not looks_like_zip(data):
        raise ValueError("invalid zip archive")
    if _count is None:
        _count = [0]
    if _total_uncompressed is None:
        _total_uncompressed = [0]
    prefix = (source_prefix or "").strip()
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    try:
        archive = _open_zip(data)
    except (zipfile.BadZipFile, OSError) as err:
        raise ValueError(f"invalid zip: {err}") from err
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member = info.filename
            norm = _norm(member)
            raw = _read_member_bytes(archive, info, total_budget=_total_uncompressed)
            nested = norm.endswith(".zip") and depth < MAX_DEPTH
            if nested and looks_like_zip(raw):
                nested_prefix = prefix + member
                yield from iter_xccdf_results_files(
                    raw,
                    source_prefix=nested_prefix,
                    depth=depth + 1,
                    _count=_count,
                    _total_uncompressed=_total_uncompressed,
                )
                continue
            if not is_xccdf_results_member(member, raw):
                continue
            _count[0] += 1
            if _count[0] > MAX_RESULT_FILES:
                raise ValueError(
                    f"zip contains more than {MAX_RESULT_FILES} XCCDF results files"
                )
            path = prefix + member
            yield path, raw


def list_xccdf_results_files(
    data: bytes, *, source_prefix: str = ""
) -> List[Tuple[str, bytes]]:
    return list(iter_xccdf_results_files(data, source_prefix=source_prefix))
