import React, { useEffect } from "react";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import { viewUrl } from "../api";
import {
    Brand,
    BrandKicker,
    Header,
    HeaderMeta,
    PagePad,
    Shell,
} from "../layout";
import BaselineImportPanel from "./BaselineImportPanel";
import ChecklistImportPanel from "./ChecklistImportPanel";

function scrollToSection(id) {
    const el = document.getElementById(id);
    if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        window.location.hash = id;
    }
}

export default function ImportApp() {
    useEffect(() => {
        const id = (window.location.hash || "").replace(/^#/, "");
        if (id === "baselines" || id === "checklists") {
            requestAnimationFrame(() => scrollToSection(id));
        }
    }, []);

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
            <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
                <PagePad style={{ paddingBottom: 8 }}>
                    <p style={{ maxWidth: 820, marginTop: 0, marginBottom: 16 }}>
                        Import checklist results into a workspace, or upload STIG baseline
                        catalogs (XCCDF / CKL / CKLB) for the editor. Jump to{" "}
                        <Link onClick={() => scrollToSection("checklists")}>
                            checklists
                        </Link>{" "}
                        or{" "}
                        <Link onClick={() => scrollToSection("baselines")}>
                            baselines
                        </Link>
                        .
                    </p>
                </PagePad>
                <section id="checklists" style={{ scrollMarginTop: 12 }}>
                    <PagePad style={{ paddingTop: 0, paddingBottom: 8 }}>
                        <Heading level={3} style={{ margin: "0 0 8px" }}>
                            Checklists
                        </Heading>
                    </PagePad>
                    <ChecklistImportPanel />
                </section>
                <hr
                    style={{
                        margin: "32px 20px",
                        border: "none",
                        borderTop: "1px solid var(--splunk-color-border, #ccc)",
                    }}
                />
                <section id="baselines" style={{ scrollMarginTop: 12, paddingBottom: 24 }}>
                    <PagePad style={{ paddingTop: 0, paddingBottom: 8 }}>
                        <Heading level={3} style={{ margin: "0 0 8px" }}>
                            Baselines
                        </Heading>
                    </PagePad>
                    <BaselineImportPanel />
                </section>
            </div>
        </Shell>
    );
}
