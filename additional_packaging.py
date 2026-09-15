"""UCC build hooks: reload triggers and post-build steps."""

from __future__ import annotations

import os
import shutil
from os.path import dirname, join

_LAST_OUTPUT_PATH = "output"


def cleanup_output_files(output_path, ta_name):
    """Remove UCC scaffold artifacts not used by this conf-only REST app."""
    global _LAST_OUTPUT_PATH
    _LAST_OUTPUT_PATH = output_path
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
    _restore_nav_and_views(app_root)


def _restore_nav_and_views(app_root: str) -> None:
    """UCC may overwrite nav after copying package/; put our pages back."""
    repo = dirname(os.path.abspath(__file__))
    src_nav = join(repo, "package", "default", "data", "ui", "nav", "default.xml")
    dst_nav = join(app_root, "default", "data", "ui", "nav", "default.xml")
    if os.path.isfile(src_nav):
        os.makedirs(dirname(dst_nav), exist_ok=True)
        shutil.copy2(src_nav, dst_nav)
    src_views = join(repo, "package", "default", "data", "ui", "views")
    dst_views = join(app_root, "default", "data", "ui", "views")
    if os.path.isdir(src_views):
        os.makedirs(dst_views, exist_ok=True)
        for name in os.listdir(src_views):
            if name.endswith(".xml"):
                shutil.copy2(join(src_views, name), join(dst_views, name))


def additional_packaging(ta_name=None):
    """Append KV reload triggers to generated app.conf; restore custom nav/views."""
    if not ta_name:
        return
    app_root = join(_LAST_OUTPUT_PATH, ta_name)
    _restore_nav_and_views(app_root)
    app_conf = join(app_root, "default", "app.conf")
    if not os.path.isfile(app_conf):
        return
    with open(app_conf, encoding="utf-8") as handle:
        content = handle.read()
    extra = ""
    if "reload.collections" not in content:
        extra += "reload.collections = simple\n"
    if "reload.nav" not in content:
        extra += "reload.nav = simple\n"
    if extra:
        with open(app_conf, "a", encoding="utf-8") as handle:
            if "[triggers]" not in content:
                handle.write("\n[triggers]\n")
            handle.write(extra)
            if "reload.stig_editor" not in content:
                handle.write("reload.stig_editor = simple\n")
