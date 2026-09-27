require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/mvc/simplexml/ready!",
], function ($, mvc) {
    "use strict";

    function localePrefix() {
        var path = window.location.pathname || "";
        var match = path.match(/^(\/[^/]+)\//);
        return match ? match[1] : "/en-US";
    }

    function apiUrl(path) {
        return (
            localePrefix() +
            "/splunkd/__raw/servicesNS/nobody/stigs_in_splunk/" +
            String(path).replace(/^\//, "")
        );
    }

    function renderChecklist(report) {
        var $root = $("#stig-setup-status");
        if (!$root.length) {
            return;
        }

        var roles = report.roles || {};
        var hec = report.hec || {};
        var own = report.ownership || {};

        function row(title, item, okClass) {
            var ok = !!item.ok;
            var status = ok ? "Ready" : "Action needed";
            var cls = ok ? "stig-setup-ok" : "stig-setup-warn";
            var next = item.next_action
                ? "<p class=\"stig-setup-next\"><strong>Next:</strong> " + item.next_action + "</p>"
                : "";
            var extra = "";
            if (item.fix_in_splunk) {
                extra +=
                    "<p class=\"stig-setup-where\"><strong>In Splunk:</strong> " +
                    item.fix_in_splunk +
                    "</p>";
            }
            if (item.verify_in_splunk && !ok) {
                extra +=
                    "<p class=\"stig-setup-where\"><strong>Verify:</strong> " +
                    item.verify_in_splunk +
                    "</p>";
            }
            if (item.chown_command && !ok) {
                extra +=
                    "<p class=\"stig-setup-chown\"><strong>Fix ownership:</strong> " +
                    "<code>" +
                    item.chown_command +
                    "</code></p>";
            }
            if (item.guidance && !ok) {
                extra += "<p class=\"stig-setup-guidance\">" + item.guidance + "</p>";
            }
            if (item.message) {
                extra += "<p>" + item.message + "</p>";
            }
            return (
                "<section class=\"stig-setup-block " +
                cls +
                "\">" +
                "<h3>" +
                title +
                " — <span class=\"" +
                okClass +
                "\">" +
                status +
                "</span></h3>" +
                extra +
                next +
                "</section>"
            );
        }

        var html = "";
        html += row("STIG role (stig_user or stig_admin)", roles, "stig-setup-badge-ok");
        html += row("HEC input stig_findings (index stig)", hec, "stig-setup-badge-hec");
        html += row("App directory ownership (local/)", own, "stig-setup-badge-own");

        if (report.is_configured) {
            html +=
                "<p class=\"stig-setup-done\">Setup is already marked complete. You can still use this page to verify platform settings.</p>";
        }

        $root.html(html);

        var adminCanComplete = own.ok;
        $("#stig-setup-complete").prop("disabled", !adminCanComplete);
    }

    function loadReadiness() {
        $.ajax({
            url: apiUrl("stig_readiness"),
            type: "GET",
            dataType: "json",
        })
            .done(function (report) {
                renderChecklist(report);
            })
            .fail(function (xhr) {
                var msg =
                    (xhr.responseJSON && xhr.responseJSON.error) ||
                    "Could not load readiness. Reload this page or check splunkd logs.";
                $("#stig-setup-status").html(
                    "<p class=\"stig-setup-error\">" + msg + "</p>"
                );
            });
    }

    $("#stig-setup-complete").on("click", function () {
        var $btn = $(this);
        var $msg = $("#stig-setup-complete-msg");
        $btn.prop("disabled", true);
        $msg.text("Saving…");
        $.ajax({
            url: apiUrl("stig_readiness"),
            type: "POST",
            dataType: "json",
            contentType: "application/json",
            data: JSON.stringify({ action: "complete" }),
        })
            .done(function (resp) {
                if (resp.ok) {
                    $msg.text(resp.next_action || "Setup complete. Opening app…");
                    window.setTimeout(function () {
                        window.location.href =
                            localePrefix() + "/app/stigs_in_splunk/stig_editor_ui";
                    }, 1200);
                } else {
                    $msg.text(resp.error || resp.next_action || "Setup could not be saved.");
                    $btn.prop("disabled", false);
                }
            })
            .fail(function (xhr) {
                var body = xhr.responseJSON || {};
                $msg.text(
                    body.error ||
                        body.next_action ||
                        "Setup could not be saved. Fix ownership or use a Splunk admin account."
                );
                $btn.prop("disabled", false);
            });
    });

    loadReadiness();

    $("#stig-setup-doc-link").attr(
        "href",
        localePrefix() + "/app/stigs_in_splunk/stig_documentation_ui"
    );
});
