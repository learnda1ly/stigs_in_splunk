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

export default function TransferApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [sourceId, setSourceId] = useState("");
    const [destId, setDestId] = useState("");
    const [hosts, setHosts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [resultRows, setResultRows] = useState([]);
    const [selectedHostIds, setSelectedHostIds] = useState({});
    const [cloneName, setCloneName] = useState("");
    const [cloneCopyReviews, setCloneCopyReviews] = useState(true);
    const [cloneCopyGrants, setCloneCopyGrants] = useState(false);
    // Clone UI always uses API defaults (full host/checklist copy).
    const cloneIncludesHostsAndLabels = true;

    const destOptions = useMemo(
        () => (workspaces || []).filter((ws) => ws && ws._key !== sourceId),
        [workspaces, sourceId]
    );

    const selectedIds = useMemo(
        () => Object.keys(selectedHostIds).filter((id) => selectedHostIds[id]),
        [selectedHostIds]
    );

    const loadHosts = useCallback(async (cid) => {
        if (!cid) {
            setHosts([]);
            return;
        }
        const rows = await apiGet("stig_hosts", { stig_collection_id: cid });
        setHosts(Array.isArray(rows) ? rows : []);
        setSelectedHostIds({});
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const colls = await apiGet("stig_collections");
            setWorkspaces(colls || []);
            const def = defaultWorkspaceId(colls);
            const sid = sourceId || def || "";
            if (!sourceId && sid) {
                setSourceId(sid);
            }
            if (sid) {
                await loadHosts(sid);
            }
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, [sourceId, loadHosts]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (sourceId) {
            loadHosts(sourceId).catch((err) =>
                setError(String(err.message || err))
            );
        }
        if (destId === sourceId) {
            setDestId("");
        }
    }, [sourceId, destId, loadHosts]);

    function toggleAll(on) {
        const next = {};
        if (on) {
            (hosts || []).forEach((h) => {
                if (h && h._key) {
                    next[h._key] = true;
                }
            });
        }
        setSelectedHostIds(next);
    }

    async function runClone() {
        setError("");
        setInfo("");
        if (!sourceId) {
            setError("Choose a source workspace to clone.");
            return;
        }
        const src =
            (workspaces || []).find((w) => w._key === sourceId) || {};
        const defaultName =
            ((src.name || sourceId) + " (clone)").trim();
        const name = (cloneName || defaultName).trim();
        if (
            !window.confirm(
                'Clone workspace "' +
                    workspaceLabel(src) +
                    '" to new workspace "' +
                    name +
                    '"?'
            )
        ) {
            return;
        }
        setBusy(true);
        try {
            const result = await apiFetch(
                "stig_collections/" + sourceId + "/clone",
                {
                    method: "POST",
                    body: {
                        name,
                        copy_hosts: true,
                        copy_labels: true,
                        copy_reviews: cloneCopyReviews,
                        copy_grants: cloneCopyGrants,
                    },
                }
            );
            const summary = (result && result.summary) || {};
            const colls = await apiGet("stig_collections");
            setWorkspaces(colls || []);
            setInfo(
                "Cloned workspace " +
                    name +
                    " (" +
                    (result.stig_collection_id || "") +
                    "): " +
                    Number(summary.hosts || 0) +
                    " hosts, " +
                    Number(summary.checklists || 0) +
                    " checklists, " +
                    Number(summary.reviews || 0) +
                    " reviews."
            );
            setCloneName("");
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusy(false);
        }
    }

    async function runTransfer() {
        setError("");
        setInfo("");
        setResultRows([]);
        if (!sourceId || !destId) {
            setError("Choose source and destination workspaces.");
            return;
        }
        if (!selectedIds.length) {
            setError("Select at least one host to transfer.");
            return;
        }
        const destName =
            (destOptions.find((w) => w._key === destId) || {}).name || destId;
        if (
            !window.confirm(
                "Move " +
                    selectedIds.length +
                    ' host(s) to workspace "' +
                    destName +
                    '"? Checklists move with each host. Labels are kept only when the same label id exists in the destination workspace.'
            )
        ) {
            return;
        }
        setBusy(true);
        try {
            const result = await apiFetch(
                "stig_collections/" +
                    sourceId +
                    "/export-to/" +
                    destId,
                {
                    method: "POST",
                    body: { host_ids: selectedIds },
                }
            );
            const summary = (result && result.summary) || {};
            const moved = Number(summary.moved || 0);
            const failed = Number(summary.failed || 0);
            const skipped = Number(summary.skipped || 0);
            await loadHosts(sourceId);
            let msg =
                "Transferred " +
                moved +
                " host(s) to " +
                workspaceLabel(
                    destOptions.find((w) => w._key === destId) || {
                        _key: destId,
                    }
                );
            if (failed || skipped) {
                msg +=
                    " (" +
                    failed +
                    " failed, " +
                    skipped +
                    " skipped).";
            }
            setInfo(msg);
            const rows = Array.isArray(result.results) ? result.results : [];
            const problems = rows.filter((r) => r && r.status !== "moved");
            setResultRows(problems);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusy(false);
        }
    }

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={1}>Transfer assets</Heading>
                </Brand>
            </Header>
            <PagePad>
                {error ? <Message type="error">{error}</Message> : null}
                {info ? <Message type="info">{info}</Message> : null}
                {resultRows.length ? (
                    <>
                        <Heading level={4}>Hosts not transferred</Heading>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>Host id</Table.HeadCell>
                                <Table.HeadCell>Status</Table.HeadCell>
                                <Table.HeadCell>Detail</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {resultRows.map((row) => (
                                    <Table.Row key={row.host_id || row.status}>
                                        <Table.Cell>
                                            {row.host_id || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {row.status || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {row.error || "—"}
                                        </Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                    </>
                ) : null}
                <Heading level={3}>Clone workspace</Heading>
                <p>
                    Create a new workspace from the source. Requires read access on
                    the source and stig_write. Global STIG baselines are shared,
                    not duplicated.
                </p>
                <Toolbar>
                    <ControlGroup label="New workspace name">
                        <Text
                            value={cloneName}
                            onChange={(e, { value }) => setCloneName(value)}
                            placeholder="Defaults to “(source name) (clone)”"
                        />
                    </ControlGroup>
                    <ControlGroup label="Copy reviews">
                        <Switch
                            selected={cloneCopyReviews}
                            onClick={() =>
                                setCloneCopyReviews((v) => !v)
                            }
                        />
                    </ControlGroup>
                    <ControlGroup
                        label="Copy grants"
                        help={
                            cloneIncludesHostsAndLabels
                                ? "Remaps host and label ACL scopes in copied grants."
                                : "Requires copying hosts and labels (full workspace clone)."
                        }
                    >
                        <Switch
                            selected={cloneCopyGrants}
                            disabled={!cloneIncludesHostsAndLabels || busy}
                            onClick={() => setCloneCopyGrants((v) => !v)}
                        />
                    </ControlGroup>
                    <Button
                        label="Clone workspace"
                        appearance="secondary"
                        disabled={busy || !sourceId}
                        onClick={runClone}
                    />
                </Toolbar>
                <Heading level={3}>Transfer hosts</Heading>
                <p>
                    Move hosts and their checklists to another workspace. You need
                    write access on both workspaces. Workspace grants are not
                    copied; destination ACL applies after the move.
                </p>
                <Toolbar>
                    <ControlGroup label="Source workspace">
                        <Select
                            value={sourceId}
                            onChange={(e, { value }) => setSourceId(value)}
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
                    <ControlGroup label="Destination workspace">
                        <Select
                            value={destId}
                            onChange={(e, { value }) => setDestId(value)}
                        >
                            <Select.Option label="Select destination" value="" />
                            {destOptions.map((ws) => (
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
                        <Toolbar>
                            <Button
                                label="Select all"
                                appearance="secondary"
                                onClick={() => toggleAll(true)}
                            />
                            <Button
                                label="Clear selection"
                                appearance="secondary"
                                onClick={() => toggleAll(false)}
                            />
                            <Button
                                label="Transfer selected"
                                appearance="primary"
                                disabled={busy || !destId || !selectedIds.length}
                                onClick={runTransfer}
                            />
                        </Toolbar>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>Select</Table.HeadCell>
                                <Table.HeadCell>Hostname</Table.HeadCell>
                                <Table.HeadCell>Host id</Table.HeadCell>
                                <Table.HeadCell>IP</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {(hosts || []).map((host) => (
                                    <Table.Row key={host._key}>
                                        <Table.Cell>
                                            <Switch
                                                appearance="checkbox"
                                                selected={
                                                    !!selectedHostIds[host._key]
                                                }
                                                onClick={() =>
                                                    setSelectedHostIds(
                                                        (prev) => ({
                                                            ...prev,
                                                            [host._key]:
                                                                !prev[host._key],
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
                                            {host.ip_address || "—"}
                                        </Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                    </>
                )}
            </PagePad>
        </Shell>
    );
}
