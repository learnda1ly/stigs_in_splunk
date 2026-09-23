import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiGet } from "../api";
import CreateChecklistModal from "../components/CreateChecklistModal";
import { Brand, BrandKicker, Header, PagePad, Shell } from "../layout";

const textBlockStyle = {
    whiteSpace: "pre-wrap",
    fontSize: "13px",
    lineHeight: 1.45,
    margin: 0,
};

function revisionLabel(rev) {
    const parts = [
        rev.version || "—",
        rev.release_info || "",
        rev.rule_count != null ? rev.rule_count + " rules" : "",
    ].filter(Boolean);
    return parts.join(" · ");
}

function RuleDetailPanel({ detail }) {
    if (!detail) {
        return null;
    }
    const ruleId = detail.rule_id || detail.group_id || "—";
    const title = detail.rule_title || detail.title || "";
    const optionalSections = [
        { label: "Description", value: detail.description },
        { label: "Check content", value: detail.check_content },
        { label: "Fix text", value: detail.fix_text },
        { label: "Discussion", value: detail.discussion },
    ].filter((section) => section.value);

    return (
        <div style={{ marginTop: "1rem" }}>
            <Heading level={3}>Rule detail</Heading>
            <div style={{ marginBottom: "0.5rem" }}>
                <strong>{ruleId}</strong>
                {title ? <span> — {title}</span> : null}
            </div>
            {detail.severity ? (
                <div style={{ marginBottom: "0.75rem" }}>
                    <strong>Severity:</strong> {detail.severity}
                </div>
            ) : null}
            {optionalSections.map((section) => (
                <div key={section.label} style={{ marginBottom: "1rem" }}>
                    <Heading level={4}>{section.label}</Heading>
                    <pre style={textBlockStyle}>{section.value}</pre>
                </div>
            ))}
        </div>
    );
}

