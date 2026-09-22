"""Lightweight checks for docs/openapi.yaml."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "openapi.yaml"
HANDLER_PATH = ROOT / "package" / "bin" / "stig_rest_handler.py"
RESTMAP_PATH = ROOT / "package" / "default" / "restmap.conf"

HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def _load_openapi():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def test_openapi_file_exists():
    assert OPENAPI_PATH.is_file()


def test_openapi_parses():
    data = _load_openapi()
    assert data.get("openapi", "").startswith("3.")
    assert data.get("info", {}).get("title")
    paths = data.get("paths") or {}
    assert "/stig_collections" in paths
    assert "/stig_reviews/batch" in paths


def test_openapi_version_matches_app_manifest():
    manifest = json.loads((ROOT / "package" / "app.manifest").read_text(encoding="utf-8"))
    app_version = manifest["info"]["id"]["version"]
    spec = _load_openapi()
    assert spec["info"]["version"] == app_version


def test_openapi_documents_handler_resources():
    """Every top-level persist resource in the handler should appear in OpenAPI paths."""
    handler = HANDLER_PATH.read_text(encoding="utf-8")
    resource_names = set(re.findall(r'if resource == "([^"]+)"', handler))
    spec = _load_openapi()
    path_blob = "\n".join(spec.get("paths", {}).keys())
    missing = [name for name in sorted(resource_names) if name not in path_blob]
    assert not missing, f"OpenAPI paths missing resources: {missing}"


def test_restmap_matches_documented_in_openapi():
    """Each restmap.conf persist `match` must appear as an OpenAPI path prefix."""
    restmap = RESTMAP_PATH.read_text(encoding="utf-8")
    matches = re.findall(r"^match = (/[^\s]+)", restmap, flags=re.MULTILINE)
    spec = _load_openapi()
    path_keys = list(spec.get("paths", {}).keys())
    missing = []
    for match in matches:
        if match == "/stig_assignment/preview":
            if match not in path_keys:
                missing.append(match)
            continue
        prefix = match if match.endswith("/") else match
        if not any(p == prefix or p.startswith(prefix + "/") or p == match for p in path_keys):
            if match not in path_keys:
                missing.append(match)
    assert not missing, f"restmap match not in OpenAPI paths: {missing}"


def test_no_null_operation_responses():
    """Catch YAML null response objects (bare \"200\": with no mapping)."""
    spec = _load_openapi()
    paths = spec.get("paths") or {}
    bad = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            bad.append((path, "path item not a mapping"))
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                bad.append((path, method, "operation not a mapping"))
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                bad.append((path, method, "missing responses"))
                continue
            for code, response in responses.items():
                if response is None:
                    bad.append((path, method, code, "null response"))
                elif not isinstance(response, dict):
                    bad.append((path, method, code, f"not a mapping: {type(response)}"))
    assert not bad, f"Invalid responses: {bad[:20]}{'...' if len(bad) > 20 else ''}"


def test_dual_status_import_paths_document_200_and_201():
    """Regression guard for handler status selection on imports and transfers."""
    spec = _load_openapi()
    paths = spec["paths"]
    for path in (
        "/stig_collections/{collectionId}/export-to/{destCollectionId}",
        "/stig_collections/{collectionId}/imports",
        "/stig_baselines/import",
        "/stig_baselines/jobs/{jobId}",
        "/stig_imports",
    ):
        post = paths[path]["post"]
        codes = set(post["responses"])
        assert "200" in codes and "201" in codes, path
        for code in ("200", "201"):
            resp = post["responses"][code]
            assert resp.get("content"), f"{path} {code} missing content"
            assert str(resp.get("description") or "").strip(), f"{path} {code} missing description"
