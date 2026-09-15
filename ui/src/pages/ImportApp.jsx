import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Search from "@splunk/react-ui/Search";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, apiUpload, defaultWorkspaceId, viewUrl, workspaceLabel } from "../api";
import {
    Actions,
    Brand,
    BrandKicker,
    DropHint,
    DropTitle,
    DropZone,
    Header,
    HeaderMeta,
    PagePad,
    ProgressFill,
    ProgressTrack,
    Shell,
    Toolbar,
} from "../layout";

const CHUNK = 4 * 1024 * 1024;

const ACCEPT =
    ".ckl,.cklb,application/json,text/xml,application/xml";

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
    if (lower.endsWith(".xml") || lower.endsWith(".xccdf")) {
        return "xccdf";
    }
    return "";
}

function fileKey(file) {
    return [file.name, file.size, file.lastModified].join(":");
}

function contentTypeFor(fmt) {
    return fmt === "cklb" ? "application/json" : "application/xml";
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

function basename(name) {
    const path = String(name || "").replace(/\\/g, "/");
    const parts = path.split("/").filter(Boolean);
    return parts[parts.length - 1] || path;
}

function bytesToBase64(bytes) {
    let binary = "";
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    }
    return btoa(binary);
}

function formatBytes(n) {
    const size = Number(n) || 0;
    if (!size) {
        return "—";
    }
    if (size < 1024) {
        return size + " B";
    }
    if (size < 1024 * 1024) {
        return (size / 1024).toFixed(1) + " KB";
    }
    return (size / (1024 * 1024)).toFixed(1) + " MB";
}

function patchRow(rows, key, fields) {
    return rows.map((item) => (item.key === key ? { ...item, ...fields } : item));
}

function baselineStatus(row) {
    if (row.status === "scanning") {
        return "Scanning zip…";
    }
    if (row.status === "reading") {
        return "Reading…";
    }
    if (row.status === "uploading") {
        return "Importing…";
    }
    if (row.status === "done") {
        if (row.deduplicated) {
            return "Already present";
        }
        return row.created ? "Created" : "Imported";
    }
    if (row.status === "error") {
        return row.error || "Failed";
    }
    return "Queued";
}

