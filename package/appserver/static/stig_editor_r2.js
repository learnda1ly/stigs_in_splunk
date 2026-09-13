require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/ready!",
], function ($, mvc) {
    "use strict";

    var STATUS_LABELS = {
        not_reviewed: "Not Reviewed",
        open: "Open",
        not_a_finding: "Not a Finding",
        not_applicable: "Not Applicable",
    };

    var STATUS_KEYS = {
        "1": "not_reviewed",
        "2": "open",
        "3": "not_a_finding",
        "4": "not_applicable",
    };

    var service = mvc.createService({ owner: "nobody", app: "stigs_in_splunk" });

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

    function apiPatch(path, body) {
        return new Promise(function (resolve, reject) {
            service.request(path, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            }, function (err, res) {
                if (err) {
                    reject(err);
                    return;
                }
                resolve(parseBody(res));
            });
        });
    }

    function unwrapPayload(data) {
        if (data == null) {
            return data;
        }
        if (typeof data === "string") {
            var trimmed = data.trim();
            if (!trimmed) {
                return data;
            }
            if (trimmed.charAt(0) === "{" || trimmed.charAt(0) === "[") {
                try {
                    data = JSON.parse(trimmed);
                } catch (e) {
                    return data;
                }
            } else {
                return data;
            }
        }
        if (data && typeof data === "object" && data.entry && data.messages) {
            var entries = data.entry || [];
            if (entries.length === 1 && entries[0].content) {
                var content = entries[0].content;
                if (content && content.payload !== undefined) {
                    return unwrapPayload(content.payload);
                }
                return content;
            }
            return entries.map(function (entry) {
                return entry.content || entry;
            });
        }
        if (
            data &&
            typeof data === "object" &&
            !Array.isArray(data) &&
            data.payload !== undefined &&
            Object.keys(data).length === 1
        ) {
            return unwrapPayload(data.payload);
        }
        return data;
    }

    function parseBody(res) {
        if (!res) {
            return null;
        }
        if (res.data !== undefined && res.data !== null) {
            return unwrapPayload(res.data);
        }
        if (typeof res === "string") {
            return unwrapPayload(res);
        }
        return unwrapPayload(res);
    }

    function toast(msg, isError) {
        var el = $("#stig-toast");
        if (!el.length) {
            el = $('<div id="stig-toast" class="stig-toast"></div>').appendTo("body");
        }
        el.text(msg).toggleClass("error", !!isError).addClass("show");
        setTimeout(function () {
            el.removeClass("show");
        }, 2800);
    }

    function StigEditor() {
        this.root = document.getElementById("stig-editor-root");
        this.collections = [];
        this.checklists = [];
        this.hostsById = {};
        this.rulesByKey = {};
        this.items = [];
        this.filtered = [];
        this.selectedIndex = -1;
        this.statusFilter = null;
        this.searchQuery = "";
        this.vimMode = "normal";
        this.pendingSave = false;
        var self = this;
        this.renderShell();
        this.bindVim();
        this.fitLayout();
        $(window).on("resize.stigEditor", function () {
            self.fitLayout();
        });
        setTimeout(function () {
            self.fitLayout();
        }, 0);
        setTimeout(function () {
            self.fitLayout();
        }, 300);
        this.loadCollections();
    }

    StigEditor.prototype.fitLayout = function () {
        var root = this.root;
        if (!root) {
            return;
        }
        document.body.classList.add("stig-editor-page");
        var header = document.querySelector(".dashboard-header");
        if (header) {
            header.style.display = "none";
        }
        var top = root.getBoundingClientRect().top;
        var height = Math.max(240, window.innerHeight - top);
        root.style.height = height + "px";
        root.style.maxHeight = height + "px";
        root.style.minHeight = "0";
        root.style.overflow = "hidden";
        root.style.display = "flex";
        root.style.flexDirection = "column";
        var main = root.querySelector(".stig-main");
        if (main) {
            main.style.flex = "1 1 auto";
            main.style.minHeight = "0";
            main.style.height = "auto";
            main.style.overflow = "hidden";
        }
        var pane = root.querySelector(".stig-list-pane");
        if (pane) {
            pane.style.display = "flex";
            pane.style.flexDirection = "column";
            pane.style.minHeight = "0";
            pane.style.height = "100%";
            pane.style.overflow = "hidden";
        }
        var list = document.getElementById("stig-rule-list");
        if (list) {
            list.style.flex = "1 1 auto";
            list.style.minHeight = "0";
            list.style.height = "100%";
            list.style.overflowY = "auto";
            list.style.overflowX = "hidden";
        }
    };

    StigEditor.prototype.renderShell = function () {
        this.root.innerHTML =
            '<div class="stig-toolbar">' +
            '<div><label>Collection</label><select id="stig-collection"></select></div>' +
            '<div><label>Checklist</label><select id="stig-checklist" disabled></select></div>' +
            '<input type="search" class="stig-search" id="stig-search" placeholder="Filter rules (/) …" />' +
            '<div class="stig-status-filters" id="stig-filters"></div>' +
            '<span class="stig-vim-mode" id="stig-vim-mode">NORMAL</span>' +
            '<span class="stig-toolbar-meta" id="stig-meta"></span>' +
            "</div>" +
            '<div class="stig-main">' +
            '<div class="stig-list-pane">' +
            '<div class="stig-list-header"><span>Status</span><span>Rule</span><span>Title</span></div>' +
            '<ul class="stig-rule-list" id="stig-rule-list" tabindex="0"></ul>' +
            "</div>" +
            '<div class="stig-detail-pane" id="stig-detail"></div>' +
            "</div>";

        var self = this;
        $("#stig-collection").on("change", function () {
            self.onCollectionChange(this.value);
        });
        $("#stig-checklist").on("change", function () {
            self.loadChecklistData(this.value);
        });
        $("#stig-search").on("input", function () {
            self.searchQuery = this.value.trim().toLowerCase();
            self.applyFilter();
        });
        $("#stig-rule-list").on("click", "li", function () {
            var idx = parseInt(this.getAttribute("data-idx"), 10);
            self.selectIndex(idx);
        });

        var filters = $("#stig-filters");
        filters.append(
            '<button type="button" class="stig-filter-btn active" data-status="">All</button>'
        );
        Object.keys(STATUS_LABELS).forEach(function (st) {
            filters.append(
                '<button type="button" class="stig-filter-btn" data-status="' +
                    st +
                    '">' +
                    STATUS_LABELS[st] +
                    "</button>"
            );
        });
        filters.on("click", "button", function () {
            filters.find("button").removeClass("active");
            $(this).addClass("active");
            self.statusFilter = $(this).data("status") || null;
            self.applyFilter();
        });

        $("#stig-detail").html(
            '<div class="stig-detail-empty">Select a collection and checklist to edit reviews.</div>'
        );
        if (!document.getElementById("stig-editor-layout-css")) {
            var layout = document.createElement("style");
            layout.id = "stig-editor-layout-css";
            layout.textContent =
                ".stig-list-pane{width:48%!important;min-width:560px!important;max-width:760px!important;}" +
                "ul.stig-rule-list>li.stig-rule-row,.stig-list-header{" +
                "display:grid!important;grid-template-columns:136px 160px minmax(0,1fr)!important;" +
                "column-gap:12px!important;align-items:center!important;}";
            document.head.appendChild(layout);
        }
    };

    StigEditor.prototype.setMeta = function (text) {
        $("#stig-meta").text(text || "");
    };

    StigEditor.prototype.loadCollections = function () {
        var self = this;
        var sel = $("#stig-collection");
        sel.html('<option value="">Loading…</option>');
        apiGet("stig_collections")
            .then(function (data) {
                self.collections = Array.isArray(data) ? data : [];
                if (!self.collections.length) {
                    sel.html('<option value="">No collections in KV store</option>');
                    self.setMeta("KV store is empty");
                    $("#stig-detail").html(
                        '<div class="stig-detail-empty">No stig_collections in the KV store. Import a baseline (for example <code>scripts/demo_rhel8_web01.py</code>), then reload this page.</div>'
                    );
                    return;
                }
                sel.empty().append('<option value="">— select —</option>');
                self.collections.forEach(function (c) {
                    sel.append(
                        $("<option></option>").val(c._key).text(c.name || c._key)
                    );
                });
            })
            .catch(function (err) {
                toast("Failed to load collections: " + err, true);
                sel.html('<option value="">Error</option>');
            });
    };

    StigEditor.prototype.onCollectionChange = function (collectionId) {
        var sel = $("#stig-checklist");
        sel.prop("disabled", true).html('<option value="">Loading…</option>');
        this.items = [];
        this.filtered = [];
        this.renderList();
        $("#stig-detail").html(
            '<div class="stig-detail-empty">Select a checklist.</div>'
        );
        if (!collectionId) {
            sel.html('<option value="">— select collection first —</option>');
            return;
        }
        var self = this;
        Promise.all([
            apiGet("stig_checklists", { stig_collection_id: collectionId }),
            apiGet("stig_hosts", { stig_collection_id: collectionId }),
        ])
            .then(function (results) {
                self.checklists = Array.isArray(results[0]) ? results[0] : [];
                var hosts = Array.isArray(results[1]) ? results[1] : [];
                self.hostsById = {};
                hosts.forEach(function (h) {
                    self.hostsById[h._key] = h;
                });
                sel.empty().append('<option value="">— select —</option>');
                self.checklists.forEach(function (cl) {
                    var host = self.hostsById[cl.host_id] || {};
                    var label =
                        (cl.title || "Checklist") +
                        " · " +
                        (host.hostname || cl.host_id || "?");
                    sel.append($("<option></option>").val(cl._key).text(label));
                });
                sel.prop("disabled", false);
            })
            .catch(function (err) {
                toast("Failed to load checklists: " + err, true);
            });
    };

    StigEditor.prototype.loadChecklistData = function (checklistId) {
        if (!checklistId) {
            return;
        }
        var checklist = this.checklists.find(function (c) {
            return c._key === checklistId;
        });
        if (!checklist) {
            return;
        }
        var self = this;
        $("#stig-rule-list").html('<li class="stig-loading">Loading rules…</li>');
        Promise.all([
            apiGet("stig_reviews", { checklist_id: checklistId }),
            apiGet("stig_baselines/" + checklist.baseline_id + "/rules"),
        ])
            .then(function (results) {
                var reviews = Array.isArray(results[0]) ? results[0] : [];
                var rules = Array.isArray(results[1]) ? results[1] : [];
                self.rulesByKey = {};
                rules.forEach(function (r) {
                    var k = (r.rule_id || "") + "|" + (r.group_id || "");
                    self.rulesByKey[k] = r;
                    if (r.rule_id) {
                        self.rulesByKey[r.rule_id] = r;
                    }
                });
                self.items = reviews.map(function (rev) {
                    var rule =
                        self.rulesByKey[rev.rule_id] ||
                        self.rulesByKey[
                            (rev.rule_id || "") + "|" + (rev.group_id || "")
                        ] ||
                        {};
                    return {
                        review: rev,
                        rule: rule,
                        dirty: false,
                        local: null,
                    };
                });
                self.items.sort(function (a, b) {
                    var va = a.rule.rule_version || a.review.rule_version || "";
                    var vb = b.rule.rule_version || b.review.rule_version || "";
                    return va.localeCompare(vb, undefined, { numeric: true });
                });
                self.setMeta(
                    self.items.length + " rules · " + (checklist.title || checklistId)
                );
                self.applyFilter();
                if (self.filtered.length) {
                    self.selectIndex(0);
                }
            })
            .catch(function (err) {
                toast("Failed to load reviews: " + err, true);
            });
    };

    StigEditor.prototype.applyFilter = function () {
        var q = this.searchQuery;
        var st = this.statusFilter;
        this.filtered = this.items.filter(function (item) {
            var rev = item.review;
            if (st && rev.status !== st) {
                return false;
            }
            if (!q) {
                return true;
            }
            var rule = item.rule;
            var hay =
                (rev.rule_id || "") +
                " " +
                (rev.group_id || "") +
                " " +
                (rule.rule_version || "") +
                " " +
                (rule.rule_title || "") +
                " " +
                (rev.finding_details || "") +
                " " +
                (rev.comments || "");
            return hay.toLowerCase().indexOf(q) >= 0;
        });
        if (
            this.selectedIndex >= this.filtered.length ||
            (this.selectedIndex >= 0 &&
                this.filtered[this.selectedIndex] !== this.currentItem())
        ) {
            this.selectedIndex = this.filtered.length ? 0 : -1;
        }
        this.renderList();
        this.renderDetail();
    };

    StigEditor.prototype.currentItem = function () {
        if (this.selectedIndex < 0 || this.selectedIndex >= this.filtered.length) {
            return null;
        }
        return this.filtered[this.selectedIndex];
    };

    StigEditor.prototype.findItemIndex = function (item) {
        return this.filtered.indexOf(item);
    };

    StigEditor.prototype.renderList = function () {
        var list = $("#stig-rule-list");
        list.empty();
        var self = this;
        this.filtered.forEach(function (item, idx) {
            var rev = item.review;
            var rule = item.rule;
            var st = rev.status || "not_reviewed";
            var li = $("<li></li>")
                .addClass("stig-rule-row")
                .attr("data-idx", idx)
                .toggleClass("selected", idx === self.selectedIndex)
                .toggleClass("dirty", item.dirty);
            var statusCell = $("<span></span>").addClass("stig-col-status");
            statusCell.append(
                $("<span></span>")
                    .addClass("stig-badge stig-badge-" + st)
                    .text(STATUS_LABELS[st] || st)
            );
            var idCell = $("<span></span>")
                .addClass("stig-rule-id stig-col-id")
                .text(rule.rule_version || rev.rule_version || rev.rule_id || "—");
            var titleCell = $("<span></span>")
                .addClass("stig-rule-title stig-col-title")
                .text(rule.rule_title || rev.rule_id || "Untitled rule");
            li.append(statusCell, idCell, titleCell);
            list.append(li);
        });
        if (!this.filtered.length) {
            list.html('<li class="stig-loading">No matching rules.</li>');
        }
    };

    StigEditor.prototype.renderDetail = function () {
        var pane = $("#stig-detail");
        var item = this.currentItem();
        if (!item) {
            pane.html('<div class="stig-detail-empty">No rule selected.</div>');
            return;
        }
        var rev = item.review;
        var rule = item.rule;
        var st = rev.status || "not_reviewed";
        var self = this;

        pane.html(
            '<div class="stig-detail-header">' +
                "<h2>" +
                escapeHtml(rule.rule_title || rev.rule_id || "Rule") +
                "</h2>" +
                '<div class="stig-detail-meta">' +
                "<span><strong>Version:</strong> " +
                escapeHtml(rule.rule_version || rev.rule_version || "—") +
                "</span>" +
                "<span><strong>Rule:</strong> " +
                escapeHtml(rev.rule_id || "—") +
                "</span>" +
                "<span><strong>Group:</strong> " +
                escapeHtml(rev.group_id || rule.group_id || "—") +
                "</span>" +
                "<span><strong>Severity:</strong> " +
                escapeHtml(rule.severity || "—") +
                "</span>" +
                "</div></div>" +
                '<div class="stig-field"><label>Status</label>' +
                '<select id="stig-status-select">' +
                optionStatuses(st) +
                "</select></div>" +
                '<div class="stig-field"><label>Check content</label>' +
                '<div class="stig-pre-block">' +
                escapeHtml(rule.check_content || "(no check content in baseline)") +
                "</div></div>" +
                '<div class="stig-field"><label>Fix text</label>' +
                '<div class="stig-pre-block">' +
                escapeHtml(rule.fix_text || "—") +
                "</div></div>" +
                '<div class="stig-field"><label>Finding details</label>' +
                '<textarea id="stig-finding" rows="4"></textarea></div>' +
                '<div class="stig-field"><label>Comments</label>' +
                '<textarea id="stig-comments" rows="3"></textarea></div>' +
                '<div class="stig-actions">' +
                '<button type="button" class="stig-btn" id="stig-save">Save (:w)</button>' +
                '<button type="button" class="stig-btn stig-btn-secondary" id="stig-revert">Revert</button>' +
                "<span id=\"stig-save-hint\"></span>" +
                "</div>"
        );

        $("#stig-finding").val(rev.finding_details || "");
        $("#stig-comments").val(rev.comments || "");

        $("#stig-status-select").on("change", function () {
            self.markDirty(item, { status: this.value });
        });
        $("#stig-finding, #stig-comments")
            .on("focus", function () {
                self.setVimMode("insert");
            })
            .on("blur", function () {
                self.setVimMode("normal");
            })
            .on("input", function () {
                var patch = {};
                patch[this.id === "stig-finding" ? "finding_details" : "comments"] =
                    this.value;
                self.markDirty(item, patch);
            });

        $("#stig-save").on("click", function () {
            self.saveCurrent();
        });
        $("#stig-revert").on("click", function () {
            item.dirty = false;
            item.local = null;
            self.renderDetail();
            self.renderList();
        });
    };

    StigEditor.prototype.markDirty = function (item, patch) {
        item.dirty = true;
        item.local = item.local || {};
        Object.assign(item.local, patch);
        if (patch.status) {
            item.review.status = patch.status;
        }
        if (patch.finding_details !== undefined) {
            item.review.finding_details = patch.finding_details;
        }
        if (patch.comments !== undefined) {
            item.review.comments = patch.comments;
        }
        this.renderList();
        $("#stig-save-hint").text("Unsaved changes");
    };

    StigEditor.prototype.collectPatch = function (item) {
        var patch = item.local ? Object.assign({}, item.local) : {};
        patch.status =
            patch.status || $("#stig-status-select").val() || item.review.status;
        patch.finding_details = $("#stig-finding").val();
        patch.comments = $("#stig-comments").val();
        return patch;
    };

    StigEditor.prototype.saveCurrent = function () {
        var item = this.currentItem();
        if (!item || this.pendingSave) {
            return;
        }
        var patch = this.collectPatch(item);
        var self = this;
        this.pendingSave = true;
        $("#stig-save").prop("disabled", true);
        apiPatch("stig_reviews/" + item.review._key, patch)
            .then(function (updated) {
                item.review = updated;
                item.dirty = false;
                item.local = null;
                toast("Saved " + (item.rule.rule_version || item.review._key));
                self.renderList();
                self.renderDetail();
            })
            .catch(function (err) {
                toast("Save failed: " + err, true);
            })
            .finally(function () {
                self.pendingSave = false;
                $("#stig-save").prop("disabled", false);
            });
    };

    StigEditor.prototype.selectIndex = function (idx) {
        if (idx < 0 || idx >= this.filtered.length) {
            return;
        }
        this.selectedIndex = idx;
        this.renderList();
        this.renderDetail();
        var row = $("#stig-rule-list li.stig-rule-row.selected");
        if (row.length && row[0].scrollIntoView) {
            row[0].scrollIntoView({ block: "nearest" });
        }
    };

    StigEditor.prototype.moveSelection = function (delta) {
        if (!this.filtered.length) {
            return;
        }
        var next = this.selectedIndex < 0 ? 0 : this.selectedIndex + delta;
        next = Math.max(0, Math.min(this.filtered.length - 1, next));
        this.selectIndex(next);
    };

    StigEditor.prototype.setStatus = function (status) {
        var item = this.currentItem();
        if (!item) {
            return;
        }
        $("#stig-status-select").val(status);
        this.markDirty(item, { status: status });
    };

    StigEditor.prototype.setVimMode = function (mode) {
        this.vimMode = mode;
        var el = $("#stig-vim-mode");
        el.text(mode === "insert" ? "INSERT" : "NORMAL");
        el.toggleClass("insert", mode === "insert");
    };

    StigEditor.prototype.isEditingField = function () {
        var ae = document.activeElement;
        if (!ae) {
            return false;
        }
        var tag = ae.tagName;
        return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    };

    StigEditor.prototype.showHelp = function () {
        var html =
            '<div class="stig-help-overlay" id="stig-help">' +
            '<div class="stig-help-panel">' +
            "<h3>Keyboard shortcuts</h3>" +
            "<table>" +
            "<tr><td><kbd>j</kbd> / <kbd>k</kbd></td><td>Next / previous rule</td></tr>" +
            "<tr><td><kbd>g</kbd><kbd>g</kbd> / <kbd>G</kbd></td><td>First / last rule</td></tr>" +
            "<tr><td><kbd>1</kbd>–<kbd>4</kbd></td><td>Status: Not Reviewed, Open, Not a Finding, N/A</td></tr>" +
            "<tr><td><kbd>o</kbd> <kbd>n</kbd> <kbd>f</kbd> <kbd>a</kbd></td><td>Quick status: Open, Not Reviewed, Not a Finding, N/A</td></tr>" +
            "<tr><td><kbd>:</kbd><kbd>w</kbd> / <kbd>Ctrl</kbd>+<kbd>s</kbd></td><td>Save current review</td></tr>" +
            "<tr><td><kbd>/</kbd></td><td>Focus rule filter</td></tr>" +
            "<tr><td><kbd>i</kbd></td><td>Focus finding details</td></tr>" +
            "<tr><td><kbd>Esc</kbd></td><td>Leave insert mode / close help</td></tr>" +
            "<tr><td><kbd>?</kbd></td><td>This help</td></tr>" +
            "</table>" +
            '<p><button type="button" class="stig-btn" id="stig-help-close">Close</button></p>' +
            "</div></div>";
        $("body").append(html);
        $("#stig-help-close, .stig-help-overlay").on("click", function (e) {
            if (e.target.id === "stig-help-close" || e.target.id === "stig-help") {
                $("#stig-help").remove();
            }
        });
    };

    StigEditor.prototype.bindVim = function () {
        var self = this;
        var pendingG = false;

        $(document).on("keydown.stigEditor", function (e) {
            if ($("#stig-help").length) {
                if (e.key === "Escape") {
                    $("#stig-help").remove();
                }
                return;
            }

            if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                e.preventDefault();
                self.saveCurrent();
                return;
            }

            if (self.isEditingField()) {
                if (e.key === "Escape") {
                    $(document.activeElement).blur();
                    self.setVimMode("normal");
                }
                return;
            }

            if (e.key === "?") {
                e.preventDefault();
                self.showHelp();
                return;
            }

            if (e.key === "/") {
                e.preventDefault();
                $("#stig-search").focus();
                return;
            }

            if (e.key === "i") {
                e.preventDefault();
                var f = document.getElementById("stig-finding");
                if (f) {
                    f.focus();
                }
                return;
            }

            if (e.key === ":") {
                e.preventDefault();
                self._vimCmd = "";
                toast("Command mode — type w then Enter to save");
                $(document).one("keypress.stigCmd", function (ev) {
                    if (ev.key === "w") {
                        self._vimCmd = "w";
                    }
                });
                $(document).one("keydown.stigCmd", function (ev) {
                    if (ev.key === "Enter" && self._vimCmd === "w") {
                        self.saveCurrent();
                    }
                    if (ev.key === "Escape") {
                        self._vimCmd = "";
                    }
                    $(document).off(".stigCmd");
                });
                return;
            }

            if (e.key === "j") {
                e.preventDefault();
                pendingG = false;
                self.moveSelection(1);
                return;
            }
            if (e.key === "k") {
                e.preventDefault();
                pendingG = false;
                self.moveSelection(-1);
                return;
            }
            if (e.key === "G") {
                e.preventDefault();
                pendingG = false;
                if (self.filtered.length) {
                    self.selectIndex(self.filtered.length - 1);
                }
                return;
            }
            if (e.key === "g") {
                if (pendingG) {
                    e.preventDefault();
                    pendingG = false;
                    if (self.filtered.length) {
                        self.selectIndex(0);
                    }
                } else {
                    pendingG = true;
                    setTimeout(function () {
                        pendingG = false;
                    }, 400);
                }
                return;
            }

            if (STATUS_KEYS[e.key]) {
                e.preventDefault();
                self.setStatus(STATUS_KEYS[e.key]);
                return;
            }
            var quick = {
                o: "open",
                n: "not_reviewed",
                f: "not_a_finding",
                a: "not_applicable",
            };
            if (quick[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                self.setStatus(quick[e.key]);
            }
        });
    };

    function optionStatuses(selected) {
        return Object.keys(STATUS_LABELS)
            .map(function (st) {
                return (
                    '<option value="' +
                    st +
                    '"' +
                    (st === selected ? " selected" : "") +
                    ">" +
                    STATUS_LABELS[st] +
                    "</option>"
                );
            })
            .join("");
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    new StigEditor();
});
