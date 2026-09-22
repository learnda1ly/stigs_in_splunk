"""Walk zip archives for STIG Viewer checklist files (.ckl / .cklb)."""

from __future__ import annotations

import io
import zipfile
from typing import Iterator, List, Optional, Tuple, Union

from importers.archive_limits import MAX_ARCHIVE_IMPORT_FILES, MAX_TOTAL_UNCOMPRESSED
from importers.stig_zip import MAX_MEMBER_BYTES, _norm

MAX_CHECKLIST_FILES = MAX_ARCHIVE_IMPORT_FILES

ZipSource = Union[bytes, bytearray]


def is_checklist_member(name: str) -> bool:
    path = _norm(name)
    base = path.rsplit("/", 1)[-1]
    if base.startswith(".") or "/__macosx/" in path:
        return False
    return base.endswith(".ckl") or base.endswith(".cklb")


def checklist_format(name: str) -> str:
    lower = _norm(name)
    if lower.endswith(".cklb"):
        return "cklb"
    if lower.endswith(".ckl"):
        return "ckl"
    return ""


def _open_zip(source: ZipSource) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(source))


def _read_member_bytes(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    total_budget: List[int],
) -> bytes:
    member = info.filename
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"zip member too large: {member}")
    chunks: List[bytes] = []
    read_total = 0
    try:
        with archive.open(info, "r") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                read_total += len(chunk)
                total_budget[0] += len(chunk)
                if read_total > MAX_MEMBER_BYTES:
                    raise ValueError(
                        f"zip member exceeds max uncompressed size: {member}"
                    )
                if total_budget[0] > MAX_TOTAL_UNCOMPRESSED:
                    raise ValueError("zip exceeds total uncompressed size limit")
                chunks.append(chunk)
    except (KeyError, RuntimeError, zipfile.BadZipFile, OSError) as err:
        raise ValueError(f"failed to read zip member {member}: {err}") from err
    return b"".join(chunks)


def iter_checklist_files(
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
            include_checklists=True,
            include_xccdf_results=False,
            depth=depth,
            _import_count=_count,
            _total_uncompressed=_total_uncompressed,
        )
    )


def list_checklist_files(data: bytes, *, source_prefix: str = "") -> List[Tuple[str, bytes]]:
    return list(iter_checklist_files(data, source_prefix=source_prefix))
