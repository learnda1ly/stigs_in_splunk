import React from "react";
import { createRoot } from "react-dom/client";
import ThemeRoot from "./ThemeRoot";

function ensureSkipLink() {
    if (document.getElementById("stig-skip-link")) {
        return;
    }
    const link = document.createElement("a");
    link.id = "stig-skip-link";
    link.href = "#stig-main-content";
    link.textContent = "Skip to main content";
    link.className = "stig-skip-link";
    document.body.insertBefore(link, document.body.firstChild);
}

function hideSplunkChrome() {
    document.body.classList.add("stig-ui-page");
    ensureSkipLink();
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
      .stig-skip-link {
        position: absolute;
        left: -9999px;
        top: auto;
        width: 1px;
        height: 1px;
        overflow: hidden;
        z-index: 10000;
        padding: 12px 16px;
        background: #111;
        color: #fff;
        font: inherit;
        text-decoration: none;
        border-radius: 4px;
      }
      .stig-skip-link:focus {
        left: 12px;
        top: 12px;
        width: auto;
        height: auto;
        overflow: visible;
        outline: 3px solid #4c9aff;
        outline-offset: 2px;
      }
      #stig-ui-root :focus-visible {
        outline: 2px solid #4c9aff;
        outline-offset: 2px;
      }
      #stig-ui-root .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      }
      @media (prefers-reduced-motion: reduce) {
        #stig-ui-root *,
        #stig-ui-root *::before,
        #stig-ui-root *::after {
          animation-duration: 0.01ms !important;
          animation-iteration-count: 1 !important;
          transition-duration: 0.01ms !important;
          scroll-behavior: auto !important;
        }
      }
      /* Dashboard bootstrap styles input[type=search|text] with its own
         border, background, height, and margin. SplunkUI Text/Search already
         draws that chrome on the outer box, so the inner input looks nested. */
      #stig-ui-root input[type="search"],
      #stig-ui-root input[type="text"],
      #stig-ui-root input[type="password"],
      #stig-ui-root input[type="email"],
      #stig-ui-root input[type="number"],
      #stig-ui-root input[type="tel"],
      #stig-ui-root input[type="url"],
      #stig-ui-root textarea {
        background-color: transparent;
        border: 0;
        border-radius: 0;
        box-shadow: none;
        box-sizing: border-box;
        height: auto;
        line-height: inherit;
        margin: 0;
        padding: 0;
      }
    `;
    document.head.appendChild(style);
}

export function mountPage(App) {
    const start = () => {
        const el = document.getElementById("stig-ui-root");
        if (!el) {
            requestAnimationFrame(start);
            return;
        }
        hideSplunkChrome();
        if (!el.getAttribute("role")) {
            el.setAttribute("role", "presentation");
        }
        const root = createRoot(el);
        root.render(
            <ThemeRoot>
                <App />
            </ThemeRoot>
        );
    };
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
}
