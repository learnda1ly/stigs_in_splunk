import React from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Text from "@splunk/react-ui/Text";
import Link from "@splunk/react-ui/Link";
import { viewUrl } from "../../api";

export default function EditorAssignCallout({
    busy,
    allBaselines,
    assignBaselineId,
    setAssignBaselineId,
    assignStigId,
    setAssignStigId,
    onAssign,
}) {
    const importUrl = viewUrl("stig_import_ui") + "#baselines";

    return (
        <Message appearance="info" style={{ marginBottom: 16 }}>
            <p style={{ marginTop: 0 }}>
                This host has no checklist yet. Assign a STIG baseline so there are findings to
                review.
            </p>
            {!allBaselines.length ? (
                <p style={{ marginBottom: 12 }}>
                    Import baselines first on the{" "}
                    <Link to={importUrl}>Import</Link> page.
                </p>
            ) : null}
            <ControlGroup label="Assign STIG" labelPosition="top">
                <Select
                    value={assignBaselineId}
                    onChange={(e, { value }) => {
                        setAssignBaselineId(value);
                        if (value) {
                            setAssignStigId("");
                        }
                    }}
                    placeholder="Baseline revision"
                    filter
                    disabled={busy || !allBaselines.length}
                >
                    {allBaselines.map((b) => (
                        <Select.Option
                            key={b._key}
                            label={
                                (b.stig_id || b.title || b._key) +
                                (b.version ? " " + b.version : "")
                            }
                            value={b._key}
                        />
                    ))}
                </Select>
                <Text
                    value={assignStigId}
                    onChange={(e, { value }) => {
                        setAssignStigId(value);
                        if (value) {
                            setAssignBaselineId("");
                        }
                    }}
                    disabled={busy}
                    placeholder="Or stig_id (uses workspace default)"
                />
                <Button
                    appearance="primary"
                    disabled={busy || (!assignBaselineId && !assignStigId.trim())}
                    onClick={onAssign}
                    label="Assign to host"
                />
            </ControlGroup>
        </Message>
    );
}
