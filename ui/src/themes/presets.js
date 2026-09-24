/** Built-in editor palettes (Tokyo Night, Catppuccin Mocha, Rosé Pine). */

export const THEME_PRESET_IDS = [
    "tokyo_night",
    "catppuccin",
    "rose_pine",
    "light",
    "follow_splunk",
    "custom",
];

export const DEFAULT_THEME_PRESET = "tokyo_night";

/**
 * @typedef {Object} StigPalette
 * @property {string} id
 * @property {string} label
 * @property {'dark'|'light'} colorScheme
 * @property {Record<string, string>} cssVars
 */

function palette(id, label, colorScheme, colors) {
    return {
        id,
        label,
        colorScheme,
        cssVars: {
            "--stig-bg-page": colors.bgPage,
            "--stig-bg-section": colors.bgSection,
            "--stig-bg-elevated": colors.bgElevated,
            "--stig-bg-input": colors.bgInput,
            "--stig-fg": colors.fg,
            "--stig-fg-muted": colors.fgMuted,
            "--stig-border": colors.border,
            "--stig-accent": colors.accent,
            "--stig-focus": colors.focus,
            "--stig-row-hover": colors.rowHover,
            "--stig-row-selected": colors.rowSelected,
        },
    };
}

/** Tokyo Night (default) — https://github.com/tokyo-night/tokyo-night-vscode-theme */
export const TOKYO_NIGHT = palette("tokyo_night", "Tokyo Night", "dark", {
    bgPage: "#1a1b26",
    bgSection: "#16161e",
    bgElevated: "#24283b",
    bgInput: "#1f2335",
    fg: "#c0caf5",
    fgMuted: "#565f89",
    border: "#292e42",
    accent: "#7aa2f7",
    focus: "#7aa2f7",
    rowHover: "rgba(122, 162, 247, 0.08)",
    rowSelected: "rgba(122, 162, 247, 0.16)",
});

/** Catppuccin Mocha — https://github.com/catppuccin/catppuccin */
export const CATPPUCCIN = palette("catppuccin", "Catppuccin Mocha", "dark", {
    bgPage: "#1e1e2e",
    bgSection: "#181825",
    bgElevated: "#313244",
    bgInput: "#313244",
    fg: "#cdd6f4",
    fgMuted: "#a6adc8",
    border: "#45475a",
    accent: "#89b4fa",
    focus: "#89b4fa",
    rowHover: "rgba(137, 180, 250, 0.1)",
    rowSelected: "rgba(137, 180, 250, 0.18)",
});

/** Rosé Pine — https://rosepinetheme.com/ */
export const ROSE_PINE = palette("rose_pine", "Rosé Pine", "dark", {
    bgPage: "#191724",
    bgSection: "#1f1d2e",
    bgElevated: "#26233a",
    bgInput: "#26233a",
    fg: "#e0def4",
    fgMuted: "#908caa",
    border: "#403d52",
    accent: "#c4a7e7",
    focus: "#c4a7e7",
    rowHover: "rgba(196, 167, 231, 0.1)",
    rowSelected: "rgba(196, 167, 231, 0.18)",
});

export const LIGHT_SPLUNK = palette("light", "Light (Splunk Prisma)", "light", {
    bgPage: "#ffffff",
    bgSection: "#f7f8fa",
    bgElevated: "#ffffff",
    bgInput: "#ffffff",
    fg: "#171d21",
    fgMuted: "#5c6773",
    border: "#d5dde3",
    accent: "#006d9c",
    focus: "#006d9c",
    rowHover: "rgba(0, 109, 156, 0.06)",
    rowSelected: "rgba(0, 109, 156, 0.12)",
});

const PRESET_MAP = {
    tokyo_night: TOKYO_NIGHT,
    catppuccin: CATPPUCCIN,
    rose_pine: ROSE_PINE,
    light: LIGHT_SPLUNK,
};

export function getBuiltinPreset(id) {
    const key = String(id || "").toLowerCase();
    return PRESET_MAP[key] || TOKYO_NIGHT;
}

/** In-app theme picker (editor toolbar). Custom JSON still lives under Workspaces → Editor & ingest. */
export const EDITOR_THEME_CHOICES = [
    { value: "tokyo_night", label: "Tokyo Night" },
    { value: "catppuccin", label: "Catppuccin Mocha" },
    { value: "rose_pine", label: "Rosé Pine" },
    { value: "light", label: "Light" },
    { value: "follow_splunk", label: "Follow Splunk" },
    { value: "custom", label: "Custom (JSON in Workspaces)" },
];

export const COLOR_KEY_MAP = {
    bgPage: "--stig-bg-page",
    bgSection: "--stig-bg-section",
    bgElevated: "--stig-bg-elevated",
    bgInput: "--stig-bg-input",
    fg: "--stig-fg",
    fgMuted: "--stig-fg-muted",
    border: "--stig-border",
    accent: "--stig-accent",
    focus: "--stig-focus",
    rowHover: "--stig-row-hover",
    rowSelected: "--stig-row-selected",
};
