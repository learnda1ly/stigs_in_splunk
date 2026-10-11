import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import { apiGet } from "../api";
import ConfigurationStepper from "../components/ConfigurationStepper";
import RmfPackagesStep from "../components/configuration/RmfPackagesStep";
import { CONFIGURATION_STEPS } from "../configurationSteps";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";

const CURRENT_STEP_ID = CONFIGURATION_STEPS[0].id;

export default function ConfigurationApp() {
    const [canAdmin, setCanAdmin] = useState(null);

    useEffect(() => {
        apiGet("stig_readiness")
            .then((report) => {
                if (report && typeof report.can_stig_admin === "boolean") {
                    setCanAdmin(report.can_stig_admin);
                } else {
                    setCanAdmin(false);
                }
            })
            .catch(() => setCanAdmin(false));
    }, []);

    const stepContent = useMemo(() => {
        if (CURRENT_STEP_ID === "rmf_packages") {
            return <RmfPackagesStep canAdmin={canAdmin} />;
        }
        return null;
    }, [canAdmin]);

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
                    currentStepId={CURRENT_STEP_ID}
                />
                {stepContent}
            </PagePad>
        </Shell>
    );
}
