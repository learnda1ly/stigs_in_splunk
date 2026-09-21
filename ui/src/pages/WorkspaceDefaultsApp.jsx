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
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";

function baselineLabel(row) {
    if (!row) {
        return "—";
    }
    const parts = [
        row.title || row.stig_id || row._key,
        row.version ? "v" + row.version : "",
        row.release_info || "",
    ].filter(Boolean);
    return parts.join(" · ") || row._key;
}

export default function WorkspaceDefaultsApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [baselines, setBaselines] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [defaults, setDefaults] = useState([]);
    const [draftStigId, setDraftStigId] = useState("");
    const [draftBaselineId, setDraftBaselineId] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const stigOptions = useMemo(() => {
        const seen = {};
        (baselines || []).forEach((row) => {
            const sid = (row.stig_id || "").trim();
            if (!sid || seen[sid]) {
                return;
            }
            seen[sid] = true;
        });
        return Object.keys(seen)
            .sort()
            .map((sid) => ({ label: sid, value: sid }));
    }, [baselines]);

    const baselineOptions = useMemo(() => {
        const sid = (draftStigId || "").trim();
        return (baselines || [])
            .filter((row) => !sid || (row.stig_id || "") === sid)
            .map((row) => ({
                label: baselineLabel(row),
                value: row._key,
            }));
    }, [baselines, draftStigId]);

    const loadDefaults = useCallback(async (cid) => {
        if (!cid) {
            setDefaults([]);
            return;
        }
        const rows = await apiGet("stig_collections/" + cid + "/baseline_defaults");
        setDefaults(rows || []);
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const [colls, baseRows] = await Promise.all([
                apiGet("stig_collections"),
                apiGet("stig_baselines"),
            ]);
            setWorkspaces(colls || []);
            setBaselines(baseRows || []);
            const def = defaultWorkspaceId(colls);
            const cid = collectionId || def || "";
            if (!collectionId && cid) {
                setCollectionId(cid);
            }
            await loadDefaults(cid || collectionId);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, [collectionId, loadDefaults]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (collectionId) {
            loadDefaults(collectionId).catch((err) =>
                setError(String(err.message || err))
            );
        }
    }, [collectionId, loadDefaults]);

    async function saveDefault() {
        setError("");
        try {
            await apiFetch(
                "stig_collections/" + collectionId + "/baseline_defaults",
                {
                    method: "POST",
                    body: {
                        stig_id: draftStigId,
                        baseline_id: draftBaselineId,
                    },
                }
            );
            setDraftStigId("");
            setDraftBaselineId("");
            await loadDefaults(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function removeDefault(stigId) {
        setError("");
        try {
            await apiFetch(
                "stig_collections/" +
                    collectionId +
                    "/baseline_defaults/" +
                    encodeURIComponent(stigId),
                { method: "DELETE" }
            );
            await loadDefaults(collectionId);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    const workspaceOptions = workspaces.map((ws) => ({
        label: workspaceLabel(ws),
        value: ws._key,
    }));

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    Default STIG revisions
                </Brand>
            </Header>
            <PagePad>
                <Message type="info">
                    Per-workspace default baseline per STIG id. Checklist creation and
                    scan ingest use this revision when no explicit baseline_id is
                    provided. Explicit baseline_id always wins.
                </Message>
                {error ? <Message type="error">{error}</Message> : null}
                {loading ? <WaitSpinner /> : null}
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(_, { value }) => setCollectionId(value)}
                        >
                            {workspaceOptions.map((opt) => (
                                <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                            ))}
                        </Select>
                    </ControlGroup>
                </Toolbar>
                <Heading level={3}>Set default</Heading>
                <Toolbar>
                    <ControlGroup label="STIG id" labelPosition="top">
                        <Select
                            value={draftStigId}
                            onChange={(_, { value }) => {
                                setDraftStigId(value);
                                setDraftBaselineId("");
                            }}
                        >
                            {stigOptions.map((opt) => (
                                <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                            ))}
                        </Select>
                    </ControlGroup>
                    <ControlGroup label="Baseline revision" labelPosition="top">
                        <Select
                            value={draftBaselineId}
                            onChange={(_, { value }) => setDraftBaselineId(value)}
                            disabled={!draftStigId}
                        >
                            {baselineOptions.map((opt) => (
                                <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                            ))}
                        </Select>
                    </ControlGroup>
                    <Button
                        label="Save default"
                        onClick={saveDefault}
                        disabled={!collectionId || !draftStigId || !draftBaselineId}
                    />
                </Toolbar>
                <Heading level={3}>Current defaults</Heading>
                <Table>
                    <Table.Head>
                        <Table.HeadCell>STIG id</Table.HeadCell>
                        <Table.HeadCell>Baseline</Table.HeadCell>
                        <Table.HeadCell>Version</Table.HeadCell>
                        <Table.HeadCell />
                    </Table.Head>
                    <Table.Body>
                        {(defaults || []).map((row) => (
                            <Table.Row key={row.stig_id}>
                                <Table.Cell>{row.stig_id}</Table.Cell>
                                <Table.Cell>
                                    {row.baseline_title || row.baseline_id}
                                    {row.missing_baseline ? " (missing)" : ""}
                                </Table.Cell>
                                <Table.Cell>{row.baseline_version || "—"}</Table.Cell>
                                <Table.Cell>
                                    <Button
                                        appearance="secondary"
                                        label="Remove"
                                        onClick={() => removeDefault(row.stig_id)}
                                    />
                                </Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>
                {!defaults.length && !loading ? (
                    <Text as="p">No defaults configured for this workspace.</Text>
                ) : null}
            </PagePad>
        </Shell>
    );
}
