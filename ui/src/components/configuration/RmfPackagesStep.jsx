import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet } from "../../api";
import { SectionBlock } from "../../layout";
import {
    RMF_SYSTEM_PACKAGE_ID,
    sortPackages,
} from "../../types/rmf";

function mergeDraftsFromPackages(prev, list) {
    const next = {};
    list.forEach((row) => {
        const key = row._key;
        if (!key) {
            return;
        }
        const prior = prev[key];
        const serverName = row.name || "";
        if (
            prior &&
            prior.id === key &&
            prior.name === serverName &&
            !prior.dirty
        ) {
            next[key] = prior;
        } else if (prior) {
            next[key] = {
                id: key,
                name: serverName || prior.name,
                dirty: prior.dirty,
            };
        } else {
            next[key] = { id: key, name: serverName, dirty: false };
        }
    });
    return next;
}

export default function RmfPackagesStep({ canAdmin }) {
    const [packages, setPackages] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [drafts, setDrafts] = useState({});
    const [newRow, setNewRow] = useState({ id: "", name: "" });
    const [busyKey, setBusyKey] = useState("");

    const loadPackages = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const rows = await apiGet("stig_rmf_packages");
            const list = sortPackages(Array.isArray(rows) ? rows : []);
            setPackages(list);
            setDrafts((prev) => mergeDraftsFromPackages(prev, list));
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadPackages();
    }, [loadPackages]);

    const adminHint = useMemo(() => {
        if (canAdmin === false) {
            return "View-only: stig_admin (or Splunk admin) is required to add or edit packages.";
        }
        if (canAdmin === true) {
            return "Packages span workspaces. Findings inherit assignment via host defaults and host×baseline overrides (next wizard steps). The unassigned system package (-1) cannot be renamed or removed.";
        }
        return "";
    }, [canAdmin]);

    function updateDraft(pkgId, field, value) {
        setDrafts((d) => ({
            ...d,
            [pkgId]: {
                ...(d[pkgId] || { id: pkgId, name: "" }),
                [field]: value,
                dirty: true,
            },
        }));
    }

    async function saveExisting(pkgId) {
        setError("");
        setInfo("");
        if (!canAdmin) {
            setError("stig_admin is required to save packages.");
            return;
        }
        const draft = drafts[pkgId] || {};
        const name = String(draft.name || "").trim();
        const newId = String(draft.id || "").trim();
        if (!name) {
            setError("Name cannot be empty.");
            return;
        }
        const isSystem = pkgId === RMF_SYSTEM_PACKAGE_ID;
        if (isSystem && newId !== RMF_SYSTEM_PACKAGE_ID) {
            setError("The unassigned package id cannot be changed.");
            return;
        }
        if (!isSystem && newId !== pkgId) {
            setBusyKey(pkgId);
            try {
                await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                    method: "PATCH",
                    body: { id: newId, name },
                });
                setInfo("Package id renamed; assignments and findings were updated.");
                await loadPackages();
            } catch (err) {
                setError(String(err.message || err));
            } finally {
                setBusyKey("");
            }
            return;
        }
        setBusyKey(pkgId);
        try {
            await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                method: "PATCH",
                body: { name },
            });
            setInfo("Package saved.");
            await loadPackages();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function removePackage(pkgId) {
        setError("");
        setInfo("");
        if (!canAdmin) {
            setError("stig_admin is required to remove packages.");
            return;
        }
        if (pkgId === RMF_SYSTEM_PACKAGE_ID) {
            setError("The unassigned system package cannot be removed.");
            return;
        }
        if (!window.confirm("Remove package " + pkgId + "? Assignments will be cleared.")) {
            return;
        }
        setBusyKey(pkgId);
        try {
            await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                method: "DELETE",
            });
            setInfo("Package removed.");
            await loadPackages();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function createPackage() {
        setError("");
        setInfo("");
        if (!canAdmin) {
            setError("stig_admin is required to add packages.");
            return;
        }
        const id = String(newRow.id || "").trim();
        const name = String(newRow.name || "").trim();
        if (!id || !name) {
            setError("Package id and name are required for a new row.");
            return;
        }
        if (id === RMF_SYSTEM_PACKAGE_ID) {
            setError("Package id -1 is reserved for unassigned.");
            return;
        }
        setBusyKey("new");
        try {
            await apiFetch("stig_rmf_packages", {
                method: "POST",
                body: { id, name },
            });
            setNewRow({ id: "", name: "" });
            setInfo("Package added.");
            await loadPackages();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    return (
        <SectionBlock>
            <Heading level={2}>RMF packages</Heading>
            {loading ? <WaitSpinner /> : null}
            {error ? (
                <Message type="error" style={{ marginTop: 12 }}>
                    {error}
                </Message>
            ) : null}
            {info ? (
                <Message type="info" style={{ marginTop: 12 }}>
                    {info}
                </Message>
            ) : null}
            {adminHint ? (
                <Message type={canAdmin ? "info" : "warning"} style={{ marginTop: 12 }}>
                    {adminHint}
                </Message>
            ) : null}
            <Table style={{ marginTop: 16 }}>
                <Table.Head>
                    <Table.HeadCell>Package id</Table.HeadCell>
                    <Table.HeadCell>Name</Table.HeadCell>
                    <Table.HeadCell width={200}>Actions</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {packages.map((row) => {
                        const pkgId = row._key;
                        const isSystem = pkgId === RMF_SYSTEM_PACKAGE_ID || row.is_system;
                        const draft = drafts[pkgId] || {
                            id: pkgId,
                            name: row.name || "",
                        };
                        return (
                            <Table.Row key={pkgId}>
                                <Table.Cell>
                                    {canAdmin && !isSystem ? (
                                        <Text
                                            value={draft.id}
                                            onChange={(_, { value }) =>
                                                updateDraft(pkgId, "id", value)
                                            }
                                        />
                                    ) : (
                                        <code>{pkgId}</code>
                                    )}
                                </Table.Cell>
                                <Table.Cell>
                                    {canAdmin ? (
                                        <Text
                                            value={draft.name}
                                            onChange={(_, { value }) =>
                                                updateDraft(pkgId, "name", value)
                                            }
                                        />
                                    ) : (
                                        row.name || "—"
                                    )}
                                </Table.Cell>
                                <Table.Cell>
                                    {canAdmin ? (
                                        <>
                                            <Button
                                                label="Save"
                                                disabled={busyKey === pkgId}
                                                onClick={() => saveExisting(pkgId)}
                                            />
                                            {!isSystem ? (
                                                <Button
                                                    label="Remove"
                                                    appearance="destructive"
                                                    disabled={busyKey === pkgId}
                                                    onClick={() => removePackage(pkgId)}
                                                />
                                            ) : null}
                                        </>
                                    ) : (
                                        "—"
                                    )}
                                </Table.Cell>
                            </Table.Row>
                        );
                    })}
                    {canAdmin ? (
                        <Table.Row key="__new__">
                            <Table.Cell>
                                <Text
                                    placeholder="New package id"
                                    value={newRow.id}
                                    onChange={(_, { value }) =>
                                        setNewRow((r) => ({ ...r, id: value }))
                                    }
                                />
                            </Table.Cell>
                            <Table.Cell>
                                <Text
                                    placeholder="Name"
                                    value={newRow.name}
                                    onChange={(_, { value }) =>
                                        setNewRow((r) => ({ ...r, name: value }))
                                    }
                                />
                            </Table.Cell>
                            <Table.Cell>
                                <Button
                                    label="Add"
                                    disabled={busyKey === "new"}
                                    onClick={createPackage}
                                />
                            </Table.Cell>
                        </Table.Row>
                    ) : null}
                </Table.Body>
            </Table>
        </SectionBlock>
    );
}
