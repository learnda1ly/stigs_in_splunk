import React from "react";
import { createRoot } from "react-dom/client";
import { SplunkThemeProvider, getUserTheme } from "@splunk/themes";

function hideSplunkChrome() {
    document.body.classList.add("stig-ui-page");
    if (document.querySelector("style[data-stig-ui-chrome]")) {
        return;
    }
    const style = document.createElement("style");
    style.setAttribute("data-stig-ui-chrome", "true");
    style.textContent = `
      html:has(#stig-ui-root), body:has(#stig-ui-root) {
        overflow: hidden !important;
        height: 100%;
      }
      body:has(#stig-ui-root) .dashboard-header,
      body:has(#stig-ui-root) .dashboard-view-controls,
      body:has(#stig-ui-root) .splunk-view-controls {
        display: none !important;
      }
      body:has(#stig-ui-root) .main-section-body.dashboard-body,
      body:has(#stig-ui-root) #dashboard1,
      body:has(#stig-ui-root) #layout1,
      body:has(#stig-ui-root) #row1,
      body:has(#stig-ui-root) .dashboard-panel,
      body:has(#stig-ui-root) .panel-element-row,
      body:has(#stig-ui-root) .panel-body.html,
      body:has(#stig-ui-root) .dashboard-cell,
      body:has(#stig-ui-root) .fieldset {
        height: 100% !important;
        max-height: 100% !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
      }
      #stig-ui-root {
        height: calc(100vh - 48px);
        min-height: 0;
      }
    `;
    document.head.appendChild(style);
}

const FALLBACK = {
    family: "prisma",
    colorScheme: "light",
    density: "comfortable",
};

export function mountPage(App) {
    const start = () => {
        const el = document.getElementById("stig-ui-root");
        if (!el) {
            requestAnimationFrame(start);
            return;
        }
        hideSplunkChrome();
        const render = (theme) => {
            const root = createRoot(el);
            root.render(
                <SplunkThemeProvider
                    family={theme.family || "prisma"}
                    colorScheme={theme.colorScheme || "light"}
                    density={theme.density || "comfortable"}
                >
                    <App />
                </SplunkThemeProvider>
            );
        };
        if (typeof getUserTheme === "function") {
            Promise.resolve(getUserTheme())
                .then(render)
                .catch(() => render(FALLBACK));
            return;
        }
        render(FALLBACK);
    };
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
}
