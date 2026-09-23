import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, apiUpload } from "../api";
import {
    formatBytes,
    importDisaBaselineZip,
    importJobMembers,
    patchImportRow,
    rowImportStatus,
    skipLine,
} from "../baselineZipImport";
import { DropHint, DropTitle, DropZone, PagePad, ProgressFill, ProgressTrack } from "../layout";

/** Extension-only: mixed MIME tokens in `accept` grey out .zip in many file dialogs. */
const ACCEPT_BASELINE_FILES = ".xml,.xccdf,.ckl,.cklb,.json";
const ACCEPT_DISA_ZIP =
    ".zip,application/zip,application/x-zip-compressed,application/octet-stream";

function detectBaselineFormat(name, textSample) {
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
    const sample = String(textSample || "").trimStart();
    if (sample.startsWith("{") || sample.startsWith("[")) {
        return "cklb";
    }
    return "xccdf";
}

function contentTypeFor(fmt) {
    if (fmt === "cklb") {
        return "application/json";
    }
    if (fmt === "zip") {
        return "application/zip";
    }
    return "application/xml";
}

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error("read failed"));
        reader.readAsText(file);
    });
}

function baselineTitle(rec) {
    return rec.title || rec.stig_name || rec.stig_id || rec._key || "—";
}

function fileAcceptForFormat(formatOverride) {
    if (formatOverride === "zip") {
        return ACCEPT_DISA_ZIP;
    }
    if (formatOverride === "auto") {
        return ACCEPT_DISA_ZIP + "," + ACCEPT_BASELINE_FILES;
    }
    return ACCEPT_BASELINE_FILES;
}

