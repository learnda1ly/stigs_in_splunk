import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Text from "@splunk/react-ui/Text";
import {
    apiFetch,
    apiGet,
    apiPatch,
    isAllWorkspaces,
    viewUrl,
    workspaceLabel,
    workspaceScopeQuery,
} from "../api";

function baselineOptionLabel(b) {
    return (
        (b.stig_id || b.title || b._key) + (b.version ? " " + b.version : "")
    );
}

export default function HostSetupPanel({
    host,
    collectionId,
    workspaces,
    onClose,
    onChanged,
}) {
    const [baselines, setBaselines] = useState([]);
    const [checklists, setChecklists] = useState([]);
    const [busy, setBusy] = useState(false);
    const [banner, setBanner] = useState(null);
    const [assignBaselineId, setAssignBaselineId] = useState("");
    const [assignStigId, setAssignStigId] = useState("");
    const [upgradeChecklistId, setUpgradeChecklistId] = useState("");
    const [upgradeBaselineId, setUpgradeBaselineId] = useState("");
    const [moveTo, setMoveTo] = useState("");

    const hostId = host && host._key;
    const hostLabel = (host && host.hostname) || hostId || "host";

    useEffect(() => {
        if (!hostId || !collectionId || isAllWorkspaces(collectionId)) {
            setChecklists([]);
            return;
        }
        apiGet("stig_checklists", workspaceScopeQuery(collectionId))
            .then((rows) => {
                const list = Array.isArray(rows) ? rows : [];
                setChecklists(list.filter((cl) => cl.host_id === hostId));
            })
            .catch(() => setChecklists([]));
    }, [hostId, collectionId]);

    useEffect(() => {
        apiGet("stig_baselines")
            .then((rows) => setBaselines(Array.isArray(rows) ? rows : []))
            .catch(() => setBaselines([]));
    }, []);

    const hostChecklists = checklists;

    const activeUpgradeChecklist = useMemo(() => {
        if (!hostChecklists.length) {
            return null;
        }
        if (upgradeChecklistId) {
            return hostChecklists.find((cl) => cl._key === upgradeChecklistId) || hostChecklists[0];
        }
        return hostChecklists[0];
    }, [hostChecklists, upgradeChecklistId]);

    const upgradeBaselineOptions = useMemo(() => {
        if (!activeUpgradeChecklist || !baselines.length) {
            return [];
        }
        const current = baselines.find((b) => b._key === activeUpgradeChecklist.baseline_id);
        const stigId = (current && current.stig_id) || activeUpgradeChecklist.stig_id;
        if (!stigId) {
            return [];
        }
        const sameStig = baselines.filter((b) => b.stig_id === stigId);
        if (!current) {
            return sameStig;
        }
        const curVer = String(current.version || "");
        return sameStig.filter((b) => String(b.version || "") > curVer);
    }, [activeUpgradeChecklist, baselines]);

    const assignStig = () => {
        if (!hostId) {
            return;
        }
        const body = assignBaselineId
            ? { baseline_id: assignBaselineId }
            : { stig_id: assignStigId.trim() };
        setBusy(true);
        setBanner(null);
        apiFetch("stig_hosts/" + hostId + "/stigs", { method: "POST", body })
            .then((doc) => {
                setBanner({
                    type: "success",
                    text: doc.created
                        ? "Assigned STIG and created checklist."
                        : "STIG already assigned (existing checklist).",
                });
                if (onChanged) {
                    onChanged();
                }
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Assign failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const upgradeChecklist = () => {
        const cl = activeUpgradeChecklist;
        if (!cl || !upgradeBaselineId) {
            return;
        }
        setBusy(true);
        apiFetch("stig_checklists/" + cl._key + "/upgrade", {
            method: "POST",
            body: { baseline_id: upgradeBaselineId },
        })
            .then((result) => {
                setBanner({
                    type: "success",
                    text:
                        "Upgraded checklist: " +
                        (result.merged || 0) +
                        " merged, " +
                        (result.reset || 0) +
                        " reset.",
                });
                if (onChanged) {
                    onChanged();
                }
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Upgrade failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const moveHost = () => {
        if (!hostId || !moveTo) {
            return;
        }
        setBusy(true);
        apiPatch("stig_hosts/" + hostId, { stig_collection_id: moveTo })
            .then(() => {
                setBanner({
                    type: "success",
                    text:
                        "Moved host to " +
                        workspaceLabel(
                            workspaces.find((c) => c._key === moveTo) || { name: moveTo }
                        ) +
                        ".",
                });
                if (onChanged) {
                    onChanged(moveTo);
                }
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Move failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    if (!host) {
        return null;
    }

    return (
        <div
            style={{
                marginTop: 24,
                padding: 16,
                border: "1px solid var(--splunk-color-border, #ccc)",
                borderRadius: 8,
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 12,
                }}
            >
                <Heading level={4} style={{ margin: 0 }}>
                    Host setup — {hostLabel}
                </Heading>
                <Button appearance="secondary" onClick={onClose} label="Close" />
            </div>
            {banner ? (
                <Message appearance={banner.type} style={{ marginBottom: 12 }}>
                    {banner.text}
                </Message>
            ) : null}
            <p style={{ fontSize: 13, marginTop: 0 }}>
                Assign STIGs, upgrade checklist revisions, or move this host to another workspace.
                Import new baseline revisions from the{" "}
                <Link to={viewUrl("stig_library_ui")}>STIG library</Link> (Add revisions).
            </p>
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
                    disabled={busy || !baselines.length}
                >
                    {baselines.map((b) => (
                        <Select.Option
                            key={b._key}
                            label={baselineOptionLabel(b)}
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
                    onClick={assignStig}
                    label="Assign to host"
                />
            </ControlGroup>
            {hostChecklists.length ? (
                <div style={{ marginTop: 16 }}>
                    <ControlGroup label="Upgrade revision" labelPosition="top">
                        {hostChecklists.length > 1 ? (
                            <Select
                                value={upgradeChecklistId || activeUpgradeChecklist._key}
                                onChange={(e, { value }) => setUpgradeChecklistId(value)}
                                filter
                                disabled={busy}
                            >
                                {hostChecklists.map((cl) => (
                                    <Select.Option
                                        key={cl._key}
                                        label={cl.title || cl._key}
                                        value={cl._key}
                                    />
                                ))}
                            </Select>
                        ) : null}
                        <Select
                            value={upgradeBaselineId}
                            onChange={(e, { value }) => setUpgradeBaselineId(value)}
                            placeholder={
                                upgradeBaselineOptions.length
                                    ? "Newer baseline"
                                    : "Import newer revision in STIG library"
                            }
                            filter
                            disabled={busy || !upgradeBaselineOptions.length}
                        >
                            {upgradeBaselineOptions.map((b) => (
                                <Select.Option
                                    key={b._key}
                                    label={baselineOptionLabel(b)}
                                    value={b._key}
                                />
                            ))}
                        </Select>
                        <Button
                            appearance="secondary"
                            disabled={busy || !upgradeBaselineId}
                            onClick={upgradeChecklist}
                            label="Upgrade checklist"
                        />
                    </ControlGroup>
                </div>
            ) : null}
            <div style={{ marginTop: 16 }}>
                <ControlGroup label="Move host" labelPosition="top">
                    <Select
                        value={moveTo}
                        onChange={(e, { value }) => setMoveTo(value)}
                        placeholder="Another workspace"
                        filter
                        disabled={busy}
                    >
                        {workspaces
                            .filter((c) => c._key !== collectionId)
                            .map((c) => (
                                <Select.Option
                                    key={c._key}
                                    label={workspaceLabel(c)}
                                    value={c._key}
                                />
                            ))}
                    </Select>
                    <Button
                        appearance="secondary"
                        disabled={busy || !moveTo}
                        onClick={moveHost}
                        label="Move host"
                    />
                </ControlGroup>
            </div>
        </div>
    );
}
