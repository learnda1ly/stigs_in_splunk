import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, apiUpload, defaultWorkspaceId, viewUrl, workspaceLabel } from "../api";
import {
    Actions,
    DropHint,
    DropTitle,
    DropZone,
    PagePad,
    ProgressFill,
    ProgressTrack,
    Toolbar,
} from "../layout";

const ACCEPT =
    ".ckl,.cklb,.zip,.xml,application/json,text/xml,application/xml,application/zip";

function detectFormat(name) {
    const lower = String(name || "").toLowerCase();
    if (lower.endsWith(".zip")) {
        return "zip";
    }
    if (lower.endsWith(".cklb")) {
        return "cklb";
    }
    if (lower.endsWith(".ckl")) {
        return "ckl";
    }
    if (lower.endsWith("-results.xml") || lower.endsWith("_results.xml")) {
        return "xccdf-results";
    }
    return "";
}

function fileKey(file) {
    return [file.name, file.size, file.lastModified].join(":");
}

function contentTypeFor(fmt) {
    if (fmt === "cklb") {
        return "application/json";
    }
    return "application/xml";
}

function statsLine(stats) {
    if (!stats) {
        return "—";
    }
    const parts = [
        ["fail", "Open"],
        ["pass", "NF"],
        ["notapplicable", "NA"],
        ["notchecked", "NR"],
    ]
        .map(([key, label]) => {
            const n = stats[key] || 0;
            return n ? n + " " + label : "";
        })
        .filter(Boolean);
    return parts.join(" · ") || "—";
}

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error("read failed"));
        reader.readAsText(file);
    });
}

