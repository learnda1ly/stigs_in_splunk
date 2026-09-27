import { useEffect, useState } from "react";

function localePrefix() {
    const path = window.location.pathname || "";
    const match = path.match(/^(\/[^/]+)\//);
    return match ? match[1] : "/en-US";
}

function normalizeCapabilities(raw) {
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        const out = {};
        Object.keys(raw).forEach((key) => {
            out[key] = !!raw[key];
        });
        return out;
    }
    if (Array.isArray(raw)) {
        const out = {};
        raw.forEach((item) => {
            const key = String(item || "").trim();
            if (key) {
                out[key] = true;
            }
        });
        return out;
    }
    return {};
}

/**
 * Splunk current-context capabilities (no app REST endpoint).
 * @returns {Record<string, boolean>|null} null while loading
 */
export function useSessionCapabilities() {
    const [capabilities, setCapabilities] = useState(null);

    useEffect(() => {
        const url =
            localePrefix() +
            "/splunkd/__raw/services/authentication/current-context?output_mode=json";
        fetch(url, {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then((res) => res.json())
            .then((data) => {
                const entry = data && data.entry && data.entry[0];
                const content = (entry && entry.content) || data || {};
                setCapabilities(normalizeCapabilities(content.capabilities));
            })
            .catch(() => setCapabilities({}));
    }, []);

    return capabilities;
}

export function sessionMissingGrantCapabilities(capabilities) {
    if (!capabilities || typeof capabilities !== "object") {
        return false;
    }
    if (capabilities.stig_admin) {
        return false;
    }
    return !capabilities.stig_write;
}
