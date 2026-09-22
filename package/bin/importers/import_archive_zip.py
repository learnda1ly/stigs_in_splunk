"""Single-pass zip traversal for checklist and XCCDF results archive import."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

from importers.archive_limits import MAX_ARCHIVE_IMPORT_FILES, MAX_TOTAL_UNCOMPRESSED
from importers.checklist_zip import (
    _open_zip,
    _read_member_bytes,
    checklist_format,
    is_checklist_member,
)
from importers.stig_zip import MAX_DEPTH, looks_like_zip, _norm
from importers.xccdf_results_zip import is_xccdf_results_member

@dataclass(frozen=True)
class ArchiveImportMember:
    path: str
    format: str
    content: bytes


def iter_archive_import_members(
    data: bytes,
    *,
    source_prefix: str = "",
    include_checklists: bool = True,
    include_xccdf_results: bool = True,
    depth: int = 0,
    _import_count: Optional[List[int]] = None,
    _total_uncompressed: Optional[List[int]] = None,
) -> Iterator[ArchiveImportMember]:
    if not include_checklists and not include_xccdf_results:
        raise ValueError("at least one member kind must be enabled")
    if not looks_like_zip(data):
        raise ValueError("invalid zip archive")
    if _import_count is None:
        _import_count = [0]
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
                yield from iter_archive_import_members(
                    raw,
                    source_prefix=nested_prefix,
                    include_checklists=include_checklists,
                    include_xccdf_results=include_xccdf_results,
                    depth=depth + 1,
                    _import_count=_import_count,
                    _total_uncompressed=_total_uncompressed,
                )
                continue
            fmt = ""
            if include_checklists and is_checklist_member(member):
                fmt = checklist_format(member)
            elif include_xccdf_results and is_xccdf_results_member(member, raw):
                fmt = "xccdf-results"
            if not fmt:
                continue
            _import_count[0] += 1
            if _import_count[0] > MAX_ARCHIVE_IMPORT_FILES:
                raise ValueError(
                    f"zip contains more than {MAX_ARCHIVE_IMPORT_FILES} importable files"
                )
            path = prefix + member
            yield ArchiveImportMember(path=path, format=fmt, content=raw)


def list_archive_import_members(
    data: bytes,
    *,
    source_prefix: str = "",
    include_checklists: bool = True,
    include_xccdf_results: bool = True,
) -> List[ArchiveImportMember]:
    return list(
        iter_archive_import_members(
            data,
            source_prefix=source_prefix,
            include_checklists=include_checklists,
            include_xccdf_results=include_xccdf_results,
        )
    )


def list_checklist_and_results_files(
    data: bytes, *, source_prefix: str = ""
) -> Tuple[List[Tuple[str, bytes]], List[Tuple[str, bytes]]]:
    """Return (checklist_members, results_members) from one traversal."""
    checklists: List[Tuple[str, bytes]] = []
    results: List[Tuple[str, bytes]] = []
    for item in iter_archive_import_members(
        data,
        source_prefix=source_prefix,
        include_checklists=True,
        include_xccdf_results=True,
    ):
        if item.format in {"ckl", "cklb"}:
            checklists.append((item.path, item.content))
        else:
            results.append((item.path, item.content))
    return checklists, results
