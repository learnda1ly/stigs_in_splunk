"""Walk zip archives for STIG Viewer checklist files (.ckl / .cklb)."""

from __future__ import annotations

import io
import zipfile
from typing import Iterator, List, Optional, Tuple, Union

from importers.stig_zip import MAX_DEPTH, MAX_MEMBER_BYTES, looks_like_zip, _norm

MAX_CHECKLIST_FILES = 500

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


def iter_checklist_files(
    data: bytes,
    *,
    source_prefix: str = "",
    depth: int = 0,
    _count: Optional[List[int]] = None,
) -> Iterator[Tuple[str, bytes]]:
    if not looks_like_zip(data):
        raise ValueError("invalid zip archive")
    if _count is None:
        _count = [0]
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
            try:
                if info.file_size > MAX_MEMBER_BYTES:
                    raise ValueError(f"zip member too large: {member}")
                raw = archive.read(info)
            except (KeyError, RuntimeError, zipfile.BadZipFile) as err:
                raise ValueError(f"failed to read zip member {member}: {err}") from err
            nested = norm.endswith(".zip") and depth < MAX_DEPTH
            if nested and looks_like_zip(raw):
                nested_prefix = prefix + member
                yield from iter_checklist_files(
                    raw,
                    source_prefix=nested_prefix,
                    depth=depth + 1,
                    _count=_count,
                )
                continue
            if not is_checklist_member(member):
                continue
            _count[0] += 1
            if _count[0] > MAX_CHECKLIST_FILES:
                raise ValueError(
                    f"zip contains more than {MAX_CHECKLIST_FILES} checklist files"
                )
            path = prefix + member
            yield path, raw


def list_checklist_files(data: bytes, *, source_prefix: str = "") -> List[Tuple[str, bytes]]:
    return list(iter_checklist_files(data, source_prefix=source_prefix))
