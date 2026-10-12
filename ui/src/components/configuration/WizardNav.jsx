import React from "react";
import Button from "@splunk/react-ui/Button";
import styled from "styled-components";

const Bar = styled.div`
    display: flex;
    gap: 12px;
    margin-top: 24px;
    justify-content: flex-end;
`;

export default function WizardNav({ isFirst, isLast, onBack, onNext }) {
    return (
        <Bar>
            <Button label="Back" disabled={isFirst} onClick={onBack} />
            <Button
                appearance="primary"
                label={isLast ? "Done" : "Next"}
                onClick={onNext}
            />
        </Bar>
    );
}
