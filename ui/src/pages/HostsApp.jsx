import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import {
    apiFetch,
    apiGet,
    apiUrl,
    defaultWorkspaceId,
    downloadText,
    formatErr,
    isAllWorkspaces,
    viewUrl,
    viewUrlWithQuery,
    workspaceScopeQuery,
} from "../api";
import WorkspaceSelect from "../components/WorkspaceSelect";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";

const ASSET_TYPES = ["Computing", "Non-Computing"];

const emptyDraft = () => ({
    hostname: "",
    ip_address: "",
    fqdn: "",
    mac_address: "",
    role: "None",
    asset_type: "Computing",
});

export default function HostsApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [hosts, setHosts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [banner, setBanner] = useState(null);
    const [filter, setFilter] = useState("");
    const [draft, setDraft] = useState(emptyDraft());
    const [editId, setEditId] = useState("");
    const [editDraft, setEditDraft] = useState(emptyDraft());
    const [showAddForm, setShowAddForm] = useState(false);
    const [pendingCsv, setPendingCsv] = useState("");
    const [importReport, setImportReport] = useState(null);

    const loadWorkspaces = useCallback(() =>
        apiGet("stig_collections")
            .then((rows) => {
                const list = Array.isArray(rows) ? rows : [];
                setWorkspaces(list);
                setCollectionId((prev) => {
                    if (prev && list.some((w) => w._key === prev)) {
                        return prev;
                    }
                    return defaultWorkspaceId(list) || (list[0] && list[0]._key) || "";
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load workspaces: " + err.message })
            )
    , []);

    const loadHosts = useCallback(() => {
        if (!collectionId) {
            setHosts([]);
            setLoading(false);
            return Promise.resolve();
        }
        setLoading(true);
        return apiGet("stig_hosts", workspaceScopeQuery(collectionId))
            .then((rows) => setHosts(Array.isArray(rows) ? rows : []))
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load hosts: " + err.message })
            )
            .finally(() => setLoading(false));
    }, [collectionId]);

    useEffect(() => {
        loadWorkspaces();
    }, [loadWorkspaces]);

    useEffect(() => {
        loadHosts();
    }, [loadHosts]);

    const visibleHosts = useMemo(() => {
        const q = filter.trim().toLowerCase();
        if (!q) {
            return hosts;
        }
        return hosts.filter((h) =>
            [h.hostname, h.ip_address, h.fqdn, h._key, h.role]
                .join(" ")
                .toLowerCase()
                .includes(q)
        );
    }, [hosts, filter]);

    const createHost = () => {
        const name = draft.hostname.trim();
        if (!collectionId || isAllWorkspaces(collectionId)) {
            setBanner({
                type: "warning",
                text: "Select a single workspace to create a host.",
            });
            return;
        }
        if (!name) {
            setBanner({ type: "warning", text: "Hostname is required." });
            return;
        }
        setBusy(true);
        apiFetch("stig_hosts", {
            method: "POST",
            body: {
                stig_collection_id: collectionId,
                hostname: name,
                ip_address: draft.ip_address.trim(),
                fqdn: draft.fqdn.trim(),
                mac_address: draft.mac_address.trim(),
                role: draft.role.trim() || "None",
                asset_type: draft.asset_type,
            },
        })
            .then(() => {
                setDraft(emptyDraft());
                setShowAddForm(false);
                setBanner({ type: "success", text: "Created host " + name + "." });
                return loadHosts();
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Create failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const startEdit = (host) => {
        setEditId(host._key);
        setEditDraft({
            hostname: host.hostname || "",
            ip_address: host.ip_address || "",
            fqdn: host.fqdn || "",
            mac_address: host.mac_address || "",
            role: host.role || "None",
            asset_type: host.asset_type || "Computing",
        });
    };

    const saveEdit = () => {
        if (!editId) {
            return;
        }
        setBusy(true);
        apiFetch("stig_hosts/" + encodeURIComponent(editId), {
            method: "PATCH",
            body: {
                hostname: editDraft.hostname.trim(),
                ip_address: editDraft.ip_address.trim(),
                fqdn: editDraft.fqdn.trim(),
                mac_address: editDraft.mac_address.trim(),
                role: editDraft.role.trim() || "None",
                asset_type: editDraft.asset_type,
            },
        })
            .then(() => {
                setEditId("");
                setBanner({ type: "success", text: "Host updated." });
                return loadHosts();
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Update failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const exportAssetsCsv = () => {
        if (!collectionId || isAllWorkspaces(collectionId)) {
            setBanner({
                type: "warning",
                text: "Select a single workspace to export assets.",
            });
            return;
        }
        setBusy(true);
        const url = apiUrl(
            "stig_collections/" + encodeURIComponent(collectionId) + "/assets/csv"
        );
        fetch(url, {
            method: "GET",
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then((res) =>
                res.text().then((text) => {
                    if (!res.ok) {
                        throw new Error(formatErr(text) || "HTTP " + res.status);
                    }
                    const disp = res.headers.get("Content-Disposition") || "";
                    const match = disp.match(/filename="([^"]+)"/);
                    const filename = match ? match[1] : "stig_assets.csv";
                    downloadText(filename, text, "text/csv");
                    setBanner({
                        type: "success",
                        text: "Exported assets CSV (" + (res.headers.get("X-Stig-Row-Count") || "?") + " rows).",
                    });
                })
            )
            .catch((err) =>
                setBanner({ type: "error", text: "Export failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const validateCsvImport = (csvText) => {
        if (!collectionId || isAllWorkspaces(collectionId)) {
            setBanner({
                type: "warning",
                text: "Select a single workspace to import assets.",
            });
            return;
        }
        setBusy(true);
        apiFetch("stig_collections/" + encodeURIComponent(collectionId) + "/assets/csv", {
            method: "POST",
            body: { csv: csvText, submit: false },
        })
            .then((report) => {
                setPendingCsv(csvText);
                setImportReport(report);
                const valid = report && report.valid_count;
                const invalid = report && report.invalid_count;
                setBanner({
                    type: invalid ? "warning" : "success",
                    text:
                        "CSV validated: " +
                        valid +
                        " valid row(s), " +
                        invalid +
                        " invalid. Review errors below, then apply import.",
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Validate failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const applyCsvImport = () => {
        if (!pendingCsv) {
            setBanner({ type: "warning", text: "Choose and validate a CSV file first." });
            return;
        }
        setBusy(true);
        apiFetch("stig_collections/" + encodeURIComponent(collectionId) + "/assets/csv", {
            method: "POST",
            body: { csv: pendingCsv, submit: true },
        })
            .then((report) => {
                setImportReport(report);
                setPendingCsv("");
                const summary = (report && report.summary) || {};
                setBanner({
                    type: "success",
                    text:
                        "Import complete. Created " +
                        (summary.created || 0) +
                        ", updated " +
                        (summary.updated || 0) +
                        ", STIG assignments " +
                        (summary.stigs_assigned || 0) +
                        ".",
                });
                return loadHosts();
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Import failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const onCsvFileChange = (event) => {
        const file = event.target.files && event.target.files[0];
        event.target.value = "";
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            validateCsvImport(String(reader.result || ""));
        };
        reader.onerror = () => {
            setBanner({ type: "error", text: "Could not read CSV file." });
        };
        reader.readAsText(file);
    };

    const deleteHost = (host) => {
        const label = host.hostname || host._key;
        if (!window.confirm("Delete host " + label + "? Requires stig_admin.")) {
            return;
        }
        setBusy(true);
        apiFetch("stig_hosts/" + encodeURIComponent(host._key), { method: "DELETE" })
            .then(() => {
                setBanner({ type: "success", text: "Deleted " + label + "." });
                return loadHosts();
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Delete failed: " + err.message + " (stig_admin required).",
                })
            )
            .finally(() => setBusy(false));
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>Hosts</Heading>
                </Brand>
            </Header>
            <PagePad>
                <p style={{ maxWidth: 760, marginTop: 0 }}>
                    Manage assets (hosts) per workspace. Assign STIGs from the{" "}
                    <Link to={viewUrl("stig_editor_ui")}>Editor</Link> or{" "}
                    <Link to={viewUrl("stig_library_ui")}>STIG library</Link> after creating a
                    host. Checklist import also creates hosts automatically.
                </p>
                {banner ? (
                    <Message appearance={banner.type} onRequestRemove={() => setBanner(null)}>
                        {banner.text}
                    </Message>
                ) : null}
                <Toolbar style={{ marginBottom: 16, flexWrap: "wrap" }}>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <WorkspaceSelect
                            workspaces={workspaces}
                            value={collectionId}
                            onChange={(e, { value }) => setCollectionId(value)}
                            filter
                            disabled={busy}
                        />
                    </ControlGroup>
                    <ControlGroup label="Filter" labelPosition="top">
                        <Text
                            value={filter}
                            onChange={(e, { value }) => setFilter(value)}
                            placeholder="Hostname, IP, id…"
                            disabled={busy}
                        />
                    </ControlGroup>
                </Toolbar>

                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: 8,
                        marginBottom: 12,
                    }}
                >
                    <Heading level={3} style={{ margin: 0 }}>
                        Hosts in workspace
                    </Heading>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        <Button
                            appearance="secondary"
                            disabled={busy || !collectionId}
                            onClick={exportAssetsCsv}
                            label="Export assets CSV"
                        />
                        <Button
                            appearance="secondary"
                            disabled={busy || !collectionId}
                            onClick={() =>
                                document.getElementById("stig-hosts-csv-input")?.click()
                            }
                            label="Import assets CSV"
                        />
                        <input
                            id="stig-hosts-csv-input"
                            type="file"
                            accept=".csv,text/csv"
                            style={{ display: "none" }}
                            onChange={onCsvFileChange}
                        />
                        {pendingCsv ? (
                            <Button
                                appearance="primary"
                                disabled={busy || !collectionId}
                                onClick={applyCsvImport}
                                label="Apply validated import"
                            />
                        ) : null}
                        <Button
                            appearance="primary"
                            disabled={busy || !collectionId}
                            onClick={() => setShowAddForm((open) => !open)}
                            label={showAddForm ? "Cancel add" : "Add host"}
                        />
                    </div>
                </div>
                {importReport && importReport.rows && importReport.rows.length ? (
                    <Message
                        appearance={importReport.invalid_count ? "warning" : "info"}
                        style={{ marginBottom: 16 }}
                    >
                        <div>
                            {importReport.rows
                                .filter((row) => row.errors && row.errors.length)
                                .slice(0, 8)
                                .map((row) => (
                                    <div key={row.row}>
                                        Row {row.row} ({row.name || "—"}):{" "}
                                        {row.errors.join("; ")}
                                    </div>
                                ))}
                            {importReport.rows.filter(
                                (row) => row.errors && row.errors.length
                            ).length > 8
                                ? "…more row errors omitted"
                                : null}
                        </div>
                    </Message>
                ) : null}
                {showAddForm ? (
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
                            gap: 12,
                            marginBottom: 24,
                            alignItems: "end",
                            padding: 16,
                            border: "1px solid var(--splunk-color-border, #ccc)",
                            borderRadius: 8,
                        }}
                    >
                        <ControlGroup label="Hostname" labelPosition="top" required>
                            <Text
                                value={draft.hostname}
                                onChange={(e, { value }) =>
                                    setDraft((d) => ({ ...d, hostname: value }))
                                }
                                disabled={busy}
                            />
                        </ControlGroup>
                        <ControlGroup label="IP" labelPosition="top">
                            <Text
                                value={draft.ip_address}
                                onChange={(e, { value }) =>
                                    setDraft((d) => ({ ...d, ip_address: value }))
                                }
                                disabled={busy}
                            />
                        </ControlGroup>
                        <ControlGroup label="FQDN" labelPosition="top">
                            <Text
                                value={draft.fqdn}
                                onChange={(e, { value }) =>
                                    setDraft((d) => ({ ...d, fqdn: value }))
                                }
                                disabled={busy}
                            />
                        </ControlGroup>
                        <ControlGroup label="Asset type" labelPosition="top">
                            <Select
                                value={draft.asset_type}
                                onChange={(e, { value }) =>
                                    setDraft((d) => ({ ...d, asset_type: value }))
                                }
                                disabled={busy}
                            >
                                {ASSET_TYPES.map((t) => (
                                    <Select.Option key={t} label={t} value={t} />
                                ))}
                            </Select>
                        </ControlGroup>
                        <Button
                            appearance="primary"
                            disabled={busy || !collectionId}
                            onClick={createHost}
                            label="Create host"
                        />
                    </div>
                ) : null}
                {loading ? (
                    <WaitSpinner />
                ) : (
                    <Table stripeRows>
                        <Table.Head>
                            <Table.HeadCell>Hostname</Table.HeadCell>
                            <Table.HeadCell>IP</Table.HeadCell>
                            <Table.HeadCell>FQDN</Table.HeadCell>
                            <Table.HeadCell>Type</Table.HeadCell>
                            <Table.HeadCell>Actions</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {visibleHosts.length ? (
                                visibleHosts.map((host) => (
                                    <Table.Row key={host._key}>
                                        <Table.Cell>{host.hostname || "—"}</Table.Cell>
                                        <Table.Cell>{host.ip_address || "—"}</Table.Cell>
                                        <Table.Cell>{host.fqdn || "—"}</Table.Cell>
                                        <Table.Cell>{host.asset_type || "—"}</Table.Cell>
                                        <Table.Cell>
                                            <Button
                                                appearance="secondary"
                                                disabled={busy}
                                                onClick={() =>
                                                    window.location.assign(
                                                        viewUrlWithQuery("stig_editor_ui", {
                                                            stig_collection_id: collectionId,
                                                            host_id: host._key,
                                                        })
                                                    )
                                                }
                                                label="Editor"
                                            />
                                            <Button
                                                appearance="secondary"
                                                disabled={busy}
                                                onClick={() => startEdit(host)}
                                                label="Edit"
                                            />
                                            <Button
                                                appearance="destructive"
                                                disabled={busy}
                                                onClick={() => deleteHost(host)}
                                                label="Delete"
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                ))
                            ) : (
                                <Table.Row>
                                    <Table.Cell colSpan={5} align="center">
                                        <div style={{ padding: "20px 12px" }}>
                                            <p style={{ marginTop: 0 }}>
                                                No hosts in this workspace.
                                            </p>
                                            <Button
                                                appearance="primary"
                                                disabled={busy || !collectionId}
                                                onClick={() => setShowAddForm(true)}
                                                label="Add host"
                                            />
                                            <p style={{ marginBottom: 0, fontSize: 13 }}>
                                                <Link
                                                    to={
                                                        viewUrl("stig_import_ui") + "#checklists"
                                                    }
                                                >
                                                    Import checklists
                                                </Link>{" "}
                                                to create hosts automatically.
                                            </p>
                                        </div>
                                    </Table.Cell>
                                </Table.Row>
                            )}
                        </Table.Body>
                    </Table>
                )}

                {editId ? (
                    <div
                        style={{
                            marginTop: 24,
                            padding: 16,
                            border: "1px solid var(--splunk-color-border, #ccc)",
                            borderRadius: 8,
                        }}
                    >
                        <Heading level={4} style={{ marginTop: 0 }}>Edit host</Heading>
                        <div
                            style={{
                                display: "grid",
                                gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
                                gap: 12,
                                alignItems: "end",
                            }}
                        >
                            <ControlGroup label="Hostname" labelPosition="top">
                                <Text
                                    value={editDraft.hostname}
                                    onChange={(e, { value }) =>
                                        setEditDraft((d) => ({ ...d, hostname: value }))
                                    }
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="IP" labelPosition="top">
                                <Text
                                    value={editDraft.ip_address}
                                    onChange={(e, { value }) =>
                                        setEditDraft((d) => ({ ...d, ip_address: value }))
                                    }
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="FQDN" labelPosition="top">
                                <Text
                                    value={editDraft.fqdn}
                                    onChange={(e, { value }) =>
                                        setEditDraft((d) => ({ ...d, fqdn: value }))
                                    }
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="MAC" labelPosition="top">
                                <Text
                                    value={editDraft.mac_address}
                                    onChange={(e, { value }) =>
                                        setEditDraft((d) => ({ ...d, mac_address: value }))
                                    }
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="Role" labelPosition="top">
                                <Text
                                    value={editDraft.role}
                                    onChange={(e, { value }) =>
                                        setEditDraft((d) => ({ ...d, role: value }))
                                    }
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="Asset type" labelPosition="top">
                                <Select
                                    value={editDraft.asset_type}
                                    onChange={(e, { value }) =>
                                        setEditDraft((d) => ({ ...d, asset_type: value }))
                                    }
                                    disabled={busy}
                                >
                                    {ASSET_TYPES.map((t) => (
                                        <Select.Option key={t} label={t} value={t} />
                                    ))}
                                </Select>
                            </ControlGroup>
                        </div>
                        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                            <Button
                                appearance="primary"
                                disabled={busy}
                                onClick={saveEdit}
                                label="Save"
                            />
                            <Button
                                appearance="secondary"
                                disabled={busy}
                                onClick={() => setEditId("")}
                                label="Cancel"
                            />
                        </div>
                    </div>
                ) : null}
            </PagePad>
        </Shell>
    );
}
