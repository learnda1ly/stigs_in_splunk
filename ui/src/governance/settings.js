import { useEffect, useState } from "react";
import { apiFetch, unwrap } from "../api";

const GOVERNANCE_NAV_VIEWS = [
    "stig_collection_review_ui",
    "stig_review_requirements_ui",
];

let cachedGovernanceEnabled = null;

function parseGovernanceEnabled(raw) {
    if (raw === undefined || raw === null || raw === "") {
        return true;
    }
    if (typeof raw === "boolean") {
        return raw;
    }
    if (typeof raw === "number") {
        return raw !== 0;
    }
    const text = String(raw).trim().toLowerCase();
    if (text === "0" || text === "false" || text === "no") {
        return false;
    }
    return true;
}

export async function fetchGovernanceEnabled() {
    if (cachedGovernanceEnabled !== null) {
        return cachedGovernanceEnabled;
    }
    try {
        const data = unwrap(await apiFetch("stig_settings"));
        cachedGovernanceEnabled = parseGovernanceEnabled(
            data && data.governance_enabled
        );
    } catch (e) {
        cachedGovernanceEnabled = true;
    }
    return cachedGovernanceEnabled;
}

export function useGovernanceEnabled() {
    const [enabled, setEnabled] = useState(null);
    useEffect(() => {
        fetchGovernanceEnabled().then(setEnabled);
    }, []);
    return enabled !== false;
}

export function hideGovernanceNavEntries() {
    fetchGovernanceEnabled().then((enabled) => {
        if (enabled) {
            return;
        }
        GOVERNANCE_NAV_VIEWS.forEach((view) => {
            document.querySelectorAll(`a[href*="${view}"]`).forEach((anchor) => {
                const item = anchor.closest("li");
                if (item) {
                    item.style.display = "none";
                }
            });
        });
    });
}
