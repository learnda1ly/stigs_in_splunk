"""Classify and list XCCDF TestResult XML inside zip archives."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterator, List, Optional, Tuple

from importers.checklist_zip import MAX_CHECKLIST_FILES
from importers.stig_zip import _norm
from models import strip_ns

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


def _looks_like_test_result_xml(raw: bytes) -> bool:
    sample = raw[:16384].lstrip()
    if b"TestResult" not in sample or b"rule-result" not in sample:
        return False
    if b"Manual-xccdf" in sample or b"manual-xccdf" in sample.lower():
        if b"<TestResult" not in sample:
            return False
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return False
    has_test_result = False
    has_rule_result = False
    for el in root.iter():
        tag = strip_ns(el.tag)
        if tag == "TestResult":
            has_test_result = True
        if tag == "rule-result":
            has_rule_result = True
        if has_test_result and has_rule_result:
            return True
    return has_test_result and has_rule_result


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
    from importers.import_archive_zip import iter_archive_import_members

    yield from (
        (m.path, m.content)
        for m in iter_archive_import_members(
            data,
            source_prefix=source_prefix,
            include_checklists=False,
            include_xccdf_results=True,
            depth=depth,
            _import_count=_count,
            _total_uncompressed=_total_uncompressed,
        )
    )


def list_xccdf_results_files(
    data: bytes, *, source_prefix: str = ""
) -> List[Tuple[str, bytes]]:
    return list(iter_xccdf_results_files(data, source_prefix=source_prefix))
