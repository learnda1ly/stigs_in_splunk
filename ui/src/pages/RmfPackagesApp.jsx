import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import TextArea from "@splunk/react-ui/TextArea";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import {
    apiFetch,
    apiGet,
    defaultWorkspaceId,
    isAllWorkspaces,
    workspaceScopeQuery,
} from "../api";
import WorkspaceSelect from "../components/WorkspaceSelect";
import {
    Brand,
    BrandKicker,
    FormCard,
    FormRow,
    Header,
    PageIntro,
    PagePad,
    SectionBlock,
    Shell,
    Toolbar,
    TwoColGrid,
} from "../layout";

const SYSTEM_PACKAGE_ID = "-1";

function normalizeHostname(value) {
    return String(value || "").trim().toLowerCase();
}

function packageLabel(packages, id) {
    const row = (packages || []).find((p) => p._key === id);
    if (!row) {
        return id || "—";
    }
    const name = (row.name || "").trim();
    return name ? name + " (" + id + ")" : id;
}

function resolveRmfPackage(hostname, baselineRef, defaults, overrides) {
    const hostKey = normalizeHostname(hostname);
    if (!hostKey) {
        return { package_id: SYSTEM_PACKAGE_ID, source: "unassigned" };
    }
    const bref = String(baselineRef || "").trim();
    if (bref) {
        const match = (overrides || []).find(
            (row) =>
                normalizeHostname(row.hostname) === hostKey &&
                String(row.baseline_ref || "")
                    .trim()
                    .toLowerCase() === bref.toLowerCase()
        );
        if (match && match.package_id) {
            return { package_id: String(match.package_id), source: "override" };
        }
    }
    const def = (defaults || []).find(
        (row) =>
            normalizeHostname(row.hostname) === hostKey ||
            normalizeHostname(row._key) === hostKey
    );
    if (def && def.package_id) {
        return { package_id: String(def.package_id), source: "host default" };
    }
    return { package_id: SYSTEM_PACKAGE_ID, source: "unassigned" };
}

