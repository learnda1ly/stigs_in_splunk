import React from "react";
import Button from "@splunk/react-ui/Button";
import Link from "@splunk/react-ui/Link";
import { viewUrl, viewUrlWithQuery } from "../../api";
import { Empty } from "../../layout";

export default function EditorEmptyState({ collectionId }) {
    const importUrl = viewUrl("stig_import_ui") + "#baselines";
    const hostsUrl = collectionId
        ? viewUrlWithQuery("stig_hosts_ui", { stig_collection_id: collectionId })
        : viewUrl("stig_hosts_ui");
    const workspacesUrl = viewUrl("configuration");

    return (
        <Empty style={{ textAlign: "center", padding: "32px 20px", maxWidth: 420, margin: "0 auto" }}>
            <p style={{ marginTop: 0, marginBottom: 16 }}>
                No findings in this workspace yet. Import a STIG baseline catalog, add a host,
                and assign a checklist to start reviewing.
            </p>
            <Button
                appearance="primary"
                label="Import baselines"
                onClick={() => {
                    window.location.assign(importUrl);
                }}
            />
            <p style={{ marginBottom: 0, marginTop: 16, fontSize: 13 }}>
                <Link to={hostsUrl}>Add host</Link>
                {" · "}
                <Link to={workspacesUrl}>Workspaces</Link>
            </p>
        </Empty>
    );
}
