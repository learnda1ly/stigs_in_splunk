import { apiFetch } from "../api";

export const VIM_STORAGE_KEY = "stigs_in_splunk.vim_mode";

export function parseBool(raw) {
    raw = String(raw == null ? "" : raw)
        .trim()
        .toLowerCase();
    return raw === "1" || raw === "true" || raw === "yes";
}

export function extractVimEnabled(raw) {
    if (raw == null) {
        return null;
    }
    if (typeof raw === "boolean") {
        return raw;
    }
    if (typeof raw === "number") {
        return raw !== 0;
    }
    if (typeof raw === "string") {
        const text = raw.trim().toLowerCase();
        if (!text) {
            return null;
        }
        if (text === "1" || text === "true" || text === "yes") {
            return true;
        }
        if (text === "0" || text === "false" || text === "no") {
            return false;
        }
        return null;
    }
    if (typeof raw !== "object") {
        return null;
    }
    if (Object.prototype.hasOwnProperty.call(raw, "vim_mode")) {
        return extractVimEnabled(raw.vim_mode);
    }
    if (raw.value != null && typeof raw.value !== "object") {
        return extractVimEnabled(raw.value);
    }
    const entry = raw.entry && raw.entry[0];
    const content = entry && entry.content;
    if (content && typeof content === "object") {
        if (Object.prototype.hasOwnProperty.call(content, "vim_mode")) {
            return extractVimEnabled(content.vim_mode);
        }
        if (content.value != null && typeof content.value !== "object") {
            return extractVimEnabled(content.value);
        }
    } else if (content != null) {
        return extractVimEnabled(content);
    }
    return null;
}

export function readLocalVim() {
    try {
        const stored = window.localStorage.getItem(VIM_STORAGE_KEY);
        if (stored == null) {
            return null;
        }
        return parseBool(stored);
    } catch (e) {
        return null;
    }
}

export function writeLocalVim(enabled) {
    try {
        window.localStorage.setItem(VIM_STORAGE_KEY, enabled ? "true" : "false");
        return true;
    } catch (e) {
        return false;
    }
}

export function loadVimSetting() {
    const local = readLocalVim();
    if (local != null) {
        return Promise.resolve(local);
    }
    return apiFetch("stig_settings")
        .then((raw) => !!extractVimEnabled(raw))
        .catch(() => false);
}

export function persistVimSetting(enabled) {
    const local = writeLocalVim(enabled);
    return apiFetch("stig_settings", {
        method: "POST",
        body: { vim_mode: !!enabled },
    })
        .then(() => ({ local, remote: true }))
        .catch((err) => {
            const error = new Error(err && err.message ? err.message : String(err));
            error.local = local;
            error.remote = false;
            throw error;
        });
}
