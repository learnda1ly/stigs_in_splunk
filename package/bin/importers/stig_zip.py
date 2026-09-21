"""Walk DISA STIG product zips and library zip-of-zips for Manual XCCDF baselines."""

from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

ZIP_MAGIC = b"PK"
MAX_DEPTH = 4
MAX_MEMBER_BYTES = 150 * 1024 * 1024
MAX_BASELINES = 800

ZipSource = Union[bytes, bytearray, str]

_SKIP_SUBSTR = (
    "/__macosx/",
    "_srg_",
    "-srg-",
    "/srg_",
    "srg_v",
    "_scap_",
    "-scap-",
    "/scap/",
    "_ocil",
    "-ocil",
)


def looks_like_zip(data: bytes) -> bool:
    return bool(data) and data[:2] == ZIP_MAGIC


def _norm(name: str) -> str:
    return (name or "").replace("\\", "/").lower()


def is_baseline_xccdf_name(name: str) -> bool:
    """True for DISA Manual XCCDF STIG benchmarks, not SRGs/SCAP/checklists."""
    path = _norm(name)
    base = path.rsplit("/", 1)[-1]
    if not base.endswith(".xml") or base.startswith("."):
        return False
    if "manual-xccdf" not in base:
        return False
    if any(part in path for part in _SKIP_SUBSTR):
        return False
    return True


def skip_reason(name: str) -> str:
    path = _norm(name)
    if is_baseline_xccdf_name(name):
        return ""
    if "manual-xccdf" in path and any(
        part in path for part in ("_srg_", "-srg-", "/srg_", "srg_v")
    ):
        return "srg"
    if "scap" in path or "ocil" in path:
        return "scap"
    return "other"


def _open_zip(source: ZipSource) -> zipfile.ZipFile:
    if isinstance(source, (bytes, bytearray)):
        return zipfile.ZipFile(io.BytesIO(source))
    return zipfile.ZipFile(source)


def iter_baseline_xccdfs(
    data: bytes,
    *,
    source_prefix: str = "",
    depth: int = 0,
    _count: Optional[list] = None,
) -> Iterator[Tuple[str, bytes]]:
    yield from iter_baseline_xccdfs_from(
        data, source_prefix=source_prefix, depth=depth, _count=_count
    )


def iter_baseline_xccdfs_from(
    source: ZipSource,
    *,
    source_prefix: str = "",
    depth: int = 0,
    _count: Optional[list] = None,
) -> Iterator[Tuple[str, bytes]]:
    if depth > MAX_DEPTH:
        return
    count = _count if _count is not None else [0]
    try:
        archive = _open_zip(source)
    except (zipfile.BadZipFile, OSError) as err:
        raise ValueError(f"invalid zip: {err}") from err
    with archive:
        for info in archive.infolist():
            if info.is_dir() or info.file_size <= 0:
                continue
            member = (source_prefix + info.filename).replace("\\", "/")
            if info.file_size > MAX_MEMBER_BYTES:
                continue
            try:
                raw = archive.read(info)
            except Exception:
                continue
            if looks_like_zip(raw) and depth < MAX_DEPTH:
                yield from iter_baseline_xccdfs_from(
                    raw,
                    source_prefix=member.rstrip("/") + "/",
                    depth=depth + 1,
                    _count=count,
                )
                continue
            if is_baseline_xccdf_name(member):
                count[0] += 1
                if count[0] > MAX_BASELINES:
                    raise ValueError(
                        f"zip contains more than {MAX_BASELINES} Manual-xccdf baselines"
                    )
                yield member, raw


def list_baseline_xccdfs(data: bytes) -> List[Tuple[str, bytes]]:
    found = list(iter_baseline_xccdfs_from(data))
    if not found:
        raise ValueError(
            "no Manual-xccdf STIG baselines found (SRGs, SCAP, and checklists are skipped)"
        )
    return found


def explore_baseline_zip(source: ZipSource) -> Dict[str, Any]:
    """List Manual-xccdf members without loading every XML body."""
    found: List[Dict[str, Any]] = []
    skipped = {"srg": 0, "scap": 0, "other": 0}

    def walk(src: ZipSource, prefix: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        archive = _open_zip(src)
        with archive:
            for info in archive.infolist():
                if info.is_dir() or info.file_size <= 0:
                    continue
                member = (prefix + info.filename).replace("\\", "/")
                nested = member.lower().endswith(".zip") and depth < MAX_DEPTH
                if nested:
                    if info.file_size > MAX_MEMBER_BYTES:
                        skipped["other"] += 1
                        continue
                    try:
                        raw = archive.read(info)
                    except Exception:
                        skipped["other"] += 1
                        continue
                    if looks_like_zip(raw):
                        walk(raw, member.rstrip("/") + "/", depth + 1)
                    continue
                if is_baseline_xccdf_name(member):
                    if len(found) >= MAX_BASELINES:
                        raise ValueError(
                            f"zip contains more than {MAX_BASELINES} Manual-xccdf baselines"
                        )
                    found.append({"path": member, "size": int(info.file_size)})
                    continue
                reason = skip_reason(member)
                skipped[reason] = skipped.get(reason, 0) + 1

    walk(source, "", 0)
    if not found:
        raise ValueError(
            "no Manual-xccdf STIG baselines found (SRGs, SCAP, and checklists are skipped)"
        )
    return {"found": found, "skipped": skipped}


def extract_baseline_xccdf(source: ZipSource, want_path: str) -> bytes:
    want = (want_path or "").replace("\\", "/")
    if not is_baseline_xccdf_name(want):
        raise ValueError("not a Manual-xccdf baseline path")

    def walk(src: ZipSource, prefix: str, depth: int) -> Optional[bytes]:
        if depth > MAX_DEPTH:
            return None
        archive = _open_zip(src)
        with archive:
            for info in archive.infolist():
                if info.is_dir() or info.file_size <= 0:
                    continue
                member = (prefix + info.filename).replace("\\", "/")
                nested = member.lower().endswith(".zip") and depth < MAX_DEPTH
                if nested:
                    if info.file_size > MAX_MEMBER_BYTES:
                        continue
                    try:
                        raw = archive.read(info)
                    except Exception:
                        continue
                    if looks_like_zip(raw):
                        hit = walk(raw, member.rstrip("/") + "/", depth + 1)
                        if hit is not None:
                            return hit
                    continue
                if member == want:
                    return archive.read(info)
        return None

    data = walk(source, "", 0)
    if not data:
        raise ValueError(f"member not found: {want}")
    return data
