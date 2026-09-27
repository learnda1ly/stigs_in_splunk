import React, { useEffect, useState } from "react";
import Heading from "@splunk/react-ui/Heading";
import TabBar from "@splunk/react-ui/TabBar";
import { apiGet } from "../api";
import {
    defaultImportTabWhenCatalogEmpty,
    readImportTabFromHash,
    storeImportTab,
} from "../components/onboarding/importTabPrefs";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
} from "../layout";
import BaselineImportPanel from "./BaselineImportPanel";
import ChecklistImportPanel from "./ChecklistImportPanel";

export default function ImportApp() {
    const [tab, setTab] = useState(() => readImportTabFromHash() || "baselines");

    useEffect(() => {
        const onHashChange = () => {
            const fromHash = readImportTabFromHash();
            if (fromHash) {
                setTab(fromHash);
                storeImportTab(fromHash);
            }
        };
        window.addEventListener("hashchange", onHashChange);
        return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    useEffect(() => {
        if (readImportTabFromHash()) {
            return;
        }
        apiGet("stig_baselines")
            .then((rows) => {
                const list = Array.isArray(rows) ? rows : [];
                const next = defaultImportTabWhenCatalogEmpty(!list.length);
                setTab(next);
                if (window.location.hash.replace(/^#/, "") !== next) {
                    window.location.hash = next;
                }
            })
            .catch(() => {
                setTab(defaultImportTabWhenCatalogEmpty(true));
            });
    }, []);

    const onTabChange = (e, { selectedTabId }) => {
        setTab(selectedTabId);
        storeImportTab(selectedTabId);
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
