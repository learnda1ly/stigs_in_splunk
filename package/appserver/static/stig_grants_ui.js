/** @deprecated Use dashboard script stig_splunk_ui_boot.js; kept for cached views. */
require(["splunkjs/ready!"], function () {
    var root = document.getElementById("stig-ui-root");
    if (!root) {
        return;
    }
    if (!root.getAttribute("data-ui-bundle")) {
        root.setAttribute("data-ui-bundle", "grants");
    }
    var path = window.location.pathname || "";
    var locale = (path.match(/^(\/[^/]+)\//) || [])[1] || "/en-US";
    var script = document.createElement("script");
    script.src = locale + "/static/app/stigs_in_splunk/ui/grants.js?v=grants";
    document.head.appendChild(script);
});
