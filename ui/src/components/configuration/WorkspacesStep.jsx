import React, { useCallback, useEffect, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet } from "../../api";
import { SectionBlock } from "../../layout";

export default function WorkspacesStep({ canWrite, canAdmin }) {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [drafts, setDrafts] = useState({});
    const [newName, setNewName] = useState("");
    const [newDescription, setNewDescription] = useState("");
    const [busyKey, setBusyKey] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const list = await apiGet("stig_collections");
            const arr = Array.isArray(list) ? list : [];
            setRows(arr);
            setDrafts((prev) => {
                const next = { ...prev };
                arr.forEach((row) => {
                    const key = row._key;
                    if (!key) {
                        return;
                    }
                    if (!next[key]) {
                        next[key] = {
                            name: row.name || "",
                            description: row.description || "",
                        };
                    }
                });
                return next;
            });
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    function updateDraft(key, field, value) {
        setDrafts((d) => ({
            ...d,
            [key]: { ...(d[key] || {}), [field]: value },
        }));
    }

    async function saveRow(key) {
        if (!canWrite) {
            setError("stig_write is required to edit workspaces.");
            return;
        }
        const draft = drafts[key] || {};
        const name = String(draft.name || "").trim();
        if (!name) {
            setError("Workspace name is required.");
            return;
        }
        setBusyKey(key);
        setError("");
        try {
            await apiFetch("stig_collections/" + encodeURIComponent(key), {
                method: "PATCH",
                body: {
                    name,
                    description: String(draft.description || ""),
                },
            });
            setInfo("Workspace saved.");
            await load();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function createWorkspace() {
        if (!canWrite) {
            setError("stig_write is required to create workspaces.");
            return;
        }
        const name = newName.trim();
        if (!name) {
            setError("Name is required for a new workspace.");
            return;
        }
        setBusyKey("new");
        setError("");
        try {
            await apiFetch("stig_collections", {
                method: "POST",
                body: { name, description: newDescription.trim() },
            });
            setNewName("");
            setNewDescription("");
            setInfo("Workspace created.");
            await load();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function removeRow(row) {
        if (!canAdmin) {
            setError("stig_admin is required to delete workspaces.");
            return;
        }
        if (row.is_default) {
            setError("Cannot delete the default workspace.");
            return;
        }
        const name = row.name || row._key;
        if (!window.confirm("Delete workspace \"" + name + "\"? Empty workspaces only.")) {
            return;
        }
        setBusyKey(row._key);
        setError("");
        try {
            await apiFetch("stig_collections/" + encodeURIComponent(row._key), {
                method: "DELETE",
            });
            setInfo("Workspace deleted.");
            await load();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    return (
        <SectionBlock>
            <Heading level={2}>Workspaces</Heading>
            {loading ? <WaitSpinner /> : null}
            {error ? (
                <Message type="error" style={{ marginTop: 12 }}>{error}</Message>
            ) : null}
            {info ? (
                <Message type="info" style={{ marginTop: 12 }}>{info}</Message>
            ) : null}
            <Table style={{ marginTop: 16 }}>
                <Table.Head>
                    <Table.HeadCell>Name</Table.HeadCell>
                    <Table.HeadCell>Description</Table.HeadCell>
                    <Table.HeadCell width={200}>Actions</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {rows.map((row) => {
                        const key = row._key;
                        const draft = drafts[key] || {
                            name: row.name || "",
                            description: row.description || "",
                        };
                        const isDefault = row.is_default;
                        return (
                            <Table.Row key={key}>
                                <Table.Cell>
                                    {canWrite ? (
                                        <Text
                                            value={draft.name}
                                            onChange={(_, { value }) =>
                                                updateDraft(key, "name", value)
                                            }
                                        />
                                    ) : (
                                        row.name || "—"
                                    )}
                                    {isDefault ? " (default)" : ""}
                                </Table.Cell>
                                <Table.Cell>
                                    {canWrite ? (
                                        <Text
                                            value={draft.description}
                                            onChange={(_, { value }) =>
                                                updateDraft(key, "description", value)
                                            }
                                        />
                                    ) : (
                                        row.description || "—"
                                    )}
                                </Table.Cell>
                                <Table.Cell>
                                    {canWrite ? (
                                        <>
                                            <Button
                                                label="Save"
                                                disabled={busyKey === key}
                                                onClick={() => saveRow(key)}
                                            />
                                            {canAdmin && !isDefault ? (
                                                <Button
                                                    label="Remove"
                                                    appearance="destructive"
                                                    disabled={busyKey === key}
                                                    onClick={() => removeRow(row)}
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
                    {canWrite ? (
                        <Table.Row key="__new__">
                            <Table.Cell>
                                <Text
                                    placeholder="New workspace name"
                                    value={newName}
                                    onChange={(_, { value }) => setNewName(value)}
                                />
                            </Table.Cell>
                            <Table.Cell>
                                <Text
                                    placeholder="Description"
                                    value={newDescription}
                                    onChange={(_, { value }) => setNewDescription(value)}
                                />
                            </Table.Cell>
                            <Table.Cell>
                                <Button
                                    label="Add"
                                    disabled={busyKey === "new"}
                                    onClick={createWorkspace}
                                />
                            </Table.Cell>
                        </Table.Row>
                    ) : null}
                </Table.Body>
            </Table>
        </SectionBlock>
    );
}
