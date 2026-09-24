export const STIG_THEME_UPDATED = "stig-theme-updated";

export function notifyThemeUpdated(theme) {
    window.dispatchEvent(
        new CustomEvent(STIG_THEME_UPDATED, { detail: theme || null })
    );
}
