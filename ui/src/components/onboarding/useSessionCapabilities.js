import { useEffect, useState } from "react";
import { apiGet } from "../../api";

/**
 * Whether the signed-in user can edit findings (server-side access rules).
 * @returns {boolean|null} null while loading or if the probe failed
 */
export function useSessionCapabilities() {
    const [caps, setCaps] = useState({ canStigWrite: null, canStigAdmin: null });

    useEffect(() => {
        let cancelled = false;
        apiGet("stig_readiness")
            .then((report) => {
                if (cancelled) {
                    return;
                }
                setCaps({
                    canStigWrite:
                        report && typeof report.can_stig_write === "boolean"
                            ? report.can_stig_write
                            : null,
                    canStigAdmin:
                        report && typeof report.can_stig_admin === "boolean"
                            ? report.can_stig_admin
                            : null,
                });
            })
            .catch(() => {
                if (!cancelled) {
                    setCaps({ canStigWrite: null, canStigAdmin: null });
                }
            });
        return () => {
            cancelled = true;
        };
    }, []);

    return caps;
}

/** @returns {boolean|null} */
export function useCanStigWrite() {
    return useSessionCapabilities().canStigWrite;
}

/** @returns {boolean|null} */
export function useCanStigAdmin() {
    return useSessionCapabilities().canStigAdmin;
}

/** @param {boolean|null} canStigWrite from useCanStigWrite or useSessionCapabilities */
export function sessionMissingGrantCapabilities(canStigWrite) {
    if (canStigWrite !== true && canStigWrite !== false) {
        return false;
    }
    return !canStigWrite;
}
