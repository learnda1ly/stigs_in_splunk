require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/ready!",
], function ($, mvc) {
    "use strict";

    var VIM_STORAGE_KEY = "stigs_in_splunk.vim_mode";
    var userService = mvc.createService({ app: "stigs_in_splunk" });

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
                    return m.text || m.message || String(m);
                })
                .join("; ");
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
        return new Promise(function (resolve) {
            userService.get(
                "configs/conf-stig_editor/settings",
                {},
                function (err, res) {
                    if (err) {
                        resolve(null);
                        return;
                    }
                    resolve(extractVimEnabled(res && res.data));
                }
            );
        });
    }

    function writeRemoteVim(enabled) {
        return new Promise(function (resolve, reject) {
            userService.post(
                "configs/conf-stig_editor/settings",
                { vim_mode: enabled ? "true" : "false" },
                function (err) {
                    if (err) {
                        reject(err);
                        return;
                    }
                    resolve();
                }
            );
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
