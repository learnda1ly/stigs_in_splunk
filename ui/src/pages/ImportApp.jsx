import React, { useEffect, useState } from "react";
import Heading from "@splunk/react-ui/Heading";
import TabBar from "@splunk/react-ui/TabBar";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
} from "../layout";
import BaselineImportPanel from "./BaselineImportPanel";
import ChecklistImportPanel from "./ChecklistImportPanel";

const TAB_IDS = ["checklists", "baselines"];

function tabFromHash() {
    const id = (window.location.hash || "").replace(/^#/, "");
    return TAB_IDS.includes(id) ? id : "checklists";
}

export default function ImportApp() {
    const [tab, setTab] = useState(() => tabFromHash());

    useEffect(() => {
        const onHashChange = () => setTab(tabFromHash());
        window.addEventListener("hashchange", onHashChange);
        return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    const onTabChange = (e, { selectedTabId }) => {
        setTab(selectedTabId);
        if (window.location.hash.replace(/^#/, "") !== selectedTabId) {
            window.location.hash = selectedTabId;
        }
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Import
                    </Heading>
                </Brand>
            </Header>
            <div style={{ flex: 1, minHeight: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
                <PagePad style={{ paddingBottom: 8 }}>
                    <p style={{ maxWidth: 820, marginTop: 0, marginBottom: 16 }}>
                        Import checklist results into a workspace, or upload STIG baseline
                        catalogs (XCCDF, CKL, CKLB) for the editor.
                    </p>
                    <TabBar activeTabId={tab} onChange={onTabChange}>
                        <TabBar.Tab label="Checklists" tabId="checklists" />
                        <TabBar.Tab label="Baselines" tabId="baselines" />
                    </TabBar>
                </PagePad>
                <div
                    id="checklists"
                    style={{
                        display: tab === "checklists" ? "flex" : "none",
                        flexDirection: "column",
                        flex: 1,
                        minHeight: 0,
                    }}
                >
                    <ChecklistImportPanel />
                </div>
                <div
                    id="baselines"
                    style={{
                        display: tab === "baselines" ? "block" : "none",
                        paddingBottom: 24,
                    }}
                >
                    <BaselineImportPanel />
                </div>
            </div>
        </Shell>
    );
}
