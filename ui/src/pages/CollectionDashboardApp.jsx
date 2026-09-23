import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
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
    downloadBase64,
    downloadText,
    workspaceLabel,
} from "../api";
import {
    Actions,
    Brand,
    BrandKicker,
    Body,
    Header,
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
    const [aggregate, setAggregate] = useState(null);
    const [aggregateLoading, setAggregateLoading] = useState(false);
    const [unreviewedAssets, setUnreviewedAssets] = useState(null);
    const [unreviewedRules, setUnreviewedRules] = useState(null);
    const [unreviewedLoading, setUnreviewedLoading] = useState(false);
    const [poamLoading, setPoamLoading] = useState(false);
    const [reviewAging, setReviewAging] = useState(null);
    const [staleSummary, setStaleSummary] = useState(null);
    const [banner, setBanner] = useState(null);

    useEffect(() => {
        apiGet("stig_collections")
            .then((rows) => {
                setCollections(rows);
                setCollectionId((prev) => {
                    if (prev) {
                        return prev;
                    }
                    const params = new URLSearchParams(window.location.search || "");
                    const fromQuery = params.get("stig_collection_id");
                    if (
                        fromQuery &&
                        rows.some((c) => c && c._key === fromQuery)
                    ) {
                        return fromQuery;
                    }
                    return defaultWorkspaceId(rows);
                });
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
        Promise.all([
            apiFetch("stig_collections/" + cid + "/metrics"),
            apiFetch("stig_collections/" + cid + "/review_aging"),
            apiFetch("stig_collections/" + cid + "/review_aging/stale", {
                query: { limit: 5 },
            }),
        ])
            .then(([metricsData, agingData, staleData]) => {
                setMetrics(metricsData);
                setReviewAging(
                    (agingData && agingData.review_aging) || null
                );
                setStaleSummary(staleData || null);
            })
            .catch((err) => {
                setMetrics(null);
                setReviewAging(null);
                setStaleSummary(null);
                setBanner({ type: "error", message: String(err.message || err) });
            })
            .finally(() => setLoading(false));
    };

    const findingsRestQuery = (extra) => {
        const query = {};
        if (statusFilter) {
            query.status = statusFilter;
        }
        if (severityFilter) {
            query.severity = severityFilter;
        }
        if (hostFilter) {
            query.host_id = hostFilter;
        }
        return Object.assign(query, extra || {});
    };

    const loadAggregate = (cid) => {
        if (!cid) {
            setAggregate(null);
            return;
        }
        setAggregateLoading(true);
        apiFetch("stig_collections/" + cid + "/findings/aggregate", {
            query: findingsRestQuery({ group_by: "group_id,rule_id,cci" }),
        })
            .then((data) => setAggregate(data))
            .catch((err) => {
                setAggregate(null);
                setBanner({ type: "error", message: String(err.message || err) });
            })
            .finally(() => setAggregateLoading(false));
    };

    const loadUnreviewed = (cid) => {
        if (!cid) {
            setUnreviewedAssets(null);
            setUnreviewedRules(null);
            return;
        }
        setUnreviewedLoading(true);
        const query = {};
        if (hostFilter) {
            query.host_id = hostFilter;
        }
        if (severityFilter) {
            query.severity = severityFilter;
        }
        Promise.all([
            apiFetch("stig_collections/" + cid + "/unreviewed/assets", { query }),
            apiFetch("stig_collections/" + cid + "/unreviewed/rules", { query }),
        ])
            .then(([assets, rules]) => {
                setUnreviewedAssets(assets);
                setUnreviewedRules(rules);
            })
            .catch((err) => {
                setUnreviewedAssets(null);
                setUnreviewedRules(null);
                setBanner({ type: "error", message: String(err.message || err) });
            })
            .finally(() => setUnreviewedLoading(false));
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
        if (tab === "aggregate") {
            loadAggregate(collectionId);
        }
        if (tab === "unreviewed") {
            loadUnreviewed(collectionId);
        }
    }, [collectionId]);

    useEffect(() => {
        if (tab === "findings" && collectionId) {
            loadFindings(collectionId);
        }
    }, [tab, statusFilter, severityFilter, hostFilter, collectionId]);

    useEffect(() => {
        if (tab === "aggregate" && collectionId) {
            loadAggregate(collectionId);
        }
    }, [tab, collectionId, statusFilter, severityFilter, hostFilter]);

    useEffect(() => {
        if (tab === "unreviewed" && collectionId) {
            loadUnreviewed(collectionId);
        }
    }, [tab, collectionId, severityFilter, hostFilter]);

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

    const poamRowsToCsv = (data) => {
        const headers = (data.columns || []).map((c) => c.label || c.key);
        const keys = (data.columns || []).map((c) => c.key);
        const lines = [headers.join(",")];
        (data.rows || []).forEach((row) => {
            lines.push(keys.map((key) => csvEscape(row[key])).join(","));
        });
        return lines.join("\n");
    };

    const exportPoam = (fmt) => {
        if (!collectionId) {
            return;
        }
        setPoamLoading(true);
        setBanner(null);
        const path = "stig_collections/" + collectionId + "/poam";
        const filterQuery = findingsRestQuery();
        apiFetch(path, { query: Object.assign({ format: "json" }, filterQuery) })
            .then((data) => {
                if (!data || !data.row_count) {
                    setBanner({
                        type: "warning",
                        message: "No findings match the current filters for POA&M.",
                    });
                    return;
                }
                if (fmt === "xlsx") {
                    return apiFetch(path, {
                        query: Object.assign({ format: "xlsx" }, filterQuery),
                    }).then((xlsx) => {
                        if (xlsx.content_base64) {
                            downloadBase64(
                                xlsx.filename || "stig_poam.xlsx",
                                xlsx.content_base64,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            );
                        }
                    });
                }
                const filename =
                    (data.stig_collection_id || collectionId).slice(0, 8) +
                    "_poam.csv";
                downloadText(filename, poamRowsToCsv(data), "text/csv");
            })
            .catch((err) =>
                setBanner({ type: "error", message: String(err.message || err) })
            )
            .finally(() => setPoamLoading(false));
    };

    const renderUnreviewedFilters = (actions) => (
        <Toolbar style={{ marginTop: 12, marginBottom: 12 }}>
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
            <Actions>{actions}</Actions>
        </Toolbar>
    );

    const renderFindingsFilters = (actions) => (
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
            <Actions>{actions}</Actions>
        </Toolbar>
    );

    const renderAggregateTable = (title, rows, keyField, opts) => {
        opts = opts || {};
        if (!rows || !rows.length) {
            return (
                <Message appearance="info" style={{ marginTop: 12 }}>
                    No rows for {title}.
                </Message>
            );
        }
        return (
            <>
                <Heading level={4} style={{ marginTop: 20 }}>{title}</Heading>
                <Table>
                    <Table.Head>
                        {opts.showBaseline ? (
                            <Table.HeadCell>STIG</Table.HeadCell>
                        ) : null}
                        <Table.HeadCell>{keyField}</Table.HeadCell>
                        <Table.HeadCell>Count</Table.HeadCell>
                        <Table.HeadCell>Hosts</Table.HeadCell>
                        <Table.HeadCell>Severity</Table.HeadCell>
                    </Table.Head>
                    <Table.Body>
                        {rows.map((row) => (
                            <Table.Row
                                key={
                                    (row.baseline_id || "") +
                                    (row[keyField] || "") +
                                    row.count
                                }
                            >
                                {opts.showBaseline ? (
                                    <Table.Cell>{row.stig_id || "—"}</Table.Cell>
                                ) : null}
                                <Table.Cell>{row[keyField] || "—"}</Table.Cell>
                                <Table.Cell>{row.count}</Table.Cell>
                                <Table.Cell>{row.host_count}</Table.Cell>
                                <Table.Cell>
                                    {SEVERITY_LABELS[row.severity] || row.severity || "—"}
                                </Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>
            </>
        );
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
            </Header>
            <Body>
                <PagePad>
                    {banner ? (
                        <Message appearance={banner.type || "info"}>{banner.message}</Message>
                    ) : null}
                    <TabBar activeTabId={tab} onChange={(e, { selectedTabId }) => setTab(selectedTabId)}>
                        <TabBar.Tab label="Metrics" tabId="metrics" />
                        <TabBar.Tab label="Findings report" tabId="findings" />
                        <TabBar.Tab label="Aggregated findings" tabId="aggregate" />
                        <TabBar.Tab label="Unreviewed" tabId="unreviewed" />
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
                                    {reviewAging ? (
                                        <>
                                            <Heading level={4}>Review aging</Heading>
                                            <Message appearance="info">
                                                {reviewAging.enabled
                                                    ? "Enabled — stale after " +
                                                      (reviewAging.stale_after_hours
                                                          ? reviewAging.stale_after_hours +
                                                            " hour(s)"
                                                          : (reviewAging.stale_after_days ||
                                                                90) +
                                                            " day(s)") +
                                                      ". Stale count: " +
                                                      ((staleSummary &&
                                                          staleSummary.stale_count) ||
                                                          0) +
                                                      "."
                                                    : "Disabled — enable via PATCH /stig_collections/{id}/review_aging."}
                                            </Message>
                                            {reviewAging.enabled &&
                                            staleSummary &&
                                            Array.isArray(staleSummary.items) &&
                                            staleSummary.items.length ? (
                                                <Table style={{ marginTop: 12 }}>
                                                    <Table.Head>
                                                        <Table.HeadCell>Host</Table.HeadCell>
                                                        <Table.HeadCell>Rule</Table.HeadCell>
                                                        <Table.HeadCell>Status</Table.HeadCell>
                                                        <Table.HeadCell>Age (days)</Table.HeadCell>
                                                    </Table.Head>
                                                    <Table.Body>
                                                        {staleSummary.items.map((row) => (
                                                            <Table.Row key={row._key}>
                                                                <Table.Cell>
                                                                    {row.hostname || "—"}
                                                                </Table.Cell>
                                                                <Table.Cell>
                                                                    {row.rule_id || row.group_id || "—"}
                                                                </Table.Cell>
                                                                <Table.Cell>
                                                                    <StatusChip status={row.status} />
                                                                </Table.Cell>
                                                                <Table.Cell>
                                                                    {row.aging_age_seconds != null
                                                                        ? Math.floor(
                                                                              row.aging_age_seconds /
                                                                                  86400
                                                                          )
                                                                        : "—"}
                                                                </Table.Cell>
                                                            </Table.Row>
                                                        ))}
                                                    </Table.Body>
                                                </Table>
                                            ) : null}
                                        </>
                                    ) : null}
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
                                <Message appearance="info">Select a workspace to load metrics.</Message>
                            ) : null}
                        </>
                    ) : null}

                    {tab === "findings" ? (
                        <>
                            {renderFindingsFilters(
                                <>
                                    <Button onClick={() => loadFindings(collectionId)}>
                                        Refresh
                                    </Button>
                                    <Button appearance="primary" onClick={exportCsv}>
                                        Export CSV
                                    </Button>
                                    <Button
                                        disabled={poamLoading}
                                        onClick={() => exportPoam("csv")}
                                    >
                                        POA&M CSV
                                    </Button>
                                    <Button
                                        disabled={poamLoading}
                                        onClick={() => exportPoam("xlsx")}
                                    >
                                        POA&M XLSX
                                    </Button>
                                </>
                            )}
                            {findingsLoading ? <WaitSpinner /> : null}
                            {pagination ? (
                                <Message appearance="info">
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
                                <Message appearance="info">No findings match the current filters.</Message>
                            ) : null}
                        </>
                    ) : null}

                    {tab === "aggregate" ? (
                        <>
                            {renderFindingsFilters(
                                <Button onClick={() => loadAggregate(collectionId)}>
                                    Refresh
                                </Button>
                            )}
                            {aggregateLoading ? <WaitSpinner /> : null}
                            {aggregate ? (
                                <>
                                    <Message appearance="info">
                                        Matching findings after filters (governance applies when
                                        status includes open): {aggregate.open_findings_total || 0}
                                    </Message>
                                    {renderAggregateTable(
                                        "By group (V-ID)",
                                        aggregate.by_group_id,
                                        "group_id",
                                        { showBaseline: true }
                                    )}
                                    {renderAggregateTable(
                                        "By rule",
                                        aggregate.by_rule_id,
                                        "rule_id",
                                        { showBaseline: true }
                                    )}
                                    {renderAggregateTable(
                                        "By CCI",
                                        aggregate.by_cci,
                                        "cci"
                                    )}
                                </>
                            ) : !aggregateLoading ? (
                                <Message appearance="info">
                                    Select a workspace to load aggregated open findings.
                                </Message>
                            ) : null}
                        </>
                    ) : null}

                    {tab === "unreviewed" ? (
                        <>
                            {renderUnreviewedFilters(
                                <Button onClick={() => loadUnreviewed(collectionId)}>
                                    Refresh
                                </Button>
                            )}
                            {unreviewedLoading ? <WaitSpinner /> : null}
                            {unreviewedAssets ? (
                                <>
                                    <Message appearance="info">
                                        Counts only assessor status{" "}
                                        <strong>not_reviewed</strong> (not affected by the
                                        findings Status filter on other tabs).{" "}
                                        Total: {unreviewedAssets.total_unreviewed || 0} across{" "}
                                        {unreviewedAssets.asset_count || 0} host(s).
                                    </Message>
                                    <Heading level={4} style={{ marginTop: 16 }}>
                                        By host (per baseline)
                                    </Heading>
                                    <Table>
                                        <Table.Head>
                                            <Table.HeadCell>Host</Table.HeadCell>
                                            <Table.HeadCell>STIG</Table.HeadCell>
                                            <Table.HeadCell>Unreviewed</Table.HeadCell>
                                        </Table.Head>
                                        <Table.Body>
                                            {(unreviewedAssets.assets || []).flatMap((asset) => {
                                                const baselines = asset.by_baseline || [];
                                                if (!baselines.length) {
                                                    return [
                                                        <Table.Row key={asset.host_id}>
                                                            <Table.Cell>
                                                                {asset.hostname || asset.host_id}
                                                            </Table.Cell>
                                                            <Table.Cell>—</Table.Cell>
                                                            <Table.Cell>
                                                                {asset.unreviewed_count}
                                                            </Table.Cell>
                                                        </Table.Row>,
                                                    ];
                                                }
                                                return baselines.map((bl, idx) => (
                                                    <Table.Row
                                                        key={
                                                            asset.host_id +
                                                            ":" +
                                                            (bl.baseline_id || idx)
                                                        }
                                                    >
                                                        <Table.Cell>
                                                            {idx === 0
                                                                ? asset.hostname || asset.host_id
                                                                : ""}
                                                        </Table.Cell>
                                                        <Table.Cell>
                                                            {bl.stig_id || bl.baseline_id}
                                                        </Table.Cell>
                                                        <Table.Cell>
                                                            {bl.unreviewed_count}
                                                        </Table.Cell>
                                                    </Table.Row>
                                                ));
                                            })}
                                        </Table.Body>
                                    </Table>
                                    <Heading level={4} style={{ marginTop: 20 }}>
                                        By rule (hosts affected)
                                    </Heading>
                                    <Table>
                                        <Table.Head>
                                            <Table.HeadCell>STIG / rule</Table.HeadCell>
                                            <Table.HeadCell>Unreviewed</Table.HeadCell>
                                            <Table.HeadCell>Hosts</Table.HeadCell>
                                            <Table.HeadCell>Hostnames</Table.HeadCell>
                                            <Table.HeadCell>Severity</Table.HeadCell>
                                        </Table.Head>
                                        <Table.Body>
                                            {(unreviewedRules && unreviewedRules.rules
                                                ? unreviewedRules.rules
                                                : []
                                            ).map((row) => (
                                                <Table.Row
                                                    key={
                                                        (row.baseline_id || "") +
                                                        ":" +
                                                        (row.rule_id || row.group_id)
                                                    }
                                                >
                                                    <Table.Cell>
                                                        {(row.stig_id || row.baseline_id || "") +
                                                            " " +
                                                            (row.group_id || "") +
                                                            (row.rule_id
                                                                ? " / " + row.rule_id
                                                                : "")}
                                                    </Table.Cell>
                                                    <Table.Cell>
                                                        {row.unreviewed_count}
                                                    </Table.Cell>
                                                    <Table.Cell>{row.host_count}</Table.Cell>
                                                    <Table.Cell
                                                        title={(row.hostnames || []).join(", ")}
                                                    >
                                                        {(row.hostnames || []).join(", ") || "—"}
                                                    </Table.Cell>
                                                    <Table.Cell>
                                                        {SEVERITY_LABELS[row.severity] ||
                                                            row.severity}
                                                    </Table.Cell>
                                                </Table.Row>
                                            ))}
                                        </Table.Body>
                                    </Table>
                                </>
                            ) : !unreviewedLoading ? (
                                <Message appearance="info">
                                    Select a workspace to load unreviewed reports.
                                </Message>
                            ) : null}
                        </>
                    ) : null}
                </PagePad>
            </Body>
        </Shell>
    );
}
