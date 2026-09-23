// Legacy view: canonical baseline import UI is Import → Baselines tab (stig_import_ui).
import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Search from "@splunk/react-ui/Search";
import Table from "@splunk/react-ui/Table";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, apiUpload, viewUrl } from "../api";
import {
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
const ACCEPT_ZIP = ".zip,application/zip,application/x-zip-compressed,application/octet-stream";
const ACCEPT_XML = ".xml,.xccdf";
const ACCEPT = ACCEPT_ZIP + "," + ACCEPT_XML;

function detectKind(name) {
    const lower = String(name || "").toLowerCase();
    if (lower.endsWith(".zip")) {
        return "zip";
    }
    if (lower.endsWith(".xml") || lower.endsWith(".xccdf")) {
        return "xccdf";
    }
    return "";
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

function rowStatus(row) {
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

function skipLine(skip) {
    if (!skip) {
        return "";
    }
    return [
        skip.srg ? skip.srg + " SRGs" : "",
        skip.scap ? skip.scap + " SCAP/OCIL" : "",
        skip.other ? skip.other + " other files" : "",
    ]
        .filter(Boolean)
        .join(", ");
}

export default function BaselinesApp() {
    const inputRef = useRef(null);
    const jobIdRef = useRef("");
    const [catalog, setCatalog] = useState([]);
    const [rows, setRows] = useState([]);
    const [busy, setBusy] = useState(false);
    const [over, setOver] = useState(false);
    const [banner, setBanner] = useState(null);
    const [phase, setPhase] = useState("");
    const [zipName, setZipName] = useState("");
    const [uploadPct, setUploadPct] = useState(0);
    const [skipped, setSkipped] = useState(null);
    const [filter, setFilter] = useState("");
    const [catalogFilter, setCatalogFilter] = useState("");

    const loadCatalog = () =>
        apiGet("stig_baselines")
            .then((list) => setCatalog(Array.isArray(list) ? list : []))
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load catalog: " + err.message,
                })
            );

    useEffect(() => {
        loadCatalog();
    }, []);

    const importMembers = (jobId, pending) => {
        const total = pending.length;
        setPhase("import");
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
                                    title: rec.title || "",
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
        setUploadPct(0);
        let listed = false;
        setBanner({
            type: "info",
            text:
                "Uploading " +
                file.name +
                " (" +
                formatBytes(file.size) +
                ") in 4MB persist chunks…",
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
                        setUploadPct(100);
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
                                setUploadPct(pctDone);
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
                    name: basename(item.path),
                    path: item.path,
                    size: item.size,
                    status: "queued",
                    error: "",
                    stigId: "",
                    title: "",
                    version: "",
                    rules: 0,
                    created: false,
                    deduplicated: false,
                }));
                setRows(nextRows);
                listed = true;
                const skipBits = skipLine(skip);
                if (!nextRows.length) {
                    throw new Error(
                        "no Manual-xccdf STIG baselines found" +
                            (skipBits ? " (skipped " + skipBits + ")" : "")
                    );
                }
                setBanner({
                    type: "info",
                    text:
                        "Found " +
                        nextRows.length +
                        " Manual-xccdf STIG" +
                        (nextRows.length === 1 ? "" : "s") +
                        (skipBits ? ". Skipped " + skipBits : "") +
                        ". Importing the full set…",
                });
                return importMembers(jobIdRef.current, nextRows).then((total) => ({
                    total,
                    skipBits,
                }));
            })
            .then((summary) => {
                loadCatalog();
                setBanner({
                    type: "success",
                    text:
                        "Finished " +
                        summary.total +
                        " baseline" +
                        (summary.total === 1 ? "" : "s") +
                        " from the zip." +
                        (summary.skipBits ? " Skipped " + summary.skipBits + "." : ""),
                });
            })
            .catch((err) => {
                if (listed) {
                    loadCatalog();
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

    const importXmlFiles = (files) => {
        const incoming = Array.from(files || []);
        if (!incoming.length) {
            return;
        }
        const nextRows = incoming.map((file) => ({
            key: [file.name, file.size, file.lastModified].join(":"),
            name: file.name,
            path: file.name,
            size: file.size,
            file,
            status: "queued",
            error: "",
            stigId: "",
            title: "",
            version: "",
            rules: 0,
            created: false,
            deduplicated: false,
        }));
        setRows(nextRows);
        setZipName("");
        setSkipped(null);
        setBusy(true);
        setPhase("import");
        incoming
            .reduce((chain, file, index) => {
                return chain.then(() => {
                    const key = nextRows[index].key;
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
                    return new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => resolve(reader.result);
                        reader.onerror = () =>
                            reject(reader.error || new Error("read failed"));
                        reader.readAsText(file);
                    }).then((xml) =>
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
                                    title: rec.title || "",
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
                loadCatalog();
                setBanner({
                    type: "success",
                    text:
                        "Finished " +
                        incoming.length +
                        " XCCDF file" +
                        (incoming.length === 1 ? "" : "s") +
                        ".",
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
        const zips = incoming.filter((file) => detectKind(file.name) === "zip");
        const xmls = incoming.filter((file) => detectKind(file.name) === "xccdf");
        const unknown = incoming.filter((file) => !detectKind(file.name));
        if (unknown.length) {
            setBanner({
                type: "error",
                text:
                    "This page accepts a DISA .zip or Manual-xccdf .xml. " +
                    unknown.map((file) => file.name).join(", ") +
                    " is not supported. Checklists (.ckl / .cklb) go on Import checklists.",
            });
            return;
        }
        if (zips.length) {
            if (busy) {
                setBanner({
                    type: "warning",
                    text: "Wait for the current import to finish before dropping another zip.",
                });
                return;
            }
            scanLibraryZip(zips[0]);
            return;
        }
        if (xmls.length) {
            importXmlFiles(xmls);
        }
    };

    const failed = useMemo(
        () => rows.filter((row) => row.status === "error"),
        [rows]
    );
    const doneCount = useMemo(
        () => rows.filter((row) => row.status === "done").length,
        [rows]
    );
    const visibleRows = useMemo(() => {
        const q = filter.trim().toLowerCase();
        if (!q) {
            return rows;
        }
        return rows.filter((row) =>
            (row.name + " " + row.path + " " + row.stigId + " " + row.title)
                .toLowerCase()
                .includes(q)
        );
    }, [rows, filter]);
    const visibleCatalog = useMemo(() => {
        const q = catalogFilter.trim().toLowerCase();
        if (!q) {
            return catalog;
        }
        return catalog.filter((row) =>
            (
                (row.stig_id || "") +
                " " +
                (row.title || "") +
                " " +
                (row.version || "") +
                " " +
                (row.source_uri || "")
            )
                .toLowerCase()
                .includes(q)
        );
    }, [catalog, catalogFilter]);

    const retryFailed = () => {
        const jobId = jobIdRef.current;
        if (!jobId || !failed.length) {
            return;
        }
        setBusy(true);
        importMembers(jobId, failed)
            .then(() => {
                loadCatalog();
                setBanner({
                    type: "success",
                    text:
                        "Retried " +
                        failed.length +
                        " failed baseline" +
                        (failed.length === 1 ? "" : "s") +
                        ".",
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Retry failed: " + err.message })
            )
            .finally(() => {
                setBusy(false);
                setPhase("");
            });
    };

    const deleteBaseline = (row) => {
        const label = row.title || row.stig_id || row._key;
        if (!window.confirm("Delete baseline “" + label + "” and its rules?")) {
            return;
        }
        setBusy(true);
        apiFetch("stig_baselines/" + row._key, { method: "DELETE" })
            .then(() => {
                setCatalog((prev) => prev.filter((item) => item._key !== row._key));
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Delete failed: " + err.message,
                })
            )
            .finally(() => setBusy(false));
    };

    const importPct = rows.length
        ? Math.round((doneCount / rows.length) * 100)
        : phase === "upload"
          ? uploadPct
          : 0;
    const dropDisabled = busy;

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Import baselines
                    </Heading>
                </Brand>
                <Toolbar>
                    {failed.length ? (
                        <Button
                            appearance="primary"
                            disabled={busy}
                            onClick={retryFailed}
                            label={"Retry " + failed.length + " failed"}
                        />
                    ) : null}
                    {busy ? <WaitSpinner size="small" /> : null}
                </Toolbar>
                <HeaderMeta>
                    <span>
                        {catalog.length} in catalog
                        {rows.length
                            ? " · " + doneCount + "/" + rows.length + " this zip"
                            : ""}
                        {phase === "upload" ? " · uploading zip" : ""}
                        {phase === "scan" ? " · listing baselines" : ""}
                        {phase === "import" ? " · importing" : ""}
                    </span>
                    <ProgressTrack title={importPct + "%"}>
                        <ProgressFill $pct={importPct} />
                    </ProgressTrack>
                </HeaderMeta>
            </Header>
            <PagePad>
                <p style={{ maxWidth: 760, marginTop: 0 }}>
                    This page imports DISA STIG <strong>baselines</strong>. Drop a
                    product <code>.zip</code> or a quarterly zip-of-zips. The file is
                    uploaded in 4MB chunks to persist REST (
                    <code>/stig_baselines/jobs</code>), not the UCC Configuration
                    form. Every <code>Manual-xccdf</code> STIG is imported;
                    SRGs, SCAP, and checklists inside the zip are skipped. Host
                    checklists (<code>.ckl</code> / <code>.cklb</code>) belong on{" "}
                    <Link to={viewUrl("stig_import_ui")}>Import checklists</Link>.
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
                            : "Drop a DISA .zip here"}
                    </DropTitle>
                    <DropHint>
                        {busy
                            ? phase === "upload"
                                ? "Sending 4MB chunks to persist REST…"
                                : phase === "scan"
                                  ? "Listing Manual-xccdf members on the server…"
                                  : "Importing one Manual-xccdf at a time."
                            : "Accepts .zip (library or product) and Manual-xccdf .xml. Not .ckl / .cklb."}
                    </DropHint>
                </DropZone>
                {skipped ? (
                    <p style={{ color: "inherit", opacity: 0.8 }}>
                        Skipped {skipLine(skipped) || "nothing extra"}.
                    </p>
                ) : null}
                {rows.length ? (
                    <div style={{ marginTop: 24 }}>
                        <Heading level={3} style={{ margin: "0 0 12px" }}>
                            This import
                        </Heading>
                        <Search
                            value={filter}
                            onChange={(e, { value }) => setFilter(value)}
                            placeholder="Filter this zip…"
                            style={{ maxWidth: 360, marginBottom: 12 }}
                        />
                        <Table stripeRows>
                            <Table.Head>
                                <Table.HeadCell>File</Table.HeadCell>
                                <Table.HeadCell>STIG id</Table.HeadCell>
                                <Table.HeadCell>Rules</Table.HeadCell>
                                <Table.HeadCell>Status</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {visibleRows.map((row) => (
                                    <Table.Row key={row.key}>
                                        <Table.Cell>{row.name}</Table.Cell>
                                        <Table.Cell>{row.stigId || "—"}</Table.Cell>
                                        <Table.Cell>
                                            {row.rules ? String(row.rules) : "—"}
                                        </Table.Cell>
                                        <Table.Cell>{rowStatus(row)}</Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                    </div>
                ) : null}
                <div style={{ marginTop: 32 }}>
                    <Heading level={3} style={{ margin: "0 0 12px" }}>
                        Catalog
                    </Heading>
                    <Search
                        value={catalogFilter}
                        onChange={(e, { value }) => setCatalogFilter(value)}
                        placeholder="Filter catalog…"
                        style={{ maxWidth: 360, marginBottom: 12 }}
                    />
                    <Table stripeRows>
                        <Table.Head>
                            <Table.HeadCell>STIG id</Table.HeadCell>
                            <Table.HeadCell>Title</Table.HeadCell>
                            <Table.HeadCell>Version</Table.HeadCell>
                            <Table.HeadCell>Rules</Table.HeadCell>
                            <Table.HeadCell>Source</Table.HeadCell>
                            <Table.HeadCell> </Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {visibleCatalog.length ? (
                                visibleCatalog.map((row) => (
                                    <Table.Row key={row._key}>
                                        <Table.Cell>{row.stig_id || row.name || "—"}</Table.Cell>
                                        <Table.Cell>{row.title || "—"}</Table.Cell>
                                        <Table.Cell>{row.version || "—"}</Table.Cell>
                                        <Table.Cell>
                                            {row.rule_count != null
                                                ? String(row.rule_count)
                                                : "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {basename(row.source_uri || "") || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Button
                                                appearance="secondary"
                                                disabled={busy}
                                                onClick={() => deleteBaseline(row)}
                                                label="Delete"
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                ))
                            ) : (
                                <Table.Row>
                                    <Table.Cell>No baselines yet</Table.Cell>
                                    <Table.Cell>Drop a DISA zip above.</Table.Cell>
                                    <Table.Cell>—</Table.Cell>
                                    <Table.Cell>—</Table.Cell>
                                    <Table.Cell>—</Table.Cell>
                                    <Table.Cell> </Table.Cell>
                                </Table.Row>
                            )}
                        </Table.Body>
                    </Table>
                </div>
            </PagePad>
        </Shell>
    );
}
