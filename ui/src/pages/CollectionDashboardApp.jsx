import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import TabBar from "@splunk/react-ui/TabBar";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import styled from "styled-components";
import {
    apiFetch,
    apiGet,
    defaultWorkspaceId,
    downloadText,
    viewUrl,
    workspaceLabel,
} from "../api";
import {
    Actions,
    Brand,
    BrandKicker,
    Body,
    Header,
    HeaderMeta,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";
import { STATUS_LABELS, StatusChip } from "../status";

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

const SEVERITY_LABELS = {
    high: "High",
    medium: "Medium",
    low: "Low",
    unknown: "Unknown",
};

function csvEscape(value) {
    const text = value == null ? "" : String(value);
    if (/[",\n\r]/.test(text)) {
        return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
}

function findingsToCsv(rows) {
    const headers = [
        "hostname",
        "stig_id",
        "group_id",
        "rule_id",
        "rule_version",
        "severity",
        "status",
        "finding_details",
        "comments",
        "updated_at",
        "updated_by",
        "checklist_id",
        "host_id",
        "baseline_id",
        "_key",
    ];
    const lines = [headers.join(",")];
    (rows || []).forEach((row) => {
        lines.push(
            headers.map((key) => csvEscape(row[key])).join(",")
        );
    });
    return lines.join("\n");
}

function countRows(mapObj) {
    if (!mapObj) {
        return [];
    }
    return Object.keys(mapObj)
        .sort()
        .map((key) => ({ key, count: mapObj[key] }));
}

export default function CollectionDashboardApp() {
    const [tab, setTab] = useState("metrics");
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [metrics, setMetrics] = useState(null);
    const [findings, setFindings] = useState([]);
    const [pagination, setPagination] = useState(null);
    const [hosts, setHosts] = useState([]);
    const [statusFilter, setStatusFilter] = useState("open");
    const [severityFilter, setSeverityFilter] = useState("");
    const [hostFilter, setHostFilter] = useState("");
    const [loading, setLoading] = useState(false);
    const [findingsLoading, setFindingsLoading] = useState(false);
    const [banner, setBanner] = useState(null);

    useEffect(() => {
        apiGet("stig_collections")
            .then((rows) => {
                setCollections(rows);
                setCollectionId((prev) => prev || defaultWorkspaceId(rows));
            })
            .catch((err) => setBanner({ type: "error", message: String(err.message || err) }));
    }, []);

    const loadMetrics = (cid) => {
        if (!cid) {
            setMetrics(null);
            return;
        }
        setLoading(true);
        setBanner(null);
        apiFetch("stig_collections/" + cid + "/metrics")
            .then((data) => setMetrics(data))
            .catch((err) => {
                setMetrics(null);
                setBanner({ type: "error", message: String(err.message || err) });
            })
            .finally(() => setLoading(false));
    };

    const loadFindings = (cid, opts) => {
        opts = opts || {};
        if (!cid) {
            setFindings([]);
            setPagination(null);
            return;
        }
        setFindingsLoading(true);
        const query = {
            stig_collection_id: cid,
            limit: 500,
            offset: 0,
        };
        if (opts.status != null ? opts.status : statusFilter) {
            query.status = opts.status != null ? opts.status : statusFilter;
        }
        const sev = opts.severity != null ? opts.severity : severityFilter;
        if (sev) {
            query.severity = sev;
        }
        const host = opts.host_id != null ? opts.host_id : hostFilter;
        if (host) {
            query.host_id = host;
        }
        apiFetch("stig_findings", { query })
            .then((data) => {
                setFindings(data.findings || []);
                setPagination(data.pagination || null);
            })
            .catch((err) => {
                setFindings([]);
                setPagination(null);
                setBanner({ type: "error", message: String(err.message || err) });
            })
            .finally(() => setFindingsLoading(false));
    };

    useEffect(() => {
        if (!collectionId) {
            return;
        }
        loadMetrics(collectionId);
        apiGet("stig_hosts", { stig_collection_id: collectionId })
            .then(setHosts)
            .catch(() => setHosts([]));
        if (tab === "findings") {
            loadFindings(collectionId);
        }
    }, [collectionId]);

    useEffect(() => {
        if (tab === "findings" && collectionId) {
            loadFindings(collectionId);
        }
    }, [tab, statusFilter, severityFilter, hostFilter]);

    const statusCounts = useMemo(
        () => countRows(metrics && metrics.by_status),
        [metrics]
    );
    const severityCounts = useMemo(
        () => countRows(metrics && metrics.open_by_severity),
        [metrics]
    );

    const exportCsv = () => {
        if (!findings.length) {
            setBanner({ type: "warning", message: "No findings to export." });
            return;
        }
        const name =
            "stig_findings_" +
            (collectionId || "workspace").slice(0, 8) +
            ".csv";
        downloadText(name, findingsToCsv(findings), "text/csv");
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2}>Collection dashboard</Heading>
                </Brand>
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => setCollectionId(value)}
                        >
                            {collections.map((c) => (
                                <Select.Option
                                    key={c._key}
                                    label={workspaceLabel(c)}
                                    value={c._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                </Toolbar>
                <HeaderMeta>
                    <Link to={viewUrl("stig_collection_review_ui")}>
                        Collection review
                    </Link>
                    <Link to={viewUrl("stig_editor_ui")}>STIG Editor</Link>
                </HeaderMeta>
            </Header>
            <Body>
                <PagePad>
                    {banner ? (
                        <Message type={banner.type || "info"}>{banner.message}</Message>
                    ) : null}
                    <TabBar activeTabId={tab} onChange={(e, { selectedTabId }) => setTab(selectedTabId)}>
                        <TabBar.Tab label="Metrics" tabId="metrics" />
                        <TabBar.Tab label="Findings report" tabId="findings" />
                    </TabBar>

                    {tab === "metrics" ? (
                        <>
                            {loading ? <WaitSpinner /> : null}
                            {metrics ? (
                                <>
                                    <Heading level={4} style={{ marginTop: 16 }}>
                                        Completion
                                    </Heading>
                                    <MetricGrid>
                                        <MetricCard>
                                            <MetricValue>
                                                {metrics.completion &&
                                                    metrics.completion.percent_reviewed}
                                                %
                                            </MetricValue>
                                            <MetricLabel>Reviewed</MetricLabel>
                                        </MetricCard>
                                        <MetricCard>
                                            <MetricValue>
                                                {(metrics.completion &&
                                                    metrics.completion.open_findings) ||
                                                    0}
                                            </MetricValue>
                                            <MetricLabel>Open findings</MetricLabel>
                                        </MetricCard>
                                        <MetricCard>
                                            <MetricValue>
                                                {(metrics.totals && metrics.totals.hosts) || 0}
                                            </MetricValue>
                                            <MetricLabel>Hosts</MetricLabel>
                                        </MetricCard>
                                        <MetricCard>
                                            <MetricValue>
                                                {(metrics.totals &&
                                                    metrics.totals.checklists) ||
                                                    0}
                                            </MetricValue>
                                            <MetricLabel>Checklists</MetricLabel>
                                        </MetricCard>
                                        <MetricCard>
                                            <MetricValue>
                                                {(metrics.totals && metrics.totals.reviews) || 0}
                                            </MetricValue>
                                            <MetricLabel>Reviews</MetricLabel>
                                        </MetricCard>
                                    </MetricGrid>
                                    <Heading level={4}>By status</Heading>
                                    <Table>
                                        <Table.Head>
                                            <Table.HeadCell>Status</Table.HeadCell>
                                            <Table.HeadCell>Count</Table.HeadCell>
                                        </Table.Head>
                                        <Table.Body>
                                            {statusCounts.map((row) => (
                                                <Table.Row key={row.key}>
                                                    <Table.Cell>
                                                        <StatusChip status={row.key} />
                                                        {" "}
                                                        {STATUS_LABELS[row.key] || row.key}
                                                    </Table.Cell>
                                                    <Table.Cell>{row.count}</Table.Cell>
                                                </Table.Row>
                                            ))}
                                        </Table.Body>
                                    </Table>
                                    <Heading level={4} style={{ marginTop: 20 }}>
                                        Open findings by severity
                                    </Heading>
                                    <Table>
                                        <Table.Head>
                                            <Table.HeadCell>Severity</Table.HeadCell>
                                            <Table.HeadCell>Count</Table.HeadCell>
                                        </Table.Head>
                                        <Table.Body>
                                            {severityCounts.length ? (
                                                severityCounts.map((row) => (
                                                    <Table.Row key={row.key}>
                                                        <Table.Cell>
                                                            {SEVERITY_LABELS[row.key] ||
                                                                row.key}
                                                        </Table.Cell>
                                                        <Table.Cell>{row.count}</Table.Cell>
                                                    </Table.Row>
                                                ))
                                            ) : (
                                                <Table.Row>
                                                    <Table.Cell colSpan={2}>
                                                        No open findings
                                                    </Table.Cell>
                                                </Table.Row>
                                            )}
                                        </Table.Body>
                                    </Table>
                                </>
                            ) : !loading ? (
                                <Message type="info">Select a workspace to load metrics.</Message>
                            ) : null}
                        </>
                    ) : (
                        <>
                            <Toolbar style={{ marginTop: 12, marginBottom: 12 }}>
                                <ControlGroup label="Status" labelPosition="top">
                                    <Select
                                        value={statusFilter}
                                        onChange={(e, { value }) => setStatusFilter(value)}
                                    >
                                        <Select.Option label="Open (default)" value="open" />
                                        <Select.Option
                                            label="Open + Not reviewed"
                                            value="open,not_reviewed"
                                        />
                                        <Select.Option
                                            label="All statuses"
                                            value="not_reviewed,open,not_a_finding,not_applicable"
                                        />
                                    </Select>
                                </ControlGroup>
                                <ControlGroup label="Severity" labelPosition="top">
                                    <Select
                                        value={severityFilter}
                                        onChange={(e, { value }) => setSeverityFilter(value)}
                                    >
                                        <Select.Option label="Any" value="" />
                                        <Select.Option label="High" value="high" />
                                        <Select.Option label="Medium" value="medium" />
                                        <Select.Option label="Low" value="low" />
                                    </Select>
                                </ControlGroup>
                                <ControlGroup label="Host" labelPosition="top">
                                    <Select
                                        value={hostFilter}
                                        onChange={(e, { value }) => setHostFilter(value)}
                                    >
                                        <Select.Option label="All hosts" value="" />
                                        {hosts.map((h) => (
                                            <Select.Option
                                                key={h._key}
                                                label={h.hostname || h._key}
                                                value={h._key}
                                            />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <Actions>
                                    <Button onClick={() => loadFindings(collectionId)}>
                                        Refresh
                                    </Button>
                                    <Button appearance="primary" onClick={exportCsv}>
                                        Export CSV
                                    </Button>
                                </Actions>
                            </Toolbar>
                            {findingsLoading ? <WaitSpinner /> : null}
                            {pagination ? (
                                <Message type="info">
                                    Showing {findings.length} of {pagination.total} matching
                                    rows
                                    {pagination.has_more ? " (increase limit via REST for more)" : ""}
                                </Message>
                            ) : null}
                            <Table>
                                <Table.Head>
                                    <Table.HeadCell>Host</Table.HeadCell>
                                    <Table.HeadCell>Rule</Table.HeadCell>
                                    <Table.HeadCell>Severity</Table.HeadCell>
                                    <Table.HeadCell>Status</Table.HeadCell>
                                    <Table.HeadCell>Finding</Table.HeadCell>
                                    <Table.HeadCell>Updated</Table.HeadCell>
                                </Table.Head>
                                <Table.Body>
                                    {findings.map((row) => (
                                        <Table.Row key={row._key}>
                                            <Table.Cell>{row.hostname}</Table.Cell>
                                            <Table.Cell>
                                                {(row.group_id || "") +
                                                    (row.rule_id ? " / " + row.rule_id : "")}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {SEVERITY_LABELS[row.severity] ||
                                                    row.severity}
                                            </Table.Cell>
                                            <Table.Cell>
                                                <StatusChip status={row.status} />
                                            </Table.Cell>
                                            <Table.Cell>
                                                {row.finding_details || row.comments || "—"}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {row.updated_by
                                                    ? row.updated_by + " "
                                                    : ""}
                                                {row.updated_at
                                                    ? new Date(
                                                          row.updated_at * 1000
                                                      ).toLocaleString()
                                                    : ""}
                                            </Table.Cell>
                                        </Table.Row>
                                    ))}
                                </Table.Body>
                            </Table>
                            {!findingsLoading && !findings.length ? (
                                <Message type="info">No findings match the current filters.</Message>
                            ) : null}
                        </>
                    )}
                </PagePad>
            </Body>
        </Shell>
    );
}
