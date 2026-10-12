import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import { apiGet } from "../api";
import ConfigurationStepper from "../components/ConfigurationStepper";
import BaselinesStep from "../components/configuration/BaselinesStep";
import HostsStep from "../components/configuration/HostsStep";
import RmfPackagesStep from "../components/configuration/RmfPackagesStep";
import WorkspacesStep from "../components/configuration/WorkspacesStep";
import WizardNav from "../components/configuration/WizardNav";
import { CONFIGURATION_STEPS } from "../configurationSteps";
import { useGovernanceStep } from "../hooks/useGovernanceStep";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";

export default function ConfigurationApp() {
    const [canAdmin, setCanAdmin] = useState(null);
    const [canWrite, setCanWrite] = useState(null);
    const { stepId, goToStep, goNext, goBack, isFirst, isLast } = useGovernanceStep();

    useEffect(() => {
        apiGet("stig_readiness")
            .then((report) => {
                if (report && typeof report.can_stig_admin === "boolean") {
                    setCanAdmin(report.can_stig_admin);
                } else {
                    setCanAdmin(false);
                }
                if (report && typeof report.can_stig_write === "boolean") {
                    setCanWrite(report.can_stig_write);
                } else {
                    setCanWrite(false);
                }
            })
            .catch(() => {
                setCanAdmin(false);
                setCanWrite(false);
            });
    }, []);

    const stepContent = useMemo(() => {
        switch (stepId) {
            case "rmf_packages":
                return <RmfPackagesStep canAdmin={canAdmin} />;
            case "workspaces":
                return (
                    <WorkspacesStep canWrite={canWrite} canAdmin={canAdmin} />
                );
            case "hosts":
                return <HostsStep canWrite={canWrite} canAdmin={canAdmin} />;
            case "stig_baselines":
                return (
                    <BaselinesStep canWrite={canWrite} canAdmin={canAdmin} />
                );
            default:
                return null;
        }
    }, [stepId, canAdmin, canWrite]);

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>Admin</BrandKicker>
                    <Heading level={1}>Governance</Heading>
                </Brand>
                <Toolbar>
                    <Button
                        label="Refresh"
                        onClick={() => window.location.reload()}
                    />
                </Toolbar>
            </Header>
            <PagePad>
                <ConfigurationStepper
                    steps={CONFIGURATION_STEPS}
                    currentStepId={stepId}
                    onStepSelect={goToStep}
                />
                {stepContent}
                <WizardNav
                    isFirst={isFirst}
                    isLast={isLast}
                    onBack={goBack}
                    onNext={goNext}
                />
            </PagePad>
        </Shell>
    );
}
