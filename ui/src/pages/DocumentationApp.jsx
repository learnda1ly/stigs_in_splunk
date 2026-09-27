import React from "react";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Table from "@splunk/react-ui/Table";
import { viewUrl } from "../api";
import { Brand, Header, PageIntro, PagePad, SectionBlock, Shell } from "../layout";

const prose = {
    fontSize: "14px",
    lineHeight: 1.55,
    maxWidth: "960px",
};

const listStyle = {
    margin: "0 0 12px",
    paddingLeft: "1.35rem",
};

function DocSection({ id, title, children }) {
    return (
        <SectionBlock id={id} style={{ marginBottom: "28px" }}>
            <Heading level={2}>{title}</Heading>
            <div style={prose}>{children}</div>
        </SectionBlock>
    );
}

const CAPABILITY_ROWS = [
    {
        capability: "stig_read",
        meaning: "View workspaces, hosts, baselines, checklists, and reviews via the app REST API.",
    },
    {
        capability: "stig_write",
        meaning: "Create and update STIG data (reviews, hosts, imports) via the app REST API.",
    },
    {
        capability: "stig_review_accept",
        meaning: "Accept or reject submitted reviews (owner/manager governance).",
    },
    {
        capability: "stig_admin",
        meaning: "Manage workspace access lists and delete STIG entities.",
    },
];

