import { getUserTheme } from "@splunk/themes";
import { apiFetch, unwrap } from "./api";
import { mergeCustomOntoPreset, paletteForFollowSplunk, parseCustomThemeJson } from "./themes/customTheme";
import { applyPaletteToDocument } from "./themes/injectTheme";
import {
    DEFAULT_THEME_PRESET,
    getBuiltinPreset,
    LIGHT_SPLUNK,
    THEME_PRESET_IDS,
} from "./themes/presets";

const FALLBACK = {
    family: "prisma",
    colorScheme: "dark",
    density: "comfortable",
};

function normalizePreset(raw) {
    const value = String(raw || DEFAULT_THEME_PRESET).toLowerCase();
    if (THEME_PRESET_IDS.includes(value)) {
        return value;
    }
    return DEFAULT_THEME_PRESET;
}

/** Legacy ui_color_scheme → preset when ui_theme_preset is unset. */
function legacySchemeToPreset(scheme) {
    const s = String(scheme || "").toLowerCase();
    if (s === "light") {
        return "light";
    }
    if (s === "follow_splunk") {
        return "follow_splunk";
    }
    return DEFAULT_THEME_PRESET;
}

async function splunkUserTheme() {
    if (typeof getUserTheme !== "function") {
        return { ...FALLBACK };
    }
    try {
        const theme = await getUserTheme();
        return { ...FALLBACK, ...theme };
    } catch (e) {
        return { ...FALLBACK };
    }
}

async function loadSettings() {
    try {
        const data = unwrap(await apiFetch("stig_settings"));
        if (data && typeof data === "object") {
            return data;
        }
    } catch (e) {
        /* stig_read may be missing on first paint */
    }
    return {};
}

export function resolvePaletteFromSettings(settings, splunkTheme) {
    const presetId = settings.ui_theme_preset
        ? normalizePreset(settings.ui_theme_preset)
        : legacySchemeToPreset(settings.ui_color_scheme);

    if (presetId === "follow_splunk") {
        const splunkScheme =
            splunkTheme.colorScheme === "light" ? "light" : "dark";
        return {
            ...paletteForFollowSplunk(splunkScheme),
            id: "follow_splunk",
        };
    }

    if (presetId === "custom") {
        const custom = parseCustomThemeJson(settings.ui_theme_custom);
        if (custom) {
            return {
                id: "custom",
                label: "Custom",
                colorScheme: custom.colorScheme,
                cssVars: custom.cssVars,
            };
        }
        return getBuiltinPreset(DEFAULT_THEME_PRESET);
    }

    if (presetId === "light") {
        return LIGHT_SPLUNK;
    }

    let palette = getBuiltinPreset(presetId);
    if (settings.ui_theme_custom) {
        palette = mergeCustomOntoPreset(palette, settings.ui_theme_custom);
    }
    return palette;
}

export async function resolveAppTheme() {
    const settings = await loadSettings();
    const splunkTheme = await splunkUserTheme();
    const palette = resolvePaletteFromSettings(settings, splunkTheme);
    return {
        family: splunkTheme.family || "prisma",
        colorScheme: palette.colorScheme === "light" ? "light" : "dark",
        density: splunkTheme.density || "comfortable",
        palette,
        presetId: palette.id,
    };
}

export function applyThemeDocument(scheme) {
    const colorScheme = scheme === "light" ? "light" : "dark";
    document.documentElement.dataset.stigColorScheme = colorScheme;
    document.body.classList.toggle("stig-ui-dark", colorScheme === "dark");
    document.body.classList.toggle("stig-ui-light", colorScheme === "light");
}

export function applyAppTheme(theme) {
    if (theme && theme.palette) {
        applyPaletteToDocument(theme.palette);
        return;
    }
    applyThemeDocument(theme?.colorScheme || "dark");
}
