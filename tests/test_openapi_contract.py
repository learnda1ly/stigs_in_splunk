"""Lightweight checks for docs/openapi.yaml."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "openapi.yaml"
HANDLER_PATH = ROOT / "package" / "bin" / "stig_rest_handler.py"


def test_openapi_file_exists():
    assert OPENAPI_PATH.is_file()


def test_openapi_parses():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert data.get("openapi", "").startswith("3.")
    assert data.get("info", {}).get("title")
    paths = data.get("paths") or {}
    assert "/stig_collections" in paths
    assert "/stig_reviews/batch" in paths


def test_openapi_version_matches_app_manifest():
    yaml = pytest.importorskip("yaml")
    import json

    manifest = json.loads((ROOT / "package" / "app.manifest").read_text(encoding="utf-8"))
    app_version = manifest["info"]["id"]["version"]
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert spec["info"]["version"] == app_version


def test_openapi_documents_handler_resources():
    """Every top-level persist resource in the handler should appear in OpenAPI paths."""
    yaml = pytest.importorskip("yaml")
    handler = HANDLER_PATH.read_text(encoding="utf-8")
    resource_names = set(
        re.findall(r'if resource == "([^"]+)"', handler)
    )
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    path_blob = "\n".join(spec.get("paths", {}).keys())
    missing = []
    for name in sorted(resource_names):
        if name not in path_blob:
            missing.append(name)
    assert not missing, f"OpenAPI paths missing resources: {missing}"
