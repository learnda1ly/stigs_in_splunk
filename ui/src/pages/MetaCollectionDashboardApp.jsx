import React, { useEffect, useMemo, useState } from "react";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Table from "@splunk/react-ui/Table";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import styled from "styled-components";
import Button from "@splunk/react-ui/Button";
import { apiFetch, apiGet, viewUrl, viewUrlWithQuery } from "../api";
import { useSessionCapabilities } from "../components/onboarding/useSessionCapabilities";
import {
    Brand,
    BrandKicker,
    Body,
    Header,
    PagePad,
    Shell,
} from "../layout";

const MetricGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
`;

const MetricCard = styled.div`
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 12px 14px;
    background: #fafafa;
`;

const MetricValue = styled.div`
    font-size: 22px;
    font-weight: 700;
    line-height: 1.2;
`;

const MetricLabel = styled.div`
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #666;
    margin-top: 4px;
`;

function checklistItem(label, done, href) {
    return (
        <li key={label} style={{ marginBottom: 6 }}>
            {done ? "✓ " : "○ "}
            {href && !done ? <Link to={href}>{label}</Link> : label}
        </li>
    );
}

export default function MetaCollectionDashboardApp() {
    const { canStigAdmin, canStigWrite } = useSessionCapabilities();
    const [data, setData] = useState(null);
    const [readiness, setReadiness] = useState(null);
    const [loading, setLoading] = useState(false);
    const [banner, setBanner] = useState(null);

    useEffect(() => {
        setLoading(true);
        setBanner(null);
        Promise.all([
            apiFetch("stig_collections/meta/metrics"),
            apiGet("stig_readiness").catch(() => null),
        ])
            .then(([payload, ready]) => {
                setData(payload);
                setReadiness(ready);
            })
            .catch((err) => {
                setData(null);
                setBanner({ type: "error", message: String(err.message || err) });
            })
            .finally(() => setLoading(false));
    }, []);

    const summary = data && data.summary;
    const completion = summary && summary.completion;
    const totals = summary && summary.totals;
    const workspaces = (data && data.workspaces) || [];

    const showAdminChecklist = useMemo(() => {
        if (canStigAdmin !== true && canStigWrite !== true) {
            return false;
        }
        if (!readiness) {
            return false;
        }
        const rolesOk = readiness.roles && readiness.roles.ok;
        const ownershipOk = readiness.ownership && readiness.ownership.ok;
        const configured = readiness.is_configured;
        const empty =
            !data || data.workspace_count === 0 || (totals && !totals.checklists);
        return !configured || !rolesOk || !ownershipOk || empty;
    }, [canStigAdmin, canStigWrite, readiness, data, totals]);

    const checklistSteps = useMemo(() => {
        const rolesOk = readiness && readiness.roles && readiness.roles.ok;
        const ownershipOk = readiness && readiness.ownership && readiness.ownership.ok;
        const hecOk = readiness && readiness.hec && readiness.hec.ok;
        const hasWorkspaces = data && data.workspace_count > 0;
        const hasHosts = totals && totals.hosts > 0;
        const hasChecklists = totals && totals.checklists > 0;
        return [
            {
                label: "Assign STIG role (stig_user or stig_admin)",
                done: rolesOk,
                href: viewUrl("stig_documentation_ui") + "#access-control",
            },
            {
                label: "Fix app ownership / open Setup checklist",
                done: ownershipOk && readiness && readiness.is_configured,
                href: viewUrl("setup"),
            },
            {
                label: "Create a workspace",
                done: hasWorkspaces,
                href: viewUrl("configuration"),
            },
            {
                label: "Import STIG revisions (STIG library)",
                done: hasChecklists,
                href: viewUrl("stig_library_ui"),
            },
            {
                label: "Add hosts",
                done: hasHosts,
                href: viewUrl("stig_hosts_ui"),
            },
            {
                label: "Configure HEC (optional)",
                done: hecOk,
                href: viewUrl("configuration"),
            },
        ];
    }, [readiness, data, totals]);

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2}>Overview</Heading>
                </Brand>
            </Header>
            <Body>
                <PagePad>
                    {banner ? (
                        <Message type={banner.type} style={{ marginBottom: 12 }}>
                            {banner.message}
                        </Message>
                    ) : null}
                    {showAdminChecklist ? (
                        <Message type="info" style={{ marginBottom: 16 }}>
                            <Heading level={4} style={{ marginTop: 0 }}>
                                Getting started
                            </Heading>
                            <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
                                {checklistSteps.map((step) =>
                                    checklistItem(step.label, step.done, step.href)
                                )}
                            </ul>
                        </Message>
                    ) : null}
                    <Message type="info" style={{ marginBottom: 16 }}>
                        Cross-workspace metrics for workspaces you can read. Open{" "}
                        <strong>Reports</strong> for workspace dashboards, or use the table to jump
                        into <strong>Assess</strong> and <strong>Review</strong>.
                    </Message>
                    {loading ? <WaitSpinner size="medium" /> : null}
                    {!loading && (!data || data.workspace_count === 0) ? (
                        <Message type="info">
                            <p style={{ marginTop: 0 }}>
                                No workspace metrics yet. Create a workspace, import STIG revisions,
                                and add hosts to see org-wide totals here.
                            </p>
                            <Button
                                appearance="primary"
                                label="Workspaces and settings"
                                onClick={() => {
                                    window.location.assign(viewUrl("configuration"));
                                }}
                            />
                            <p style={{ marginBottom: 0, fontSize: 13 }}>
                                <Link to={viewUrl("stig_library_ui")}>STIG library</Link> — add
                                baseline revisions when you are ready.
                            </p>
                        </Message>
                    ) : null}
                    {!loading && data && data.workspace_count > 0 && totals ? (
                        <>
                            <Heading level={4}>
                                Org totals ({data.workspace_count} workspace
                                {data.workspace_count === 1 ? "" : "s"})
                            </Heading>
                            <MetricGrid>
                                <MetricCard>
                                    <MetricValue>{totals.hosts}</MetricValue>
                                    <MetricLabel>Hosts</MetricLabel>
                                </MetricCard>
                                <MetricCard>
                                    <MetricValue>{totals.checklists}</MetricValue>
                                    <MetricLabel>Checklists</MetricLabel>
                                </MetricCard>
                                <MetricCard>
                                    <MetricValue>{totals.reviews}</MetricValue>
                                    <MetricLabel>Reviews</MetricLabel>
                                </MetricCard>
                                <MetricCard>
                                    <MetricValue>
                                        {completion ? completion.percent_reviewed : "—"}%
                                    </MetricValue>
                                    <MetricLabel>Reviewed</MetricLabel>
                                </MetricCard>
                                <MetricCard>
                                    <MetricValue>
                                        {completion ? completion.not_reviewed : "—"}
                                    </MetricValue>
                                    <MetricLabel>Not reviewed</MetricLabel>
                                </MetricCard>
                                <MetricCard>
                                    <MetricValue>
                                        {completion ? completion.open_findings : "—"}
                                    </MetricValue>
                                    <MetricLabel>Open findings</MetricLabel>
                                </MetricCard>
                            </MetricGrid>
                        </>
                    ) : null}
                    {!loading && data && data.workspace_count > 0 && workspaces.length ? (
                        <>
                            <Heading level={4} style={{ marginTop: 8 }}>
                                By workspace
                            </Heading>
                            <Table>
                                <Table.Head>
                                    <Table.HeadCell>Workspace</Table.HeadCell>
                                    <Table.HeadCell>Hosts</Table.HeadCell>
                                    <Table.HeadCell>Checklists</Table.HeadCell>
                                    <Table.HeadCell>Reviews</Table.HeadCell>
                                    <Table.HeadCell>% reviewed</Table.HeadCell>
                                    <Table.HeadCell>Assess</Table.HeadCell>
                                    <Table.HeadCell>Review</Table.HeadCell>
                                    <Table.HeadCell>Reports</Table.HeadCell>
                                </Table.Head>
                                <Table.Body>
                                    {workspaces.map((row) => {
                                        const rowTotals = row.totals || {};
                                        const rowCompletion = row.completion || {};
                                        const wsId = row.stig_collection_id;
                                        const wsQuery = { stig_collection_id: wsId };
                                        return (
                                            <Table.Row key={wsId}>
                                                <Table.Cell>
                                                    {row.collection_name || wsId}
                                                </Table.Cell>
                                                <Table.Cell>{rowTotals.hosts ?? "—"}</Table.Cell>
                                                <Table.Cell>
                                                    {rowTotals.checklists ?? "—"}
                                                </Table.Cell>
                                                <Table.Cell>{rowTotals.reviews ?? "—"}</Table.Cell>
                                                <Table.Cell>
                                                    {rowCompletion.percent_reviewed != null
                                                        ? rowCompletion.percent_reviewed + "%"
                                                        : "—"}
                                                </Table.Cell>
                                                <Table.Cell>
                                                    <Link
                                                        to={viewUrlWithQuery(
                                                            "stig_editor_ui",
                                                            wsQuery
                                                        )}
                                                    >
                                                        Open
                                                    </Link>
                                                </Table.Cell>
                                                <Table.Cell>
                                                    <Link
                                                        to={viewUrlWithQuery(
                                                            "stig_collection_review_ui",
                                                            wsQuery
                                                        )}
                                                    >
                                                        Open
                                                    </Link>
                                                </Table.Cell>
                                                <Table.Cell>
                                                    <Link
                                                        to={viewUrlWithQuery(
                                                            "stig_collection_dashboard_ui",
                                                            wsQuery
                                                        )}
                                                    >
                                                        Open
                                                    </Link>
                                                </Table.Cell>
                                            </Table.Row>
                                        );
                                    })}
                                </Table.Body>
                            </Table>
                        </>
                    ) : null}
                </PagePad>
            </Body>
        </Shell>
    );
}
