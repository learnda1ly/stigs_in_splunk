import React, { useEffect, useState } from "react";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import TabBar from "@splunk/react-ui/TabBar";
import { viewUrl } from "../api";
import {
    Brand,
    BrandKicker,
    Header,
    HeaderMeta,
    Shell,
} from "../layout";
import BaselineImportPanel from "./BaselineImportPanel";
import ChecklistImportPanel from "./ChecklistImportPanel";

function tabFromHash() {
    const id = (window.location.hash || "").replace(/^#/, "");
    return id === "baselines" ? "baselines" : "checklists";
}

export default function ImportApp() {
    const [tab, setTab] = useState(tabFromHash);

    useEffect(() => {
        const onHash = () => setTab(tabFromHash());
        window.addEventListener("hashchange", onHash);
        return () => window.removeEventListener("hashchange", onHash);
    }, []);

    const onTabChange = (e, { selectedTabId }) => {
        setTab(selectedTabId);
        window.location.hash = selectedTabId;
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
                <HeaderMeta>
                    <Link to={viewUrl("stig_editor_ui")}>Editor</Link>
                    <Link to={viewUrl("stig_export_ui")}>Export</Link>
                    <Link to={viewUrl("configuration")}>Configuration</Link>
                </HeaderMeta>
            </Header>
            <div style={{ flex: "0 0 auto", padding: "0 20px" }}>
                <TabBar activeTabId={tab} onChange={onTabChange}>
                    <TabBar.Tab tabId="checklists" label="Checklists" />
                    <TabBar.Tab tabId="baselines" label="Baselines" />
                </TabBar>
            </div>
            {tab === "baselines" ? (
                <BaselineImportPanel />
            ) : (
                <ChecklistImportPanel />
            )}
        </Shell>
    );
}
