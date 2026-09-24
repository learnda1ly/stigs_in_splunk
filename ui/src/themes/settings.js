import { apiFetch, unwrap } from "../api";
import { applyAppTheme, resolveAppTheme } from "../theme";
import { DEFAULT_THEME_PRESET, THEME_PRESET_IDS } from "./presets";
import { notifyThemeUpdated } from "./themeEvents";

function normalizePreset(raw) {
    const value = String(raw || DEFAULT_THEME_PRESET).toLowerCase();
    if (THEME_PRESET_IDS.includes(value)) {
        return value;
    }
    return DEFAULT_THEME_PRESET;
}

export function extractThemePreset(raw) {
    const data = unwrap(raw);
    if (!data || typeof data !== "object") {
        return DEFAULT_THEME_PRESET;
    }
    if (data.ui_theme_preset) {
        return normalizePreset(data.ui_theme_preset);
    }
    const legacy = String(data.ui_color_scheme || "").toLowerCase();
    if (legacy === "light") {
        return "light";
    }
    if (legacy === "follow_splunk") {
        return "follow_splunk";
    }
    return DEFAULT_THEME_PRESET;
}

export function loadThemePreset() {
    return apiFetch("stig_settings")
        .then((raw) => extractThemePreset(raw))
        .catch(() => DEFAULT_THEME_PRESET);
}

export async function persistThemePreset(presetId) {
    const preset = normalizePreset(presetId);
    await apiFetch("stig_settings", {
        method: "POST",
        body: { ui_theme_preset: preset },
    });
    await refreshAppThemeFromServer();
    return preset;
}

export async function refreshAppThemeFromServer() {
    const theme = await resolveAppTheme();
    applyAppTheme(theme);
    notifyThemeUpdated(theme);
    return theme;
}
