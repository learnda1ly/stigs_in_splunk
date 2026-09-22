import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import Table from "@splunk/react-ui/Table";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import styled from "styled-components";
import {
    apiFetch,
    apiGet,
    defaultWorkspaceId,
    viewUrl,
    workspaceLabel,
} from "../api";
import {
    Actions,
    Brand,
    BrandKicker,
    Header,
    HeaderMeta,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";
import { STATUS_LABELS, StatusChip, reviewIsValid, reviewValidationIssues, DEFAULT_REVIEW_REQUIREMENTS, normalizeReviewRequirements } from "../status";

const CellInput = styled.textarea`
    box-sizing: border-box;
    width: 100%;
    min-height: 52px;
    font: inherit;
    font-size: 12px;
    padding: 6px 8px;
    border: 1px solid #ccc;
    border-radius: 4px;
    resize: vertical;
`;

function ruleLabel(rule) {
    if (!rule) {
        return "";
    }
    const ver = rule.rule_version || rule.group_id || "";
    const title = rule.rule_title || rule.title || "";
    return ver + (title ? " — " + title : "");
}

function reviewMatchesRule(review, rule) {
    if (!review || !rule) {
        return false;
    }
    const rid = rule.rule_id || "";
    const gid = rule.group_id || "";
    if (rid && (review.rule_id === rid || review.group_id === gid)) {
        return true;
    }
    if (gid && review.group_id === gid) {
        return true;
    }
    return false;
}

function emptyRow(host, checklist, review) {
    return {
        key: review ? review._key : checklist._key,
        hostId: host._key,
        hostname: host.hostname || host._key,
        checklistId: checklist._key,
        review,
        status: (review && review.status) || "not_reviewed",
        finding: (review && review.finding_details) || "",
        comments: (review && review.comments) || "",
        ingestLock: !!(review && review.ingest_lock),
        dirty: false,
    };
}

export default function CollectionReviewApp() {
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [reviewRequirements, setReviewRequirements] = useState(
        DEFAULT_REVIEW_REQUIREMENTS
    );
    const [hosts, setHosts] = useState([]);
    const [checklists, setChecklists] = useState([]);
    const [baselines, setBaselines] = useState([]);
    const [baselineId, setBaselineId] = useState("");
    const [rules, setRules] = useState([]);
    const [ruleKey, setRuleKey] = useState("");
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [banner, setBanner] = useState(null);

    const baselineOptions = useMemo(() => {
        const ids = {};
        checklists.forEach((cl) => {
            if (cl.baseline_id) {
                ids[cl.baseline_id] = true;
            }
        });
        return baselines.filter((b) => b._key && ids[b._key]);
    }, [checklists, baselines]);

    const selectedRule = useMemo(() => {
        return rules.find((r) => (r.rule_id || "") + "|" + (r.group_id || "") === ruleKey) || null;
    }, [rules, ruleKey]);

    const dirtyCount = rows.filter((r) => r.dirty).length;

    const loadWorkspace = (cid) => {
        setCollectionId(cid);
        setBaselineId("");
        setRuleKey("");
        setRules([]);
        setRows([]);
        if (!cid) {
            setHosts([]);
            setChecklists([]);
            setReviewRequirements(DEFAULT_REVIEW_REQUIREMENTS);
            return;
        }
        setLoading(true);
        Promise.all([
            apiGet("stig_hosts", { stig_collection_id: cid }),
            apiGet("stig_checklists", { stig_collection_id: cid }),
            apiGet("stig_baselines"),
            apiGet("stig_collections/" + cid + "/review_requirements"),
        ])
            .then(([hs, cls, bl, reqBody]) => {
                setReviewRequirements(
                    normalizeReviewRequirements(
                        (reqBody && reqBody.review_requirements) ||
                            DEFAULT_REVIEW_REQUIREMENTS
                    )
                );
                setHosts(Array.isArray(hs) ? hs : []);
                setChecklists(Array.isArray(cls) ? cls : []);
                setBaselines(Array.isArray(bl) ? bl : []);
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load workspace: " + err.message,
                })
            )
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        apiGet("stig_collections")
            .then((data) => {
                const list = Array.isArray(data) ? data : [];
                setCollections(list);
                const id = defaultWorkspaceId(list);
                if (id) {
                    loadWorkspace(id);
                }
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load collections: " + err.message,
                })
            );
    }, []);

    const loadRulesForBaseline = (bid) => {
        setBaselineId(bid);
        setRuleKey("");
        setRows([]);
        if (!bid) {
            setRules([]);
            return;
        }
        setLoading(true);
        apiGet("stig_baselines/" + bid + "/rules")
            .then((data) => {
                const list = Array.isArray(data) ? data : [];
                setRules(list);
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load rules: " + err.message,
                })
            )
            .finally(() => setLoading(false));
    };

    const loadRuleRows = (rkey) => {
        setRuleKey(rkey);
        if (!collectionId || !baselineId || !rkey) {
            setRows([]);
            return;
        }
        const rule = rules.find(
            (r) => (r.rule_id || "") + "|" + (r.group_id || "") === rkey
        );
        if (!rule) {
            setRows([]);
            return;
        }
        setLoading(true);
        const query = { stig_collection_id: collectionId };
        if (rule.rule_id) {
            query.rule_id = rule.rule_id;
        } else if (rule.group_id) {
            query.rule_id = rule.group_id;
        }
        Promise.all([
            apiGet("stig_reviews", query),
            Promise.resolve(null),
        ])
            .then(([reviews]) => {
                const reviewList = Array.isArray(reviews) ? reviews : [];
                const hostMap = {};
                hosts.forEach((h) => {
                    hostMap[h._key] = h;
                });
                const clsForBaseline = checklists.filter(
                    (cl) => cl.baseline_id === baselineId
                );
                const next = clsForBaseline
                    .map((cl) => {
                        const host = hostMap[cl.host_id] || { _key: cl.host_id };
                        const rev =
                            reviewList.find(
                                (r) =>
                                    r.checklist_id === cl._key &&
                                    reviewMatchesRule(r, rule)
                            ) ||
                            reviewList.find((r) => r.checklist_id === cl._key);
                        return emptyRow(host, cl, rev);
                    })
                    .sort((a, b) =>
                        (a.hostname || "").localeCompare(b.hostname || "")
                    );
                setRows(next);
                setBanner({
                    type: "info",
                    text:
                        ruleLabel(rule) +
                        " · " +
                        next.length +
                        " host" +
                        (next.length === 1 ? "" : "s"),
                });
            })
            .catch((err) =>
                setBanner({
                    type: "error",
                    text: "Failed to load reviews: " + err.message,
                })
            )
            .finally(() => setLoading(false));
    };

    const patchRow = (rowKey, patch) => {
        setRows((prev) =>
            prev.map((row) => {
                if (row.key !== rowKey) {
                    return row;
                }
                const next = { ...row, ...patch };
                const saved = row.review || {};
                const dirty =
                    next.status !== (saved.status || "not_reviewed") ||
                    next.finding !== (saved.finding_details || "") ||
                    next.comments !== (saved.comments || "") ||
                    next.ingestLock !== !!saved.ingest_lock;
                next.dirty = dirty;
                return next;
            })
        );
    };

    const onSave = () => {
        const pending = rows.filter((r) => r.dirty && r.review && r.review._key);
        if (!pending.length) {
            setBanner({ type: "warning", text: "No changes to save." });
            return;
        }
        for (let i = 0; i < pending.length; i += 1) {
            const row = pending[i];
            const issues = reviewValidationIssues(
                {
                    status: row.status,
                    finding_details: row.finding,
                    comments: row.comments,
                },
                reviewRequirements
            );
            if (issues.length) {
                setBanner({
                    type: "error",
                    text:
                        (row.hostname || row.hostId) +
                        ": " +
                        (issues[0].message || "Review validation failed"),
                });
                return;
            }
        }
        setBusy(true);
        const body = {
            reviews: pending.map((r) => ({
                _key: r.review._key,
                status: r.status,
                finding_details: r.finding,
                comments: r.comments,
                ingest_lock: r.ingestLock,
            })),
        };
        apiFetch("stig_reviews/batch", { method: "POST", body })
            .then((result) => {
                const failed = (result.errors || []).length;
                const updated = result.updated || [];
                const byKey = {};
                updated.forEach((rec) => {
                    if (rec._key) {
                        byKey[rec._key] = rec;
                    }
                });
                setRows((prev) =>
                    prev.map((row) => {
                        const rec = row.review && byKey[row.review._key];
                        if (!rec) {
                            return row;
                        }
                        return {
                            ...row,
                            review: rec,
                            status: rec.status || row.status,
                            finding: rec.finding_details || "",
                            comments: rec.comments || "",
                            ingestLock: !!rec.ingest_lock,
                            dirty: false,
                        };
                    })
                );
                if (failed) {
                    setBanner({
                        type: "warning",
                        text:
                            "Saved " +
                            updated.length +
                            " row(s); " +
                            failed +
                            " failed. See server response for details.",
                    });
                } else {
                    setBanner({
                        type: "success",
                        text: "Saved " + updated.length + " review(s).",
                    });
                }
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Batch save failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Collection review
                    </Heading>
                </Brand>
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => loadWorkspace(value)}
                            placeholder="Select workspace"
                            filter
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
                    <ControlGroup label="Baseline" labelPosition="top">
                        <Select
                            value={baselineId}
                            onChange={(e, { value }) => loadRulesForBaseline(value)}
                            disabled={!collectionId}
                            placeholder="Select baseline"
                            filter
                        >
                            {baselineOptions.map((b) => (
                                <Select.Option
                                    key={b._key}
                                    label={
                                        (b.stig_id || b.title || b._key) +
                                        (b.version ? " V" + b.version : "")
                                    }
                                    value={b._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                    <ControlGroup label="Rule" labelPosition="top">
                        <Select
                            value={ruleKey}
                            onChange={(e, { value }) => loadRuleRows(value)}
                            disabled={!baselineId}
                            placeholder="Select rule"
                            filter
                        >
                            {rules.map((r) => {
                                const key =
                                    (r.rule_id || "") + "|" + (r.group_id || "");
                                return (
                                    <Select.Option
                                        key={key}
                                        label={ruleLabel(r)}
                                        value={key}
                                    />
                                );
                            })}
                        </Select>
                    </ControlGroup>
                    <Actions>
                        <Button
                            appearance="primary"
                            disabled={busy || !dirtyCount}
                            onClick={onSave}
                        >
                            Save {dirtyCount ? "(" + dirtyCount + ")" : "changes"}
                        </Button>
                    </Actions>
                </Toolbar>
                <HeaderMeta>
                    {loading ? <WaitSpinner /> : null}
                    <Link to={viewUrl("stig_editor_ui")}>Editor</Link>
                    <Link to={viewUrl("stig_import_ui")}>Import</Link>
                    <Link to={viewUrl("stig_export_ui")}>Export</Link>
                    <Link to={viewUrl("configuration")}>Configuration</Link>
                </HeaderMeta>
            </Header>
            <PagePad>
                {banner ? (
                    <Message type={banner.type} onRequestRemove={() => setBanner(null)}>
                        {banner.text}
                    </Message>
                ) : null}
                {selectedRule ? (
                    <p style={{ margin: "0 0 12px", fontSize: 13, color: "#555" }}>
                        {selectedRule.rule_title || selectedRule.title || ""}
                    </p>
                ) : null}
                {!ruleKey ? (
                    <Message type="info">
                        Choose a workspace, baseline, and rule to review that check across
                        all hosts with that checklist assigned.
                    </Message>
                ) : (
                    <Table>
                        <Table.Head>
                            <Table.HeadCell>Host</Table.HeadCell>
                            <Table.HeadCell width={140}>Status</Table.HeadCell>
                            <Table.HeadCell>Finding details</Table.HeadCell>
                            <Table.HeadCell>Comments</Table.HeadCell>
                            <Table.HeadCell width={90}>Complete</Table.HeadCell>
                            <Table.HeadCell width={110}>Ingest lock</Table.HeadCell>
                        </Table.Head>
                        <Table.Body>
                            {rows.map((row) => {
                                const complete = reviewIsValid(
                                    {
                                        status: row.status,
                                        finding_details: row.finding,
                                        comments: row.comments,
                                    },
                                    reviewRequirements
                                );
                                const rowId = row.review
                                    ? row.review._key
                                    : row.checklistId;
                                return (
                                    <Table.Row key={rowId}>
                                        <Table.Cell>
                                            {row.hostname}
                                            {row.dirty ? " *" : ""}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Select
                                                value={row.status}
                                                onChange={(e, { value }) =>
                                                    patchRow(row.key, { status: value })
                                                }
                                                disabled={!row.review || busy}
                                            >
                                                {Object.keys(STATUS_LABELS).map((st) => (
                                                    <Select.Option
                                                        key={st}
                                                        label={STATUS_LABELS[st]}
                                                        value={st}
                                                    />
                                                ))}
                                            </Select>
                                            <StatusChip status={row.status} />
                                        </Table.Cell>
                                        <Table.Cell>
                                            <CellInput
                                                value={row.finding}
                                                onChange={(e) =>
                                                    patchRow(row.key, {
                                                        finding: e.target.value,
                                                    })
                                                }
                                                disabled={!row.review || busy}
                                            />
                                        </Table.Cell>
                                        <Table.Cell>
                                            <CellInput
                                                value={row.comments}
                                                onChange={(e) =>
                                                    patchRow(row.key, {
                                                        comments: e.target.value,
                                                    })
                                                }
                                                disabled={!row.review || busy}
                                            />
                                        </Table.Cell>
                                        <Table.Cell>
                                            {complete ? "Yes" : "No"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Switch
                                                selected={row.ingestLock}
                                                onClick={(e, { selected }) =>
                                                    patchRow(row.key, {
                                                        ingestLock: selected,
                                                    })
                                                }
                                                disabled={!row.review || busy}
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                );
                            })}
                        </Table.Body>
                    </Table>
                )}
            </PagePad>
        </Shell>
    );
}
