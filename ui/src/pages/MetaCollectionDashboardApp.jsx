import React, { useEffect, useState } from "react";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Table from "@splunk/react-ui/Table";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import styled from "styled-components";
import { apiFetch, viewUrlWithQuery } from "../api";
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

export default function MetaCollectionDashboardApp() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [banner, setBanner] = useState(null);

    useEffect(() => {
        setLoading(true);
        setBanner(null);
        apiFetch("stig_collections/meta/metrics")
            .then((payload) => setData(payload))
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

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2}>All workspaces</Heading>
                </Brand>
            </Header>
            <Body>
                <PagePad>
                    {banner ? (
                        <Message type={banner.type} style={{ marginBottom: 12 }}>
                            {banner.message}
                        </Message>
                    ) : null}
                    <Message type="info" style={{ marginBottom: 16 }}>
                        Cross-workspace metrics for workspaces you can read (same ACL as{" "}
                        <code>GET /stig_collections</code>). Org totals include every readable
                        workspace; the table may be paginated on large deployments. Open a
                        workspace dashboard from the table below.
                    </Message>
                    {loading ? <WaitSpinner size="medium" /> : null}
                    {!loading && data && data.workspace_count === 0 ? (
                        <Message type="info">No readable workspaces.</Message>
                    ) : null}
                    {!loading && totals ? (
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
                    {!loading && workspaces.length ? (
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
                                    <Table.HeadCell>Not reviewed</Table.HeadCell>
                                    <Table.HeadCell>Open findings</Table.HeadCell>
                                    <Table.HeadCell>Dashboard</Table.HeadCell>
                                </Table.Head>
                                <Table.Body>
                                    {workspaces.map((row) => {
                                        const rowTotals = row.totals || {};
                                        const rowCompletion = row.completion || {};
                                        return (
                                            <Table.Row key={row.stig_collection_id}>
                                                <Table.Cell>
                                                    {row.collection_name || row.stig_collection_id}
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
                                                    {rowCompletion.not_reviewed ?? "—"}
                                                </Table.Cell>
                                                <Table.Cell>
                                                    {rowCompletion.open_findings ?? "—"}
                                                </Table.Cell>
                                                <Table.Cell>
                                                    <Link
                                                        to={viewUrlWithQuery(
                                                            "stig_collection_dashboard_ui",
                                                            {
                                                                stig_collection_id:
                                                                    row.stig_collection_id,
                                                            }
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
