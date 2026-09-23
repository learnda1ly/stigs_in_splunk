import { getUserTheme } from "@splunk/themes";
import { apiFetch, unwrap } from "./api";

const FALLBACK = {
    family: "prisma",
    colorScheme: "dark",
    density: "comfortable",
};

function normalizePreference(raw) {
    const value = String(raw || "dark").toLowerCase();
    if (value === "light" || value === "dark" || value === "follow_splunk") {
        return value;
    }
    return "dark";
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

async function settingsColorPreference() {
    try {
        const data = unwrap(await apiFetch("stig_settings"));
        if (data && typeof data === "object") {
            return normalizePreference(data.ui_color_scheme);
        }
    } catch (e) {
        /* stig_read may be missing on first paint; default dark */
    }
    return "dark";
}

export async function resolveAppTheme() {
    const preference = await settingsColorPreference();
    const splunkTheme = await splunkUserTheme();
    if (preference === "follow_splunk") {
        return splunkTheme;
    }
    return { ...splunkTheme, colorScheme: preference };
}

export function applyThemeDocument(scheme) {
    const colorScheme = scheme === "light" ? "light" : "dark";
    document.documentElement.dataset.stigColorScheme = colorScheme;
    document.body.classList.toggle("stig-ui-dark", colorScheme === "dark");
    document.body.classList.toggle("stig-ui-light", colorScheme === "light");
}
