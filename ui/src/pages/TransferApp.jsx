import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import Table from "@splunk/react-ui/Table";
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
    const [selectedHostIds, setSelectedHostIds] = useState({});

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

    async function runTransfer() {
        setError("");
        setInfo("");
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
