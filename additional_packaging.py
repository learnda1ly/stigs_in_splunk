"""UCC build hooks: reload triggers and post-build steps."""

from __future__ import annotations

import os
from os.path import join

_LAST_OUTPUT_PATH = "output"


def cleanup_output_files(output_path: str, ta_name: str) -> None:
    global _LAST_OUTPUT_PATH
    _LAST_OUTPUT_PATH = output_path
    """Remove UCC scaffold artifacts not used by this conf-only REST app."""
    app_root = join(output_path, ta_name)
    to_remove = [
        join(app_root, "default", "data", "ui", "views", "configuration.xml"),
        join(app_root, "default", "data", "ui", "views", "inputs.xml"),
        join(app_root, "default", "data", "ui", "views", "dashboard.xml"),
        join(app_root, "default", "data", "ui", "views", "_redirect.xml"),
    ]
    for path in to_remove:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def additional_packaging(ta_name: str | None = None) -> None:
    """Append KV reload triggers to generated app.conf."""
    if not ta_name:
        return
    app_conf = join(_LAST_OUTPUT_PATH, ta_name, "default", "app.conf")
    if not os.path.isfile(app_conf):
        return
    with open(app_conf, encoding="utf-8") as handle:
        content = handle.read()
    if "reload.collections" in content:
        return
    with open(app_conf, "a", encoding="utf-8") as handle:
        handle.write(
            "\n[triggers]\nreload.collections = simple\nreload.stig_editor = simple\n"
        )
