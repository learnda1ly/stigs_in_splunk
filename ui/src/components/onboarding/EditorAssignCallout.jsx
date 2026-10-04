import React from "react";
import Button from "@splunk/react-ui/Button";
import Message from "@splunk/react-ui/Message";
import Link from "@splunk/react-ui/Link";
import { viewUrl, viewUrlWithQuery } from "../../api";

export default function EditorAssignCallout({ collectionId, hostId }) {
    const hostsUrl = collectionId
        ? viewUrlWithQuery("stig_hosts_ui", {
              stig_collection_id: collectionId,
          })
        : viewUrl("stig_hosts_ui");
    const libraryUrl = viewUrl("stig_library_ui");

    return (
        <Message appearance="info" style={{ marginBottom: 16 }}>
            <p style={{ marginTop: 0 }}>
                This host has no checklist yet. Open <strong>Hosts</strong> and use{" "}
                <strong>Setup</strong> to assign a STIG baseline, or add revisions in the{" "}
                <Link to={libraryUrl}>STIG library</Link> first.
            </p>
            <Button
                appearance="primary"
                onClick={() => {
                    const url = hostId
                        ? hostsUrl + (hostsUrl.includes("?") ? "&" : "?") + "host_id=" + hostId
                        : hostsUrl;
                    window.location.assign(url);
                }}
                label="Open Hosts"
            />
        </Message>
    );
}