export default function ChecklistImportPanel() {
    const inputRef = useRef(null);
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [newName, setNewName] = useState("");
    const [rows, setRows] = useState([]);
    const [busy, setBusy] = useState(false);
    const [over, setOver] = useState(false);
    const [banner, setBanner] = useState(null);

    const loadCollections = () =>
        apiGet("stig_collections")
            .then((colls) => {
                const list = Array.isArray(colls) ? colls : [];
                setCollections(list);
                setCollectionId((prev) => {
                    if (prev && list.some((c) => c._key === prev)) {
                        return prev;
                    }
                    const def = list.find((c) => c._key === defaultWorkspaceId(list));
                    return def ? def._key : list[0] ? list[0]._key : "";
                });
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load workspaces: " + err.message,
                })
            );

    useEffect(() => {
        loadCollections();
    }, []);

    const addFiles = (fileList) => {
        const incoming = Array.from(fileList || []);
        const next = [];
        incoming.forEach((file) => {
            const fmt = detectFormat(file.name);
            next.push({
                key: fileKey(file),
                file,
                name: file.name,
                format: fmt,
                status: fmt ? "queued" : "error",
                error: fmt
                    ? ""
                    : "Supported: .ckl, .cklb, .zip archives, or XCCDF *-results.xml.",
                host: "",
                checklists: 0,
                reviews: 0,
                stats: null,
                created: false,
            });
        });
        if (!next.length) {
            return;
        }
        setRows((prev) => {
            const seen = {};
            prev.forEach((row) => {
                seen[row.key] = true;
            });
            return prev.concat(next.filter((row) => !seen[row.key]));
        });
        setBanner(null);
    };

    const queued = useMemo(
        () => rows.filter((row) => row.status === "queued" && row.format),
        [rows]
    );
    const done = rows.filter((row) => row.status === "done").length;
    const failed = rows.filter((row) => row.status === "error" && row.format).length;
    const pct = rows.length ? Math.round((done / rows.length) * 100) : 0;

    const createWorkspace = () => {
        const name = newName.trim();
        if (!name) {
            setBanner({ type: "warning", text: "Enter a workspace name." });
            return;
        }
        setBusy(true);
        apiFetch("stig_collections", { method: "POST", body: { name } })
            .then((rec) => {
                setNewName("");
                setBanner({ type: "success", text: "Created workspace " + name + "." });
                return loadCollections().then(() => {
                    if (rec && rec._key) {
                        setCollectionId(rec._key);
                    }
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Create workspace failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const importOne = (row) => {
        setRows((prev) =>
            prev.map((item) =>
                item.key === row.key ? { ...item, status: "uploading", error: "" } : item
            )
        );
        if (row.format === "zip") {
            return readFileAsArrayBuffer(row.file)
                .then((buffer) =>
                    apiUpload("stig_imports", {
                        query: {
                            stig_collection_id: collectionId,
                            format: "zip",
                            source_uri: row.name,
                        },
                        contentType: "application/zip",
                        body: buffer,
                    })
                )
                .then((doc) => applyZipImportResult(row.key, doc))
                .catch((err) => applyRowError(row.key, err.message));
        }
        return readFile(row.file)
            .then((text) =>
                apiUpload("stig_imports", {
                    query: {
                        stig_collection_id: collectionId,
                        format: row.format,
                        source_uri: row.name,
                    },
                    contentType: contentTypeFor(row.format),
                    body: text,
                })
            )
            .then((doc) => applySingleImportResult(row.key, doc))
            .catch((err) => applyRowError(row.key, err.message));
    };

    const applyRowError = (key, message) => {
        setRows((prev) =>
            prev.map((item) =>
                item.key === key ? { ...item, status: "error", error: message } : item
            )
        );
    };

    const applySingleImportResult = (key, doc) => {
        const checklists = (doc && doc.checklists) || [];
        setRows((prev) =>
            prev.map((item) =>
                item.key === key
                    ? {
                          ...item,
                          status: "done",
                          host: (doc.host && doc.host.hostname) || "",
                          checklists: checklists.length,
                          reviews: doc.finding_count || 0,
                          stats: doc.stats || null,
                          created:
                              !!(doc.host && doc.host.created) ||
                              checklists.some((cl) => cl.created),
                          error: "",
                      }
                    : item
            )
        );
    };

    const applyZipImportResult = (parentKey, doc) => {
        const results = (doc && doc.results) || [];
        const summary = (doc && doc.summary) || {};
        const memberRows = results.map((entry, index) => {
            const name = entry.source_uri || "member-" + (index + 1);
            const ok = entry.status === "ok";
            return {
                key: parentKey + ":" + name + ":" + index,
                file: null,
                name,
                format: entry.format || "ckl",
                status: ok ? "done" : "error",
                error: ok ? "" : entry.error || "Import failed",
                host: ok ? (entry.host && entry.host.hostname) || "—" : "—",
                checklists: ok ? (entry.checklists || []).length : 0,
                reviews: ok ? entry.finding_count || 0 : 0,
                stats: ok ? entry.stats || null : null,
                created: ok ? !!entry.created : false,
            };
        });
        setRows((prev) => {
            const withoutParent = prev.filter((item) => item.key !== parentKey);
            if (!memberRows.length) {
                return withoutParent.concat([
                    {
                        key: parentKey,
                        file: null,
                        name: "archive",
                        format: "zip",
                        status: "error",
                        error: "Zip import returned no file results",
                        host: "",
                        checklists: 0,
                        reviews: 0,
                        stats: null,
                        created: false,
                    },
                ]);
            }
            return withoutParent.concat(memberRows);
        });
        if (summary.failed) {
            setBanner({
                type: "warning",
                text:
                    "Archive import finished with " +
                    summary.failed +
                    " failed and " +
                    (summary.succeeded || 0) +
                    " succeeded file(s).",
            });
        }
    };

    const readFileAsArrayBuffer = (file) =>
        new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(reader.error || new Error("read failed"));
            reader.readAsArrayBuffer(file);
        });

    const startImport = () => {
        if (!collectionId) {
            setBanner({ type: "warning", text: "Select a workspace first." });
            return;
        }
        const pending = rows.filter((row) => row.status === "queued" && row.format);
        if (!pending.length) {
            setBanner({
                type: "warning",
                text: "Add at least one .ckl, .cklb, .zip, or XCCDF results file.",
            });
            return;
        }
        setBusy(true);
        setBanner({
            type: "info",
            text: "Importing " + pending.length + " file" + (pending.length === 1 ? "" : "s") + "…",
        });
        pending
            .reduce((chain, row) => chain.then(() => importOne(row)), Promise.resolve())
            .then(() =>
                setBanner({
                    type: "success",
                    text: "Import finished. Open the editor to review findings.",
                })
            )
            .finally(() => setBusy(false));
    };

    const dropDisabled = busy;

    return (
        <>
            <div
                style={{
                    flex: "0 0 auto",
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "flex-end",
                    gap: "12px 16px",
                    padding: "12px 20px",
                    borderBottom: "1px solid var(--splunk-color-border, #ccc)",
                }}
            >
                <Toolbar style={{ flex: 1 }}>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => setCollectionId(value)}
                            placeholder="Select collection"
                            filter
                            disabled={busy}
                        >
                            {collections.map((c) => (
                                <Select.Option
                                    key={c._key}
                                    label={workspaceLabel(c)}
                                    value={c._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                    <ControlGroup label="New workspace" labelPosition="top">
                        <Text
                            value={newName}
                            onChange={(e, { value }) => setNewName(value)}
                            placeholder="Name"
                            disabled={busy}
                        />
                    </ControlGroup>
                    <Button
                        appearance="secondary"
                        disabled={busy}
                        onClick={createWorkspace}
                        label="Create"
                    />
                    <Button
                        appearance="primary"
                        disabled={busy || !collectionId || !queued.length}
                        onClick={startImport}
                        label={busy ? "Importing…" : "Import queued files"}
                    />
                </Toolbar>
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        color: "var(--splunk-color-content-muted)",
                        fontSize: 12,
                    }}
                >
                    <span>
                        {rows.length} file{rows.length === 1 ? "" : "s"}
                    </span>
                    <ProgressTrack title={pct + "% imported"}>
                        <ProgressFill $pct={pct} />
                    </ProgressTrack>
                </div>
            </div>
            <PagePad>
                <p style={{ maxWidth: 760, marginTop: 0 }}>
                    Drop STIG Viewer <code>.ckl</code>, <code>.cklb</code>, or a{" "}
                    <code>.zip</code> archive of checklists into a workspace. Each
                    finding is indexed through HEC as <code>stig:finding</code>. DISA
                    XCCDF benchmarks are imported in the{" "}
                    <Link onClick={() => document.getElementById("baselines")?.scrollIntoView()}>
                        Baselines
                    </Link>{" "}
                    section below. Create workspaces under{" "}
                    <Link to={viewUrl("configuration")}>Configuration</Link>. Incoming
                    results overwrite matching checks unless the finding is locked in the
                    editor.
                    <br />
                    <strong>XCCDF scan results</strong> (single <code>*-results.xml</code>{" "}
                    file) upload here; multi-file results archives are not supported — use
                    REST/HEC per README.
                </p>
                {banner ? (
                    <Message
                        appearance={banner.type}
                        onRequestRemove={() => setBanner(null)}
                    >
                        {banner.text}
                    </Message>
                ) : null}
                <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPT}
                    multiple
                    style={{ display: "none" }}
                    onChange={(e) => {
                        addFiles(e.target.files);
                        e.target.value = "";
                    }}
                />
                <DropZone
                    className={(over ? "is-over" : "") + (dropDisabled ? " is-disabled" : "")}
                    onClick={() => {
                        if (!dropDisabled && inputRef.current) {
                            inputRef.current.click();
                        }
                    }}
                    onDragEnter={(e) => {
                        e.preventDefault();
                        if (!dropDisabled) {
                            setOver(true);
                        }
                    }}
                    onDragOver={(e) => {
                        e.preventDefault();
                    }}
                    onDragLeave={() => setOver(false)}
                    onDrop={(e) => {
                        e.preventDefault();
                        setOver(false);
                        if (!dropDisabled) {
                            addFiles(e.dataTransfer.files);
                        }
                    }}
                >
                    <DropTitle>Drop checklists, zip archives, or XCCDF results here</DropTitle>
                    <DropHint>
                        {collectionId
                            ? "Or click to browse. Existing hosts and checklists in this workspace are updated."
                            : "Create or select a workspace before uploading."}
                    </DropHint>
                </DropZone>
                <div style={{ marginTop: 20 }}>
                    {busy && !rows.length ? (
                        <WaitSpinner size="medium" />
                    ) : (
                        <Table stripeRows>
                            <Table.Head>
                                <Table.HeadCell>File</Table.HeadCell>
                                <Table.HeadCell>Format</Table.HeadCell>
                                <Table.HeadCell>Host</Table.HeadCell>
                                <Table.HeadCell>Checklists</Table.HeadCell>
                                <Table.HeadCell>Findings</Table.HeadCell>
                                <Table.HeadCell>Results</Table.HeadCell>
                                <Table.HeadCell>Status</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {rows.length ? (
                                    rows.map((row) => (
                                        <Table.Row key={row.key}>
                                            <Table.Cell>{row.name}</Table.Cell>
                                            <Table.Cell>
                                                {row.format
                                                    ? row.format === "xccdf-results"
                                                        ? "XCCDF"
                                                        : row.format.toUpperCase()
                                                    : "—"}
                                            </Table.Cell>
                                            <Table.Cell>{row.host || "—"}</Table.Cell>
                                            <Table.Cell>
                                                {row.status === "done" ? row.checklists : "—"}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {row.status === "done" ? row.reviews : "—"}
                                            </Table.Cell>
                                            <Table.Cell>{statsLine(row.stats)}</Table.Cell>
                                            <Table.Cell>
                                                {row.status === "uploading"
                                                    ? "Uploading…"
                                                    : row.status === "done"
                                                      ? row.created
                                                          ? "Created"
                                                          : "Updated"
                                                      : row.status === "error"
                                                        ? row.error
                                                        : "Queued"}
                                            </Table.Cell>
                                        </Table.Row>
                                    ))
                                ) : (
                                    <Table.Row>
                                        <Table.Cell align="center" colSpan={7}>
                                            No files queued.
                                        </Table.Cell>
                                    </Table.Row>
                                )}
                            </Table.Body>
                        </Table>
                    )}
                </div>
                <Actions>
                    <span>
                        {done} imported
                        {failed ? " · " + failed + " failed" : ""}
                    </span>
                    <Button
                        appearance="secondary"
                        disabled={busy || !rows.length}
                        onClick={() => setRows([])}
                        label="Clear list"
                    />
                </Actions>
            </PagePad>
        </>
    );
}
