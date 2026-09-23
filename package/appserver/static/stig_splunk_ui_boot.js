/**
 * Splunk dashboard `script=` hooks must be AMD (RequireJS). Webpack SplunkUI pages are
 * plain IIFE bundles under appserver/static/ui/*.js — load them with a script tag instead
 * of require(["../appserver/..."]) which resolves to the wrong URL under /app/.
 */
require(["splunkjs/ready!"], function () {
    var root = document.getElementById("stig-ui-root");
    if (!root) {
        return;
    }
    var bundle = (root.getAttribute("data-ui-bundle") || "").trim();
    if (!bundle) {
        if (typeof console !== "undefined" && console.error) {
            console.error(
                "[stigs_in_splunk] #stig-ui-root is missing data-ui-bundle (e.g. grants, editor)."
            );
        }
        return;
    }
    if (bundle.indexOf("/") >= 0 || bundle.indexOf("..") >= 0) {
        return;
    }
    var file = bundle.indexOf(".js") === bundle.length - 3 ? bundle : bundle + ".js";
    var path = window.location.pathname || "";
    var locale = (path.match(/^(\/[^/]+)\//) || [])[1] || "/en-US";
    var src =
        locale +
        "/static/app/stigs_in_splunk/ui/" +
        file +
        "?v=" +
        encodeURIComponent(bundle);
    var existing = document.querySelector('script[data-stig-ui-bundle="' + bundle + '"]');
    if (existing) {
        return;
    }
    var script = document.createElement("script");
    script.setAttribute("data-stig-ui-bundle", bundle);
    script.src = src;
    document.head.appendChild(script);
});