export default function BaselineImportPanel() {
    const inputRef = useRef(null);
    const zipInputRef = useRef(null);
    const jobIdRef = useRef("");
    const [baselines, setBaselines] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [over, setOver] = useState(false);
    const [banner, setBanner] = useState(null);
    const [formatOverride, setFormatOverride] = useState("auto");
    const [zipRows, setZipRows] = useState([]);
    const [phase, setPhase] = useState("");
    const [uploadPct, setUploadPct] = useState(0);
    const [skipped, setSkipped] = useState(null);
    const [zipName, setZipName] = useState("");

    const loadBaselines = () => {
        setLoading(true);
        return apiGet("stig_baselines")
            .then((rows) => setBaselines(Array.isArray(rows) ? rows : []))
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load baselines: " + err.message,
                })
            )
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        loadBaselines();
    }, []);

    const importSingleFile = (file) => {
        setBusy(true);
        setBanner({ type: "info", text: "Importing " + file.name + "…" });
        return readFile(file)
            .then((text) => {
                const fmt =
                    formatOverride === "auto"
                        ? detectBaselineFormat(file.name, text)
                        : formatOverride;
                if (fmt === "zip") {
                    throw new Error("use zip import path");
                }
                return apiUpload("stig_baselines/import", {
                    query: { format: fmt, source_uri: file.name },
                    contentType: contentTypeFor(fmt),
                    body: text,
                }).then((doc) => {
                    const deduped = !!(doc && doc.deduplicated);
                    setBanner({
                        type: "success",
                        text: deduped
                            ? "Matched existing baseline (" + baselineTitle(doc) + ")."
                            : "Imported baseline " + baselineTitle(doc) + ".",
                    });
                    return loadBaselines();
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Import failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const importZipFile = (file) => {
        jobIdRef.current = "";
        setZipName(file.name);
        setSkipped(null);
        setZipRows([]);
        setBusy(true);
        setPhase("upload");
        setUploadPct(0);
        setBanner({
            type: "info",
            text:
                "Uploading " +
                file.name +
                " (" +
                formatBytes(file.size) +
                ") — nested zips are scanned; only Manual-xccdf STIGs are imported.",
        });
        return importDisaBaselineZip(file, {
            onPhase: setPhase,
            onUploadPct: setUploadPct,
            onBanner: setBanner,
            onJobId: (id) => {
                jobIdRef.current = id;
            },
            onSkipped: setSkipped,
            onRows: setZipRows,
            onRowPatch: (key, fields) => {
                setZipRows((prev) => patchImportRow(prev, key, fields));
            },
        })
            .then((summary) => {
                loadBaselines();
                setBanner({
                    type: "success",
                    text:
                        "Finished " +
                        summary.total +
                        " baseline" +
                        (summary.total === 1 ? "" : "s") +
                        " from " +
                        file.name +
                        (summary.skipBits ? ". Skipped " + summary.skipBits + "." : "."),
                });
            })
            .catch((err) => {
                loadBaselines();
                setBanner({
                    type: "error",
                    text: "Zip import failed: " + err.message,
                });
            })
            .finally(() => {
                setBusy(false);
                setPhase("");
            });
    };

    const onFiles = (fileList) => {
        const files = Array.from(fileList || []);
        if (!files.length) {
            return;
        }
        if (formatOverride === "zip") {
            const zips = files.filter((f) => detectBaselineFormat(f.name, "") === "zip");
            if (!zips.length) {
                setBanner({
                    type: "warning",
                    text: "Choose a .zip file (DISA product or library archive).",
                });
                return;
            }
            if (busy) {
                setBanner({
                    type: "warning",
                    text: "Wait for the current import to finish before starting another zip.",
                });
                return;
            }
            importZipFile(zips[0]);
            return;
        }
        const zips = files.filter((f) => detectBaselineFormat(f.name, "") === "zip");
        const others = files.filter((f) => detectBaselineFormat(f.name, "") !== "zip");
        if (zips.length) {
            if (busy) {
                setBanner({
                    type: "warning",
                    text: "Wait for the current import to finish before dropping another zip.",
                });
                return;
            }
            if (zips.length > 1) {
                setBanner({
                    type: "warning",
                    text: "Import one DISA zip at a time; starting with " + zips[0].name + ".",
                });
            }
            importZipFile(zips[0]);
        }
        if (others.length) {
            others
                .reduce(
                    (chain, file) => chain.then(() => importSingleFile(file)),
                    Promise.resolve()
                )
                .catch(() => {});
        }
    };

    const deleteBaseline = (rec) => {
        const key = rec._key;
        if (!key) {
            return;
        }
        const label = baselineTitle(rec);
        if (!window.confirm("Delete baseline " + label + "? This cannot be undone.")) {
            return;
        }
        setBusy(true);
        apiFetch("stig_baselines/" + encodeURIComponent(key), { method: "DELETE" })
            .then(() => {
                setBanner({ type: "success", text: "Deleted " + label + "." });
                return loadBaselines();
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Delete failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const failedZipRows = useMemo(
        () => zipRows.filter((row) => row.status === "error"),
        [zipRows]
    );
    const doneZipCount = useMemo(
        () => zipRows.filter((row) => row.status === "done").length,
        [zipRows]
    );
    const progressPct = zipRows.length
        ? Math.round((doneZipCount / zipRows.length) * 100)
        : phase === "upload"
          ? uploadPct
          : phase === "scan" || phase === "import"
            ? 100
            : 0;

    const retryFailedZip = () => {
        const jobId = jobIdRef.current;
        if (!jobId || !failedZipRows.length) {
            return;
        }
        setBusy(true);
        setPhase("import");
        importJobMembers(jobId, failedZipRows, {
            onBanner: setBanner,
            onRow: (key, fields) => {
                setZipRows((prev) => patchImportRow(prev, key, fields));
            },
        })
            .then(() => {
                loadBaselines();
                setBanner({
                    type: "success",
                    text: "Retried " + failedZipRows.length + " failed baseline(s).",
                });
            })
            .finally(() => {
                setBusy(false);
                setPhase("");
            });
    };

    const dropDisabled = busy;

    return (
        <PagePad style={{ paddingTop: 0 }}>
            <p style={{ maxWidth: 760, marginTop: 0 }}>
                Upload Manual-xccdf <code>.xml</code>, a DISA product or library{" "}
                <code>.zip</code> (nested zips; only <code>*Manual-xccdf.xml</code>), or
                baseline content from <code>.ckl</code> / <code>.cklb</code>. Duplicate
                content is deduplicated. Checklist imports are on the{" "}
                <Link
                    onClick={() => {
                        window.location.hash = "checklists";
                    }}
                >
                    Checklists
                </Link>{" "}
                tab.
            </p>
            {banner ? (
                <Message appearance={banner.type} onRequestRemove={() => setBanner(null)}>
                    {banner.text}
                </Message>
            ) : null}
            <div
                style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 16,
                    alignItems: "flex-end",
                    marginBottom: 16,
                }}
            >
                <ControlGroup label="Format" labelPosition="top">
                    <Select
                        value={formatOverride}
                        onChange={(e, { value }) => setFormatOverride(value)}
                        disabled={busy}
                    >
                        <Select.Option label="Auto-detect" value="auto" />
                        <Select.Option label="DISA zip archive" value="zip" />
                        <Select.Option label="XCCDF" value="xccdf" />
                        <Select.Option label="CKLB" value="cklb" />
                        <Select.Option label="CKL" value="ckl" />
                    </Select>
                </ControlGroup>
                <Button
                    appearance="primary"
                    disabled={busy}
                    onClick={() => zipInputRef.current && zipInputRef.current.click()}
                    label="Browse for DISA zip…"
                />
                {failedZipRows.length ? (
                    <Button
                        appearance="secondary"
                        disabled={busy}
                        onClick={retryFailedZip}
                        label={"Retry " + failedZipRows.length + " failed"}
                    />
                ) : null}
                {phase || zipRows.length ? (
                    <div style={{ minWidth: 160, flex: "1 1 200px" }}>
                        <ProgressTrack title={progressPct + "%"}>
                            <ProgressFill $pct={progressPct} />
                        </ProgressTrack>
                    </div>
                ) : null}
            </div>
            <input
                ref={zipInputRef}
                type="file"
                accept={ACCEPT_DISA_ZIP}
                style={{ display: "none" }}
                onChange={(e) => {
                    onFiles(e.target.files);
                    e.target.value = "";
                }}
            />
            <input
                ref={inputRef}
                type="file"
                accept={fileAcceptForFormat(formatOverride)}
                multiple
                style={{ display: "none" }}
                onChange={(e) => {
                    onFiles(e.target.files);
                    e.target.value = "";
                }}
            />
            <DropZone
                className={(over ? "is-over" : "") + (dropDisabled ? " is-disabled" : "")}
                onClick={() => {
                    if (dropDisabled) {
                        return;
                    }
                    if (formatOverride === "zip" && zipInputRef.current) {
                        zipInputRef.current.click();
                        return;
                    }
                    if (inputRef.current) {
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
                        onFiles(e.dataTransfer.files);
                    }
                }}
            >
                <DropTitle>
                    {zipName && phase === "upload"
                        ? "Uploading " + zipName
                        : "Drop DISA zip or benchmark files here"}
                </DropTitle>
                <DropHint>
                    {busy && phase === "upload"
                        ? "Large zips upload in 4MB chunks to persist REST…"
                        : "Or click to browse (.zip library/product, Manual-xccdf .xml, .ckl, .cklb)"}
                </DropHint>
            </DropZone>
            {skipped ? (
                <p style={{ marginTop: 12, opacity: 0.85 }}>
                    Skipped in archive: {skipLine(skipped) || "nothing extra"}.
                </p>
            ) : null}
            {zipRows.length ? (
                <div style={{ marginTop: 20 }}>
                    <h3 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600 }}>
                        This zip ({doneZipCount}/{zipRows.length} imported)
                    </h3>
                    <Table stripeRows>
                        <Table.Head>
                            <Table.HeadCell>Member</Table.HeadCell>
                            <Table.HeadCell>STIG id</Table.HeadCell>
                            <Table.HeadCell>Rules</Table.HeadCell>
                            <Table.HeadCell>Status</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {zipRows.map((row) => (
                                <Table.Row key={row.key}>
                                    <Table.Cell>{row.name}</Table.Cell>
                                    <Table.Cell>{row.stigId || "—"}</Table.Cell>
                                    <Table.Cell>{row.rules ? String(row.rules) : "—"}</Table.Cell>
                                    <Table.Cell>{rowImportStatus(row)}</Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </div>
            ) : null}
            <div style={{ marginTop: 24 }}>
                <h3 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600 }}>
                    Imported baselines
                </h3>
                {loading ? (
                    <WaitSpinner size="medium" />
                ) : (
                    <Table stripeRows>
                        <Table.Head>
                            <Table.HeadCell>STIG id</Table.HeadCell>
                            <Table.HeadCell>Title</Table.HeadCell>
                            <Table.HeadCell>Version</Table.HeadCell>
                            <Table.HeadCell>Rules</Table.HeadCell>
                            <Table.HeadCell>Source</Table.HeadCell>
                            <Table.HeadCell width={100}>Actions</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {baselines.length ? (
                                baselines.map((rec) => (
                                    <Table.Row key={rec._key}>
                                        <Table.Cell>{rec.stig_id || "—"}</Table.Cell>
                                        <Table.Cell>{baselineTitle(rec)}</Table.Cell>
                                        <Table.Cell>{rec.version || "—"}</Table.Cell>
                                        <Table.Cell>{rec.rule_count ?? "—"}</Table.Cell>
                                        <Table.Cell>
                                            {rec.source_type || rec.source_uri || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Button
                                                appearance="destructive"
                                                disabled={busy}
                                                onClick={() => deleteBaseline(rec)}
                                                label="Delete"
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                ))
                            ) : (
                                <Table.Row>
                                    <Table.Cell align="center" colSpan={6}>
                                        No baselines yet.
                                    </Table.Cell>
                                </Table.Row>
                            )}
                        </Table.Body>
                    </Table>
                )}
            </div>
        </PagePad>
    );
}
