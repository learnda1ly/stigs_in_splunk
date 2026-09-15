import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Search from "@splunk/react-ui/Search";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiGet, apiPatch, viewUrl } from "../api";
import {
    Actions,
    Body,
    Brand,
    BrandKicker,
    DetailPane,
    Empty,
    FieldStack,
    FilterRow,
    FindingList,
    FindingRow,
    FindingTitle,
    Header,
    HeaderMeta,
    ListPane,
    MetaLine,
    PreBlock,
    ProgressFill,
    ProgressTrack,
    Shell,
    Toolbar,
    VimBadge,
} from "../layout";
import { STATUS_LABELS, StatusChip, reviewIsValid } from "../status";
import VimField from "../vim/VimField";
import { HelpOverlay, JumpOverlay, VimCommandBar } from "../vim/overlays";
import { loadVimSetting, persistVimSetting } from "../vim/settings";
import { VimGlobalStyle } from "../vim/styles";
import { useEditorKeys } from "../vim/useEditorKeys";

function lookupRule(rulesByKey, rev) {
    return (
        rulesByKey[rev.rule_id] ||
        rulesByKey[(rev.rule_id || "") + "|" + (rev.group_id || "")] ||
        {}
    );
}

export default function EditorApp() {
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [hosts, setHosts] = useState([]);
    const [hostId, setHostId] = useState("");
    const [checklists, setChecklists] = useState([]);
    const [rulesByKey, setRulesByKey] = useState({});
    const [items, setItems] = useState([]);
    const [selectedKey, setSelectedKey] = useState("");
    const [statusFilter, setStatusFilter] = useState("");
    const [validityFilter, setValidityFilter] = useState("");
    const [query, setQuery] = useState("");
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [banner, setBanner] = useState(null);
    const [finding, setFinding] = useState("");
    const [comments, setComments] = useState("");
    const [status, setStatus] = useState("not_reviewed");
    const [vimEnabled, setVimEnabled] = useState(false);
    const [vimLayer, setVimLayer] = useState("nav");
    const [helpOpen, setHelpOpen] = useState(false);
    const [cmdOpen, setCmdOpen] = useState(false);
    const [jump, setJump] = useState(null);
    const [fieldRequest, setFieldRequest] = useState(null);
    const listRef = useRef(null);
    const searchWrapRef = useRef(null);
    const ctxRef = useRef({});
    const skipLeaveRef = useRef(false);

    const hostsById = useMemo(() => {
        const map = {};
        hosts.forEach((h) => {
            map[h._key] = h;
        });
        return map;
    }, [hosts]);

    const checklistById = useCallback(
        (id) => checklists.find((c) => c._key === id) || {},
        [checklists]
    );

    const loadCollections = useCallback(() => {
        apiGet("stig_collections")
            .then((data) => setCollections(Array.isArray(data) ? data : []))
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load collections: " + err.message })
            );
    }, []);

    useEffect(() => {
        loadCollections();
    }, [loadCollections]);

    const mergeRules = (rules, prev) => {
        const next = { ...prev };
        (rules || []).forEach((r) => {
            next[(r.rule_id || "") + "|" + (r.group_id || "")] = r;
            if (r.rule_id) {
                next[r.rule_id] = r;
            }
        });
        return next;
    };

    const loadRules = (cls) => {
        const ids = [];
        (cls || []).forEach((cl) => {
            if (cl.baseline_id && ids.indexOf(cl.baseline_id) < 0) {
                ids.push(cl.baseline_id);
            }
        });
        return Promise.all(
            ids.map((id) => apiGet("stig_baselines/" + id + "/rules"))
        ).then((sets) => {
            setRulesByKey((prev) => {
                let next = prev;
                sets.forEach((rules) => {
                    next = mergeRules(Array.isArray(rules) ? rules : [], next);
                });
                return next;
            });
        });
    };

    const toItems = (reviews) =>
        (reviews || []).map((rev) => ({
            review: rev,
            savedFinding: rev.finding_details || "",
            savedComments: rev.comments || "",
            dirty: false,
        }));

    const loadFindings = (cls, reviews) => {
        const allowed = {};
        cls.forEach((cl) => {
            allowed[cl._key] = true;
        });
        const next = toItems(
            (reviews || []).filter((r) => allowed[r.checklist_id])
        ).sort((a, b) => {
            const ha = a.review.rule_version || "";
            const hb = b.review.rule_version || "";
            const c = ha.localeCompare(hb, undefined, { numeric: true });
            if (c !== 0) {
                return c;
            }
            return (a.review.checklist_id || "").localeCompare(b.review.checklist_id || "");
        });
        setItems(next);
        setSelectedKey(next[0] ? next[0].review._key : "");
    };

    const onCollection = (id) => {
        setCollectionId(id);
        setHostId("");
        setItems([]);
        setSelectedKey("");
        if (!id) {
            setHosts([]);
            setChecklists([]);
            return;
        }
        setLoading(true);
        Promise.all([
            apiGet("stig_checklists", { stig_collection_id: id }),
            apiGet("stig_hosts", { stig_collection_id: id }),
        ])
            .then(([cls, hs]) => {
                const checkList = Array.isArray(cls) ? cls : [];
                const hostList = Array.isArray(hs) ? hs : [];
                setChecklists(checkList);
                setHosts(hostList);
                return Promise.all([
                    checkList,
                    apiGet("stig_reviews", { stig_collection_id: id }),
                    loadRules(checkList),
                ]);
            })
            .then(([cls, reviews]) => {
                loadFindings(cls, Array.isArray(reviews) ? reviews : []);
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load workspace: " + err.message })
            )
            .finally(() => setLoading(false));
    };

    const onHost = (id) => {
        setHostId(id);
        if (!collectionId) {
            return;
        }
        setLoading(true);
        const cls = id
            ? checklists.filter((cl) => cl.host_id === id)
            : checklists;
        const req = id
            ? Promise.all(cls.map((cl) => apiGet("stig_reviews", { checklist_id: cl._key })))
            : apiGet("stig_reviews", { stig_collection_id: collectionId }).then((r) => [r]);
        Promise.all([req, loadRules(cls)])
            .then(([sets]) => {
                const reviews = [].concat.apply([], sets || []);
                loadFindings(cls, reviews);
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load findings: " + err.message })
            )
            .finally(() => setLoading(false));
    };

    const loadRuleAcrossHosts = (ruleVersion, ruleId) => {
        if (!collectionId) {
            setBanner({ type: "warning", text: "Select a collection first." });
            return;
        }
        setLoading(true);
        const query = { stig_collection_id: collectionId };
        if (ruleVersion) {
            query.rule_version = ruleVersion;
        } else if (ruleId) {
            query.rule_id = ruleId;
        }
        Promise.all([
            apiGet("stig_reviews", query),
            loadRules(checklists),
        ])
            .then(([reviews]) => {
                let next = Array.isArray(reviews) ? reviews : [];
                if (!next.length && (ruleVersion || ruleId)) {
                    return apiGet("stig_reviews", {
                        stig_collection_id: collectionId,
                    }).then((all) =>
                        (Array.isArray(all) ? all : []).filter(
                            (r) =>
                                r.rule_version === ruleVersion || r.rule_id === ruleId
                        )
                    );
                }
                return next;
            })
            .then((reviews) => {
                loadFindings(checklists, reviews);
                setBanner({
                    type: "info",
                    text:
                        (ruleVersion || ruleId || "Rule") +
                        " · " +
                        (reviews || []).length +
                        " hosts",
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load rule: " + err.message })
            )
            .finally(() => setLoading(false));
    };

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        return items.filter((item) => {
            const rev = item.review;
            const rule = lookupRule(rulesByKey, rev);
            if (statusFilter && rev.status !== statusFilter) {
                return false;
            }
            const complete = reviewIsValid(rev);
            if (validityFilter === "complete" && !complete) {
                return false;
            }
            if (validityFilter === "incomplete" && complete) {
                return false;
            }
            if (!q) {
                return true;
            }
            const host = hostsById[checklistById(rev.checklist_id).host_id] || {};
            const hay = [
                rev.rule_id,
                rev.group_id,
                rule.rule_version || rev.rule_version,
                rule.rule_title,
                host.hostname,
                rev.finding_details,
                rev.comments,
            ]
                .join(" ")
                .toLowerCase();
            return hay.indexOf(q) >= 0;
        });
    }, [
        items,
        query,
        statusFilter,
        validityFilter,
        rulesByKey,
        hostsById,
        checklistById,
    ]);

    const selected = filtered.find((item) => item.review._key === selectedKey) || filtered[0];

    useEffect(() => {
        if (!selected) {
            setFinding("");
            setComments("");
            setStatus("not_reviewed");
            return;
        }
        setFinding(selected.review.finding_details || "");
        setComments(selected.review.comments || "");
        setStatus(selected.review.status || "not_reviewed");
    }, [selected && selected.review._key, selected && selected.review.updated_at]);

    const doneCount = items.filter((item) => reviewIsValid(item.review)).length;
    const pct = items.length ? Math.round((doneCount / items.length) * 100) : 0;
    const dirty =
        selected &&
        ((finding || "") !== (selected.savedFinding || "") ||
            (comments || "") !== (selected.savedComments || ""));

    const patchItem = (key, nextReview, extra) => {
        setItems((prev) =>
            prev.map((item) =>
                item.review._key === key
                    ? {
                          ...item,
                          review: nextReview,
                          dirty:
                              extra && extra.dirty != null
                                  ? extra.dirty
                                  : item.dirty,
                          savedFinding:
                              extra && extra.savedFinding != null
                                  ? extra.savedFinding
                                  : item.savedFinding,
                          savedComments:
                              extra && extra.savedComments != null
                                  ? extra.savedComments
                                  : item.savedComments,
                      }
                    : item
            )
        );
    };

    const onStatus = (value) => {
        if (!selected || busy) {
            return;
        }
        const previous = selected.review.status;
        setStatus(value);
        const optimistic = { ...selected.review, status: value };
        patchItem(selected.review._key, optimistic);
        setBusy(true);
        apiPatch("stig_reviews/" + selected.review._key, { status: value })
            .then((updated) => {
                patchItem(selected.review._key, {
                    ...optimistic,
                    ...updated,
                    status: updated.status || value,
                });
                setBanner({
                    type: "success",
                    text:
                        "Status saved → " +
                        (STATUS_LABELS[updated.status || value] || value),
                });
            })
            .catch((err) => {
                setStatus(previous);
                patchItem(selected.review._key, { ...selected.review, status: previous });
                setBanner({ type: "error", text: "Status save failed: " + err.message });
            })
            .finally(() => setBusy(false));
    };

    const onIngestLock = (value) => {
        if (!selected || busy) {
            return;
        }
        const previous = !!selected.review.ingest_lock;
        const optimistic = { ...selected.review, ingest_lock: value };
        patchItem(selected.review._key, optimistic);
        setBusy(true);
        apiPatch("stig_reviews/" + selected.review._key, { ingest_lock: value })
            .then((updated) => {
                patchItem(selected.review._key, {
                    ...optimistic,
                    ...updated,
                    ingest_lock: !!updated.ingest_lock,
                });
                setBanner({
                    type: "success",
                    text: value
                        ? "Incoming findings will not override this check."
                        : "Incoming findings are authoritative for this check.",
                });
            })
            .catch((err) => {
                patchItem(selected.review._key, {
                    ...selected.review,
                    ingest_lock: previous,
                });
                setBanner({ type: "error", text: "Lock save failed: " + err.message });
            })
            .finally(() => setBusy(false));
    };

    const onWrite = () => {
        if (!selected || busy) {
            return;
        }
        setBusy(true);
        apiPatch("stig_reviews/" + selected.review._key, {
            finding_details: finding,
            comments,
        })
            .then((updated) => {
                patchItem(
                    selected.review._key,
                    { ...selected.review, ...updated },
                    {
                        dirty: false,
                        savedFinding: updated.finding_details || "",
                        savedComments: updated.comments || "",
                    }
                );
                setBanner({ type: "success", text: "Wrote finding details and comments." });
                enterNav();
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Write failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const onRevert = () => {
        if (!selected) {
            return;
        }
        setFinding(selected.savedFinding || "");
        setComments(selected.savedComments || "");
        patchItem(selected.review._key, {
            ...selected.review,
            finding_details: selected.savedFinding,
            comments: selected.savedComments,
        });
    };

    const onValidate = () => {
        const ids = [];
        checklists.forEach((cl) => {
            if (ids.indexOf(cl._key) < 0) {
                ids.push(cl._key);
            }
        });
        if (!ids.length) {
            setBanner({ type: "warning", text: "Select a collection first." });
            return;
        }
        setBusy(true);
        Promise.all(ids.map((id) => apiPatch("stig_checklists/" + id + "/validate", {})))
            .then((results) => {
                let total = 0;
                let valid = 0;
                results.forEach((r) => {
                    total += r.total || 0;
                    valid += r.valid || 0;
                });
                setBanner({
                    type: "info",
                    text: "Validated: " + valid + " of " + total + " findings are completed.",
                });
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Validate failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    const onFieldMode = useCallback((mode) => {
        setVimLayer(mode === "insert" ? "insert" : "text");
    }, []);

    const onFieldCommand = useCallback(() => {
        skipLeaveRef.current = true;
        setCmdOpen(true);
    }, []);

    const enterNav = useCallback(() => {
        const ae = document.activeElement;
        if (ae && ae._stigVim) {
            ae.blur();
        }
        setVimLayer("nav");
        setCmdOpen(false);
        if (listRef.current && listRef.current.focus) {
            listRef.current.focus();
        }
    }, []);

    const onFieldLeave = useCallback(() => {
        if (skipLeaveRef.current) {
            skipLeaveRef.current = false;
            return;
        }
        const next = document.activeElement;
        if (next && next.id === "stig-vim-cmd-input") {
            return;
        }
        enterNav();
    }, [enterNav]);

    const focusSearch = useCallback(() => {
        const input = searchWrapRef.current && searchWrapRef.current.querySelector("input");
        if (input) {
            input.focus();
            input.select();
        }
    }, []);

    const focusField = useCallback((id, mode) => {
        const fieldMode = mode === "normal" ? "normal" : "insert";
        setFieldRequest({ id, mode: fieldMode, token: Date.now() });
        setVimLayer(fieldMode === "insert" ? "insert" : "text");
    }, []);

    const focusFinding = useCallback((mode) => {
        focusField("stig-finding", mode);
    }, [focusField]);

    const onSwitchField = useCallback(
        (id, mode) => {
            skipLeaveRef.current = true;
            focusField(id, mode);
        },
        [focusField]
    );

    const selectRelative = useCallback(
        (delta) => {
            if (!filtered.length) {
                return;
            }
            if (delta === "first") {
                setSelectedKey(filtered[0].review._key);
                return;
            }
            if (delta === "last") {
                setSelectedKey(filtered[filtered.length - 1].review._key);
                return;
            }
            const idx = Math.max(
                0,
                filtered.findIndex((item) => item.review._key === (selected && selected.review._key))
            );
            const next = Math.max(0, Math.min(filtered.length - 1, idx + delta));
            setSelectedKey(filtered[next].review._key);
        },
        [filtered, selected]
    );

    const jumpChoices = useCallback(
        (kind) => {
            if (kind === "collection") {
                return collections.map((c) => ({
                    id: c._key,
                    label: c.name || c._key,
                    sub: c.description || "",
                }));
            }
            if (kind === "host") {
                return [
                    {
                        id: "",
                        label: "All hosts",
                        sub: "Every finding in this collection",
                    },
                ].concat(
                    hosts.map((h) => ({
                        id: h._key,
                        label: h.hostname || h._key,
                        sub: h.fqdn || h.ip_address || "",
                    }))
                );
            }
            const seen = {};
            const rules = [];
            items.forEach((item) => {
                const rule = lookupRule(rulesByKey, item.review);
                const ver = rule.rule_version || item.review.rule_version || "";
                const rid = item.review.rule_id || "";
                const key = ver || rid;
                if (!key || seen[key]) {
                    return;
                }
                seen[key] = true;
                rules.push({
                    id: key,
                    label: ver || rid,
                    sub: rule.rule_title || rid,
                    ruleId: rid,
                    ruleVersion: ver,
                });
            });
            return rules;
        },
        [collections, hosts, items, rulesByKey]
    );

    const openJump = useCallback(
        (kind) => {
            if (kind !== "collection" && !collectionId) {
                setBanner({ type: "warning", text: "Select a collection first." });
                return;
            }
            const choices = jumpChoices(kind);
            if (kind === "rule" && !choices.length) {
                setBanner({ type: "warning", text: "Load a collection first so rules can be indexed." });
                return;
            }
            setJump({ kind, choices });
        },
        [collectionId, jumpChoices]
    );

    const toggleVim = useCallback(() => {
        setVimEnabled((prev) => {
            const next = !prev;
            persistVimSetting(next).catch(() => {
                /* localStorage already has the preference */
            });
            if (!next) {
                setVimLayer("nav");
                setCmdOpen(false);
            }
            return next;
        });
    }, []);

    useEffect(() => {
        loadVimSetting().then((enabled) => setVimEnabled(!!enabled));
    }, []);

    useEffect(() => {
        const list = listRef.current;
        if (!list || !selected) {
            return;
        }
        const row = list.querySelector('[data-key="' + selected.review._key + '"]');
        if (!row) {
            return;
        }
        const listRect = list.getBoundingClientRect();
        const rowRect = row.getBoundingClientRect();
        if (rowRect.top < listRect.top) {
            list.scrollTop -= listRect.top - rowRect.top;
        } else if (rowRect.bottom > listRect.bottom) {
            list.scrollTop += rowRect.bottom - listRect.bottom;
        }
    }, [selected && selected.review._key]);

    ctxRef.current = {
        vimEnabled,
        vimLayer,
        cmdOpen,
        helpOpen,
        jump,
        setHelpOpen,
        setCmdOpen,
        enterNav,
        focusSearch,
        focusFinding,
        selectRelative,
        openJump,
        onStatus,
        onWrite,
    };
    useEditorKeys(ctxRef);

    const selectedRule = selected ? lookupRule(rulesByKey, selected.review) : {};
    const selectedHost = selected
        ? hostsById[checklistById(selected.review.checklist_id).host_id] || {}
        : {};

    return (
        <Shell>
            <VimGlobalStyle />
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Checklist editor
                    </Heading>
                </Brand>
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => onCollection(value)}
                            placeholder="Select collection"
                            filter
                        >
                            {collections.map((c) => (
                                <Select.Option
                                    key={c._key}
                                    label={c.name || c._key}
                                    value={c._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                    <ControlGroup label="Host" labelPosition="top">
                        <Select
                            value={hostId}
                            onChange={(e, { value }) => onHost(value)}
                            disabled={!collectionId}
                            placeholder="All hosts"
                            filter
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
                    <ControlGroup label="Filter" labelPosition="top">
                        <div ref={searchWrapRef}>
                            <Search
                                value={query}
                                onChange={(e, { value }) => setQuery(value)}
                                placeholder="Rule, host, details…"
                            />
                        </div>
                    </ControlGroup>
                    <Button
                        appearance="secondary"
                        disabled={busy || !checklists.length}
                        onClick={onValidate}
                        label="Validate"
                    />
                    <Button
                        appearance="primary"
                        onClick={() => {
                            window.location.assign(viewUrl("stig_import_ui"));
                        }}
                        label="Import checklists"
                    />
                </Toolbar>
                <HeaderMeta>
                    <div>
                        {doneCount} completed · {items.length - doneCount} incomplete
                    </div>
                    <ProgressTrack title={pct + "% complete"}>
                        <ProgressFill $pct={pct} />
                    </ProgressTrack>
                    <VimBadge
                        type="button"
                        className={
                            !vimEnabled
                                ? "is-off"
                                : vimLayer === "insert"
                                  ? "insert"
                                  : vimLayer === "nav"
                                    ? "nav"
                                    : ""
                        }
                        onClick={toggleVim}
                        title={
                            vimEnabled
                                ? "Vim is on. Click to disable."
                                : "Vim keys are off. Click to enable."
                        }
                    >
                        {!vimEnabled
                            ? "VIM OFF"
                            : vimLayer === "insert"
                              ? "INSERT"
                              : vimLayer === "text"
                                ? "NORMAL"
                                : "NAV"}
                    </VimBadge>
                    <Link to={viewUrl("stig_import_ui")}>Import</Link>
                    <Link to={viewUrl("stig_settings_ui")}>Settings</Link>
                    <Link to={viewUrl("stig_editor")}>Classic</Link>
                </HeaderMeta>
            </Header>
            {banner ? (
                <div style={{ padding: "8px 20px 0" }}>
                    <Message
                        appearance={banner.type}
                        onRequestRemove={() => setBanner(null)}
                    >
                        {banner.text}
                    </Message>
                </div>
            ) : null}
            <FilterRow>
                <Button
                    appearance={!statusFilter ? "primary" : "default"}
                    label="All statuses"
                    onClick={() => setStatusFilter("")}
                />
                {Object.keys(STATUS_LABELS).map((st) => (
                    <Button
                        key={st}
                        appearance={statusFilter === st ? "primary" : "default"}
                        label={STATUS_LABELS[st]}
                        onClick={() => setStatusFilter(st)}
                    />
                ))}
                <Button
                    appearance={!validityFilter ? "primary" : "default"}
                    label="All"
                    onClick={() => setValidityFilter("")}
                />
                <Button
                    appearance={validityFilter === "complete" ? "primary" : "default"}
                    label="Completed"
                    onClick={() => setValidityFilter("complete")}
                />
                <Button
                    appearance={validityFilter === "incomplete" ? "primary" : "default"}
                    label="Incomplete"
                    onClick={() => setValidityFilter("incomplete")}
                />
            </FilterRow>
            <Body>
                <ListPane>
                    {loading ? (
                        <Empty>
                            <WaitSpinner size="medium" />
                        </Empty>
                    ) : !filtered.length ? (
                        <Empty>
                            {collectionId
                                ? "No matching findings."
                                : "Select a workspace to review STIG findings."}
                        </Empty>
                    ) : (
                        <FindingList ref={listRef} tabIndex={0}>
                            {filtered.map((item) => {
                                const rev = item.review;
                                const rule = lookupRule(rulesByKey, rev);
                                const host =
                                    hostsById[checklistById(rev.checklist_id).host_id] || {};
                                const complete = reviewIsValid(rev);
                                const isSel = selected && selected.review._key === rev._key;
                                return (
                                    <FindingRow
                                        key={rev._key}
                                        data-key={rev._key}
                                        $selected={isSel}
                                        type="button"
                                        onClick={() => setSelectedKey(rev._key)}
                                    >
                                        <span>{complete ? "✓" : ""}</span>
                                        <StatusChip status={rev.status} />
                                        <span>
                                            {host.hostname || host._key || "—"}
                                        </span>
                                        <FindingTitle>
                                            {rule.rule_version ||
                                                rev.rule_version ||
                                                rev.rule_id}{" "}
                                            · {rule.rule_title || "Untitled rule"}
                                            {item.dirty ||
                                            (isSel && dirty)
                                                ? " ●"
                                                : ""}
                                        </FindingTitle>
                                    </FindingRow>
                                );
                            })}
                        </FindingList>
                    )}
                </ListPane>
                <DetailPane>
                    {!selected ? (
                        <Empty>Select a finding to edit status, details, and comments.</Empty>
                    ) : (
                        <FieldStack>
                            <div>
                                <Heading level={2} style={{ margin: "0 0 4px" }}>
                                    {selectedRule.rule_title ||
                                        selected.review.rule_id ||
                                        "Rule"}
                                </Heading>
                                <MetaLine>
                                    <span>
                                        <strong>Host</strong>{" "}
                                        {selectedHost.hostname || "—"}
                                    </span>
                                    <span>
                                        <strong>Version</strong>{" "}
                                        {selectedRule.rule_version ||
                                            selected.review.rule_version ||
                                            "—"}
                                    </span>
                                    <span>
                                        <strong>Rule</strong> {selected.review.rule_id || "—"}
                                    </span>
                                    <span>
                                        <strong>Severity</strong>{" "}
                                        {selectedRule.severity || "—"}
                                    </span>
                                    <span>
                                        <strong>Valid</strong>{" "}
                                        {reviewIsValid({
                                            finding_details: finding,
                                            comments,
                                        })
                                            ? "yes"
                                            : "no"}
                                    </span>
                                </MetaLine>
                                <Message
                                    appearance={
                                        reviewIsValid({
                                            finding_details: finding,
                                            comments,
                                        })
                                            ? "success"
                                            : "warning"
                                    }
                                >
                                    {reviewIsValid({
                                        finding_details: finding,
                                        comments,
                                    })
                                        ? "Completed — finding details or comments are present."
                                        : "Incomplete — add finding details or comments, then Write."}
                                </Message>
                            </div>
                            <ControlGroup label="Status (saves immediately)">
                                <Select
                                    value={status}
                                    onChange={(e, { value }) => onStatus(value)}
                                >
                                    {Object.keys(STATUS_LABELS).map((st) => (
                                        <Select.Option
                                            key={st}
                                            label={STATUS_LABELS[st]}
                                            value={st}
                                        />
                                    ))}
                                </Select>
                            </ControlGroup>
                            <ControlGroup label="Incoming ingest">
                                <Switch
                                    appearance="toggle"
                                    selected={!!selected.review.ingest_lock}
                                    disabled={busy}
                                    onClick={() =>
                                        onIngestLock(!selected.review.ingest_lock)
                                    }
                                >
                                    Lock this finding — do not override from HEC
                                </Switch>
                            </ControlGroup>
                            <ControlGroup label="Check content">
                                <PreBlock>
                                    {selectedRule.check_content ||
                                        "(no check content in baseline)"}
                                </PreBlock>
                            </ControlGroup>
                            <ControlGroup label="Fix text">
                                <PreBlock>{selectedRule.fix_text || "—"}</PreBlock>
                            </ControlGroup>
                            <ControlGroup label="Finding details (must be written)">
                                <VimField
                                    id="stig-finding"
                                    value={finding}
                                    enabled={vimEnabled}
                                    minHeight={140}
                                    requestedMode={
                                        fieldRequest && fieldRequest.id === "stig-finding"
                                            ? fieldRequest
                                            : null
                                    }
                                    onChange={(value) => {
                                        setFinding(value);
                                        if (selected) {
                                            patchItem(selected.review._key, {
                                                ...selected.review,
                                                finding_details: value,
                                            });
                                        }
                                    }}
                                    onMode={onFieldMode}
                                    onCommand={onFieldCommand}
                                    onLeave={onFieldLeave}
                                    onSwitchField={onSwitchField}
                                />
                            </ControlGroup>
                            <ControlGroup label="Comments (must be written)">
                                <VimField
                                    id="stig-comments"
                                    value={comments}
                                    enabled={vimEnabled}
                                    minHeight={110}
                                    requestedMode={
                                        fieldRequest && fieldRequest.id === "stig-comments"
                                            ? fieldRequest
                                            : null
                                    }
                                    onChange={(value) => {
                                        setComments(value);
                                        if (selected) {
                                            patchItem(selected.review._key, {
                                                ...selected.review,
                                                comments: value,
                                            });
                                        }
                                    }}
                                    onMode={onFieldMode}
                                    onCommand={onFieldCommand}
                                    onLeave={onFieldLeave}
                                    onSwitchField={onSwitchField}
                                />
                            </ControlGroup>
                            <Actions>
                                <Button
                                    appearance="primary"
                                    disabled={busy || !dirty}
                                    onClick={onWrite}
                                    label="Write"
                                />
                                <Button
                                    appearance="secondary"
                                    disabled={!dirty}
                                    onClick={onRevert}
                                    label="Revert"
                                />
                                {dirty ? (
                                    <span>Unwritten finding details or comments</span>
                                ) : null}
                            </Actions>
                        </FieldStack>
                    )}
                </DetailPane>
            </Body>
            {helpOpen ? (
                <HelpOverlay vimEnabled={vimEnabled} onClose={() => setHelpOpen(false)} />
            ) : null}
            {jump ? (
                <JumpOverlay
                    title={
                        jump.kind === "collection"
                            ? "Go to collection"
                            : jump.kind === "host"
                              ? "Go to host"
                              : "Go to rule (all hosts)"
                    }
                    choices={jump.choices}
                    onClose={() => {
                        setJump(null);
                        enterNav();
                    }}
                    onPick={(choice) => {
                        setJump(null);
                        if (jump.kind === "collection") {
                            onCollection(choice.id);
                        } else if (jump.kind === "host") {
                            setHostId(choice.id);
                            onHost(choice.id);
                        } else {
                            loadRuleAcrossHosts(choice.ruleVersion, choice.ruleId);
                        }
                        enterNav();
                    }}
                />
            ) : null}
            {cmdOpen ? (
                <VimCommandBar
                    onCancel={() => {
                        setCmdOpen(false);
                        enterNav();
                    }}
                    onRun={(raw) => {
                        setCmdOpen(false);
                        const cmd = String(raw || "").replace(/^:+/, "").trim();
                        if (!cmd || cmd === "w" || cmd === "write" || cmd === "wq") {
                            if (cmd) {
                                onWrite();
                            }
                            enterNav();
                            return;
                        }
                        setBanner({ type: "error", text: "Not an editor command: :" + cmd });
                        enterNav();
                    }}
                />
            ) : null}
        </Shell>
    );
}
