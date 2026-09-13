require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/ready!",
], function ($, mvc) {
    "use strict";

    var service = mvc.createService({ owner: "nobody", app: "stigs_in_splunk" });

    function formatErr(err) {
        if (err == null) {
            return "unknown error";
        }
        if (typeof err === "string") {
            return err;
        }
        if (err.message) {
            return err.message;
        }
        if (err.error) {
            return String(err.error);
        }
        var data = err.data;
        if (data && data.messages && data.messages.length) {
            return data.messages
                .map(function (m) {
                    return m.text || m.message || "";
                })
                .filter(Boolean)
                .join("; ");
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

    function parseBody(res) {
        var raw = res && res.data;
        if (raw && raw.entry && raw.entry[0] && raw.entry[0].content) {
            raw = raw.entry[0].content;
        }
        if (typeof raw === "string") {
            try {
                raw = JSON.parse(raw);
            } catch (e) {
                /* keep string */
            }
        }
        return raw;
    }

    function apiGet(path, query) {
        return new Promise(function (resolve, reject) {
            service.get(path, query || {}, function (err, res) {
                if (err) {
                    reject(err);
                    return;
                }
                resolve(parseBody(res));
            });
        });
    }

    function csrfToken() {
        var token = "";
        document.cookie.split(";").forEach(function (part) {
            var cookie = part.trim();
            if (cookie.indexOf("splunkweb_csrf_token_") === 0) {
                token = decodeURIComponent(cookie.substring(cookie.indexOf("=") + 1));
            }
        });
        return token;
    }

    function apiUrl(path, query) {
        var url =
            "/en-US/splunkd/__raw/servicesNS/nobody/stigs_in_splunk/" +
            String(path).replace(/^\//, "");
        if (query) {
            var parts = [];
            Object.keys(query).forEach(function (key) {
                if (query[key] != null && query[key] !== "") {
                    parts.push(
                        encodeURIComponent(key) + "=" + encodeURIComponent(query[key])
                    );
                }
            });
            if (parts.length) {
                url += "?" + parts.join("&");
            }
        }
        return url;
    }

    function apiFetch(path, opts) {
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
        }).then(function (res) {
            return res.text().then(function (text) {
                var parsed = text;
                if (text && (text.charAt(0) === "{" || text.charAt(0) === "[")) {
                    try {
                        parsed = JSON.parse(text);
                    } catch (e) {
                        parsed = text;
                    }
                }
                if (!res.ok) {
                    throw new Error(formatErr(parsed) || "HTTP " + res.status);
                }
                return parsed;
            });
        });
    }

    function unwrap(data) {
        if (data && typeof data.payload === "string") {
            try {
                return JSON.parse(data.payload);
            } catch (e) {
                return data.payload;
            }
        }
        return data;
    }

    function downloadBlob(filename, blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function downloadText(filename, text, mime) {
        downloadBlob(filename, new Blob([text], { type: mime || "application/octet-stream" }));
    }

    function downloadBase64(filename, b64, mime) {
        var bin = atob(b64);
        var bytes = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i += 1) {
            bytes[i] = bin.charCodeAt(i);
        }
        downloadBlob(filename, new Blob([bytes], { type: mime || "application/octet-stream" }));
    }

    function safeName(value) {
        return String(value || "item").replace(/[^A-Za-z0-9._-]+/g, "_");
    }

    function fileNameFor(row, fmt) {
        var host = safeName(row.hostname || row._key);
        var stig = safeName(row.stig_id || row.baseline_title || "stig");
        var ver = safeName(row.baseline_version || "");
        var name = host + "_" + stig;
        if (ver) {
            name += "_" + ver;
        }
        return name + "." + (fmt === "ckl" ? "ckl" : "cklb");
    }

    function ExportDash() {
        this.root = document.getElementById("stig-export-root");
        this.collections = [];
        this.rows = [];
        this.collectionId = "";
        this.format = "cklb";
        this.renderShell();
        this.load();
    }

    ExportDash.prototype.renderShell = function () {
        this.root.innerHTML =
            '<p class="stig-export-help">' +
            "Each checklist is <strong>one host</strong> and <strong>one baseline</strong>. " +
            "<code>package_id</code> is stored on findings (reviews), not on the checklist, " +
            "so you can fill it later from a Splunk search or other system.</p>" +
            '<div class="stig-export-toolbar">' +
            '<div><label>Collection</label><select id="stig-ex-collection"></select></div>' +
            '<div><label>Format</label><select id="stig-ex-format">' +
            '<option value="cklb">CKLB (JSON)</option>' +
            '<option value="ckl">CKL (XML)</option>' +
            "</select></div>" +
            "</div>" +
            '<div class="stig-export-actions">' +
            '<button type="button" class="stig-btn" id="stig-ex-selected">Download selected</button>' +
            '<button type="button" class="stig-btn stig-btn-secondary" id="stig-ex-all">Download all in view</button>' +
            "</div>" +
            '<div class="stig-export-table-wrap">' +
            '<table class="stig-export-table">' +
            "<thead><tr>" +
            '<th><input type="checkbox" id="stig-ex-allbox" /></th>' +
            "<th>Host</th><th>Baseline</th><th>Collection</th>" +
            "<th>Completed</th><th>Package IDs (from findings)</th><th></th>" +
            "</tr></thead>" +
            '<tbody id="stig-ex-body"></tbody>' +
            "</table></div>" +
            '<div class="stig-export-status" id="stig-ex-status"></div>';

        var self = this;
        $("#stig-ex-collection").on("change", function () {
            self.collectionId = this.value;
            self.loadRows();
        });
        $("#stig-ex-format").on("change", function () {
            self.format = this.value;
        });
        $("#stig-ex-allbox").on("change", function () {
            $("#stig-ex-body input[type=checkbox]").prop("checked", this.checked);
        });
        $("#stig-ex-selected").on("click", function () {
            self.downloadIds(self.selectedIds());
        });
        $("#stig-ex-all").on("click", function () {
            self.downloadIds(
                self.rows.map(function (row) {
                    return row._key;
                })
            );
        });
        $("#stig-ex-body").on("click", "button[data-id]", function () {
            self.downloadIds([$(this).data("id")]);
        });
    };

    ExportDash.prototype.setStatus = function (text) {
        $("#stig-ex-status").text(text || "");
    };

    ExportDash.prototype.load = function () {
        var self = this;
        this.setStatus("Loading collections…");
        apiGet("stig_collections")
            .then(function (data) {
                self.collections = Array.isArray(data) ? data : [];
                var sel = $("#stig-ex-collection");
                sel.empty().append('<option value="">All collections</option>');
                self.collections.forEach(function (c) {
                    sel.append($("<option></option>").val(c._key).text(c.name || c._key));
                });
                return self.loadRows();
            })
            .catch(function (err) {
                self.setStatus("Failed to load collections: " + formatErr(err));
            });
    };

    ExportDash.prototype.enrichRows = function (checklists, hosts, baselines, collections) {
        var hostMap = {};
        var baseMap = {};
        var collMap = {};
        (hosts || []).forEach(function (h) {
            if (h && h._key) {
                hostMap[h._key] = h;
            }
        });
        (baselines || []).forEach(function (b) {
            if (b && b._key) {
                baseMap[b._key] = b;
            }
        });
        (collections || []).forEach(function (c) {
            if (c && c._key) {
                collMap[c._key] = c;
            }
        });
        return (checklists || []).map(function (cl) {
            var host = hostMap[cl.host_id] || {};
            var baseline = baseMap[cl.baseline_id] || {};
            var coll = collMap[cl.stig_collection_id] || {};
            return {
                _key: cl._key,
                title: cl.title,
                stig_collection_id: cl.stig_collection_id,
                collection_name: coll.name || "",
                host_id: cl.host_id,
                hostname: host.hostname || "",
                baseline_id: cl.baseline_id,
                baseline_title: baseline.title || "",
                stig_id: baseline.stig_id || "",
                baseline_version: baseline.version || "",
                review_count: cl.review_count || 0,
                valid_count: cl.valid_count || 0,
                package_ids: cl.package_ids || [],
            };
        });
    };

    ExportDash.prototype.loadRows = function () {
        var self = this;
        this.setStatus("Loading checklists…");
        var query = this.collectionId ? { stig_collection_id: this.collectionId } : {};
        return Promise.all([
            apiGet("stig_checklists", query),
            apiGet("stig_hosts", query),
            apiGet("stig_baselines"),
            apiGet("stig_collections"),
        ])
            .then(function (parts) {
                self.rows = self.enrichRows(parts[0], parts[1], parts[2], parts[3]);
                self.renderRows();
            })
            .catch(function (err) {
                self.setStatus("Failed to load checklists: " + formatErr(err));
            });
    };

    ExportDash.prototype.renderRows = function () {
        var body = $("#stig-ex-body");
        body.empty();
        if (!this.rows.length) {
            body.append(
                '<tr><td colspan="7" class="muted">No checklists found.</td></tr>'
            );
            this.setStatus("0 checklists");
            return;
        }
        this.rows.forEach(function (row) {
            var pkgs = (row.package_ids || []).join(", ") || "—";
            var tr = $("<tr></tr>");
            tr.append(
                '<td><input type="checkbox" class="stig-ex-row" value="' +
                    $("<div>").text(row._key).html() +
                    '" /></td>'
            );
            tr.append($("<td></td>").text(row.hostname || row.host_id || "—"));
            tr.append(
                $("<td></td>").text(
                    (row.stig_id || row.baseline_title || "—") +
                        (row.baseline_version ? " " + row.baseline_version : "")
                )
            );
            tr.append($("<td></td>").text(row.collection_name || "—"));
            tr.append(
                $("<td></td>").text(
                    (row.valid_count || 0) + " / " + (row.review_count || 0)
                )
            );
            tr.append($("<td></td>").addClass("stig-pkg-list").text(pkgs));
            tr.append(
                $("<td></td>").append(
                    $("<button></button>")
                        .attr("type", "button")
                        .addClass("stig-btn stig-btn-secondary")
                        .attr("data-id", row._key)
                        .text("Download")
                )
            );
            body.append(tr);
        });
        $("#stig-ex-allbox").prop("checked", false);
        this.setStatus(this.rows.length + " checklist" + (this.rows.length === 1 ? "" : "s"));
    };

    ExportDash.prototype.selectedIds = function () {
        var ids = [];
        $("#stig-ex-body input.stig-ex-row:checked").each(function () {
            ids.push(this.value);
        });
        return ids;
    };

    ExportDash.prototype.rowById = function (id) {
        return (
            this.rows.find(function (row) {
                return row._key === id;
            }) || {}
        );
    };

    ExportDash.prototype.downloadIds = function (ids) {
        var self = this;
        if (!ids.length) {
            this.setStatus("Select at least one checklist.");
            return;
        }
        var fmt = this.format;
        this.setStatus("Exporting " + ids.length + " checklist" + (ids.length === 1 ? "" : "s") + "…");
        $("#stig-ex-selected, #stig-ex-all").prop("disabled", true);

        var work;
        if (ids.length === 1) {
            work = apiFetch("stig_checklists/" + ids[0] + "/export", {
                query: { format: fmt },
            }).then(function (content) {
                var text = typeof content === "string" ? content : JSON.stringify(content, null, 2);
                downloadText(
                    fileNameFor(self.rowById(ids[0]), fmt),
                    text,
                    fmt === "ckl" ? "application/xml" : "application/json"
                );
            });
        } else {
            work = apiFetch("stig_checklists/export_bulk", {
                method: "POST",
                body: { checklist_ids: ids, format: fmt },
            }).then(function (payload) {
                var doc = unwrap(payload);
                if (!doc || !doc.content_base64) {
                    throw new Error("bulk export returned no zip");
                }
                downloadBase64(doc.filename || "stig-checklists.zip", doc.content_base64, "application/zip");
            });
        }

        work
            .then(function () {
                self.setStatus("Download started.");
            })
            .catch(function (err) {
                self.setStatus("Export failed: " + formatErr(err));
            })
            .finally(function () {
                $("#stig-ex-selected, #stig-ex-all").prop("disabled", false);
            });
    };

    new ExportDash();
});
