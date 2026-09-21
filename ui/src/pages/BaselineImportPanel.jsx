import React, { useEffect, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, apiUpload } from "../api";
import { DropHint, DropTitle, DropZone, PagePad } from "../layout";

const ACCEPT =
    ".xml,.xccdf,.ckl,.cklb,.json,application/xml,text/xml,application/json";

function detectBaselineFormat(name, textSample) {
    const lower = String(name || "").toLowerCase();
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
    return fmt === "cklb" ? "application/json" : "application/xml";
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

export default function BaselineImportPanel() {
    const inputRef = useRef(null);
    const [baselines, setBaselines] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [over, setOver] = useState(false);
    const [banner, setBanner] = useState(null);
    const [formatOverride, setFormatOverride] = useState("auto");

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

    const importFile = (file) => {
        setBusy(true);
        setBanner({ type: "info", text: "Importing " + file.name + "…" });
        return readFile(file)
            .then((text) => {
                const fmt =
                    formatOverride === "auto"
                        ? detectBaselineFormat(file.name, text)
                        : formatOverride;
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

    const onFiles = (fileList) => {
        const files = Array.from(fileList || []);
        if (!files.length) {
            return;
        }
        files
            .reduce((chain, file) => chain.then(() => importFile(file)), Promise.resolve())
            .catch(() => {});
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

    const dropDisabled = busy;

    return (
        <PagePad style={{ paddingTop: 0 }}>
            <p style={{ maxWidth: 760, marginTop: 0 }}>
                Upload DISA XCCDF benchmarks or extract a STIG revision from a{" "}
                <code>.ckl</code> / <code>.cklb</code> file. Identical content is
                deduplicated. Baselines are immutable; delete and re-import to replace.
                Workspace checklist imports are in the{" "}
                <Link onClick={() => document.getElementById("checklists")?.scrollIntoView()}>
                    Checklists
                </Link>{" "}
                section above.
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
                        <Select.Option label="Detect from file" value="auto" />
                        <Select.Option label="XCCDF" value="xccdf" />
                        <Select.Option label="CKLB" value="cklb" />
                        <Select.Option label="CKL" value="ckl" />
                    </Select>
                </ControlGroup>
            </div>
            <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
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
                        onFiles(e.dataTransfer.files);
                    }
                }}
            >
                <DropTitle>Drop benchmark or checklist files here</DropTitle>
                <DropHint>Or click to browse (.xml XCCDF, .cklb, .ckl)</DropHint>
            </DropZone>
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
