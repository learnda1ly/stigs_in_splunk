require(["splunkjs/ready!"], function () {
    var path = window.location.pathname || "";
    var locale = (path.match(/^(\/[^/]+)\//) || [])[1] || "/en-US";
    var script = document.createElement("script");
    script.src =
        locale + "/static/app/stigs_in_splunk/ui/review_requirements.js?b=review_requirements20260922";
    document.head.appendChild(script);
});
