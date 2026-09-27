import React from "react";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import { viewUrl } from "../../api";
import {
    sessionMissingGrantCapabilities,
    useSessionCapabilities,
} from "./useSessionCapabilities";

export default function CapabilityGrantBanner() {
    const capabilities = useSessionCapabilities();
    if (!sessionMissingGrantCapabilities(capabilities)) {
        return null;
    }
    return (
        <Message appearance="warning" style={{ marginBottom: 8 }}>
            You need the <code>stig_write</code> capability to edit and submit findings (or an
            owner/manager workspace grant). See{" "}
            <Link to={viewUrl("stig_documentation_ui")}>Documentation</Link> for roles, grants,
            and <code>stig_review_accept</code>.
        </Message>
    );
}
