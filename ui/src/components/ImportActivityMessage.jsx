import React from "react";
import Message from "@splunk/react-ui/Message";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";

/**
 * Non-dismissible status while a long import request is in flight.
 */
export default function ImportActivityMessage({ title, detail, hint }) {
    if (!title) {
        return null;
    }
    return (
        <Message appearance="info" style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <WaitSpinner size="small" style={{ flexShrink: 0, marginTop: 2 }} />
                <div>
                    <div style={{ fontWeight: 600 }}>{title}</div>
                    {detail ? <div style={{ marginTop: 4 }}>{detail}</div> : null}
                    {hint ? (
                        <div
                            style={{
                                marginTop: 6,
                                fontSize: 12,
                                color: "var(--splunk-color-content-muted, #666)",
                            }}
                        >
                            {hint}
                        </div>
                    ) : null}
                </div>
            </div>
        </Message>
    );
}
