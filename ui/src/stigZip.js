import {
    BlobReader,
    BlobWriter,
    Uint8ArrayWriter,
    ZipReader,
    configure,
} from "@zip.js/zip.js";

configure({ useWebWorkers: false });

const MAX_DEPTH = 4;
const MAX_XCCDF_BYTES = 50 * 1024 * 1024;
const MAX_INNER_ZIP_BYTES = 150 * 1024 * 1024;
const MAX_BASELINES = 500;

const SKIP = [
    "/__macosx/",
    "_srg_",
    "-srg-",
    "/srg_",
    "srg_v",
    "_scap_",
    "-scap-",
    "/scap/",
    "_ocil",
    "-ocil",
];

function norm(name) {
    return String(name || "").replace(/\\/g, "/");
}

export function isZipName(name) {
    return norm(name).toLowerCase().endsWith(".zip");
}

export function isBaselineXccdfName(name) {
    const path = norm(name).toLowerCase();
    const base = path.split("/").pop() || "";
    if (!base.endsWith(".xml") || base.startsWith(".")) {
        return false;
    }
    if (base.indexOf("manual-xccdf") < 0) {
        return false;
    }
    return !SKIP.some((part) => path.indexOf(part) >= 0);
}

export function basename(name) {
    const path = norm(name);
    const parts = path.split("/").filter(Boolean);
    return parts[parts.length - 1] || path;
}

async function withZip(blob, fn) {
    const reader = new ZipReader(new BlobReader(blob), { useWebWorkers: false });
    try {
        return await fn(await reader.getEntries());
    } finally {
        await reader.close();
    }
}

function decodeXml(bytes) {
    const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
    if (data.length >= 2 && data[0] === 0xff && data[1] === 0xfe) {
        return new TextDecoder("utf-16le").decode(data);
    }
    if (data.length >= 2 && data[0] === 0xfe && data[1] === 0xff) {
        return new TextDecoder("utf-16be").decode(data);
    }
    return new TextDecoder("utf-8").decode(data);
}

function skipReason(name) {
    const path = norm(name).toLowerCase();
    if (SKIP.some((part) => path.indexOf(part) >= 0) && path.indexOf("manual-xccdf") >= 0) {
        return "srg";
    }
    if (path.indexOf("scap") >= 0 || path.indexOf("ocil") >= 0) {
        return "scap";
    }
    if (path.endsWith(".xml") && path.indexOf("manual-xccdf") >= 0) {
        return "srg";
    }
    return "other";
}

async function walk(blob, prefix, depth, handlers, mode) {
    if (depth > MAX_DEPTH) {
        return;
    }
    await withZip(blob, async (entries) => {
        for (let i = 0; i < entries.length; i += 1) {
            const entry = entries[i];
            if (entry.directory) {
                continue;
            }
            const member = norm(prefix + entry.filename);
            const size = Number(entry.uncompressedSize || 0);
            if (isZipName(member) && depth < MAX_DEPTH) {
                if (size > MAX_INNER_ZIP_BYTES) {
                    continue;
                }
                if (handlers.onProgress) {
                    handlers.onProgress({
                        phase: "scan",
                        zip: basename(member),
                        found: handlers.found || 0,
                    });
                }
                const inner = await entry.getData(new BlobWriter("application/zip"));
                await walk(inner, member.replace(/\/?$/, "/") , depth + 1, handlers, mode);
                continue;
            }
            if (!isBaselineXccdfName(member)) {
                if (mode === "list" && handlers.onSkip) {
                    handlers.onSkip(member, skipReason(member));
                }
                continue;
            }
            if (handlers.only && !handlers.only.has(member)) {
                continue;
            }
            if (mode === "list") {
                handlers.paths.push({ path: member, size });
                handlers.found = handlers.paths.length;
                if (handlers.paths.length > MAX_BASELINES) {
                    throw new Error(
                        "zip contains more than " + MAX_BASELINES + " Manual-xccdf baselines"
                    );
                }
                if (handlers.onProgress) {
                    handlers.onProgress({
                        phase: "scan",
                        found: handlers.paths.length,
                        path: member,
                    });
                }
                continue;
            }
            if (size > MAX_XCCDF_BYTES) {
                await handlers.onEach(member, null, "file too large");
                continue;
            }
            const raw = await entry.getData(new Uint8ArrayWriter());
            await handlers.onEach(member, decodeXml(raw), "");
        }
    });
}

export async function listBaselineXccdfs(blob, onProgress) {
    const explored = await exploreStigZip(blob, onProgress);
    return explored.found.map((item) => item.path);
}

export async function exploreStigZip(blob, onProgress) {
    const skipped = { srg: 0, scap: 0, other: 0 };
    const handlers = {
        paths: [],
        found: 0,
        onProgress,
        onSkip: (name, reason) => {
            if (skipped[reason] != null) {
                skipped[reason] += 1;
            } else {
                skipped.other += 1;
            }
        },
    };
    await walk(blob, "", 0, handlers, "list");
    if (!handlers.paths.length) {
        throw new Error(
            "no Manual-xccdf STIG baselines found (SRGs, SCAP, and checklists are skipped)"
        );
    }
    return { found: handlers.paths, skipped };
}

export async function forEachBaselineXccdf(blob, paths, onEach, onProgress) {
    const only = new Set(paths || []);
    const handlers = {
        only,
        found: only.size,
        onProgress,
        onEach: async (path, xml, error) => {
            if (onProgress) {
                onProgress({ phase: "read", path });
            }
            await onEach(path, xml, error);
        },
    };
    await walk(blob, "", 0, handlers, "extract");
}
