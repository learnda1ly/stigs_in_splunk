import { useCallback, useMemo, useState } from "react";
import { CONFIGURATION_STEPS } from "../configurationSteps";

function stepFromLocation() {
    const params = new URLSearchParams(window.location.search || "");
    const raw = (params.get("step") || "").trim();
    if (CONFIGURATION_STEPS.some((s) => s.id === raw)) {
        return raw;
    }
    return CONFIGURATION_STEPS[0].id;
}

export function useGovernanceStep() {
    const [stepId, setStepId] = useState(stepFromLocation);

    const stepIndex = useMemo(
        () => CONFIGURATION_STEPS.findIndex((s) => s.id === stepId),
        [stepId]
    );

    const goToStep = useCallback((id) => {
        if (!CONFIGURATION_STEPS.some((s) => s.id === id)) {
            return;
        }
        setStepId(id);
        const url = new URL(window.location.href);
        url.searchParams.set("step", id);
        window.history.replaceState({}, "", url.toString());
    }, []);

    const goNext = useCallback(() => {
        const idx = CONFIGURATION_STEPS.findIndex((s) => s.id === stepId);
        if (idx >= 0 && idx < CONFIGURATION_STEPS.length - 1) {
            goToStep(CONFIGURATION_STEPS[idx + 1].id);
        }
    }, [goToStep, stepId]);

    const goBack = useCallback(() => {
        const idx = CONFIGURATION_STEPS.findIndex((s) => s.id === stepId);
        if (idx > 0) {
            goToStep(CONFIGURATION_STEPS[idx - 1].id);
        }
    }, [goToStep, stepId]);

    return {
        stepId,
        stepIndex,
        goToStep,
        goNext,
        goBack,
        isFirst: stepIndex <= 0,
        isLast: stepIndex >= CONFIGURATION_STEPS.length - 1,
    };
}
