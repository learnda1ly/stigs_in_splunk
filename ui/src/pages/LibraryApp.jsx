import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import {
    apiGet,
    defaultWorkspaceId,
    isAllWorkspaces,
    viewUrl,
    workspacesOfferAllChoice,
    WORKSPACE_ALL,
} from "../api";
import WorkspaceSelect from "../components/WorkspaceSelect";
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

function CompareFieldDiff({ fields }) {
    if (!fields || !Object.keys(fields).length) {
        return null;
    }
    return (
        <div style={{ marginTop: "0.5rem" }}>
            {Object.entries(fields).map(([name, pair]) => (
                <div key={name} style={{ marginBottom: "0.75rem" }}>
                    <strong>{name}</strong>
                    <div style={{ display: "flex", gap: "1rem", marginTop: "0.25rem" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div className="muted" style={{ fontSize: 12 }}>
                                From
                            </div>
                            <pre style={textBlockStyle}>{pair.from || "—"}</pre>
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div className="muted" style={{ fontSize: 12 }}>
                                To
                            </div>
                            <pre style={textBlockStyle}>{pair.to || "—"}</pre>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}

function CompareReport({ report, expandedKey, onToggleExpand }) {
    if (!report) {
        return null;
    }
    const summary = report.summary || {};
    return (
        <div style={{ marginTop: "1.5rem" }} data-testid="revision-compare-report">
            <Heading level={3}>Revision compare</Heading>
            <Message appearance="info">
                From {report.from_baseline?.version || "—"} → to{" "}
                {report.to_baseline?.version || "—"}: {summary.added || 0} added,{" "}
                {summary.removed || 0} removed, {summary.changed || 0} changed,{" "}
                {summary.unchanged || 0} unchanged.
            </Message>
            {summary.changed ? (
                <>
                    <Heading level={4} style={{ marginTop: "1rem" }}>
                        Changed rules
                    </Heading>
                    <Table>
                        <Table.Head>
                            <Table.HeadCell>Rule</Table.HeadCell>
                            <Table.HeadCell>Fields</Table.HeadCell>
                            <Table.HeadCell>Check hash</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {(report.changed || []).map((row) => {
                                const key =
                                    row.group_id + "|" + row.rule_id;
                                const open = expandedKey === key;
                                return (
                                    <React.Fragment key={key}>
                                        <Table.Row
                                            onClick={() => onToggleExpand(key)}
                                        >
                                            <Table.Cell>
                                                <strong>{row.rule_id}</strong>
                                                <div>{row.rule_title}</div>
                                            </Table.Cell>
                                            <Table.Cell>
                                                {(row.changed_fields || []).join(
                                                    ", "
                                                )}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {row.check_content_hash_changed
                                                    ? "changed"
                                                    : "same"}
                                            </Table.Cell>
                                        </Table.Row>
                                        {open ? (
                                            <Table.Row>
                                                <Table.Cell colSpan={3}>
                                                    <CompareFieldDiff
                                                        fields={row.fields}
                                                    />
                                                    {row.review_would_carry_forward ? (
                                                        <Message
                                                            appearance="info"
                                                            style={{
                                                                marginTop: "0.5rem",
                                                            }}
                                                        >
                                                            Check content hash
                                                            unchanged — reviews
                                                            would carry forward on
                                                            upgrade.
                                                        </Message>
                                                    ) : null}
                                                </Table.Cell>
                                            </Table.Row>
                                        ) : null}
                                    </React.Fragment>
                                );
                            })}
                        </Table.Body>
                    </Table>
                </>
            ) : null}
            {summary.added ? (
                <>
                    <Heading level={4} style={{ marginTop: "1rem" }}>
                        Added rules
                    </Heading>
                    <Table>
                        <Table.Head>
                            <Table.HeadCell>Rule</Table.HeadCell>
                            <Table.HeadCell>Title</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {(report.added || []).map((row) => (
                                <Table.Row
                                    key={row.rule_key || row.rule_id}
                                >
                                    <Table.Cell>{row.rule_id}</Table.Cell>
                                    <Table.Cell>{row.rule_title}</Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </>
            ) : null}
            {summary.removed ? (
                <>
                    <Heading level={4} style={{ marginTop: "1rem" }}>
                        Removed rules
                    </Heading>
                    <Table>
                        <Table.Head>
                            <Table.HeadCell>Rule</Table.HeadCell>
                            <Table.HeadCell>Title</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {(report.removed || []).map((row) => (
                                <Table.Row
                                    key={row.rule_key || row.rule_id}
                                >
                                    <Table.Cell>{row.rule_id}</Table.Cell>
                                    <Table.Cell>{row.rule_title}</Table.Cell>
                                </Table.Row>
                            ))}
                        </Table.Body>
                    </Table>
                </>
            ) : null}
        </div>
    );
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
    const [compareFrom, setCompareFrom] = useState("");
    const [compareTo, setCompareTo] = useState("");
    const [compareReport, setCompareReport] = useState(null);
    const [compareLoading, setCompareLoading] = useState(false);
    const [compareExpanded, setCompareExpanded] = useState("");

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
            const qs =
                workspaceFilter && !isAllWorkspaces(workspaceFilter)
                    ? "?stig_collection_id=" +
                      encodeURIComponent(workspaceFilter)
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
            .then((rows) => {
                const list = Array.isArray(rows) ? rows : [];
                setWorkspaces(list);
                if (workspacesOfferAllChoice(list)) {
                    setWorkspaceFilter(WORKSPACE_ALL);
                } else {
                    setWorkspaceFilter(defaultWorkspaceId(list));
                }
            })
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
        setCompareReport(null);
        setCompareExpanded("");
        const revs = row.revisions || [];
        if (revs.length >= 2) {
            setCompareFrom(revs[1].baseline_id);
            setCompareTo(revs[0].baseline_id);
        } else {
            setCompareFrom("");
            setCompareTo("");
        }
    }

    function selectRevision(rev) {
        setSelectedBaseline(rev.baseline_id);
        setRuleDetail(null);
    }

    async function runRevisionCompare() {
        if (!compareFrom || !compareTo) {
            return;
        }
        setCompareLoading(true);
        setError("");
        setCompareReport(null);
        setCompareExpanded("");
        try {
            const qs =
                "?from_baseline_id=" +
                encodeURIComponent(compareFrom) +
                "&to_baseline_id=" +
                encodeURIComponent(compareTo);
            const data = await apiGet("stig_baselines/compare" + qs);
            setCompareReport(data);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setCompareLoading(false);
        }
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
                ) : !benchmarks.length ? (
                    <Message appearance="info">
                        <p style={{ marginTop: 0 }}>
                            No STIG baselines are in the catalog yet. Import XCCDF, CKL, or CKLB
                            files to browse rules and create checklists.
                        </p>
                        <Button
                            appearance="primary"
                            label="Import baselines"
                            onClick={() => {
                                window.location.assign(viewUrl("stig_import_ui") + "#baselines");
                            }}
                        />
                        <p style={{ marginBottom: 0, fontSize: 13 }}>
                            Baselines are global; workspace filters only affect checklist scope.
                        </p>
                    </Message>
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
                            {workspacesOfferAllChoice(workspaces) ? (
                                <WorkspaceSelect
                                    workspaces={workspaces}
                                    value={workspaceFilter}
                                    onChange={(_, { value }) =>
                                        setWorkspaceFilter(value)
                                    }
                                    allLabel="All visible catalogs"
                                />
                            ) : null}
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
                                        {activeBench.revisions.length >= 2 ? (
                                            <div
                                                style={{
                                                    marginTop: "1rem",
                                                    padding: "0.75rem",
                                                    border: "1px solid var(--splunk-color-border, #3c444d)",
                                                    borderRadius: 4,
                                                }}
                                                data-testid="revision-compare-panel"
                                            >
                                                <Heading level={4}>
                                                    Compare revisions
                                                </Heading>
                                                <p
                                                    style={{
                                                        fontSize: 13,
                                                        marginTop: 0,
                                                    }}
                                                >
                                                    Read-only report of rules
                                                    added, removed, or changed
                                                    between two catalog
                                                    revisions (matched by V-id /
                                                    SV-id).
                                                </p>
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        flexWrap: "wrap",
                                                        gap: "0.75rem",
                                                        alignItems: "flex-end",
                                                    }}
                                                >
                                                    <div>
                                                        <div
                                                            style={{
                                                                fontSize: 12,
                                                                marginBottom: 4,
                                                            }}
                                                        >
                                                            From (older)
                                                        </div>
                                                        <Select
                                                            value={compareFrom}
                                                            onChange={(
                                                                _,
                                                                { value }
                                                            ) =>
                                                                setCompareFrom(
                                                                    value
                                                                )
                                                            }
                                                        >
                                                            {activeBench.revisions.map(
                                                                (rev) => (
                                                                    <Select.Option
                                                                        key={
                                                                            rev.baseline_id
                                                                        }
                                                                        label={revisionLabel(
                                                                            rev
                                                                        )}
                                                                        value={
                                                                            rev.baseline_id
                                                                        }
                                                                    />
                                                                )
                                                            )}
                                                        </Select>
                                                    </div>
                                                    <div>
                                                        <div
                                                            style={{
                                                                fontSize: 12,
                                                                marginBottom: 4,
                                                            }}
                                                        >
                                                            To (newer)
                                                        </div>
                                                        <Select
                                                            value={compareTo}
                                                            onChange={(
                                                                _,
                                                                { value }
                                                            ) =>
                                                                setCompareTo(
                                                                    value
                                                                )
                                                            }
                                                        >
                                                            {activeBench.revisions.map(
                                                                (rev) => (
                                                                    <Select.Option
                                                                        key={
                                                                            rev.baseline_id +
                                                                            "-to"
                                                                        }
                                                                        label={revisionLabel(
                                                                            rev
                                                                        )}
                                                                        value={
                                                                            rev.baseline_id
                                                                        }
                                                                    />
                                                                )
                                                            )}
                                                        </Select>
                                                    </div>
                                                    <Button
                                                        appearance="primary"
                                                        label="Compare"
                                                        disabled={
                                                            !compareFrom ||
                                                            !compareTo ||
                                                            compareFrom ===
                                                                compareTo ||
                                                            compareLoading
                                                        }
                                                        onClick={
                                                            runRevisionCompare
                                                        }
                                                    />
                                                    {compareLoading ? (
                                                        <WaitSpinner />
                                                    ) : null}
                                                </div>
                                                <CompareReport
                                                    report={compareReport}
                                                    expandedKey={compareExpanded}
                                                    onToggleExpand={(key) =>
                                                        setCompareExpanded(
                                                            compareExpanded ===
                                                                key
                                                                ? ""
                                                                : key
                                                        )
                                                    }
                                                />
                                            </div>
                                        ) : null}
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
