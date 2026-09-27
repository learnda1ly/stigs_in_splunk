import { useEffect, useState } from "react";
import { apiGet } from "../../api";

/**
 * Whether the signed-in user can edit findings (server-side access rules).
 * @returns {boolean|null} null while loading or if the probe failed
 */
export function useSessionCapabilities() {
    const [canStigWrite, setCanStigWrite] = useState(null);

    useEffect(() => {
        let cancelled = false;
        apiGet("stig_readiness")
            .then((report) => {
                if (cancelled) {
                    return;
                }
                if (report && typeof report.can_stig_write === "boolean") {
                    setCanStigWrite(report.can_stig_write);
                    return;
                }
                setCanStigWrite(null);
            })
            .catch(() => {
                if (!cancelled) {
                    setCanStigWrite(null);
                }
            });
        return () => {
            cancelled = true;
        };
    }, []);

    return canStigWrite;
}

/** @param {boolean|null} canStigWrite from useSessionCapabilities */
export function sessionMissingGrantCapabilities(canStigWrite) {
    if (canStigWrite !== true && canStigWrite !== false) {
        return false;
    }
    return !canStigWrite;
}