export default function ImportApp() {
    const inputRef = useRef(null);
    const jobIdRef = useRef("");
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [newName, setNewName] = useState("");
    const [rows, setRows] = useState([]);
    const [busy, setBusy] = useState(false);
    const [over, setOver] = useState(false);
    const [banner, setBanner] = useState(null);
    const [phase, setPhase] = useState("");
    const [zipName, setZipName] = useState("");
    const [skipped, setSkipped] = useState(null);
    const [filter, setFilter] = useState("");

    const loadCollections = () =>
        apiGet("stig_collections")
            .then((colls) => {
                const list = Array.isArray(colls) ? colls : [];
                setCollections(list);
                setCollectionId((prev) => {
                    if (prev && list.some((c) => c._key === prev)) {
                        return prev;
                    }
                    return defaultWorkspaceId(list);
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

    const addChecklistFiles = (incoming) => {
        const next = [];
        incoming.forEach((file) => {
            const fmt = detectFormat(file.name);
            next.push({
                key: fileKey(file),
                kind: "checklist",
                file,
                name: file.name,
                path: file.name,
                format: fmt,
                status: fmt ? "queued" : "error",
                error: fmt
                    ? ""
                    : "This page accepts .ckl and .cklb. DISA zips go on Import baselines.",
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

    const importJobMembers = (jobId, pending) => {
        const total = pending.length;
        setPhase("import");
        setBanner({
            type: "info",
            text: "Importing 0/" + total + " Manual-xccdf baselines from the zip…",
        });
        return pending
            .reduce((chain, row, index) => {
                return chain.then(() => {
                    setBanner({
                        type: "info",
                        text:
                            "Importing " +
                            (index + 1) +
                            "/" +
                            total +
                            " · " +
                            row.name,
                    });
                    setRows((prev) =>
                        patchRow(prev, row.key, { status: "uploading", error: "" })
                    );
                    return apiFetch("stig_baselines/jobs/" + jobId, {
                        method: "POST",
                        body: { action: "import", path: row.path },
                    })
                        .then((doc) => {
                            const rec = doc || {};
                            setRows((prev) =>
                                patchRow(prev, row.key, {
                                    status: "done",
                                    stigId: rec.stig_id || rec.ucc_name || "",
                                    version: rec.version || "",
                                    rules: rec.rule_count || 0,
                                    created: !!rec.created && !rec.deduplicated,
                                    deduplicated: !!rec.deduplicated,
                                    error: "",
                                })
                            );
                        })
                        .catch((err) => {
                            setRows((prev) =>
                                patchRow(prev, row.key, {
                                    status: "error",
                                    error: err.message,
                                })
                            );
                        });
                });
            }, Promise.resolve())
            .then(() => total);
    };

    const scanLibraryZip = (file) => {
        jobIdRef.current = "";
        setZipName(file.name);
        setSkipped(null);
        setFilter("");
        setRows([]);
        setBusy(true);
        setPhase("upload");
        let listed = false;
        setBanner({
            type: "info",
            text:
                "Uploading " +
                file.name +
                " (" +
                formatBytes(file.size) +
                ") in 4MB chunks, then importing every Manual-xccdf STIG. Do not use Configuration.",
        });
        apiFetch("stig_baselines/jobs", {
            method: "POST",
            body: { filename: file.name, size: file.size },
        })
            .then((job) => {
                const jobId = job && job.job_id;
                if (!jobId) {
                    throw new Error("no job id from server");
                }
                jobIdRef.current = jobId;
                let offset = 0;
                const send = () => {
                    if (offset >= file.size) {
                        setPhase("scan");
                        setBanner({
                            type: "info",
                            text: "Upload complete. Listing Manual-xccdf baselines…",
                        });
                        return apiFetch("stig_baselines/jobs/" + jobId, {
                            method: "POST",
                            body: { action: "finalize" },
                        });
                    }
                    return file
                        .slice(offset, offset + CHUNK)
                        .arrayBuffer()
                        .then((buf) => {
                            const bytes = new Uint8Array(buf);
                            const at = offset;
                            return apiFetch("stig_baselines/jobs/" + jobId, {
                                method: "POST",
                                body: {
                                    action: "chunk",
                                    offset: at,
                                    data: bytesToBase64(bytes),
                                },
                            }).then(() => {
                                offset += bytes.length;
                                const pctDone = Math.round((offset / file.size) * 100);
                                setBanner({
                                    type: "info",
                                    text:
                                        "Uploading zip " +
                                        pctDone +
                                        "% · " +
                                        formatBytes(offset) +
                                        " / " +
                                        formatBytes(file.size),
                                });
                                return send();
                            });
                        });
                };
                return send();
            })
            .then((result) => {
                const found = (result && result.found) || [];
                const skip = (result && result.skipped) || {};
                setSkipped(skip);
                const nextRows = found.map((item) => ({
                    key: (jobIdRef.current || file.name) + ":" + item.path,
                    kind: "baseline",
                    name: basename(item.path),
                    path: item.path,
                    size: item.size,
                    format: "xccdf",
                    status: "queued",
                    error: "",
                    stigId: "",
                    version: "",
                    rules: 0,
                    created: false,
                    deduplicated: false,
                }));
                setRows(nextRows);
                listed = true;
                const skipBits = [
                    skip.srg ? skip.srg + " SRGs" : "",
                    skip.scap ? skip.scap + " SCAP/OCIL" : "",
                    skip.other ? skip.other + " other files" : "",
                ].filter(Boolean);
                if (!nextRows.length) {
                    throw new Error(
                        "no Manual-xccdf STIG baselines found" +
                            (skipBits.length ? " (skipped " + skipBits.join(", ") + ")" : "")
                    );
                }
                setBanner({
                    type: "info",
                    text:
                        "Found " +
                        nextRows.length +
                        " Manual-xccdf STIG" +
                        (nextRows.length === 1 ? "" : "s") +
                        (skipBits.length ? ". Skipped " + skipBits.join(", ") : "") +
                        ". Importing the full set…",
                });
                return importJobMembers(jobIdRef.current, nextRows).then((total) => ({
                    total,
                    skipBits,
                }));
            })
            .then((summary) => {
                setBanner({
                    type: "success",
                    text:
                        "Finished " +
                        summary.total +
                        " baseline" +
                        (summary.total === 1 ? "" : "s") +
                        " from the zip. Catalog is under Configuration → Baselines. " +
                        "Retry any failures from this page — do not re-upload on Configuration.",
                });
            })
            .catch((err) => {
                if (listed) {
                    setBanner({
                        type: "error",
                        text: "Zip import failed: " + err.message,
                    });
                    return;
                }
                const jobId = jobIdRef.current;
                jobIdRef.current = "";
                setZipName("");
                if (jobId) {
                    apiFetch("stig_baselines/jobs/" + jobId, { method: "DELETE" }).catch(
                        () => null
                    );
                }
                setBanner({
                    type: "error",
                    text: "Zip upload failed: " + err.message,
                });
            })
            .finally(() => {
                setBusy(false);
                setPhase("");
            });
    };

    const retryFailedBaselines = () => {
        const jobId = jobIdRef.current;
        const pending = rows.filter(
            (row) => row.kind === "baseline" && row.status === "error" && row.path
        );
        if (!jobId) {
            setBanner({
                type: "warning",
                text: "Drop the DISA zip on Import — not Configuration → Baselines.",
            });
            return;
        }
        if (!pending.length) {
            return;
        }
        setBusy(true);
        importJobMembers(jobId, pending)
            .then((total) => {
                setBanner({
                    type: "success",
                    text: "Retried " + total + " failed baseline" + (total === 1 ? "" : "s") + ".",
                });
            })
            .catch((err) => {
                setBanner({
                    type: "error",
                    text: "Retry failed: " + err.message,
                });
            })
            .finally(() => {
                setBusy(false);
                setPhase("");
            });
    };

    const importXmlBaselines = (files) => {
        const incoming = Array.from(files || []);
        if (!incoming.length) {
            return;
        }
        const nextRows = incoming.map((file) => ({
            key: fileKey(file),
            kind: "baseline",
            file,
            name: file.name,
            path: file.name,
            size: file.size,
            format: "xccdf",
            status: "queued",
            error: "",
            stigId: "",
            version: "",
            rules: 0,
            created: false,
            deduplicated: false,
        }));
        setRows((prev) => {
            const seen = {};
            prev.forEach((row) => {
                seen[row.key] = true;
            });
            return prev.concat(nextRows.filter((row) => !seen[row.key]));
        });
        setBusy(true);
        setPhase("import");
        incoming
            .reduce((chain, file, index) => {
                return chain.then(() => {
                    const key = fileKey(file);
                    setBanner({
                        type: "info",
                        text:
                            "Importing " +
                            (index + 1) +
                            "/" +
                            incoming.length +
                            " · " +
                            file.name,
                    });
                    setRows((prev) =>
                        patchRow(prev, key, { status: "uploading", error: "" })
                    );
                    return readFile(file).then((xml) =>
                        apiUpload("stig_baselines/import", {
                            query: { format: "xccdf", source_uri: file.name },
                            contentType: "application/xml",
                            body: xml,
                        })
                    )
                        .then((doc) => {
                            const rec = doc || {};
                            setRows((prev) =>
                                patchRow(prev, key, {
                                    status: "done",
                                    stigId: rec.stig_id || rec.ucc_name || "",
                                    version: rec.version || "",
                                    rules: rec.rule_count || 0,
                                    created: !!rec.created && !rec.deduplicated,
                                    deduplicated: !!rec.deduplicated,
                                    error: "",
                                })
                            );
                        })
                        .catch((err) => {
                            setRows((prev) =>
                                patchRow(prev, key, {
                                    status: "error",
                                    error: err.message,
                                })
                            );
                        });
                });
            }, Promise.resolve())
            .then(() => {
                setBanner({
                    type: "success",
                    text:
                        "Finished " +
                        incoming.length +
                        " XCCDF file" +
                        (incoming.length === 1 ? "" : "s") +
                        ". Catalog is under Configuration → Baselines.",
                });
            })
            .finally(() => {
                setBusy(false);
                setPhase("");
            });
    };

    const addFiles = (fileList) => {
        const incoming = Array.from(fileList || []);
        if (!incoming.length) {
            return;
        }
        const zips = incoming.filter((file) => detectFormat(file.name) === "zip");
        const xmls = incoming.filter((file) => detectFormat(file.name) === "xccdf");
        const checklists = incoming.filter((file) => {
            const fmt = detectFormat(file.name);
            return fmt === "ckl" || fmt === "cklb";
        });
        const unknown = incoming.filter((file) => !detectFormat(file.name));
        if (zips.length || xmls.length) {
            setBanner({
                type: "warning",
                text:
                    "DISA library zips and Manual-xccdf belong on Import baselines (nav), not this checklist page.",
            });
        }
        if (unknown.length) {
            addChecklistFiles(unknown);
        }
        if (checklists.length) {
            addChecklistFiles(checklists);
        }
    };

    const queued = useMemo(
        () => rows.filter((row) => row.status === "queued" && row.format && row.kind === "checklist"),
        [rows]
    );
    const failedBaselines = useMemo(
        () => rows.filter((row) => row.kind === "baseline" && row.status === "error"),
        [rows]
    );
    const hasBaselines = rows.some((row) => row.kind === "baseline");
    const visibleRows = useMemo(() => {
        const q = filter.trim().toLowerCase();
        if (!q) {
            return rows;
        }
        return rows.filter((row) => {
            const hay = [row.name, row.path, row.stigId, row.host].join(" ").toLowerCase();
            return hay.indexOf(q) >= 0;
        });
    }, [rows, filter]);
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
            .then((doc) => {
                const checklists = (doc && doc.checklists) || [];
                setRows((prev) =>
                    prev.map((item) =>
                        item.key === row.key
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
            })
            .catch((err) => {
                setRows((prev) =>
                    prev.map((item) =>
                        item.key === row.key
                            ? { ...item, status: "error", error: err.message }
                            : item
                    )
                );
            });
    };

    const startImport = () => {
        const pending = rows.filter((row) => row.status === "queued" && row.format && row.kind === "checklist");
        if (!pending.length) {
            setBanner({ type: "warning", text: "Add at least one .ckl or .cklb file." });
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
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Import checklists
                    </Heading>
                </Brand>
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => setCollectionId(value)}
                            placeholder="Default workspace"
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
                        disabled={busy || (!queued.length && !failedBaselines.length)}
                        onClick={() => {
                            if (failedBaselines.length) {
                                retryFailedBaselines();
                            } else {
                                startImport();
                            }
                        }}
                        label={
                            busy
                                ? phase === "upload"
                                    ? "Uploading zip…"
                                    : phase === "scan"
                                      ? "Listing baselines…"
                                      : "Importing…"
                                : failedBaselines.length
                                  ? "Retry " + failedBaselines.length + " failed"
                                  : "Import queued checklists"
                        }
                    />
                </Toolbar>
                <HeaderMeta>
                    <span>
                        {rows.length} item{rows.length === 1 ? "" : "s"}
                        {phase === "upload" ? " · uploading zip" : ""}
                        {phase === "scan" ? " · listing baselines" : ""}
                        {phase === "import" ? " · importing baselines" : ""}
                    </span>
                    <ProgressTrack title={pct + "% imported"}>
                        <ProgressFill $pct={pct} />
                    </ProgressTrack>
                    <Link to={viewUrl("stig_baselines_ui")}>Import baselines</Link>
                    <Link to={viewUrl("stig_editor_ui")}>Editor</Link>
                    <Link to={viewUrl("stig_export_ui")}>Export</Link>
                    <Link to={viewUrl("configuration")}>Configuration</Link>
                </HeaderMeta>
            </Header>
            <PagePad>
                <p style={{ maxWidth: 760, marginTop: 0 }}>
                    Drop host checklists (<code>.ckl</code> / <code>.cklb</code>)
                    here. DISA library zips and Manual-xccdf go on{" "}
                    <Link to={viewUrl("stig_baselines_ui")}>Import baselines</Link>
                    — Configuration cannot accept a zip.
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
                    <DropTitle>
                        {zipName
                            ? (phase === "upload" ? "Uploading " : "") + zipName
                            : "Drop .ckl or .cklb checklists"}
                    </DropTitle>
                    <DropHint>
                        {busy
                            ? phase === "upload"
                                ? "Sending 4MB chunks to persist REST…"
                                : phase === "scan"
                                  ? "Listing Manual-xccdf members on the server…"
                                  : "Importing one Manual-xccdf at a time."
                            : "Library zips belong on Import baselines."}
                    </DropHint>
                </DropZone>
                <div style={{ marginTop: 20 }}>
                    {hasBaselines ? (
                        <div
                            style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 12,
                                alignItems: "flex-end",
                                marginBottom: 12,
                            }}
                        >
                            <ControlGroup label="Filter baselines" labelPosition="top">
                                <Search
                                    value={filter}
                                    onChange={(e, { value }) => setFilter(value)}
                                    placeholder="Name or path…"
                                />
                            </ControlGroup>
                            {skipped ? (
                                <span style={{ fontSize: 12, opacity: 0.75 }}>
                                    Skipped {skipped.srg || 0} SRGs · {skipped.scap || 0}{" "}
                                    SCAP/OCIL · {skipped.other || 0} other
                                </span>
                            ) : null}
                        </div>
                    ) : null}
                    {busy && !rows.length ? (
                        <WaitSpinner size="medium" />
                    ) : (
                        <Table stripeRows>
                            <Table.Head>
                                <Table.HeadCell>File</Table.HeadCell>
                                <Table.HeadCell>Type</Table.HeadCell>
                                {hasBaselines ? (
                                    <Table.HeadCell>Size</Table.HeadCell>
                                ) : (
                                    <Table.HeadCell>Host</Table.HeadCell>
                                )}
                                {hasBaselines ? (
                                    <Table.HeadCell>STIG</Table.HeadCell>
                                ) : (
                                    <Table.HeadCell>Checklists</Table.HeadCell>
                                )}
                                {hasBaselines ? (
                                    <Table.HeadCell>Version</Table.HeadCell>
                                ) : (
                                    <Table.HeadCell>Findings</Table.HeadCell>
                                )}
                                <Table.HeadCell>{hasBaselines ? "Path" : "Results"}</Table.HeadCell>
                                <Table.HeadCell>Status</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {visibleRows.length ? (
                                    visibleRows.map((row) => (
                                        <Table.Row key={row.key}>
                                            <Table.Cell>{row.name}</Table.Cell>
                                            <Table.Cell>
                                                {row.kind === "baseline"
                                                    ? "Baseline"
                                                    : row.format
                                                      ? row.format.toUpperCase()
                                                      : "—"}
                                            </Table.Cell>
                                            {hasBaselines ? (
                                                <Table.Cell>{formatBytes(row.size)}</Table.Cell>
                                            ) : (
                                                <Table.Cell>{row.host || "—"}</Table.Cell>
                                            )}
                                            {hasBaselines ? (
                                                <Table.Cell>{row.stigId || "—"}</Table.Cell>
                                            ) : (
                                                <Table.Cell>
                                                    {row.status === "done" ? row.checklists : "—"}
                                                </Table.Cell>
                                            )}
                                            {hasBaselines ? (
                                                <Table.Cell>{row.version || "—"}</Table.Cell>
                                            ) : (
                                                <Table.Cell>
                                                    {row.status === "done" ? row.reviews : "—"}
                                                </Table.Cell>
                                            )}
                                            <Table.Cell>
                                                {hasBaselines ? row.path || "—" : statsLine(row.stats)}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {row.status === "uploading" || row.status === "scanning"
                                                    ? (
                                                          <span>
                                                              <WaitSpinner size="small" />{" "}
                                                              {baselineStatus(row)}
                                                          </span>
                                                      )
                                                    : baselineStatus(row)}
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
                        onClick={() => {
                            const jobId = jobIdRef.current;
                            jobIdRef.current = "";
                            setZipName("");
                            setSkipped(null);
                            setFilter("");
                            setRows([]);
                            if (jobId) {
                                apiFetch("stig_baselines/jobs/" + jobId, {
                                    method: "DELETE",
                                }).catch(() => null);
                            }
                        }}
                        label="Clear list"
                    />
                </Actions>
            </PagePad>
        </Shell>
    );
}
