require([
    "jquery",
    "splunkjs/ready!",
], function ($) {
    "use strict";

    var VIM_STORAGE_KEY = "stigs_in_splunk.vim_mode";

    function localePrefix() {
        var path = window.location.pathname || "";
        var match = path.match(/^(\/[^/]+)\//);
        return match ? match[1] : "/en-US";
    }

    function csrfToken() {
        var token = "";
        String(document.cookie || "")
            .split(";")
            .forEach(function (part) {
                var cookie = part.trim();
                if (cookie.indexOf("splunkweb_csrf_token_") === 0) {
                    token = decodeURIComponent(cookie.substring(cookie.indexOf("=") + 1));
                }
            });
        return token;
    }

    function unwrap(data) {
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

    function apiFetch(path, opts) {
        opts = opts || {};
        var url =
            localePrefix() +
            "/splunkd/__raw/servicesNS/nobody/stigs_in_splunk/" +
            String(path).replace(/^\//, "");
        return fetch(url, {
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
                return unwrap(parsed);
            });
        });
    }

    function parseBool(raw) {
        raw = String(raw == null ? "" : raw).trim().toLowerCase();
        return raw === "1" || raw === "true" || raw === "yes";
    }

    function extractVimEnabled(raw) {
        if (raw == null) {
            return null;
        }
        if (typeof raw === "boolean") {
            return raw;
        }
        if (typeof raw === "number") {
            return raw !== 0;
        }
        if (typeof raw === "string") {
            var text = raw.trim().toLowerCase();
            if (!text) {
                return null;
            }
            if (text === "1" || text === "true" || text === "yes") {
                return true;
            }
            if (text === "0" || text === "false" || text === "no") {
                return false;
            }
            return null;
        }
        if (typeof raw !== "object") {
            return null;
        }
        if (Object.prototype.hasOwnProperty.call(raw, "vim_mode")) {
            return extractVimEnabled(raw.vim_mode);
        }
        if (raw.value != null && typeof raw.value !== "object") {
            return extractVimEnabled(raw.value);
        }
        var entry = raw.entry && raw.entry[0];
        var content = entry && entry.content;
        if (content && typeof content === "object") {
            if (Object.prototype.hasOwnProperty.call(content, "vim_mode")) {
                return extractVimEnabled(content.vim_mode);
            }
            if (content.value != null && typeof content.value !== "object") {
                return extractVimEnabled(content.value);
            }
        } else if (content != null) {
            return extractVimEnabled(content);
        }
        return null;
    }

    function xmlMessages(text) {
        var src = String(text || "");
        var matches = src.match(/<msg\b[^>]*>([\s\S]*?)<\/msg>/gi) || [];
        return matches
            .map(function (tag) {
                return tag
                    .replace(/<msg\b[^>]*>/i, "")
                    .replace(/<\/msg>/i, "")
                    .trim();
            })
            .filter(Boolean);
    }

    function formatErr(err) {
        if (err == null) {
            return "unknown error";
        }
        if (typeof err === "string") {
            var fromXml = xmlMessages(err);
            if (fromXml.length) {
                return fromXml.join("; ");
            }
            return err;
        }
        if (err.message) {
            var fromMsg = xmlMessages(err.message);
            if (fromMsg.length) {
                return fromMsg.join("; ");
            }
            return err.message;
        }
        if (err.error) {
            return String(err.error);
        }
        var data = err.data;
        if (data && data.messages && data.messages.length) {
            return data.messages
                .map(function (m) {
                    return m.text || m.message || String(m);
                })
                .join("; ");
        }
        if (typeof data === "string") {
            var fromData = xmlMessages(data);
            if (fromData.length) {
                return fromData.join("; ");
            }
        }
        try {
            return JSON.stringify(err);
        } catch (e) {
            return String(err);
        }
    }

    function readLocalVim() {
        try {
            var stored = window.localStorage.getItem(VIM_STORAGE_KEY);
            if (stored == null) {
                return null;
            }
            return parseBool(stored);
        } catch (e) {
            return null;
        }
    }

    function writeLocalVim(enabled) {
        try {
            window.localStorage.setItem(VIM_STORAGE_KEY, enabled ? "true" : "false");
            return true;
        } catch (e) {
            return false;
        }
    }

    function readRemoteVim() {
        return apiFetch("stig_settings")
            .then(function (raw) {
                return extractVimEnabled(raw);
            })
            .catch(function () {
                return null;
            });
    }

    function writeRemoteVim(enabled) {
        return apiFetch("stig_settings", {
            method: "POST",
            body: { vim_mode: !!enabled },
        });
    }

    function applyCheckbox(enabled) {
        $("#stig-vim-enabled").prop("checked", !!enabled);
    }

    var local = readLocalVim();
    if (local != null) {
        applyCheckbox(local);
    }
    readRemoteVim().then(function (remote) {
        if (readLocalVim() != null) {
            applyCheckbox(readLocalVim());
            return;
        }
        applyCheckbox(!!remote);
    });

    $("#stig-settings-save").on("click", function () {
        var enabled = $("#stig-vim-enabled").is(":checked");
        var btn = $(this).prop("disabled", true);
        var stored = writeLocalVim(enabled);
        writeRemoteVim(enabled)
            .then(function () {
                btn.prop("disabled", false);
                alert(
                    stored
                        ? "Vim mode saved. Return to the STIG Editor — it applies immediately."
                        : "Vim mode saved on the server. Return to the STIG Editor."
                );
            })
            .catch(function (err) {
                btn.prop("disabled", false);
                if (stored) {
                    alert(
                        "Vim mode is on for this browser. Server save failed: " +
                            formatErr(err)
                    );
                    return;
                }
                alert("Save failed: " + formatErr(err));
            });
    });
});
