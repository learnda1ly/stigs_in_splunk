import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet } from "../../api";
import { SectionBlock } from "../../layout";
import {
    packageLabel,
    resolveRmfPackage,
    sortPackages,
} from "../../types/rmf";

const emptyNew = () => ({
    hostname: "",
    ip_address: "",
    stig_collection_id: "",
    package_id: "-1",
});

export default function HostsStep({ canWrite, canAdmin }) {
    const [workspaces, setWorkspaces] = useState([]);
    const [packages, setPackages] = useState([]);
    const [defaults, setDefaults] = useState([]);
    const [hosts, setHosts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [busyKey, setBusyKey] = useState("");
    const [newRow, setNewRow] = useState(emptyNew);
    const [pkgDraft, setPkgDraft] = useState({});

    const workspaceOptions = useMemo(
        () =>
            (workspaces || []).map((w) => ({
                label: w.name || w._key,
                value: w._key,
            })),
        [workspaces]
    );

    const packageOptions = useMemo(
        () =>
            sortPackages(packages).map((p) => ({
                label: packageLabel(packages, p._key),
                value: p._key,
            })),
        [packages]
    );

    const loadAll = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const [colls, pkgRows, defRows] = await Promise.all([
                apiGet("stig_collections"),
                apiGet("stig_rmf_packages"),
                apiGet("stig_host_rmf_defaults"),
            ]);
            const ws = Array.isArray(colls) ? colls : [];
            setWorkspaces(ws);
            setPackages(Array.isArray(pkgRows) ? pkgRows : []);
            setDefaults(Array.isArray(defRows) ? defRows : []);
            const chunks = await Promise.all(
                ws.map((w) =>
                    apiGet("stig_hosts", { stig_collection_id: w._key }).then((rows) =>
                        (Array.isArray(rows) ? rows : []).map((h) => ({
                            ...h,
                            stig_collection_id: h.stig_collection_id || w._key,
                            _workspace_name: w.name || w._key,
                        }))
                    )
                )
            );
            const merged = chunks.reduce((acc, part) => acc.concat(part), []);
            setHosts(merged);
            const draft = {};
            merged.forEach((h) => {
                const resolved = resolveRmfPackage(
                    h.hostname,
                    "",
                    defRows || [],
                    []
                );
                draft[h._key] = resolved.package_id;
            });
            setPkgDraft(draft);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadAll();
    }, [loadAll]);

    async function saveRmfPackage(host) {
        if (!canAdmin) {
            setError("stig_admin is required to assign RMF packages.");
            return;
        }
        const hostname = (host.hostname || "").trim();
        const packageId = pkgDraft[host._key] || "-1";
        setBusyKey("rmf-" + host._key);
        setError("");
        try {
            await apiFetch(
                "stig_host_rmf_defaults/" + encodeURIComponent(hostname),
                {
                    method: "PUT",
                    body: { package_id: packageId },
                }
            );
            setInfo("RMF package assignment saved for " + hostname + ".");
            await loadAll();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function createHost() {
        if (!canWrite) {
            setError("stig_write is required to create hosts.");
            return;
        }
        const hostname = newRow.hostname.trim();
        const cid = newRow.stig_collection_id;
        if (!cid || !hostname) {
            setError("Workspace and hostname are required.");
            return;
        }
        setBusyKey("new");
        setError("");
        try {
            await apiFetch("stig_hosts", {
                method: "POST",
                body: {
                    stig_collection_id: cid,
                    hostname,
                    ip_address: newRow.ip_address.trim(),
                },
            });
            if (canAdmin && newRow.package_id) {
                await apiFetch(
                    "stig_host_rmf_defaults/" + encodeURIComponent(hostname),
                    {
                        method: "PUT",
                        body: { package_id: newRow.package_id },
                    }
                );
            }
            setNewRow(emptyNew());
            setInfo("Host created.");
            await loadAll();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function removeHost(host) {
        if (!canAdmin) {
            setError("stig_admin is required to delete hosts.");
            return;
        }
        const name = host.hostname || host._key;
        if (!window.confirm("Delete host \"" + name + "\"?")) {
            return;
        }
        setBusyKey(host._key);
        setError("");
        try {
            await apiFetch("stig_hosts/" + encodeURIComponent(host._key), {
                method: "DELETE",
            });
            setInfo("Host deleted.");
            await loadAll();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    return (
        <SectionBlock>
            <Heading level={2}>Hosts</Heading>
            {loading ? <WaitSpinner /> : null}
            {error ? (
                <Message type="error" style={{ marginTop: 12 }}>{error}</Message>
            ) : null}
            {info ? (
                <Message type="info" style={{ marginTop: 12 }}>{info}</Message>
            ) : null}
            <Table style={{ marginTop: 16 }}>
                <Table.Head>
                    <Table.HeadCell>Hostname</Table.HeadCell>
                    <Table.HeadCell>Workspace</Table.HeadCell>
                    <Table.HeadCell>RMF package</Table.HeadCell>
                    <Table.HeadCell width={200}>Actions</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {hosts.map((host) => (
                        <Table.Row key={host._key}>
                            <Table.Cell>{host.hostname || "—"}</Table.Cell>
                            <Table.Cell>{host._workspace_name || "—"}</Table.Cell>
                            <Table.Cell>
                                {canAdmin ? (
                                    <Select
                                        value={pkgDraft[host._key] || "-1"}
                                        onChange={(e, { value }) =>
                                            setPkgDraft((d) => ({
                                                ...d,
                                                [host._key]: value,
                                            }))
                                        }
                                    >
                                        {packageOptions.map((opt) => (
                                            <Select.Option
                                                key={opt.value}
                                                label={opt.label}
                                                value={opt.value}
                                            />
                                        ))}
                                    </Select>
                                ) : (
                                    packageLabel(
                                        packages,
                                        resolveRmfPackage(
                                            host.hostname,
                                            "",
                                            defaults,
                                            []
                                        ).package_id
                                    )
                                )}
                            </Table.Cell>
                            <Table.Cell>
                                {canAdmin ? (
                                    <>
                                        <Button
                                            label="Save RMF"
                                            disabled={busyKey === "rmf-" + host._key}
                                            onClick={() => saveRmfPackage(host)}
                                        />
                                        <Button
                                            label="Remove"
                                            appearance="destructive"
                                            disabled={busyKey === host._key}
                                            onClick={() => removeHost(host)}
                                        />
                                    </>
                                ) : (
                                    "—"
                                )}
                            </Table.Cell>
                        </Table.Row>
                    ))}
                    {canWrite ? (
                        <Table.Row key="__new__">
                            <Table.Cell>
                                <Text
                                    placeholder="Hostname"
                                    value={newRow.hostname}
                                    onChange={(_, { value }) =>
                                        setNewRow((r) => ({ ...r, hostname: value }))
                                    }
                                />
                            </Table.Cell>
                            <Table.Cell>
                                <Select
                                    value={newRow.stig_collection_id}
                                    onChange={(e, { value }) =>
                                        setNewRow((r) => ({
                                            ...r,
                                            stig_collection_id: value,
                                        }))
                                    }
                                >
                                    {workspaceOptions.map((opt) => (
                                        <Select.Option
                                            key={opt.value}
                                            label={opt.label}
                                            value={opt.value}
                                        />
                                    ))}
                                </Select>
                            </Table.Cell>
                            <Table.Cell>
                                {canAdmin ? (
                                    <Select
                                        value={newRow.package_id}
                                        onChange={(e, { value }) =>
                                            setNewRow((r) => ({
                                                ...r,
                                                package_id: value,
                                            }))
                                        }
                                    >
                                        {packageOptions.map((opt) => (
                                            <Select.Option
                                                key={opt.value}
                                                label={opt.label}
                                                value={opt.value}
                                            />
                                        ))}
                                    </Select>
                                ) : (
                                    "—"
                                )}
                            </Table.Cell>
                            <Table.Cell>
                                <Button
                                    label="Add"
                                    disabled={busyKey === "new"}
                                    onClick={createHost}
                                />
                            </Table.Cell>
                        </Table.Row>
                    ) : null}
                </Table.Body>
            </Table>
        </SectionBlock>
    );
}
