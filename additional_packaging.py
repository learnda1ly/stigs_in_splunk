"""UCC build hooks: reload triggers and post-build steps."""

from __future__ import annotations

import json
import os
import shutil
from os.path import dirname, join

_LAST_OUTPUT_PATH = "output"

# UCC generates these, then copies package/default/restmap.conf with a merge.
# A raw copy of the persist restmap wipes them and the Configuration page 404s.
_UCC_RESTMAP = """
[admin:stigs_in_splunk]
match = /
members = stigs_in_splunk_settings, stigs_in_splunk_workspace

[admin_external:stigs_in_splunk_workspace]
handlertype = python
python.version = python3
python.required = 3.9
handlerfile = stigs_in_splunk_rh_workspace.py
handleractions = edit, list, remove, create
handlerpersistentmode = true

[admin_external:stigs_in_splunk_settings]
handlertype = python
python.version = python3
python.required = 3.9
handlerfile = stigs_in_splunk_rh_settings.py
handleractions = edit, list
handlerpersistentmode = true
"""

# Splunk Web only proxies endpoints listed in web.conf. Without these, the
# Configuration page 404s even though management port 8089 works.
_UCC_WEB = """
[expose:stigs_in_splunk_workspace]
pattern = stigs_in_splunk_workspace
methods = GET, POST

[expose:stigs_in_splunk_workspace_specified]
pattern = stigs_in_splunk_workspace/*
methods = GET, POST, DELETE

[expose:stigs_in_splunk_settings]
pattern = stigs_in_splunk_settings
methods = GET, POST

[expose:stigs_in_splunk_settings_specified]
pattern = stigs_in_splunk_settings/*
methods = GET, POST, DELETE
"""


