const STYLE_ID = "stig-ui-theme-vars";
const ROOT_ID = "stig-ui-root";

function applyCssVarsToElement(el, cssVars) {
    if (!el || !cssVars) {
        return;
    }
    Object.entries(cssVars).forEach(([name, value]) => {
        el.style.setProperty(name, value);
    });
}

export function applyPaletteToDocument(palette) {
    const scheme = palette.colorScheme === "light" ? "light" : "dark";
    const root = document.documentElement;
    root.dataset.stigTheme = palette.id || "tokyo_night";
    root.dataset.stigColorScheme = scheme;
    document.body.classList.toggle("stig-ui-dark", scheme === "dark");
    document.body.classList.toggle("stig-ui-light", scheme === "light");

    const cssVars = palette.cssVars || {};
    applyCssVarsToElement(root, cssVars);
    applyCssVarsToElement(document.getElementById(ROOT_ID), cssVars);

    let style = document.getElementById(STYLE_ID);
    if (!style) {
        style = document.createElement("style");
        style.id = STYLE_ID;
        document.head.appendChild(style);
    }

    const vars = Object.entries(cssVars)
        .map(([k, v]) => `  ${k}: ${v};`)
        .join("\n");

    style.textContent = `
      html[data-stig-theme],
      html[data-stig-theme] body,
      #${ROOT_ID} {
        ${vars}
        color-scheme: ${scheme};
      }
      html[data-stig-theme],
      html[data-stig-theme] body {
        background: var(--stig-bg-page) !important;
        color: var(--stig-fg);
      }
      #${ROOT_ID} {
        background: var(--stig-bg-page) !important;
        color: var(--stig-fg);
        min-height: 100%;
      }
      #stig-ui-root .stig-themed-shell {
        background: var(--stig-bg-page) !important;
        color: var(--stig-fg) !important;
      }
      #stig-ui-root .stig-themed-section {
        background: var(--stig-bg-section) !important;
        color: var(--stig-fg) !important;
        border-color: var(--stig-border) !important;
      }
      #stig-ui-root .stig-themed-detail {
        background: var(--stig-bg-page) !important;
        color: var(--stig-fg) !important;
      }
      #stig-ui-root .stig-themed-shell,
      #stig-ui-root .stig-themed-section {
        background: var(--stig-bg-section);
        color: var(--stig-fg);
        border-color: var(--stig-border);
      }
      #stig-ui-root .stig-themed-elevated {
        background: var(--stig-bg-elevated);
        color: var(--stig-fg);
        border-color: var(--stig-border);
      }
      #stig-ui-root .stig-vim-area,
      #stig-ui-root textarea.stig-vim-area {
        background-color: var(--stig-bg-input) !important;
        color: var(--stig-fg) !important;
        border-color: var(--stig-border) !important;
        caret-color: var(--stig-fg);
      }
      #stig-ui-root [data-test="textbox"] textarea,
      #stig-ui-root [data-test="textbox"] input,
      #stig-ui-root [data-test="multiline"] textarea {
        background-color: var(--stig-bg-input) !important;
        color: var(--stig-fg) !important;
        caret-color: var(--stig-fg);
      }
      #stig-ui-root [data-test="textbox"],
      #stig-ui-root [data-test="multiline"] {
        background-color: var(--stig-bg-input) !important;
        border-color: var(--stig-border) !important;
        color: var(--stig-fg) !important;
      }
      #stig-ui-root [data-test="search"] input {
        color: var(--stig-fg) !important;
      }
      #stig-ui-root pre,
      #stig-ui-root .stig-pre-block {
        background: var(--stig-bg-elevated);
        color: var(--stig-fg);
        border: 1px solid var(--stig-border);
      }
    `;
}
