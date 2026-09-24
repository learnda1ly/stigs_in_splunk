import { COLOR_KEY_MAP, getBuiltinPreset, LIGHT_SPLUNK, TOKYO_NIGHT } from "./presets";

function normalizeScheme(value) {
    return String(value || "").toLowerCase() === "light" ? "light" : "dark";
}

/**
 * Parse optional custom theme JSON from Configuration.
 * @returns {{ colorScheme: string, cssVars: Record<string,string> } | null}
 */
export function parseCustomThemeJson(raw) {
    const text = String(raw || "").trim();
    if (!text) {
        return null;
    }
    let doc;
    try {
        doc = JSON.parse(text);
    } catch (e) {
        return null;
    }
    if (!doc || typeof doc !== "object") {
        return null;
    }
    const base =
        doc.basePreset && getBuiltinPreset(doc.basePreset)
            ? getBuiltinPreset(doc.basePreset)
            : TOKYO_NIGHT;
    const cssVars = { ...base.cssVars };
    const colors = doc.colors || doc.palette || {};
    if (colors && typeof colors === "object") {
        Object.keys(colors).forEach((key) => {
            const varName = COLOR_KEY_MAP[key];
            const val = colors[key];
            if (varName && val) {
                cssVars[varName] = String(val);
            }
        });
    }
    if (doc.cssVars && typeof doc.cssVars === "object") {
        Object.assign(cssVars, doc.cssVars);
    }
    const colorScheme = normalizeScheme(doc.colorScheme || base.colorScheme);
    return { colorScheme, cssVars };
}

export function mergeCustomOntoPreset(preset, customJson) {
    const custom = parseCustomThemeJson(customJson);
    if (!custom) {
        return preset;
    }
    return {
        ...preset,
        id: preset.id === "custom" ? "custom" : preset.id,
        colorScheme: custom.colorScheme,
        cssVars: { ...preset.cssVars, ...custom.cssVars },
    };
}

export function paletteForFollowSplunk(splunkScheme) {
    if (splunkScheme === "light") {
        return LIGHT_SPLUNK;
    }
    return TOKYO_NIGHT;
}