def cleanup_output_files(output_path, ta_name):
    """Remove UCC scaffold artifacts not used by this conf-only REST app."""
    global _LAST_OUTPUT_PATH
    _LAST_OUTPUT_PATH = output_path
    app_root = join(output_path, ta_name)
    to_remove = [
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
    _write_ucc_global_config_json(app_root)
    _ensure_ucc_restmap(app_root)
    _ensure_ucc_web(app_root)
    _ensure_configuration_fallback(app_root, os.path.isfile(
        join(app_root, "appserver", "static", "js", "build", "entry_page.js")
    ))
    _strip_non_shippable_artifacts(app_root)


def strip_ship_tree(app_root: str) -> None:
    """Public entry for scripts: remove local/, local.meta, and bytecode."""
    _strip_non_shippable_artifacts(app_root)


def _strip_non_shippable_artifacts(app_root: str) -> None:
    """Remove runtime local/ metadata and bytecode before tarball packaging."""
    local_dir = join(app_root, "local")
    if os.path.isdir(local_dir):
        shutil.rmtree(local_dir)
    local_meta = join(app_root, "metadata", "local.meta")
    if os.path.isfile(local_meta):
        os.remove(local_meta)
    for dirpath, dirnames, filenames in os.walk(app_root):
        if "__pycache__" in dirnames:
            shutil.rmtree(join(dirpath, "__pycache__"))
            dirnames.remove("__pycache__")
        for name in filenames:
            if name.endswith((".pyc", ".pyo")):
                os.remove(join(dirpath, name))


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
    ucc_entry = join(app_root, "appserver", "static", "js", "build", "entry_page.js")
    has_ucc_bundle = os.path.isfile(ucc_entry)
    if os.path.isdir(src_views):
        os.makedirs(dst_views, exist_ok=True)
        for name in os.listdir(src_views):
            if not name.endswith(".xml"):
                continue
            if name == "configuration.xml" and has_ucc_bundle:
                continue
            shutil.copy2(join(src_views, name), join(dst_views, name))
    _ensure_configuration_fallback(app_root, has_ucc_bundle)


def _write_ucc_global_config_json(app_root: str) -> None:
    """UCC UI fetches js/build/globalConfig.json; normalize from repo source."""
    repo = dirname(os.path.abspath(__file__))
    src_json = join(repo, "globalConfig.json")
    if not os.path.isfile(src_json):
        return
    with open(src_json, encoding="utf-8") as handle:
        data = json.load(handle)
    build_dir = join(app_root, "appserver", "static", "js", "build")
    os.makedirs(build_dir, exist_ok=True)
    dst_json = join(build_dir, "globalConfig.json")
    with open(dst_json, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4, ensure_ascii=False)
        handle.write("\n")


def _ensure_ucc_restmap(app_root: str) -> None:
    """Keep UCC Configuration REST endpoints if persist restmap overwrote them."""
    path = join(app_root, "default", "restmap.conf")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    if "[admin:stigs_in_splunk]" in content and "admin_external:stigs_in_splunk_workspace" in content:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if not content.endswith("\n"):
            handle.write("\n")
        handle.write(_UCC_RESTMAP)
        if not _UCC_RESTMAP.endswith("\n"):
            handle.write("\n")


def _ensure_ucc_web(app_root: str) -> None:
    """Keep UCC Configuration exposes if persist web.conf overwrote them."""
    path = join(app_root, "default", "web.conf")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    if "pattern = stigs_in_splunk_workspace" in content and "pattern = stigs_in_splunk_settings" in content:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if not content.endswith("\n"):
            handle.write("\n")
        handle.write(_UCC_WEB)
        if not _UCC_WEB.endswith("\n"):
            handle.write("\n")


def _ensure_configuration_fallback(app_root: str, has_ucc_bundle: bool) -> None:
    """BUILD-025: show rebuild instructions when the UCC bundle is missing."""
    repo = dirname(os.path.abspath(__file__))
    src_template = join(repo, "package", "appserver", "templates", "configuration_page.html")
    dst_template = join(app_root, "appserver", "templates", "configuration_page.html")
    if os.path.isfile(src_template):
        os.makedirs(dirname(dst_template), exist_ok=True)
        shutil.copy2(src_template, dst_template)

    if has_ucc_bundle:
        base_html = join(app_root, "appserver", "templates", "base.html")
        if os.path.isfile(base_html):
            _patch_ucc_base_html_fallback(base_html)
        return

    stub_view = join(
        repo, "package", "default", "data", "ui", "views", "configuration.xml"
    )
    dst_view = join(app_root, "default", "data", "ui", "views", "configuration.xml")
    if os.path.isfile(stub_view):
        os.makedirs(dirname(dst_view), exist_ok=True)
        shutil.copy2(stub_view, dst_view)


def _patch_ucc_base_html_fallback(base_html_path: str) -> None:
    with open(base_html_path, encoding="utf-8") as handle:
        content = handle.read()
    if "stig-ucc-missing" in content:
        return
    marker = "</body>"
    if marker not in content:
        return
    inject = """
        <div id="stig-ucc-missing" style="display:none;font-family:Arial,sans-serif;max-width:42rem;margin:2rem auto;padding:1rem 1.25rem;border:1px solid #ccc;border-radius:4px;">
            <h2>Configuration UI not built</h2>
            <p>Missing <code>appserver/static/js/build/entry_page.js</code>. From the repo run <code>./scripts/build_ucc.sh</code>, then reinstall the app.</p>
        </div>
        <script>
            if (typeof _loadScript === 'function') {
                var _origLoad = _loadScript;
                _loadScript = function(src, type) {
                    return _origLoad(src, type).catch(function(err) {
                        var el = document.getElementById('stig-ucc-missing');
                        if (el) { el.style.display = 'block'; }
                        throw err;
                    });
                };
            }
        </script>
"""
    content = content.replace(marker, inject + "\n    " + marker)
    with open(base_html_path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _ensure_setup_app_conf(app_conf_path: str) -> None:
    """SETUP-007: wire setup view until an admin marks is_configured."""
    if not os.path.isfile(app_conf_path):
        return
    with open(app_conf_path, encoding="utf-8") as handle:
        content = handle.read()
    changed = False
    if "setup_view" not in content:
        if "[ui]" not in content:
            content += "\n[ui]\n"
        if not content.endswith("\n"):
            content += "\n"
        content += "setup_view = setup\n"
        changed = True
    if "is_configured" not in content:
        if "[install]" not in content:
            content += "\n[install]\n"
        if not content.endswith("\n"):
            content += "\n"
        content += "is_configured = false\n"
        changed = True
    if changed:
        with open(app_conf_path, "w", encoding="utf-8") as handle:
            handle.write(content)


def additional_packaging(ta_name=None):
    """Append KV reload triggers to generated app.conf; restore custom nav/views."""
    if not ta_name:
        return
    app_root = join(_LAST_OUTPUT_PATH, ta_name)
    _restore_nav_and_views(app_root)
    _write_ucc_global_config_json(app_root)
    _ensure_ucc_restmap(app_root)
    _ensure_ucc_web(app_root)
    _ensure_configuration_fallback(app_root, os.path.isfile(
        join(app_root, "appserver", "static", "js", "build", "entry_page.js")
    ))
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
    _ensure_setup_app_conf(app_conf)
    _strip_non_shippable_artifacts(app_root)
