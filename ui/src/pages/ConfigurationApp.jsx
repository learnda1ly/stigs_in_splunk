import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet } from "../api";
import ConfigurationStepper from "../components/ConfigurationStepper";
import { CONFIGURATION_STEPS } from "../configurationSteps";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    SectionBlock,
    Shell,
    Toolbar,
} from "../layout";

const SYSTEM_PACKAGE_ID = "-1";
const CURRENT_STEP_ID = CONFIGURATION_STEPS[0].id;

function sortPackages(rows) {
    return [...(rows || [])].sort((a, b) => {
        const aSys = a.is_system ? 0 : 1;
        const bSys = b.is_system ? 0 : 1;
        if (aSys !== bSys) {
            return aSys - bSys;
        }
        return String(a._key || "").localeCompare(String(b._key || ""), undefined, {
            numeric: true,
        });
    });
}

function ConfigurationRmfPackagesStep({ canAdmin }) {
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
            setDrafts((prev) => {
                const next = { ...prev };
                list.forEach((row) => {
                    const key = row._key;
                    if (!key) {
                        return;
                    }
                    if (!next[key]) {
                        next[key] = {
                            id: key,
                            name: row.name || "",
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
        loadPackages();
    }, [loadPackages]);

    const adminHint = useMemo(() => {
        if (canAdmin === false) {
            return "View-only: stig_admin (or Splunk admin) is required to add or edit packages.";
        }
        if (canAdmin === true) {
            return "You can add packages and edit ids and names. The unassigned system package (-1) cannot be renamed or removed.";
        }
        return "";
    }, [canAdmin]);

    function updateDraft(pkgId, field, value) {
        setDrafts((d) => ({
            ...d,
            [pkgId]: {
                ...(d[pkgId] || { id: pkgId, name: "" }),
                [field]: value,
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
        const isSystem = pkgId === SYSTEM_PACKAGE_ID;
        if (isSystem && newId !== SYSTEM_PACKAGE_ID) {
            setError("The unassigned package id cannot be changed.");
            return;
        }
        if (
            !isSystem &&
            newId &&
            newId !== pkgId &&
            !window.confirm(
                "Change package id from " + pkgId + " to " + newId + "? Related assignments will be updated."
            )
        ) {
            return;
        }
        setBusyKey(pkgId);
        try {
            if (!isSystem && newId && newId !== pkgId) {
                await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                    method: "PATCH",
                    body: { id: newId, name },
                });
                setInfo("Package updated.");
            } else {
                await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                    method: "PATCH",
                    body: { name },
                });
                setInfo("Package saved.");
            }
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
        if (id === SYSTEM_PACKAGE_ID) {
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
                    <Table.HeadCell width={140}>Actions</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {packages.map((row) => {
                        const pkgId = row._key;
                        const isSystem = pkgId === SYSTEM_PACKAGE_ID || row.is_system;
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
                                        <Button
                                            label="Save"
                                            disabled={busyKey === pkgId}
                                            onClick={() => saveExisting(pkgId)}
                                        />
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

export default function ConfigurationApp() {
    const [canAdmin, setCanAdmin] = useState(null);

    useEffect(() => {
        apiGet("stig_readiness")
            .then((report) => {
                if (report && typeof report.can_stig_admin === "boolean") {
                    setCanAdmin(report.can_stig_admin);
                } else {
                    setCanAdmin(false);
                }
            })
            .catch(() => setCanAdmin(false));
    }, []);

    const stepContent = useMemo(() => {
        if (CURRENT_STEP_ID === "rmf_packages") {
            return <ConfigurationRmfPackagesStep canAdmin={canAdmin} />;
        }
        return null;
    }, [canAdmin]);

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>Setup</BrandKicker>
                    <Heading level={1}>Configuration</Heading>
                </Brand>
                <Toolbar>
                    <Button
                        label="Refresh"
                        onClick={() => window.location.reload()}
                    />
                </Toolbar>
            </Header>
            <PagePad>
                <ConfigurationStepper
                    steps={CONFIGURATION_STEPS}
                    currentStepId={CURRENT_STEP_ID}
                />
                {stepContent}
            </PagePad>
        </Shell>
    );
}