export default function LibraryApp() {
    const [hierarchy, setHierarchy] = useState(null);
    const [selectedStig, setSelectedStig] = useState("");
    const [selectedBaseline, setSelectedBaseline] = useState("");
    const [rules, setRules] = useState([]);
    const [ruleDetail, setRuleDetail] = useState(null);
    const [filter, setFilter] = useState("");
    const [workspaces, setWorkspaces] = useState([]);
    const [workspaceFilter, setWorkspaceFilter] = useState("");
    const [loading, setLoading] = useState(true);
    const [rulesLoading, setRulesLoading] = useState(false);
    const [error, setError] = useState("");
    const [checklistModal, setChecklistModal] = useState(null);

    const benchmarks = hierarchy?.benchmarks || [];

    const filteredBenchmarks = useMemo(() => {
        const q = filter.trim().toLowerCase();
        if (!q) {
            return benchmarks;
        }
        return benchmarks.filter((row) => {
            const hay = [
                row.stig_id,
                row.title,
                row.stig_name,
                row.latest_version,
            ]
                .join(" ")
                .toLowerCase();
            return hay.includes(q);
        });
    }, [benchmarks, filter]);

    const selectedBenchmark = useMemo(() => {
        const bench = benchmarks.find((b) => b.stig_id === selectedStig);
        if (!bench) {
            return null;
        }
        const rev =
            bench.revisions.find((r) => r.baseline_id === selectedBaseline) ||
            bench.revisions[0];
        return rev || null;
    }, [benchmarks, selectedStig, selectedBaseline]);

    const loadHierarchy = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const qs = workspaceFilter
                ? "?stig_collection_id=" + encodeURIComponent(workspaceFilter)
                : "";
            const data = await apiGet("stig_baselines/hierarchy" + qs);
            setHierarchy(data);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, [workspaceFilter]);

    useEffect(() => {
        apiGet("stig_collections")
            .then((rows) => setWorkspaces(Array.isArray(rows) ? rows : []))
            .catch(() => setWorkspaces([]));
    }, []);

    useEffect(() => {
        loadHierarchy();
    }, [loadHierarchy]);

    useEffect(() => {
        const bid = selectedBaseline;
        if (!bid) {
            setRules([]);
            setRuleDetail(null);
            return;
        }
        setRulesLoading(true);
        setError("");
        apiGet("stig_baselines/" + bid + "/rules")
            .then((rows) => setRules(Array.isArray(rows) ? rows : []))
            .catch((err) => setError(String(err.message || err)))
            .finally(() => setRulesLoading(false));
    }, [selectedBaseline]);

    function selectBenchmark(row) {
        setSelectedStig(row.stig_id);
        setSelectedBaseline(row.latest_baseline_id);
        setRuleDetail(null);
    }

    function selectRevision(rev) {
        setSelectedBaseline(rev.baseline_id);
        setRuleDetail(null);
    }

    function openCreateChecklist(rev, bench) {
        const label =
            (bench && bench.stig_id) +
            (rev.version ? " " + rev.version : "") +
            (rev.release_info ? " · " + rev.release_info : "");
        setChecklistModal({
            baselineId: rev.baseline_id,
            label: label.trim(),
        });
    }

    async function openRule(rule) {
        setError("");
        try {
            const detail = await apiGet(
                "stig_baselines/rule/" + encodeURIComponent(rule._key)
            );
            setRuleDetail(detail);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    const activeBench = benchmarks.find((b) => b.stig_id === selectedStig);

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={1}>STIG library</Heading>
                </Brand>
                <Button label="Refresh" onClick={loadHierarchy} />
            </Header>
            <PagePad>
                {error ? <Message appearance="error">{error}</Message> : null}
                {loading ? (
                    <WaitSpinner size="large" />
                ) : (
                    <>
                        <div
                            style={{
                                display: "flex",
                                gap: "1rem",
                                marginBottom: "1rem",
                            }}
                        >
                            <Text
                                placeholder="Filter benchmarks…"
                                value={filter}
                                onChange={(_, { value }) => setFilter(value)}
                            />
                            <Select
                                value={workspaceFilter}
                                onChange={(_, { value }) =>
                                    setWorkspaceFilter(value)
                                }
                            >
                                <Select.Option
                                    label="All visible catalogs"
                                    value=""
                                />
                                {workspaces.map((ws) => (
                                    <Select.Option
                                        key={ws._key}
                                        label={ws.name || ws._key}
                                        value={ws._key}
                                    />
                                ))}
                            </Select>
                        </div>
                        <div
                            style={{
                                display: "flex",
                                gap: "1.5rem",
                                alignItems: "flex-start",
                            }}
                        >
                            <div style={{ flex: "1 1 42%", minWidth: 0 }}>
                                <Heading level={3}>Benchmarks</Heading>
                                <Table>
                                    <Table.Head>
                                        <Table.HeadCell>
                                            STIG / benchmark
                                        </Table.HeadCell>
                                        <Table.HeadCell>Revs</Table.HeadCell>
                                        <Table.HeadCell>Latest</Table.HeadCell>
                                    </Table.Head>
                                    <Table.Body>
                                        {filteredBenchmarks.map((row) => (
                                            <Table.Row
                                                key={row.stig_id}
                                                onClick={() =>
                                                    selectBenchmark(row)
                                                }
                                                data-test-selected={
                                                    selectedStig === row.stig_id
                                                        ? "yes"
                                                        : "no"
                                                }
                                            >
                                                <Table.Cell>
                                                    <div>
                                                        <strong>
                                                            {row.stig_id}
                                                        </strong>
                                                    </div>
                                                    <div>{row.title}</div>
                                                </Table.Cell>
                                                <Table.Cell>
                                                    {row.revision_count}
                                                </Table.Cell>
                                                <Table.Cell>
                                                    {row.latest_version || "—"}
                                                </Table.Cell>
                                            </Table.Row>
                                        ))}
                                    </Table.Body>
                                </Table>
                            </div>
                            <div style={{ flex: "1 1 58%", minWidth: 0 }}>
                                {activeBench ? (
                                    <>
                                        <Heading level={3}>
                                            Revisions — {activeBench.stig_id}
                                        </Heading>
                                        <Table>
                                            <Table.Head>
                                                <Table.HeadCell>
                                                    Version
                                                </Table.HeadCell>
                                                <Table.HeadCell>
                                                    Scope
                                                </Table.HeadCell>
                                                <Table.HeadCell>
                                                    Rules
                                                </Table.HeadCell>
                                                <Table.HeadCell>
                                                    Fingerprint
                                                </Table.HeadCell>
                                                <Table.HeadCell width={160}>
                                                    Checklist
                                                </Table.HeadCell>
                                            </Table.Head>
                                            <Table.Body>
                                                {activeBench.revisions.map(
                                                    (rev) => (
                                                        <Table.Row
                                                            key={
                                                                rev.baseline_id
                                                            }
                                                            onClick={() =>
                                                                selectRevision(
                                                                    rev
                                                                )
                                                            }
                                                            data-test-selected={
                                                                selectedBaseline ===
                                                                rev.baseline_id
                                                                    ? "yes"
                                                                    : "no"
                                                            }
                                                        >
                                                            <Table.Cell>
                                                                {revisionLabel(
                                                                    rev
                                                                )}
                                                            </Table.Cell>
                                                            <Table.Cell>
                                                                {rev.scope ===
                                                                "workspace"
                                                                    ? "workspace"
                                                                    : "global"}
                                                            </Table.Cell>
                                                            <Table.Cell>
                                                                {rev.rule_count}
                                                            </Table.Cell>
                                                            <Table.Cell>
                                                                <code>
                                                                    {(
                                                                        rev.content_fingerprint ||
                                                                        ""
                                                                    ).slice(
                                                                        0,
                                                                        12
                                                                    )}
                                                                    …
                                                                </code>
                                                            </Table.Cell>
                                                            <Table.Cell>
                                                                <Button
                                                                    appearance="primary"
                                                                    label="Create checklist"
                                                                    onClick={(
                                                                        e
                                                                    ) => {
                                                                        e.stopPropagation();
                                                                        openCreateChecklist(
                                                                            rev,
                                                                            activeBench
                                                                        );
                                                                    }}
                                                                />
                                                            </Table.Cell>
                                                        </Table.Row>
                                                    )
                                                )}
                                            </Table.Body>
                                        </Table>
                                        {selectedBaseline ? (
                                            <>
                                                <Heading
                                                    level={3}
                                                    style={{ marginTop: "1rem" }}
                                                >
                                                    Rules
                                                    {selectedBenchmark
                                                        ? " — " +
                                                          revisionLabel(
                                                              selectedBenchmark
                                                          )
                                                        : ""}
                                                </Heading>
                                                {rulesLoading ? (
                                                    <WaitSpinner />
                                                ) : (
                                                    <Table>
                                                        <Table.Head>
                                                            <Table.HeadCell>
                                                                Rule
                                                            </Table.HeadCell>
                                                            <Table.HeadCell>
                                                                Title
                                                            </Table.HeadCell>
                                                            <Table.HeadCell>
                                                                Severity
                                                            </Table.HeadCell>
                                                        </Table.Head>
                                                        <Table.Body>
                                                            {rules
                                                                .slice(0, 200)
                                                                .map((rule) => (
                                                                    <Table.Row
                                                                        key={
                                                                            rule._key
                                                                        }
                                                                        onClick={() =>
                                                                            openRule(
                                                                                rule
                                                                            )
                                                                        }
                                                                    >
                                                                        <Table.Cell>
                                                                            {rule.rule_id ||
                                                                                rule.group_id}
                                                                        </Table.Cell>
                                                                        <Table.Cell>
                                                                            {
                                                                                rule.rule_title
                                                                            }
                                                                        </Table.Cell>
                                                                        <Table.Cell>
                                                                            {
                                                                                rule.severity
                                                                            }
                                                                        </Table.Cell>
                                                                    </Table.Row>
                                                                ))}
                                                        </Table.Body>
                                                    </Table>
                                                )}
                                                {rules.length > 200 ? (
                                                    <Message appearance="info">
                                                        Showing first 200 rules.
                                                        Use REST for full
                                                        export.
                                                    </Message>
                                                ) : null}
                                                <RuleDetailPanel
                                                    detail={ruleDetail}
                                                />
                                            </>
                                        ) : (
                                            <Message
                                                appearance="info"
                                                style={{ marginTop: "1rem" }}
                                            >
                                                Select a revision to browse
                                                rules.
                                            </Message>
                                        )}
                                    </>
                                ) : (
                                    <Message appearance="info">
                                        Select a benchmark to view revisions
                                        and rules.
                                    </Message>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </PagePad>
            <CreateChecklistModal
                open={!!checklistModal}
                onClose={() => setChecklistModal(null)}
                baselineId={checklistModal && checklistModal.baselineId}
                baselineLabel={checklistModal && checklistModal.label}
                defaultCollectionId={workspaceFilter}
            />
        </Shell>
    );
}
