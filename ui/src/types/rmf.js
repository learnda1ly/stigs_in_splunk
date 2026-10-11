/** RMF package types and resolution (shared across Governance wizard and Hosts). */

export const RMF_SYSTEM_PACKAGE_ID = "-1";
export const RMF_SYSTEM_PACKAGE_NAME = "unassigned";

/** @typedef {{ _key: string, name?: string, is_system?: boolean }} RmfPackage */

/** @typedef {{ hostname?: string, _key?: string, package_id?: string }} RmfHostDefault */

/** @typedef {{ hostname?: string, baseline_ref?: string, package_id?: string }} RmfBaselineOverride */

/** @typedef {{ package_id: string, source: 'override'|'host default'|'unassigned' }} RmfResolution */

export function normalizeHostname(value) {
    return String(value || "").trim().toLowerCase();
}

/**
 * Effective RMF package for a host (+ optional baseline override key).
 * Matches server resolution in services/rmf_packages.py.
 *
 * @param {string} hostname
 * @param {string} baselineRef
 * @param {RmfHostDefault[]} defaults
 * @param {RmfBaselineOverride[]} overrides
 * @returns {RmfResolution}
 */
export function resolveRmfPackage(hostname, baselineRef, defaults, overrides) {
    const hostKey = normalizeHostname(hostname);
    if (!hostKey) {
        return { package_id: RMF_SYSTEM_PACKAGE_ID, source: "unassigned" };
    }
    const bref = String(baselineRef || "").trim();
    if (bref) {
        const match = (overrides || []).find(
            (row) =>
                normalizeHostname(row.hostname) === hostKey &&
                String(row.baseline_ref || "")
                    .trim()
                    .toLowerCase() === bref.toLowerCase()
        );
        if (match && match.package_id) {
            return { package_id: String(match.package_id), source: "override" };
        }
    }
    const def = (defaults || []).find(
        (row) =>
            normalizeHostname(row.hostname) === hostKey ||
            normalizeHostname(row._key) === hostKey
    );
    if (def && def.package_id) {
        return { package_id: String(def.package_id), source: "host default" };
    }
    return { package_id: RMF_SYSTEM_PACKAGE_ID, source: "unassigned" };
}

export function packageLabel(packages, id) {
    const row = (packages || []).find((p) => p._key === id);
    if (!row) {
        if (id === RMF_SYSTEM_PACKAGE_ID) {
            return RMF_SYSTEM_PACKAGE_NAME + " (" + id + ")";
        }
        return id || "—";
    }
    const name = (row.name || "").trim();
    return name ? name + " (" + id + ")" : id;
}

export function sortPackages(rows) {
    return [...(rows || [])].sort((a, b) => {
        const aSys = a.is_system ? 0 : 1;
        const bSys = b.is_system ? 0 : 1;
        if (aSys !== bSys) {
            return aSys - bSys;
        }
        return String(a._key || "").localeCompare(String(b._key || ""), undefined, {
            numeric: true,
        });
    });
}
