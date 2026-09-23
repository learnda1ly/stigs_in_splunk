/** Chunked DISA library / product zip upload + per-member baseline import. */

import { apiFetch, apiUpload } from "./api";

export const CHUNK_BYTES = 4 * 1024 * 1024;
/** Single POST zip import; larger archives use `/stig_baselines/jobs`. */
export const DIRECT_ZIP_MAX_BYTES = 12 * 1024 * 1024;

export function formatBytes(n) {
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

export function basename(name) {
    const path = String(name || "").replace(/\\/g, "/");
    const parts = path.split("/").filter(Boolean);
    return parts[parts.length - 1] || path;
}

export function bytesToBase64(bytes) {
    let binary = "";
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    }
    return btoa(binary);
}

export function skipLine(skip) {
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

export function patchImportRow(rows, key, fields) {
    return rows.map((item) => (item.key === key ? { ...item, ...fields } : item));
}

export function rowImportStatus(row) {
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

function readArrayBuffer(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error("read failed"));
        reader.readAsArrayBuffer(file);
    });
}

export function jobRowsFromFound(jobId, fileName, found) {
    return (found || []).map((item) => ({
        key: (jobId || fileName) + ":" + item.path,
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
}

export function rowsFromDirectZipResponse(doc, fileName) {
    const list =
        (doc && doc.baselines) ||
        (doc && doc.stig_id ? [doc] : doc && doc._key ? [doc] : []);
    return list.map((rec, index) => ({
        key: fileName + ":" + (rec.source_uri || rec._key || index),
        name: basename(rec.source_uri || rec.title || rec.stig_id || "baseline"),
        path: rec.source_uri || fileName,
        size: 0,
        status: "done",
        error: "",
        stigId: rec.stig_id || rec.ucc_name || "",
        title: rec.title || "",
        version: rec.version || "",
        rules: rec.rule_count || 0,
        created: !!(doc && doc.created) || !!rec.created,
        deduplicated: !!(doc && doc.deduplicated) || !!rec.deduplicated,
    }));
}

export function importJobMembers(jobId, pending, { onRow, onBanner }) {
    const total = pending.length;
    return pending.reduce((chain, row, index) => {
        return chain.then(() => {
            if (onBanner) {
                onBanner({
                    type: "info",
                    text:
                        "Importing " +
                        (index + 1) +
                        "/" +
                        total +
                        " · " +
                        row.name,
                });
            }
            if (onRow) {
                onRow(row.key, { status: "uploading", error: "" });
            }
            return apiFetch("stig_baselines/jobs/" + jobId, {
                method: "POST",
                body: { action: "import", path: row.path },
            })
                .then((doc) => {
                    const rec = doc || {};
                    if (onRow) {
                        onRow(row.key, {
                            status: "done",
                            stigId: rec.stig_id || rec.ucc_name || "",
                            title: rec.title || "",
                            version: rec.version || "",
                            rules: rec.rule_count || 0,
                            created: !!rec.created && !rec.deduplicated,
                            deduplicated: !!rec.deduplicated,
                            error: "",
                        });
                    }
                })
                .catch((err) => {
                    if (onRow) {
                        onRow(row.key, {
                            status: "error",
                            error: err.message,
                        });
                    }
                });
        });
    }, Promise.resolve());
}

export function uploadZipInChunks(file, { onUploadPct, onBanner }) {
    let jobId = "";
    return apiFetch("stig_baselines/jobs", {
        method: "POST",
        body: { filename: file.name, size: file.size },
    })
        .then((job) => {
            jobId = job && job.job_id;
            if (!jobId) {
                throw new Error("no job id from server");
            }
            let offset = 0;
            const send = () => {
                if (offset >= file.size) {
                    if (onUploadPct) {
                        onUploadPct(100);
                    }
                    if (onBanner) {
                        onBanner({
                            type: "info",
                            text: "Upload complete. Listing Manual-xccdf baselines…",
                        });
                    }
                    return apiFetch("stig_baselines/jobs/" + jobId, {
                        method: "POST",
                        body: { action: "finalize" },
                    }).then((result) => ({ jobId, result }));
                }
                return file
                    .slice(offset, offset + CHUNK_BYTES)
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
                            if (onUploadPct) {
                                onUploadPct(pctDone);
                            }
                            if (onBanner) {
                                onBanner({
                                    type: "info",
                                    text:
                                        "Uploading zip " +
                                        pctDone +
                                        "% · " +
                                        formatBytes(offset) +
                                        " / " +
                                        formatBytes(file.size),
                                });
                            }
                            return send();
                        });
                    });
            };
            return send();
        })
        .catch((err) => {
            if (jobId) {
                apiFetch("stig_baselines/jobs/" + jobId, { method: "DELETE" }).catch(
                    () => null
                );
            }
            throw err;
        });
}

/**
 * Import every Manual-xccdf STIG from a DISA product or library zip (nested zips OK).
 * SRGs, SCAP, OCIL, checklists, and other files are skipped on the server.
 */
export function importDisaBaselineZip(file, callbacks) {
    const {
        onPhase,
        onUploadPct,
        onBanner,
        onJobId,
        onSkipped,
        onRows,
    } = callbacks || {};

    if (onPhase) {
        onPhase("upload");
    }
    if (onUploadPct) {
        onUploadPct(0);
    }
    if (onBanner) {
        onBanner({
            type: "info",
            text:
                "Uploading " +
                file.name +
                " (" +
                formatBytes(file.size) +
                ")…",
        });
    }

    if (file.size <= DIRECT_ZIP_MAX_BYTES) {
        return readArrayBuffer(file)
            .then((buffer) =>
                apiUpload("stig_baselines/import", {
                    query: { format: "zip", source_uri: file.name },
                    contentType: "application/zip",
                    body: buffer,
                })
            )
            .then((doc) => {
                const rows = rowsFromDirectZipResponse(doc, file.name);
                if (onRows) {
                    onRows(rows);
                }
                return {
                    mode: "direct",
                    total: rows.length,
                    skipBits: "",
                    jobId: "",
                };
            })
            .finally(() => {
                if (onPhase) {
                    onPhase("");
                }
            });
    }

    return uploadZipInChunks(file, { onUploadPct, onBanner })
        .then(({ jobId, result }) => {
            if (onJobId) {
                onJobId(jobId);
            }
            if (onPhase) {
                onPhase("scan");
            }
            const found = (result && result.found) || [];
            const skip = (result && result.skipped) || {};
            if (onSkipped) {
                onSkipped(skip);
            }
            const nextRows = jobRowsFromFound(jobId, file.name, found);
            if (onRows) {
                onRows(nextRows);
            }
            const skipBits = skipLine(skip);
            if (!nextRows.length) {
                throw new Error(
                    "no Manual-xccdf STIG baselines found" +
                        (skipBits ? " (skipped " + skipBits + ")" : "")
                );
            }
            if (onBanner) {
                onBanner({
                    type: "info",
                    text:
                        "Found " +
                        nextRows.length +
                        " Manual-xccdf STIG" +
                        (nextRows.length === 1 ? "" : "s") +
                        (skipBits ? ". Skipped " + skipBits : "") +
                        ". Importing…",
                });
            }
            if (onPhase) {
                onPhase("import");
            }
            return importJobMembers(jobId, nextRows, {
                onBanner,
                onRow: callbacks.onRowPatch,
            }).then(() => ({
                mode: "job",
                total: nextRows.length,
                skipBits,
                jobId,
            }));
        })
        .finally(() => {
            if (onPhase) {
                onPhase("");
            }
        });
}
