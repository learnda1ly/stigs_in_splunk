import React from "react";
import Link from "@splunk/react-ui/Link";
import { viewUrl } from "../../api";

/**
 * Shown when the workspace list is empty (ACL or greenfield).
 */
export default function WorkspaceSelectHint({ style }) {
    return (
        <p
            style={{
                margin: "4px 0 0",
                fontSize: 12,
                color: "var(--splunk-color-content-muted, #666)",
                maxWidth: 280,
                ...style,
            }}
        >
            No workspaces are available to you. Create one under{" "}
            <Link to={viewUrl("configuration")}>Workspaces</Link> or ask an admin for access.
        </p>
    );
}
