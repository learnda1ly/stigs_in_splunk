import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, defaultWorkspaceId, workspaceLabel } from "../api";
import { Brand, BrandKicker, Header, PagePad, Shell, Toolbar } from "../layout";

const ROLE_OPTIONS = [
    { label: "Owner (full control + principals)", value: "owner" },
    { label: "Manager (full assets + manage grants)", value: "manager" },
    { label: "Member (full workspace, needs stig_write)", value: "member" },
    { label: "Restricted (ACL-scoped)", value: "restricted" },
];

function labelDisplay(labels, id) {
    const row = (labels || []).find((l) => l._key === id);
    if (!row) {
        return id;
    }
    const name = (row.name || "").trim();
    return name ? name + " (" + id + ")" : id;
}

function parseIdList(text) {
    const raw = (text || "").trim();
    if (!raw) {
        return [];
    }
    if (raw.charAt(0) === "[") {
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed.map(String) : [];
        } catch (e) {
            return [];
        }
    }
    return raw
        .split(/[\s,]+/)
        .map((part) => part.trim())
        .filter(Boolean);
}

export default function GrantsApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [grants, setGrants] = useState([]);
    const [hosts, setHosts] = useState([]);
    const [baselines, setBaselines] = useState([]);
    const [draftPrincipal, setDraftPrincipal] = useState("user:");
    const [draftRole, setDraftRole] = useState("restricted");
    const [draftHosts, setDraftHosts] = useState("");
    const [draftBaselines, setDraftBaselines] = useState("");
    const [draftLabels, setDraftLabels] = useState("");
    const [labels, setLabels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [showAddGrant, setShowAddGrant] = useState(false);

    const hostOptions = useMemo(
        () =>
            (hosts || []).map((h) => ({
                label: (h.hostname || h._key) + " (" + h._key + ")",
                value: h._key,
            })),
        [hosts]
    );

    const labelOptions = useMemo(
        () =>
            (labels || []).map((l) => ({
                label: (l.name || l._key) + " (" + l._key + ")",
                value: l._key,
            })),
        [labels]
    );

    const baselineOptions = useMemo(
        () =>
            (baselines || []).map((b) => ({
                label: (b.title || b.stig_id || b._key) + " (" + b._key + ")",
                value: b._key,
            })),
        [baselines]
    );

    const loadGrants = useCallback(async (cid) => {
        if (!cid) {
            setGrants([]);
            return;
        }
        const rows = await apiGet("stig_collections/" + cid + "/grants");
        setGrants(Array.isArray(rows) ? rows : []);
    }, []);

    const loadWorkspaceAssets = useCallback(async (cid) => {
        if (!cid) {
            setHosts([]);
            return;
        }
        const [hs, cls, lbls] = await Promise.all([
            apiGet("stig_hosts", { stig_collection_id: cid }),
            apiGet("stig_checklists", { stig_collection_id: cid }),
            apiGet("stig_collections/" + cid + "/labels"),
        ]);
        setHosts(Array.isArray(hs) ? hs : []);
        setLabels(Array.isArray(lbls) ? lbls : []);
        const baselineIds = {};
        (cls || []).forEach((row) => {
            if (row.baseline_id) {
                baselineIds[row.baseline_id] = true;
            }
        });
        const all = await apiGet("stig_baselines");
        setBaselines(
            (all || []).filter((row) => baselineIds[row._key] || !Object.keys(baselineIds).length)
        );
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
                await Promise.all([loadGrants(cid), loadWorkspaceAssets(cid)]);
            }
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, [collectionId, loadGrants, loadWorkspaceAssets]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (collectionId) {
            Promise.all([loadGrants(collectionId), loadWorkspaceAssets(collectionId)]).catch(
                (err) => setError(String(err.message || err))
            );
        }
    }, [collectionId, loadGrants, loadWorkspaceAssets]);

    async function createGrant() {
        setError("");
        setInfo("");
        try {
            await apiFetch("stig_collections/" + collectionId + "/grants", {
                method: "POST",
                body: {
                    principal: draftPrincipal,
                    grant_role: draftRole,
                    acl_host_ids: parseIdList(draftHosts),
                    acl_baseline_ids: parseIdList(draftBaselines),
                    acl_labels: parseIdList(draftLabels),
                },
            });
            setInfo("Grant saved.");
            setShowAddGrant(false);
            await loadGrants(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function removeGrant(grantId) {
        setError("");
        try {
            await apiFetch(
                "stig_collections/" + collectionId + "/grants/" + grantId,
                { method: "DELETE" }
            );
            await loadGrants(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={1}>Workspace grants &amp; ACL</Heading>
                </Brand>
            </Header>
            <PagePad>
                {error ? <Message type="error">{error}</Message> : null}
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
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                flexWrap: "wrap",
                                gap: 8,
                                marginBottom: 8,
                            }}
                        >
                            <Heading level={3} style={{ margin: 0 }}>
                                Grants
                            </Heading>
                            <Button
                                label={showAddGrant ? "Cancel" : "Add grant"}
                                appearance="primary"
                                onClick={() => setShowAddGrant((open) => !open)}
                            />
                        </div>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>Principal</Table.HeadCell>
                                <Table.HeadCell>Role</Table.HeadCell>
                                <Table.HeadCell>Host ACL</Table.HeadCell>
                                <Table.HeadCell>Baseline ACL</Table.HeadCell>
                                <Table.HeadCell>Label ACL</Table.HeadCell>
                                <Table.HeadCell />
                            </Table.Head>
                            <Table.Body>
                                {(grants || []).map((row) => (
                                    <Table.Row key={row._key}>
                                        <Table.Cell>{row.principal}</Table.Cell>
                                        <Table.Cell>{row.grant_role}</Table.Cell>
                                        <Table.Cell>
                                            {(row.acl_host_ids || []).join(", ") || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {(row.acl_baseline_ids || []).join(", ") || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {(row.acl_labels || [])
                                                .map((id) => labelDisplay(labels, id))
                                                .join(", ") || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Button
                                                label="Remove"
                                                appearance="secondary"
                                                onClick={() => removeGrant(row._key)}
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                        {showAddGrant ? (
                            <div
                                style={{
                                    marginTop: 16,
                                    padding: 16,
                                    border: "1px solid var(--splunk-color-border, #ccc)",
                                    borderRadius: 8,
                                }}
                            >
                                <Heading level={4} style={{ marginTop: 0 }}>
                                    New grant
                                </Heading>
                                <ControlGroup label="Principal" help="user:login or role:rolename">
                                    <Text value={draftPrincipal} onChange={(e, { value }) => setDraftPrincipal(value)} />
                                </ControlGroup>
                                <ControlGroup label="Grant role">
                                    <Select value={draftRole} onChange={(e, { value }) => setDraftRole(value)}>
                                        {ROLE_OPTIONS.map((opt) => (
                                            <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <ControlGroup
                                    label="Host ACL (restricted)"
                                    help="Comma-separated host _key values, or pick from workspace hosts."
                                >
                                    <Text value={draftHosts} onChange={(e, { value }) => setDraftHosts(value)} />
                                </ControlGroup>
                                {hostOptions.length ? (
                                    <ControlGroup label="Quick add host">
                                        <Select
                                            placeholder="Select host id"
                                            onChange={(e, { value }) =>
                                                setDraftHosts((prev) =>
                                                    prev ? prev + "," + value : value
                                                )
                                            }
                                        >
                                            {hostOptions.map((opt) => (
                                                <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                                            ))}
                                        </Select>
                                    </ControlGroup>
                                ) : null}
                                <ControlGroup label="Baseline ACL (restricted)">
                                    <Text
                                        value={draftBaselines}
                                        onChange={(e, { value }) => setDraftBaselines(value)}
                                    />
                                </ControlGroup>
                                {baselineOptions.length ? (
                                    <ControlGroup label="Quick add baseline">
                                        <Select
                                            placeholder="Select baseline id"
                                            onChange={(e, { value }) =>
                                                setDraftBaselines((prev) =>
                                                    prev ? prev + "," + value : value
                                                )
                                            }
                                        >
                                            {baselineOptions.map((opt) => (
                                                <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                                            ))}
                                        </Select>
                                    </ControlGroup>
                                ) : null}
                                <ControlGroup
                                    label="Label ACL (restricted)"
                                    help="Comma-separated stig_labels._key values; host must have at least one matching label."
                                >
                                    <Text value={draftLabels} onChange={(e, { value }) => setDraftLabels(value)} />
                                </ControlGroup>
                                {labelOptions.length ? (
                                    <ControlGroup label="Quick add label">
                                        <Select
                                            placeholder="Select label id"
                                            onChange={(e, { value }) =>
                                                setDraftLabels((prev) =>
                                                    prev ? prev + "," + value : value
                                                )
                                            }
                                        >
                                            {labelOptions.map((opt) => (
                                                <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                                            ))}
                                        </Select>
                                    </ControlGroup>
                                ) : null}
                                <Button label="Save grant" appearance="primary" onClick={createGrant} />
                            </div>
                        ) : null}
                    </>
                )}
            </PagePad>
        </Shell>
    );
}
