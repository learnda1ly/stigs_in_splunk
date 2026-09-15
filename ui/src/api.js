function localePrefix() {
    const path = window.location.pathname || "";
    const match = path.match(/^(\/[^/]+)\//);
    return match ? match[1] : "/en-US";
}

function csrfToken() {
    let token = "";
    String(document.cookie || "")
        .split(";")
        .forEach((part) => {
            const cookie = part.trim();
            if (cookie.indexOf("splunkweb_csrf_token_") === 0) {
                token = decodeURIComponent(cookie.substring(cookie.indexOf("=") + 1));
            }
        });
    return token;
}

function apiUrl(path, query) {
    let url =
        localePrefix() +
        "/splunkd/__raw/servicesNS/nobody/stigs_in_splunk/" +
        String(path).replace(/^\//, "");
    if (query) {
        const parts = Object.keys(query)
            .filter((key) => query[key] != null && query[key] !== "")
            .map(
                (key) =>
                    encodeURIComponent(key) + "=" + encodeURIComponent(query[key])
            );
        if (parts.length) {
            url += "?" + parts.join("&");
        }
    }
    return url;
}

function parseBody(text) {
    if (text == null) {
        return text;
    }
    const trimmed = String(text).trim();
    if (!trimmed) {
        return text;
    }
    if (trimmed.charAt(0) === "{" || trimmed.charAt(0) === "[") {
        try {
            return JSON.parse(trimmed);
        } catch (e) {
            return text;
        }
    }
    return text;
}

function xmlMessages(text) {
    const src = String(text || "");
    const matches = src.match(/<msg\b[^>]*>([\s\S]*?)<\/msg>/gi) || [];
    return matches
        .map((tag) =>
            tag
                .replace(/<msg\b[^>]*>/i, "")
                .replace(/<\/msg>/i, "")
                .trim()
        )
        .filter(Boolean);
}

export function unwrap(data) {
    if (data == null) {
        return data;
    }
    if (typeof data === "string") {
        const trimmed = data.trim();
        if (!trimmed) {
            return data;
        }
        if (trimmed.charAt(0) === "{" || trimmed.charAt(0) === "[") {
            try {
                data = JSON.parse(trimmed);
            } catch (e) {
                return data;
            }
        }
    }
    if (data && typeof data.payload === "string") {
        try {
            return JSON.parse(data.payload);
        } catch (e) {
            return data.payload;
        }
    }
    if (data && data.entry && data.entry[0] && data.entry[0].content) {
        return unwrap(data.entry[0].content);
    }
    return data;
}

export function formatErr(err) {
    if (err == null) {
        return "unknown error";
    }
    if (typeof err === "string") {
        const xml = xmlMessages(err);
        if (xml.length) {
            return xml.join("; ");
        }
        return err;
    }
    if (err.message) {
        const xml = xmlMessages(err.message);
        if (xml.length) {
            return xml.join("; ");
        }
        return err.message;
    }
    const data = err.data;
    if (data && data.messages && data.messages.length) {
        return data.messages
            .map((m) => m.text || m.message || "")
            .filter(Boolean)
            .join("; ");
    }
    if (typeof data === "string") {
        const xml = xmlMessages(data);
        if (xml.length) {
            return xml.join("; ");
        }
    }
    if (data && data.error) {
        return String(data.error);
    }
    try {
        return JSON.stringify(err);
    } catch (e) {
        return String(err);
    }
}

export function apiFetch(path, opts) {
    opts = opts || {};
    return fetch(apiUrl(path, opts.query), {
        method: opts.method || "GET",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-Splunk-Form-Key": csrfToken(),
        },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then((res) =>
        res.text().then((text) => {
            const parsed = parseBody(text);
            if (!res.ok) {
                throw new Error(formatErr(parsed) || "HTTP " + res.status);
            }
            return unwrap(parsed);
        })
    );
}

export function apiUpload(path, opts) {
    opts = opts || {};
    const headers = {
        "X-Requested-With": "XMLHttpRequest",
        "X-Splunk-Form-Key": csrfToken(),
    };
    if (opts.contentType) {
        headers["Content-Type"] = opts.contentType;
    }
    return fetch(apiUrl(path, opts.query), {
        method: opts.method || "POST",
        credentials: "same-origin",
        headers,
        body: opts.body,
    }).then((res) =>
        res.text().then((text) => {
            const parsed = parseBody(text);
            if (!res.ok) {
                throw new Error(formatErr(parsed) || "HTTP " + res.status);
            }
            return unwrap(parsed);
        })
    );
}

export function apiGet(path, query) {
    return apiFetch(path, { query }).then((data) =>
        Array.isArray(data) ? data : data == null ? [] : data
    );
}

export function apiPatch(path, body) {
    return apiFetch(path, { method: "POST", body });
}

export function viewUrl(name) {
    return localePrefix() + "/app/stigs_in_splunk/" + name;
}

export function isDefaultWorkspace(rec) {
    const value = rec && rec.is_default;
    return value === true || value === 1 || value === "1" || value === "true";
}

export function workspaceLabel(rec) {
    const name = (rec && (rec.name || rec._key)) || "";
    return isDefaultWorkspace(rec) ? name + " (default)" : name;
}

export function defaultWorkspaceId(list) {
    const rows = Array.isArray(list) ? list : [];
    const flagged = rows.find(isDefaultWorkspace);
    if (flagged && flagged._key) {
        return flagged._key;
    }
    const named = rows.find(
        (row) => String(row.name || "").toLowerCase() === "default"
    );
    return (named && named._key) || (rows[0] && rows[0]._key) || "";
}

export function downloadBlob(filename, blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

export function downloadText(filename, text, mime) {
    downloadBlob(
        filename,
        new Blob([text], { type: mime || "application/octet-stream" })
    );
}

export function downloadBase64(filename, b64, mime) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) {
        bytes[i] = bin.charCodeAt(i);
    }
    downloadBlob(filename, new Blob([bytes], { type: mime || "application/octet-stream" }));
}
