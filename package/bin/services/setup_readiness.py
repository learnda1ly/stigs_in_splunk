"""Install/setup readiness checks for onboarding (roles, HEC, app ownership)."""

from __future__ import annotations

import configparser
import os
from typing import Any, Dict, List

import access
from models import APP_NAME
from services import hec as hec_svc

SPLUNK_SETTINGS_ROLES = (
    "Settings → Users and authentication → Roles → "
    "assign role_stig_user or role_stig_admin to your account"
)
SPLUNK_SETTINGS_HEC = (
    "Settings → Data inputs → HTTP Event Collector → "
    "enable HEC globally, then add or edit input stig_findings "
    "(index stig, sourcetype stig:finding). The token is stored on that input only."
)

STIG_ROLE_HINT = (
    "Assign Splunk role role_stig_user (assessor) or role_stig_admin (administrator). "
    "They grant capabilities stig_read, stig_write, and edit_kvstore (stig_admin adds stig_admin)."
)


def _capabilities_map(session: Dict[str, Any]) -> Dict[str, bool]:
    raw = session.get("capabilities") or {}
    if isinstance(raw, dict):
        return {str(k): bool(v) for k, v in raw.items()}
    if isinstance(raw, (list, tuple, set)):
        return {str(item): True for item in raw if str(item).strip()}
    return {}


def _user_has_stig_read(session: Dict[str, Any]) -> bool:
    if access.user_has_stig_admin(session):
        return True
    roles = access.user_roles(session)
    if roles & {"stig_user", "stig_admin"}:
        return True
    caps = _capabilities_map(session)
    if caps.get("stig_read"):
        return True
    return False


def assess_role_readiness(session: Dict[str, Any]) -> Dict[str, Any]:
    """ROLE-001: surface missing STIG role/capabilities for the current user."""
    ok = _user_has_stig_read(session)
    missing: List[str] = []
    if not ok:
        missing.append("stig_read (via role_stig_user or role_stig_admin)")
    return {
        "ok": ok,
        "missing": missing,
        "fix_in_splunk": SPLUNK_SETTINGS_ROLES,
        "guidance": STIG_ROLE_HINT,
        "next_action": (
            "Ask a Splunk admin to assign role_stig_user or role_stig_admin, "
            "then sign out and back in."
            if not ok
            else ""
        ),
    }


def assess_hec_readiness(session_key: str = "") -> Dict[str, Any]:
    """HEC-002: probe stig_findings token without exposing it."""
    token = hec_svc.lookup_hec_token(session_key)
    if token:
        return {
            "ok": True,
            "status": "configured",
            "message": "HEC token is set on HTTP input stig_findings.",
            "verify_in_splunk": SPLUNK_SETTINGS_HEC,
            "next_action": "",
        }

    stanza_present = _hec_stanza_present()
    if stanza_present:
        return {
            "ok": False,
            "status": "incomplete",
            "message": (
                "Input stig_findings exists but no HEC token was found. "
                "Open the input in Splunk Settings and set a token (index stig, sourcetype stig:finding)."
            ),
            "verify_in_splunk": SPLUNK_SETTINGS_HEC,
            "next_action": "Add or regenerate the token on input stig_findings, then return here.",
        }

    return {
        "ok": False,
        "status": "unknown",
        "message": (
            "Could not confirm an HEC token for stig_findings from this search head. "
            "Verify manually in Splunk Settings."
        ),
        "verify_in_splunk": SPLUNK_SETTINGS_HEC,
        "next_action": (
            "In Splunk Settings, enable HTTP Event Collector and create input stig_findings "
            "with index stig and sourcetype stig:finding."
        ),
    }


def _hec_stanza_present() -> bool:
    home = os.environ.get("SPLUNK_HOME") or ""
    candidates = []
    app_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    candidates.append(os.path.join(app_root, "default", "inputs.conf"))
    if home:
        candidates.extend(
            [
                os.path.join(home, "etc", "apps", APP_NAME, "local", "inputs.conf"),
                os.path.join(home, "etc", "apps", APP_NAME, "default", "inputs.conf"),
                os.path.join(home, "etc", "system", "local", "inputs.conf"),
            ]
        )
    for path in candidates:
        if _stanza_exists(path, hec_svc.HEC_STANZA):
            return True
    return False


def _stanza_exists(path: str, stanza: str) -> bool:
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if line.startswith("[") and line.endswith("]"):
                    if line[1:-1].strip() == stanza:
                        return True
    except OSError:
        return False
    return False