export default function DocumentationApp() {
    return (
        <Shell>
            <Header>
                <Brand>
                    <Heading level={1} style={{ margin: 0 }}>
                        Documentation
                    </Heading>
                </Brand>
            </Header>
            <PagePad>
                <PageIntro>
                    <p>
                        Operator reference for Splunk admins who need to stand up assessment
                        workflows without reading the developer README. This app stores DISA STIG
                        baseline and checklist <strong>review state</strong> in KV store; it is
                        not a STIG Manager replacement.
                    </p>
                </PageIntro>

                <DocSection id="overview" title="1. Overview">
                    <p>
                        Use STIG in Splunk to import Manual STIG baselines, register hosts per
                        workspace, assign baselines to hosts, record findings in the STIG Editor,
                        and report from collection dashboards or export CKL/CKLB/XCCDF. Automation
                        can push scan results via REST or HEC; scheduled reconcile keeps search
                        indexes aligned with KV.
                    </p>
                </DocSection>

                <DocSection id="before-you-begin" title="2. Before you begin">
                    <ul style={listStyle}>
                        <li>Splunk Enterprise 9.x search head with KV store enabled.</li>
                        <li>
                            Disk for KV collections and indexes <code>stig</code> and{" "}
                            <code>stig_audit</code> (shipped in the app).
                        </li>
                        <li>
                            A Splunk administrator who can assign custom roles and configure HTTP
                            Event Collector inputs.
                        </li>
                        <li>MIT license — see repository <code>LICENSE</code>.</li>
                    </ul>
                </DocSection>

                <DocSection id="install" title="3. Install">
                    <p>
                        Install the packaged tarball via Splunk Web → <strong>Apps</strong> →{" "}
                        <strong>Manage Apps</strong> → <strong>Install app from file</strong>, or
                        extract <code>stigs_in_splunk-*.tar.gz</code> into{" "}
                        <code>$SPLUNK_HOME/etc/apps/stigs_in_splunk</code>.
                    </p>
                    <p>
                        If files were installed as <strong>root</strong>, fix ownership once so UCC
                        can write settings:
                    </p>
                    <pre
                        style={{
                            ...prose,
                            fontSize: "13px",
                            padding: "12px",
                            background: "var(--stig-bg-elevated, rgba(255,255,255,0.04))",
                            borderRadius: "6px",
                            overflow: "auto",
                        }}
                    >
                        chown -R splunk:splunk $SPLUNK_HOME/etc/apps/stigs_in_splunk
                    </pre>
                    <p style={{ fontSize: "13px", color: "var(--stig-fg-muted)" }}>
                        Developers build with <code>./scripts/build_ucc.sh</code> and{" "}
                        <code>./scripts/package_ucc.sh</code>; that workflow is not required on
                        production search heads that install the tarball only.
                    </p>
                </DocSection>

                <DocSection id="access-control" title="4. Access control">
                    <p>
                        Assign Splunk role <strong>stig_user</strong> or <strong>stig_admin</strong>{" "}
                        (or grant capabilities individually). Users with only default Splunk roles
                        see empty data or REST 403 responses.
                    </p>
                    <Table>
                        <Table.Head>
                            <Table.HeadCell>Capability</Table.HeadCell>
                            <Table.HeadCell>Meaning</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {CAPABILITY_ROWS.map((row) => (
                                <Table.Row key={row.capability}>
                                    <Table.Cell>
                                        <code>{row.capability}</code>
                                    </Table.Cell>
                                    <Table.Cell>{row.meaning}</Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                    <p>
                        Role <code>stig_user</code> includes <code>stig_read</code>,{" "}
                        <code>stig_write</code>, and <code>edit_kvstore</code>. Role{" "}
                        <code>stig_admin</code> adds <code>stig_review_accept</code> and{" "}
                        <code>stig_admin</code>. Splunk <code>admin</code> inherits all STIG
                        capabilities in the shipped defaults.
                    </p>
                    <p>
                        Assign roles under Splunk <strong>Settings → Users and authentication →
                        Roles</strong>.
                    </p>
                </DocSection>

                <DocSection id="hec" title="5. HTTP Event Collector (HEC)">
                    <p>
                        Checklist and scan ingest index <code>stig:finding</code> events through
                        HEC. Configure the token on the Splunk input — not inside this app.
                    </p>
                    <ul style={listStyle}>
                        <li>
                            Input name: <code>stig_findings</code> (see app{" "}
                            <code>inputs.conf</code>)
                        </li>
                        <li>
                            Default index: <code>stig</code>
                        </li>
                        <li>
                            Sourcetype: <code>stig:finding</code>
                        </li>
                    </ul>
                    <p>
                        Splunk Web → <strong>Settings → Data inputs → HTTP Event Collector</strong>{" "}
                        → enable or edit the <code>stig_findings</code> input and assign a token.
                        The app stores collector URL and index names under{" "}
                        <Link to={viewUrl("configuration")}>Workspaces</Link> →{" "}
                        <strong>Editor &amp; ingest</strong> but never stores the token in app
                        settings.
                    </p>
                </DocSection>

                <DocSection id="quick-start" title="6. Quick start (about 15 minutes)">
                    <p>Follow this order on a greenfield install:</p>
                    <ol style={listStyle}>
                        <li>
                            <strong>Workspaces</strong> — Open{" "}
                            <Link to={viewUrl("configuration")}>Workspaces</Link> and create a
                            workspace (or use the auto-created <strong>Default</strong> workspace).
                            Imports without a workspace id use Default until you mark another
                            workspace as the default import target in the Workspaces table.
                        </li>
                        <li>
                            <strong>Import baselines</strong> —{" "}
                            <Link to={`${viewUrl("stig_import_ui")}#baselines`}>Import</Link> →{" "}
                            <strong>Baselines</strong> tab; load Manual STIG XCCDF or a DISA library
                            zip. Baselines are global to the app, not per workspace.
                        </li>
                        <li>
                            <strong>Hosts</strong> —{" "}
                            <Link to={viewUrl("stig_hosts_ui")}>Hosts</Link>: select your workspace,
                            add at least one host (hostname required).
                        </li>
                        <li>
                            <strong>Assign STIG</strong> —{" "}
                            <Link to={viewUrl("stig_editor_ui")}>STIG Editor</Link>: select workspace
                            and host, then use <strong>Assign STIG</strong> (shown when the host has
                            no checklist yet). Alternate: create a checklist from{" "}
                            <Link to={viewUrl("stig_library_ui")}>STIG library</Link>.
                        </li>
                        <li>
                            <strong>Review findings</strong> — In the editor, select a finding,
                            update status and details, then <strong>Write</strong> (and{" "}
                            <strong>Submit</strong> when your workflow requires review).
                        </li>
                        <li>
                            <strong>Collection dashboard</strong> — Open{" "}
                            <Link to={viewUrl("stig_collection_dashboard_ui")}>
                                Collection dashboard
                            </Link>{" "}
                            for metrics, findings report, and POA&amp;M export after data exists.
                        </li>
                    </ol>
                </DocSection>

                <DocSection id="import-reference" title="7. Import reference">
                    <p>
                        <Link to={viewUrl("stig_import_ui")}>Import</Link> has two tabs. Choose
                        based on what you are loading:
                    </p>
                    <ul style={listStyle}>
                        <li>
                            <strong>Baselines</strong> — Manual STIG XCCDF, CKL/CKLB baseline files,
                            or chunked DISA product/quarterly zips. Required before assignment and
                            before XCCDF scan results can resolve rules. No workspace selector
                            (catalog is global).
                        </li>
                        <li>
                            <strong>Checklists</strong> — CKL, CKLB, or zip archives tied to a{" "}
                            <strong>workspace</strong>. Can auto-create hosts. Success banner points
                            to the editor.
                        </li>
                    </ul>
                    <p>
                        For unattended ingest, use REST <code>POST /stig_imports</code> and{" "}
                        <code>POST /stig_baselines/import</code> (management port{" "}
                        <code>8089</code>). Supported formats include <code>xccdf-results</code>,{" "}
                        <code>ckl</code>, <code>cklb</code>, and zip variants. HEC posts use
                        sourcetype <code>stig:finding</code>; scheduled search{" "}
                        <code>stigkvreconcile</code> runs every five minutes to align KV with
                        indexed events. See repository file <code>docs/automation.md</code> for curl
                        examples and Evaluate-STIG / OpenSCAP notes.
                    </p>
                </DocSection>

                <DocSection id="multi-user" title="8. Multi-user governance">
                    <p>
                        Solo admins can skip this section. Teams should configure grants before
                        assessors hit permission errors on Submit or Accept.
                    </p>
                    <ul style={listStyle}>
                        <li>
                            <Link to={viewUrl("stig_grants_ui")}>Workspace grants</Link> — assign
                            principals as owner, manager, member, or restricted; scope hosts,
                            baselines, and labels per grant.
                        </li>
                        <li>
                            <strong>Member</strong> grants full workspace access but still requires
                            Splunk capability <code>stig_write</code> to save reviews.
                        </li>
                        <li>
                            <strong>Submit</strong> sends a completed finding for owner/manager{" "}
                            <strong>Accept</strong> or <strong>Reject</strong>; acceptors need{" "}
                            <code>stig_review_accept</code> (or owner/manager grant on that
                            workspace).
                        </li>
                        <li>
                            Optional: <Link to={viewUrl("stig_review_requirements_ui")}>
                                Review requirements
                            </Link>{" "}
                            and asset <Link to={viewUrl("stig_labels_ui")}>labels</Link> for
                            larger programs.
                        </li>
                    </ul>
                </DocSection>

                <DocSection id="troubleshooting" title="9. Troubleshooting">
                    <ul style={listStyle}>
                        <li>
                            <strong>Blank Workspaces page</strong> — Install from the built tarball,
                            not a raw git checkout without running{" "}
                            <code>./scripts/build_ucc.sh</code> (UCC bundles PyPI packages; git
                            alone leaves Configuration empty).
                        </li>
                        <li>
                            <strong>403 on REST or empty tables</strong> — Assign{" "}
                            <code>stig_user</code> or required capabilities; confirm{" "}
                            <code>edit_kvstore</code>.
                        </li>
                        <li>
                            <strong>Empty editor after import</strong> — Confirm baselines imported,
                            host selected, and STIG assigned to that host.
                        </li>
                        <li>
                            <strong>UCC save errors</strong> — Fix app directory ownership (
                            <code>chown -R splunk:splunk …</code> above).
                        </li>
                        <li>
                            <strong>Delete workspace returns 409</strong> — Workspace still has
                            hosts, checklists, or grants; delete dependents first or use REST{" "}
                            <code>DELETE …?cascade=true</code> with <code>stig_admin</code>.
                        </li>
                        <li>
                            <strong>Import succeeds but search is empty</strong> — Verify HEC token
                            on input <code>stig_findings</code> and wait for reconcile (about five
                            minutes).
                        </li>
                    </ul>
                </DocSection>

                <DocSection id="further-reading" title="10. Further reading (repository)">
                    <p>These paths exist in the shipped source repository, not in Splunk Web:</p>
                    <ul style={listStyle}>
                        <li>
                            <code>docs/automation.md</code> — REST and HEC automation
                        </li>
                        <li>
                            <code>docs/api.md</code> and <code>docs/openapi.yaml</code> — REST
                            contract
                        </li>
                        <li>
                            <code>docs/audit-index.md</code> — audit index dashboard
                        </li>
                        <li>
                            <code>docs/onboarding-user-guide.md</code> — manual QA checklist
                        </li>
                    </ul>
                </DocSection>
            </PagePad>
        </Shell>
    );
}
