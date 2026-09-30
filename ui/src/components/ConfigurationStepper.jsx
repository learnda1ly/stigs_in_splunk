import React from "react";
import styled from "styled-components";
import { variables } from "@splunk/themes";

const Track = styled.nav`
    display: flex;
    align-items: flex-start;
    gap: 0;
    margin: 0 0 24px;
    padding: 0;
    list-style: none;
    flex-wrap: wrap;
`;

const StepItem = styled.li`
    display: flex;
    align-items: center;
    flex: ${(props) => (props.$stretch ? "1 1 0" : "0 0 auto")};
    min-width: 0;
`;

const Node = styled.div`
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-width: 120px;
    max-width: 200px;
    text-align: center;
`;

const Dot = styled.span`
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    border: 2px solid
        ${(props) =>
            props.$active
                ? "var(--stig-accent, " + variables.interactiveColorPrimary + ")"
                : "var(--stig-border, " + variables.borderColor + ")"};
    background: ${(props) =>
        props.$active
            ? "var(--stig-accent, " + variables.interactiveColorPrimary + ")"
            : "var(--stig-bg-section, " + variables.backgroundColorSection + ")"};
    color: ${(props) =>
        props.$active
            ? variables.white
            : "var(--stig-fg-muted, " + variables.contentColorMuted + ")"};
`;

const Label = styled.span`
    font-size: 13px;
    font-weight: ${(props) => (props.$active ? 600 : 500)};
    color: ${(props) =>
        props.$active
            ? "var(--stig-fg, " + variables.contentColorDefault + ")"
            : "var(--stig-fg-muted, " + variables.contentColorMuted + ")"};
    line-height: 1.3;
`;

const Connector = styled.div`
    flex: 1 1 24px;
    height: 2px;
    min-width: 16px;
    margin: 13px 8px 0;
    background: var(--stig-border, ${variables.borderColor});
    opacity: ${(props) => (props.$dimmed ? 0.45 : 1)};
`;

export default function ConfigurationStepper({ steps, currentStepId }) {
    const currentIndex = steps.findIndex((s) => s.id === currentStepId);
    const safeIndex = currentIndex >= 0 ? currentIndex : 0;

    return (
        <Track aria-label="Configuration progress">
            {steps.map((step, index) => {
                const active = index === safeIndex;
                const showConnector = index < steps.length - 1;
                return (
                    <React.Fragment key={step.id}>
                        <StepItem>
                            <Node>
                                <Dot $active={active} aria-current={active ? "step" : undefined}>
                                    {index + 1}
                                </Dot>
                                <Label $active={active}>{step.title}</Label>
                            </Node>
                        </StepItem>
                        {showConnector ? (
                            <StepItem $stretch>
                                <Connector $dimmed={index >= safeIndex} aria-hidden="true" />
                            </StepItem>
                        ) : null}
                    </React.Fragment>
                );
            })}
        </Track>
    );
}
