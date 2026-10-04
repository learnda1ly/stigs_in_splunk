import React from "react";
import Heading from "@splunk/react-ui/Heading";
import {
    Brand,
    BrandKicker,
    Header,
    Shell,
} from "../layout";
import ChecklistImportPanel from "./ChecklistImportPanel";

export default function ImportApp() {
    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Import results
                    </Heading>
                </Brand>
            </Header>
            <div
                style={{
                    flex: 1,
                    minHeight: 0,
                    overflow: "auto",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
                    <ChecklistImportPanel />
                </div>
            </div>
        </Shell>
    );
}
