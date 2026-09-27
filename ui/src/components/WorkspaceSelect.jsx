import React from "react";
import Select from "@splunk/react-ui/Select";
import {
    WORKSPACE_ALL,
    workspaceLabel,
    workspacesOfferAllChoice,
} from "../api";

export default function WorkspaceSelect({
    workspaces,
    value,
    onChange,
    allLabel = "All workspaces",
    includeAll = true,
    ...selectProps
}) {
    const rows = Array.isArray(workspaces) ? workspaces : [];
    const showAll = includeAll && workspacesOfferAllChoice(rows);

    return (
        <Select value={value} onChange={onChange} {...selectProps}>
            {showAll ? (
                <Select.Option label={allLabel} value={WORKSPACE_ALL} />
            ) : null}
            {rows.map((ws) => (
                <Select.Option
                    key={ws._key}
                    label={workspaceLabel(ws)}
                    value={ws._key}
                />
            ))}
        </Select>
    );
}