export default function RmfPackagesApp() {
    const [canAdmin, setCanAdmin] = useState(null);
    const [packages, setPackages] = useState([]);
    const [defaults, setDefaults] = useState([]);
    const [overrides, setOverrides] = useState([]);
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [hosts, setHosts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");

    const [newPackageId, setNewPackageId] = useState("");
    const [newPackageName, setNewPackageName] = useState("");
    const [showCreatePackage, setShowCreatePackage] = useState(false);

    const [nameDraft, setNameDraft] = useState({});
    const [idDraft, setIdDraft] = useState({});

    const [defaultHost, setDefaultHost] = useState("");
    const [defaultPackageId, setDefaultPackageId] = useState("");

    const [overrideHost, setOverrideHost] = useState("");
    const [overrideBaseline, setOverrideBaseline] = useState("");
    const [overridePackageId, setOverridePackageId] = useState("");

    const [bulkJson, setBulkJson] = useState(
        '[\n  {"host": "web01.example.mil", "baseline": "RHEL_8_STIG", "package_id": "100001"}\n]'
    );

    const [previewHost, setPreviewHost] = useState("");
    const [previewBaseline, setPreviewBaseline] = useState("");

    const packageOptions = useMemo(
        () =>
            (packages || []).map((row) => ({
                label: packageLabel(packages, row._key),
                value: row._key,
            })),
        [packages]
    );

    const loadCore = useCallback(async () => {
        const [pkgRows, defRows, ovRows, colls] = await Promise.all([
            apiGet("stig_rmf_packages"),
            apiGet("stig_host_rmf_defaults"),
            apiGet("stig_host_baseline_rmf_overrides"),
            apiGet("stig_collections"),
        ]);
        setPackages(Array.isArray(pkgRows) ? pkgRows : []);
        setDefaults(Array.isArray(defRows) ? defRows : []);
        setOverrides(Array.isArray(ovRows) ? ovRows : []);
        setWorkspaces(colls || []);
        return colls || [];
    }, []);

    const loadHosts = useCallback(async (cid, workspaceList) => {
            const list = workspaceList || workspaces;
            if (!cid || isAllWorkspaces(cid)) {
                const ids = (list || [])
                    .map((w) => w._key)
                    .filter(Boolean);
                const chunks = await Promise.all(
                    ids.map((id) =>
                        apiGet("stig_hosts", { stig_collection_id: id }).then(
                            (rows) => (Array.isArray(rows) ? rows : [])
                        )
                    )
                );
                setHosts(chunks.reduce((acc, part) => acc.concat(part), []));
                return;
            }
            const rows = await apiGet("stig_hosts", workspaceScopeQuery(cid));
            setHosts(Array.isArray(rows) ? rows : []);
        },
        [workspaces]
    );

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const colls = await loadCore();
            const def = defaultWorkspaceId(colls);
            const cid = collectionId || def || "";
            if (!collectionId && cid) {
                setCollectionId(cid);
            }
            if (cid) {
                await loadHosts(cid, colls);
            }
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, [collectionId, loadCore, loadHosts]);

    useEffect(() => {
        load();
    }, [load]);

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

    useEffect(() => {
        if (collectionId && workspaces.length) {
            loadHosts(collectionId, workspaces).catch((err) =>
                setError(String(err.message || err))
            );
        }
    }, [collectionId, workspaces, loadHosts]);

    const uniqueHostnames = useMemo(() => {
        const seen = new Set();
        const out = [];
        (hosts || []).forEach((h) => {
            const name = (h.hostname || "").trim();
            const key = normalizeHostname(name);
            if (!key || seen.has(key)) {
                return;
            }
            seen.add(key);
            out.push(name);
        });
        return out.sort((a, b) => a.localeCompare(b));
    }, [hosts]);

    const hostResolutionRows = useMemo(() => {
        return uniqueHostnames.map((hostname) => {
            const resolved = resolveRmfPackage(
                hostname,
                "",
                defaults,
                overrides
            );
            return {
                hostname,
                package_id: resolved.package_id,
                source: resolved.source,
            };
        });
    }, [uniqueHostnames, defaults, overrides]);

    const preview = useMemo(() => {
        if (!previewHost.trim()) {
            return null;
        }
        return resolveRmfPackage(
            previewHost,
            previewBaseline,
            defaults,
            overrides
        );
    }, [previewHost, previewBaseline, defaults, overrides]);

    function clearMessages() {
        setError("");
        setInfo("");
    }

    async function refreshPackages() {
        const rows = await apiGet("stig_rmf_packages");
        setPackages(Array.isArray(rows) ? rows : []);
    }

    async function createPackage() {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin (or Splunk admin) is required to create packages.");
            return;
        }
        const id = (newPackageId || "").trim();
        const name = (newPackageName || "").trim();
        if (!id || !name) {
            setError("Package id and name are required.");
            return;
        }
        try {
            await apiFetch("stig_rmf_packages", {
                method: "POST",
                body: { id, name },
            });
            setNewPackageId("");
            setNewPackageName("");
            setShowCreatePackage(false);
            setInfo("Package created.");
            await refreshPackages();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function savePackageName(pkgId) {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required to rename packages.");
            return;
        }
        const name = (nameDraft[pkgId] || "").trim();
        if (!name) {
            setError("Name cannot be empty.");
            return;
        }
        try {
            await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                method: "PATCH",
                body: { name },
            });
            setInfo("Package name updated.");
            await refreshPackages();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function savePackageId(pkgId) {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required to change package ids.");
            return;
        }
        if (pkgId === SYSTEM_PACKAGE_ID) {
            setError("The system unassigned package id cannot be changed.");
            return;
        }
        const newId = (idDraft[pkgId] || "").trim();
        if (!newId || newId === pkgId) {
            setError("Enter a new id different from the current id.");
            return;
        }
        if (
            !window.confirm(
                "Rename package id " +
                    pkgId +
                    " to " +
                    newId +
                    "? This bulk-updates host defaults, overrides, and review fields."
            )
        ) {
            return;
        }
        try {
            await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                method: "PATCH",
                body: { id: newId },
            });
            setInfo("Package id renamed.");
            await loadCore();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function deletePackage(pkgId) {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required to delete packages.");
            return;
        }
        if (pkgId === SYSTEM_PACKAGE_ID) {
            setError("The system unassigned package cannot be deleted.");
            return;
        }
        if (!window.confirm("Delete package " + pkgId + "?")) {
            return;
        }
        try {
            await apiFetch("stig_rmf_packages/" + encodeURIComponent(pkgId), {
                method: "DELETE",
            });
            setInfo("Package deleted.");
            await refreshPackages();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function saveHostDefault() {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required to set host defaults.");
            return;
        }
        const host = (defaultHost || "").trim();
        const package_id = (defaultPackageId || "").trim();
        if (!host || !package_id) {
            setError("Hostname and package are required.");
            return;
        }
        try {
            await apiFetch("stig_host_rmf_defaults", {
                method: "POST",
                body: { hostname: host, package_id },
            });
            setDefaultHost("");
            setInfo("Host default saved.");
            const defRows = await apiGet("stig_host_rmf_defaults");
            setDefaults(Array.isArray(defRows) ? defRows : []);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function saveOverride() {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required to set overrides.");
            return;
        }
        const host = (overrideHost || "").trim();
        const baseline_ref = (overrideBaseline || "").trim();
        const package_id = (overridePackageId || "").trim();
        if (!host || !baseline_ref || !package_id) {
            setError("Hostname, baseline, and package are required.");
            return;
        }
        try {
            await apiFetch("stig_host_baseline_rmf_overrides", {
                method: "POST",
                body: {
                    hostname: host,
                    baseline_ref,
                    package_id,
                },
            });
            setOverrideHost("");
            setOverrideBaseline("");
            setInfo("Host/baseline override saved.");
            const ovRows = await apiGet("stig_host_baseline_rmf_overrides");
            setOverrides(Array.isArray(ovRows) ? ovRows : []);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function clearOverride(key) {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required.");
            return;
        }
        try {
            await apiFetch(
                "stig_host_baseline_rmf_overrides/" + encodeURIComponent(key),
                { method: "DELETE" }
            );
            setInfo("Override removed.");
            const ovRows = await apiGet("stig_host_baseline_rmf_overrides");
            setOverrides(Array.isArray(ovRows) ? ovRows : []);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function runBulkAssign() {
        clearMessages();
        if (!canAdmin) {
            setError("stig_admin is required for bulk assignment.");
            return;
        }
        let assignments;
        try {
            assignments = JSON.parse(bulkJson || "[]");
        } catch (e) {
            setError("Bulk JSON must be a valid array.");
            return;
        }
        if (!Array.isArray(assignments)) {
            setError("Bulk JSON must be an array of rows.");
            return;
        }
        try {
            const result = await apiFetch(
                "stig_rmf_packages/assignments/bulk",
                {
                    method: "POST",
                    body: { assignments },
                }
            );
            const errors = (result && result.errors) || [];
            if (errors.length) {
                setError(
                    "Applied " +
                        (result.applied || 0) +
                        " row(s); " +
                        errors.length +
                        " error(s). First: " +
                        (errors[0].error || "unknown")
                );
            } else {
                setInfo(
                    "Bulk assignment applied to " + (result.applied || 0) + " row(s)."
                );
            }
            const [defRows, ovRows] = await Promise.all([
                apiGet("stig_host_rmf_defaults"),
                apiGet("stig_host_baseline_rmf_overrides"),
            ]);
            setDefaults(Array.isArray(defRows) ? defRows : []);
            setOverrides(Array.isArray(ovRows) ? ovRows : []);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    const adminHint =
        canAdmin === false
            ? "Signed-in user cannot create, rename, or assign packages (stig_admin required). You can still view packages and resolution."
            : canAdmin === true
              ? "You have stig_admin (or Splunk admin): create, rename, and assign are enabled."
              : "";

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>Admin</BrandKicker>
                    <Heading level={1}>RMF packages</Heading>
                </Brand>
                <Toolbar>
                    <WorkspaceSelect
                        workspaces={workspaces}
                        value={collectionId}
                        onChange={setCollectionId}
                        includeAllWorkspaces
                        label="Hosts scope (resolution preview)"
                    />
                    <Button label="Refresh" onClick={load} disabled={loading} />
                </Toolbar>
            </Header>
            <PagePad>
                {loading ? <WaitSpinner /> : null}
                {error ? (
                    <Message type="error" style={{ marginBottom: 12 }}>
                        {error}
                    </Message>
                ) : null}
                {info ? (
                    <Message type="info" style={{ marginBottom: 12 }}>
                        {info}
                    </Message>
                ) : null}
                {adminHint ? (
                    <Message
                        type={canAdmin ? "info" : "warning"}
                        style={{ marginBottom: 12 }}
                    >
                        {adminHint}
                    </Message>
                ) : null}

                <PageIntro>
                    <p>
                        RMF packages group findings for authorization boundaries.
                        Assignments are global per hostname (default) with optional
                        host+baseline overrides. Findings inherit resolved package{" "}
                        <code>rmf_package_id</code> (override → host default →{" "}
                        <code>-1</code> unassigned).
                    </p>
                </PageIntro>

                <TwoColGrid>
                    <SectionBlock>
                        <Heading level={2}>Packages</Heading>
                        {canAdmin ? (
                            <Button
                                label={
                                    showCreatePackage
                                        ? "Cancel create"
                                        : "Create package"
                                }
                                onClick={() => setShowCreatePackage(!showCreatePackage)}
                                style={{ marginTop: 8 }}
                            />
                        ) : null}
                        {showCreatePackage && canAdmin ? (
                            <FormCard>
                                <FormRow $columns="1fr 1fr">
                                    <ControlGroup label="Package id (typed)">
                                        <Text
                                            value={newPackageId}
                                            onChange={(_, { value }) =>
                                                setNewPackageId(value)
                                            }
                                        />
                                    </ControlGroup>
                                    <ControlGroup label="Name">
                                        <Text
                                            value={newPackageName}
                                            onChange={(_, { value }) =>
                                                setNewPackageName(value)
                                            }
                                        />
                                    </ControlGroup>
                                </FormRow>
                                <Button label="Save package" onClick={createPackage} />
                            </FormCard>
                        ) : null}
                        <Table style={{ marginTop: 12 }}>
                            <Table.Head>
                                <Table.HeadCell>Id</Table.HeadCell>
                                <Table.HeadCell>Name</Table.HeadCell>
                                <Table.HeadCell width={200}>Actions</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {(packages || []).map((row) => {
                                    const pid = row._key;
                                    const isSystem = Boolean(row.is_system);
                                    return (
                                        <Table.Row key={pid}>
                                            <Table.Cell>
                                                <code>{pid}</code>
                                                {isSystem ? " (system)" : ""}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {canAdmin && !isSystem ? (
                                                    <Text
                                                        value={
                                                            nameDraft[pid] !== undefined
                                                                ? nameDraft[pid]
                                                                : row.name || ""
                                                        }
                                                        onChange={(_, { value }) =>
                                                            setNameDraft((d) => ({
                                                                ...d,
                                                                [pid]: value,
                                                            }))
                                                        }
                                                    />
                                                ) : (
                                                    row.name || "—"
                                                )}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {canAdmin && !isSystem ? (
                                                    <>
                                                        <Button
                                                            label="Save name"
                                                            onClick={() =>
                                                                savePackageName(pid)
                                                            }
                                                        />
                                                        <Text
                                                            placeholder="New id"
                                                            value={idDraft[pid] || ""}
                                                            onChange={(_, { value }) =>
                                                                setIdDraft((d) => ({
                                                                    ...d,
                                                                    [pid]: value,
                                                                }))
                                                            }
                                                            style={{ marginTop: 6 }}
                                                        />
                                                        <Button
                                                            label="Rename id"
                                                            onClick={() =>
                                                                savePackageId(pid)
                                                            }
                                                            style={{ marginTop: 6 }}
                                                        />
                                                        <Button
                                                            label="Delete"
                                                            onClick={() =>
                                                                deletePackage(pid)
                                                            }
                                                            style={{ marginTop: 6 }}
                                                        />
                                                    </>
                                                ) : canAdmin && isSystem ? (
                                                    <span>System package</span>
                                                ) : (
                                                    "—"
                                                )}
                                            </Table.Cell>
                                        </Table.Row>
                                    );
                                })}
                            </Table.Body>
                        </Table>
                    </SectionBlock>

                    <SectionBlock>
                        <Heading level={2}>Resolution preview</Heading>
                        <FormCard>
                            <FormRow $columns="1fr 1fr">
                                <ControlGroup label="Hostname">
                                    <Text
                                        value={previewHost}
                                        onChange={(_, { value }) =>
                                            setPreviewHost(value)
                                        }
                                    />
                                </ControlGroup>
                                <ControlGroup
                                    label="Baseline (optional)"
                                    help="Omit to see host default / unassigned only."
                                >
                                    <Text
                                        value={previewBaseline}
                                        onChange={(_, { value }) =>
                                            setPreviewBaseline(value)
                                        }
                                    />
                                </ControlGroup>
                            </FormRow>
                            {preview ? (
                                <Message type="info">
                                    Resolves to{" "}
                                    <strong>
                                        {packageLabel(packages, preview.package_id)}
                                    </strong>{" "}
                                    via <em>{preview.source}</em>
                                </Message>
                            ) : null}
                        </FormCard>
                        <Table style={{ marginTop: 12 }}>
                            <Table.Head>
                                <Table.HeadCell>Hostname</Table.HeadCell>
                                <Table.HeadCell>Package</Table.HeadCell>
                                <Table.HeadCell>Source</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {hostResolutionRows.map((row) => (
                                    <Table.Row key={row.hostname}>
                                        <Table.Cell>{row.hostname}</Table.Cell>
                                        <Table.Cell>
                                            {packageLabel(packages, row.package_id)}
                                        </Table.Cell>
                                        <Table.Cell>{row.source}</Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                    </SectionBlock>
                </TwoColGrid>

                <SectionBlock style={{ marginTop: 28 }}>
                    <Heading level={2}>Host default package</Heading>
                    {canAdmin ? (
                        <FormCard>
                            <FormRow $columns="1fr 1fr auto">
                                <ControlGroup label="Hostname (global)">
                                    <Text
                                        value={defaultHost}
                                        onChange={(_, { value }) =>
                                            setDefaultHost(value)
                                        }
                                    />
                                </ControlGroup>
                                <ControlGroup label="Package">
                                    <Select
                                        value={defaultPackageId}
                                        onChange={(_, { value }) =>
                                            setDefaultPackageId(value)
                                        }
                                        placeholder="Select package"
                                    >
                                        {packageOptions.map((opt) => (
                                            <Select.Option
                                                key={opt.value}
                                                label={opt.label}
                                                value={opt.value}
                                            />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <Button
                                    label="Set default"
                                    onClick={saveHostDefault}
                                />
                            </FormRow>
                        </FormCard>
                    ) : null}
                    <Table style={{ marginTop: 12 }}>
                        <Table.Head>
                            <Table.HeadCell>Hostname</Table.HeadCell>
                            <Table.HeadCell>Package</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {(defaults || []).map((row) => (
                                <Table.Row key={row._key || row.hostname}>
                                    <Table.Cell>{row.hostname || row._key}</Table.Cell>
                                    <Table.Cell>
                                        {packageLabel(packages, row.package_id)}
                                    </Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </SectionBlock>

                <SectionBlock style={{ marginTop: 28 }}>
                    <Heading level={2}>Host / baseline overrides</Heading>
                    {canAdmin ? (
                        <FormCard>
                            <FormRow $columns="1fr 1fr 1fr auto">
                                <ControlGroup label="Hostname">
                                    <Text
                                        value={overrideHost}
                                        onChange={(_, { value }) =>
                                            setOverrideHost(value)
                                        }
                                    />
                                </ControlGroup>
                                <ControlGroup label="Baseline ref (id or STIG id)">
                                    <Text
                                        value={overrideBaseline}
                                        onChange={(_, { value }) =>
                                            setOverrideBaseline(value)
                                        }
                                    />
                                </ControlGroup>
                                <ControlGroup label="Package">
                                    <Select
                                        value={overridePackageId}
                                        onChange={(_, { value }) =>
                                            setOverridePackageId(value)
                                        }
                                        placeholder="Select package"
                                    >
                                        {packageOptions.map((opt) => (
                                            <Select.Option
                                                key={opt.value}
                                                label={opt.label}
                                                value={opt.value}
                                            />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <Button label="Set override" onClick={saveOverride} />
                            </FormRow>
                        </FormCard>
                    ) : null}
                    <Table style={{ marginTop: 12 }}>
                        <Table.Head>
                            <Table.HeadCell>Hostname</Table.HeadCell>
                            <Table.HeadCell>Baseline</Table.HeadCell>
                            <Table.HeadCell>Package</Table.HeadCell>
                            <Table.HeadCell width={120} />
                        </Table.Head>
                        <Table.Body>
                            {(overrides || []).map((row) => (
                                <Table.Row key={row._key}>
                                    <Table.Cell>{row.hostname}</Table.Cell>
                                    <Table.Cell>{row.baseline_ref}</Table.Cell>
                                    <Table.Cell>
                                        {packageLabel(packages, row.package_id)}
                                    </Table.Cell>
                                    <Table.Cell>
                                        {canAdmin ? (
                                            <Button
                                                label="Clear"
                                                onClick={() => clearOverride(row._key)}
                                            />
                                        ) : null}
                                    </Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </SectionBlock>

                {canAdmin ? (
                    <SectionBlock style={{ marginTop: 28 }}>
                        <Heading level={2}>Bulk reassignment</Heading>
                        <PageIntro>
                            <p>
                                JSON array of rows:{" "}
                                <code>host</code>, optional <code>baseline</code>{" "}
                                (omit for host default), and <code>package_id</code>.
                            </p>
                        </PageIntro>
                        <FormCard>
                            <ControlGroup label="Assignments JSON">
                                <TextArea
                                    value={bulkJson}
                                    onChange={(_, { value }) => setBulkJson(value)}
                                    rows={8}
                                />
                            </ControlGroup>
                            <Button label="Apply bulk" onClick={runBulkAssign} />
                        </FormCard>
                    </SectionBlock>
                ) : null}
            </PagePad>
        </Shell>
    );
}