def _app_paths() -> Dict[str, str]:
    home = os.environ.get("SPLUNK_HOME") or ""
    app_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if home:
        installed = os.path.join(home, "etc", "apps", APP_NAME)
        if os.path.isdir(installed):
            app_root = installed
    local_dir = os.path.join(app_root, "local")
    settings_conf = os.path.join(local_dir, "stigs_in_splunk_settings.conf")
    app_conf = os.path.join(local_dir, "app.conf")
    return {
        "app_root": app_root,
        "local_dir": local_dir,
        "settings_conf": settings_conf,
        "app_conf": app_conf,
    }


def _splunk_runtime_user() -> str:
    for key in ("SPLUNK_USER", "SPLUNK_OS_USER"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    try:
        import pwd

        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return "splunk"


def assess_ownership_readiness() -> Dict[str, Any]:
    """OWN-013: detect unwritable local/ and return exact chown command."""
    paths = _app_paths()
    local_dir = paths["local_dir"]
    settings_conf = paths["settings_conf"]
    app_root = paths["app_root"]
    runtime_user = _splunk_runtime_user()
    chown_cmd = f"chown -R {runtime_user}:{runtime_user} {app_root}"

    if not os.path.isdir(local_dir):
        try:
            os.makedirs(local_dir, exist_ok=True)
        except OSError as exc:
            return {
                "ok": False,
                "message": (
                    f"Cannot create {local_dir}. Fix ownership on the app directory, then retry."
                ),
                "chown_command": chown_cmd,
                "next_action": f"Run on the search head as root: {chown_cmd}",
            }

    probe = settings_conf + ".stig_write_probe"
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("# probe\n")
        os.remove(probe)
        return {
            "ok": True,
            "message": "App local/ directory is writable by splunkd.",
            "chown_command": chown_cmd,
            "next_action": "",
        }
    except OSError:
        return {
            "ok": False,
            "message": (
                "UCC cannot save settings because local/ is not writable by splunkd "
                "(common when the app was installed as root)."
            ),
            "chown_command": chown_cmd,
            "next_action": f"Run on the search head as root: {chown_cmd}",
        }


def build_readiness_report(session: Dict[str, Any]) -> Dict[str, Any]:
    session_key = session.get("authtoken") or ""
    roles = assess_role_readiness(session)
    hec = assess_hec_readiness(session_key)
    ownership = assess_ownership_readiness()
    configured = is_app_configured()
    return {
        "roles": roles,
        "hec": hec,
        "ownership": ownership,
        "is_configured": configured,
        "documentation_view": "stig_documentation_ui",
        "platform_ready": bool(roles.get("ok") and ownership.get("ok")),
    }


def is_app_configured() -> bool:
    paths = _app_paths()
    app_root = paths["app_root"]
    for rel in ("local/app.conf", "default/app.conf"):
        conf_path = os.path.join(app_root, *rel.split("/"))
        if not os.path.isfile(conf_path):
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(conf_path)
        except configparser.Error:
            continue
        if parser.has_section("install"):
            val = parser.get("install", "is_configured", fallback="false").strip().lower()
            if val in {"1", "true", "yes"}:
                return True
    return False


def _write_is_configured(app_conf_path: str) -> None:
    os.makedirs(os.path.dirname(app_conf_path), exist_ok=True)
    lines: List[str] = []
    if os.path.isfile(app_conf_path):
        with open(app_conf_path, encoding="utf-8") as handle:
            lines = handle.readlines()

    out: List[str] = []
    in_install = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_install = stripped == "[install]"
            out.append(line)
            continue
        if in_install and stripped.split("=", 1)[0].strip() == "is_configured":
            out.append("is_configured = 1\n")
            replaced = True
            continue
        out.append(line)

    if not replaced:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        if not any(l.strip() == "[install]" for l in out):
            out.append("\n[install]\n")
        out.append("is_configured = 1\n")

    with open(app_conf_path, "w", encoding="utf-8") as handle:
        handle.writelines(out)


def mark_setup_complete(session: Dict[str, Any]) -> Dict[str, Any]:
    """SETUP-007: set local app.conf is_configured after admin confirms checklist."""
    if not access.user_has_stig_admin(session) and not (
        access.user_roles(session) & access.ADMIN_ROLES
    ):
        return {
            "ok": False,
            "error": (
                "Splunk admin required to mark setup complete. "
                "Ask an admin to open Set up from Manage Apps."
            ),
        }

    paths = _app_paths()
    ownership = assess_ownership_readiness()
    if not ownership.get("ok"):
        return {
            "ok": False,
            "error": ownership.get("message"),
            "chown_command": ownership.get("chown_command"),
            "next_action": ownership.get("next_action"),
        }

    try:
        _write_is_configured(paths["app_conf"])
    except OSError as exc:
        return {
            "ok": False,
            "error": f"Could not write {paths['app_conf']}: {exc}",
            "next_action": ownership.get("chown_command") or "",
        }

    return {"ok": True, "is_configured": True, "next_action": "Reload the app or open STIG in Splunk from Apps."}
