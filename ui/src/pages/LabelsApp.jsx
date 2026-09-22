import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, defaultWorkspaceId, workspaceLabel } from "../api";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";

function normalizeLabelIds(host) {
    const raw = host && host.label_ids;
    if (Array.isArray(raw)) {
        return raw.map(String);
    }
    if (typeof raw === "string" && raw.trim().charAt(0) === "[") {
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed.map(String) : [];
        } catch (e) {
            return [];
        }
    }
    return [];
}

export default function LabelsApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [labels, setLabels] = useState([]);
    const [hosts, setHosts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [warning, setWarning] = useState("");
    const [newName, setNewName] = useState("");
    const [newColor, setNewColor] = useState("");
    const [renameDraft, setRenameDraft] = useState({});
    const [selectedHostIds, setSelectedHostIds] = useState({});
    const [bulkLabelId, setBulkLabelId] = useState("");
    const [hostFilterLabelId, setHostFilterLabelId] = useState("");

    const labelById = useMemo(() => {
        const map = {};
        (labels || []).forEach((row) => {
            if (row && row._key) {
                map[row._key] = row;
            }
        });
        return map;
    }, [labels]);

    const loadWorkspaceData = useCallback(async (cid) => {
        if (!cid) {
            setLabels([]);
            setHosts([]);
            return;
        }
        const [lblRows, hostRows] = await Promise.all([
            apiGet("stig_collections/" + cid + "/labels"),
            apiGet("stig_hosts", { stig_collection_id: cid }),
        ]);
        setLabels(Array.isArray(lblRows) ? lblRows : []);
        setHosts(Array.isArray(hostRows) ? hostRows : []);
        setSelectedHostIds({});
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const colls = await apiGet("stig_collections");
            setWorkspaces(colls || []);
            const def = defaultWorkspaceId(colls);
            const cid = collectionId || def || "";
            if (!collectionId && cid) {
                setCollectionId(cid);
            }
            if (cid) {
                await loadWorkspaceData(cid);
            }
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, [collectionId, loadWorkspaceData]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (collectionId) {
            loadWorkspaceData(collectionId).catch((err) =>
                setError(String(err.message || err))
            );
        }
    }, [collectionId, loadWorkspaceData]);

    const filteredHosts = useMemo(() => {
        if (!hostFilterLabelId) {
            return hosts || [];
        }
        return (hosts || []).filter((h) =>
            normalizeLabelIds(h).includes(hostFilterLabelId)
        );
    }, [hosts, hostFilterLabelId]);

    const selectedIds = useMemo(
        () =>
            Object.keys(selectedHostIds).filter((id) => selectedHostIds[id]),
        [selectedHostIds]
    );

    const workspaceHostIds = useMemo(() => {
        const ids = new Set();
        (hosts || []).forEach((h) => {
            if (h && h._key) {
                ids.add(h._key);
            }
        });
        return ids;
    }, [hosts]);

    function clearMessages() {
        setError("");
        setInfo("");
        setWarning("");
    }

    async function createLabel() {
        clearMessages();
        const name = (newName || "").trim();
        if (!name) {
            setError("Label name cannot be empty.");
            return;
        }
        try {
            await apiFetch("stig_collections/" + collectionId + "/labels", {
                method: "POST",
                body: {
                    name,
                    color: (newColor || "").trim(),
                },
            });
            setNewName("");
            setNewColor("");
            setInfo("Label created.");
            await loadWorkspaceData(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function saveLabelName(labelId) {
        clearMessages();
        const name = (renameDraft[labelId] || "").trim();
        if (!name) {
            setError("Label name cannot be empty.");
            return;
        }
        try {
            await apiFetch(
                "stig_collections/" + collectionId + "/labels/" + labelId,
                {
                    method: "PATCH",
                    body: { name },
                }
            );
            setInfo("Label updated.");
            await loadWorkspaceData(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function removeLabel(labelId) {
        clearMessages();
        const row = labelById[labelId] || {};
        const displayName = (row.name || "").trim() || labelId;
        if (
            !window.confirm(
                'Delete label "' +
                    displayName +
                    '"? Host assignments for this label are removed.'
            )
        ) {
            return;
        }
        try {
            await apiFetch(
                "stig_collections/" + collectionId + "/labels/" + labelId,
                { method: "DELETE" }
            );
            setInfo(
                "Label deleted. Restricted grants no longer reference this label id."
            );
            await loadWorkspaceData(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function assignLabelToHosts(labelId, hostIds) {
        if (!labelId || !hostIds.length) {
            return;
        }
        await apiFetch(
            "stig_collections/" +
                collectionId +
                "/labels/" +
                labelId +
                "/assets",
            {
                method: "POST",
                body: { host_ids: hostIds },
            }
        );
    }

    async function setHostLabels(hostId, labelIds) {
        await apiFetch("stig_hosts/" + hostId, {
            method: "PATCH",
            body: { label_ids: labelIds },
        });
    }

    async function bulkAssign() {
        clearMessages();
        if (!bulkLabelId) {
            setError("Choose a label to assign.");
            return;
        }
        if (!selectedIds.length) {
            setError("Select at least one host.");
            return;
        }
        const requested = selectedIds.length;
        const skippedUnknown = selectedIds.filter(
            (id) => !workspaceHostIds.has(id)
        );
        try {
            const result = await apiFetch(
                "stig_collections/" +
                    collectionId +
                    "/labels/" +
                    bulkLabelId +
                    "/assets",
                {
                    method: "POST",
                    body: { host_ids: selectedIds },
                }
            );
            const updated = Number(
                result && result.updated_hosts != null ? result.updated_hosts : 0
            );
            await loadWorkspaceData(collectionId);
            if (updated < requested || skippedUnknown.length) {
                let msg =
                    "Assigned label to " +
                    updated +
                    " of " +
                    requested +
                    " selected host(s).";
                if (skippedUnknown.length) {
                    msg +=
                        " Skipped unknown host ids: " +
                        skippedUnknown.join(", ") +
                        ".";
                } else if (updated < requested) {
                    msg +=
                        " Remaining hosts already had this label or were not updated.";
                }
                setWarning(msg);
            } else {
                setInfo("Assigned label to " + updated + " host(s).");
            }
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function bulkUnassign() {
        clearMessages();
        if (!bulkLabelId) {
            setError("Choose a label to remove.");
            return;
        }
        if (!selectedIds.length) {
            setError("Select at least one host.");
            return;
        }
        let changed = 0;
        let failed = 0;
        const failureDetails = [];
        for (const hostId of selectedIds) {
            const host = (hosts || []).find((h) => h._key === hostId);
            if (!host) {
                failed += 1;
                failureDetails.push(hostId + ": host not in workspace");
                continue;
            }
            const before = normalizeLabelIds(host);
            const ids = before.filter((id) => id !== bulkLabelId);
            if (ids.length === before.length) {
                continue;
            }
            try {
                await setHostLabels(hostId, ids);
                changed += 1;
            } catch (err) {
                failed += 1;
                failureDetails.push(
                    hostId + ": " + String(err.message || err)
                );
            }
        }
        await loadWorkspaceData(collectionId);
        if (failed) {
            setWarning(
                "Removed label from " +
                    changed +
                    " host(s); " +
                    failed +
                    " failed. " +
                    failureDetails.join("; ")
            );
        } else {
            setInfo("Removed label from " + changed + " host(s).");
        }
    }

    async function toggleHostLabel(host, labelId, assign) {
        clearMessages();
        const ids = normalizeLabelIds(host);
        const next = assign
            ? ids.includes(labelId)
                ? ids
                : ids.concat([labelId])
            : ids.filter((id) => id !== labelId);
        try {
            if (assign && !ids.includes(labelId)) {
                await assignLabelToHosts(labelId, [host._key]);
            } else if (!assign) {
                await setHostLabels(host._key, next);
            }
            await loadWorkspaceData(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    function labelNamesForHost(host) {
        return normalizeLabelIds(host)
            .map((id) => {
                const row = labelById[id];
                return row ? row.name || id : id;
            })
            .join(", ");
    }

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={1}>Asset labels</Heading>
                </Brand>
            </Header>
            <PagePad>
                {error ? <Message type="error">{error}</Message> : null}
                {warning ? <Message type="warning">{warning}</Message> : null}
                {info ? <Message type="info">{info}</Message> : null}
                <Toolbar>
                    <ControlGroup label="Workspace">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => setCollectionId(value)}
                        >
                            {(workspaces || []).map((ws) => (
                                <Select.Option
                                    key={ws._key}
                                    label={workspaceLabel(ws)}
                                    value={ws._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                </Toolbar>
                {loading ? (
                    <WaitSpinner />
                ) : (
                    <>
                        <Heading level={3}>Workspace labels</Heading>
                        <p>
                            Labels scope restricted grants and filter hosts in the
                            STIG Editor. Create labels here instead of REST-only
                            workflows.
                        </p>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>Name</Table.HeadCell>
                                <Table.HeadCell>Id</Table.HeadCell>
                                <Table.HeadCell>Color</Table.HeadCell>
                                <Table.HeadCell />
                            </Table.Head>
                            <Table.Body>
                                {(labels || []).map((row) => (
                                    <Table.Row key={row._key}>
                                        <Table.Cell>
                                            <Text
                                                value={
                                                    renameDraft[row._key] !=
                                                    null
                                                        ? renameDraft[row._key]
                                                        : row.name || ""
                                                }
                                                onChange={(e, { value }) =>
                                                    setRenameDraft((prev) => ({
                                                        ...prev,
                                                        [row._key]: value,
                                                    }))
                                                }
                                            />
                                        </Table.Cell>
                                        <Table.Cell>{row._key}</Table.Cell>
                                        <Table.Cell>
                                            {row.color || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Button
                                                label="Save name"
                                                appearance="secondary"
                                                onClick={() =>
                                                    saveLabelName(row._key)
                                                }
                                            />
                                            <Button
                                                label="Delete"
                                                appearance="destructive"
                                                onClick={() =>
                                                    removeLabel(row._key)
                                                }
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                        <Heading level={4} style={{ marginTop: 24 }}>
                            New label
                        </Heading>
                        <ControlGroup label="Name" required>
                            <Text
                                value={newName}
                                onChange={(e, { value }) => setNewName(value)}
                            />
                        </ControlGroup>
                        <ControlGroup
                            label="Color (optional)"
                            help="Free text (e.g. #336699) for display in future UI."
                        >
                            <Text
                                value={newColor}
                                onChange={(e, { value }) => setNewColor(value)}
                            />
                        </ControlGroup>
                        <Button
                            label="Create label"
                            appearance="primary"
                            onClick={createLabel}
                        />

                        <Heading level={3} style={{ marginTop: 32 }}>
                            Assign labels to hosts
                        </Heading>
                        <Toolbar>
                            <ControlGroup label="Filter hosts by label">
                                <Select
                                    value={hostFilterLabelId}
                                    onChange={(e, { value }) =>
                                        setHostFilterLabelId(value)
                                    }
                                >
                                    <Select.Option
                                        label="All hosts"
                                        value=""
                                    />
                                    {(labels || []).map((l) => (
                                        <Select.Option
                                            key={l._key}
                                            label={l.name || l._key}
                                            value={l._key}
                                        />
                                    ))}
                                </Select>
                            </ControlGroup>
                            <ControlGroup label="Bulk label">
                                <Select
                                    value={bulkLabelId}
                                    onChange={(e, { value }) =>
                                        setBulkLabelId(value)
                                    }
                                >
                                    <Select.Option
                                        label="Select label"
                                        value=""
                                    />
                                    {(labels || []).map((l) => (
                                        <Select.Option
                                            key={l._key}
                                            label={l.name || l._key}
                                            value={l._key}
                                        />
                                    ))}
                                </Select>
                            </ControlGroup>
                            <Button
                                label="Assign to selected"
                                appearance="primary"
                                onClick={bulkAssign}
                            />
                            <Button
                                label="Remove from selected"
                                appearance="secondary"
                                onClick={bulkUnassign}
                            />
                        </Toolbar>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>Select</Table.HeadCell>
                                <Table.HeadCell>Hostname</Table.HeadCell>
                                <Table.HeadCell>Host id</Table.HeadCell>
                                <Table.HeadCell>Labels</Table.HeadCell>
                                {(labels || []).map((l) => (
                                    <Table.HeadCell key={l._key}>
                                        {l.name || l._key}
                                    </Table.HeadCell>
                                ))}
                            </Table.Head>
                            <Table.Body>
                                {filteredHosts.map((host) => {
                                    const hostLabels = normalizeLabelIds(host);
                                    return (
                                        <Table.Row key={host._key}>
                                            <Table.Cell>
                                                <Switch
                                                    appearance="checkbox"
                                                    selected={
                                                        !!selectedHostIds[
                                                            host._key
                                                        ]
                                                    }
                                                    onClick={() =>
                                                        setSelectedHostIds(
                                                            (prev) => ({
                                                                ...prev,
                                                                [host._key]:
                                                                    !prev[
                                                                        host._key
                                                                    ],
                                                            })
                                                        )
                                                    }
                                                />
                                            </Table.Cell>
                                            <Table.Cell>
                                                {host.hostname || "—"}
                                            </Table.Cell>
                                            <Table.Cell>{host._key}</Table.Cell>
                                            <Table.Cell>
                                                {labelNamesForHost(host) || "—"}
                                            </Table.Cell>
                                            {(labels || []).map((l) => {
                                                const on = hostLabels.includes(
                                                    l._key
                                                );
                                                return (
                                                    <Table.Cell key={l._key}>
                                                        <Switch
                                                            appearance="checkbox"
                                                            selected={on}
                                                            onClick={() =>
                                                                toggleHostLabel(
                                                                    host,
                                                                    l._key,
                                                                    !on
                                                                )
                                                            }
                                                        />
                                                    </Table.Cell>
                                                );
                                            })}
                                        </Table.Row>
                                    );
                                })}
                            </Table.Body>
                        </Table>
                    </>
                )}
            </PagePad>
        </Shell>
    );
}
