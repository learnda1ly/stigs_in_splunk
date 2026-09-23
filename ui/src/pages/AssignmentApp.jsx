import React, { useCallback, useEffect, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, defaultWorkspaceId, workspaceLabel } from "../api";
import {
    Actions,
    Brand,
    BrandKicker,
    FormCard,
    FormRow,
    Header,
    PageIntro,
    PagePad,
    SectionBlock,
    Shell,
    Toolbar,
    TwoColGrid,
} from "../layout";

const emptyRule = {
    name: "",
    priority: 100,
    enabled: true,
    target_stig_collection_id: "",
    match_json: '{"hostname":"","benchmark_id":""}',
};

const emptyOverride = {
    hostname: "",
    benchmark_id: "",
    target_stig_collection_id: "",
    note: "",
};

const PREVIEW_SAMPLE =
    '{"assetName":"w11-team-a-host01","benchmarkId":"Windows_11_STIG","source_product":"evaluate-stig"}';

function formatMatch(raw) {
    if (!raw) {
        return "—";
    }
    if (typeof raw === "object") {
        return JSON.stringify(raw);
    }
    const text = String(raw).trim();
    if (text.length <= 72) {
        return text;
    }
    return text.slice(0, 69) + "…";
}

export default function AssignmentApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [rules, setRules] = useState([]);
    const [overrides, setOverrides] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [ruleDraft, setRuleDraft] = useState(emptyRule);
    const [overrideDraft, setOverrideDraft] = useState(emptyOverride);
    const [previewJson, setPreviewJson] = useState(PREVIEW_SAMPLE);
    const [previewResult, setPreviewResult] = useState(null);
    const [showAddRule, setShowAddRule] = useState(false);
    const [showAddOverride, setShowAddOverride] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const [colls, ruleRows, overrideRows] = await Promise.all([
                apiGet("stig_collections"),
                apiGet("stig_assignment_rules"),
                apiGet("stig_host_baseline_assignments"),
            ]);
            setWorkspaces(colls || []);
            setRules(ruleRows || []);
            setOverrides(overrideRows || []);
            const def = defaultWorkspaceId(colls);
            setRuleDraft((d) => ({
                ...d,
                target_stig_collection_id: d.target_stig_collection_id || def || "",
            }));
            setOverrideDraft((d) => ({
                ...d,
                target_stig_collection_id: d.target_stig_collection_id || def || "",
            }));
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    async function saveRule() {
        setError("");
        try {
            const body = {
                ...ruleDraft,
                priority: Number(ruleDraft.priority) || 100,
                enabled: Boolean(ruleDraft.enabled),
            };
            await apiFetch("stig_assignment_rules", { method: "POST", body });
            setRuleDraft({
                ...emptyRule,
                target_stig_collection_id: ruleDraft.target_stig_collection_id,
            });
            setShowAddRule(false);
            await load();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function saveOverride() {
        setError("");
        try {
            await apiFetch("stig_host_baseline_assignments", {
                method: "POST",
                body: overrideDraft,
            });
            setOverrideDraft({
                ...emptyOverride,
                target_stig_collection_id: overrideDraft.target_stig_collection_id,
            });
            setShowAddOverride(false);
            await load();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function runPreview() {
        setError("");
        setPreviewResult(null);
        try {
            const event = JSON.parse(previewJson);
            const result = await apiFetch("stig_assignment/preview", {
                method: "POST",
                body: { event },
            });
            setPreviewResult(result);
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    const workspaceOptions = workspaces.map((ws) => ({
        label: workspaceLabel(ws),
        value: ws._key,
    }));

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Workspace assignment
                    </Heading>
                </Brand>
                <Toolbar>
                    <Actions>
                        <Button label="Refresh" onClick={load} disabled={loading} />
                    </Actions>
                </Toolbar>
            </Header>
            <PagePad>
                <PageIntro>
                    <p>
                        HEC and scan ingest need a workspace before findings land in the
                        editor. Unless <code>collectionId</code> on the event is trusted
                        (Configuration → Editor &amp; ingest), routing uses this order:
                    </p>
                    <ol>
                        <li>
                            <strong>Host × baseline overrides</strong> — exact hostname +
                            STIG id (e.g. <code>Windows_11_STIG</code>).
                        </li>
                        <li>
                            <strong>Assignment rules</strong> — first enabled rule (lowest
                            priority number) whose <code>match_json</code> matches the
                            event (wildcards supported on hostname).
                        </li>
                        <li>
                            <strong>Default workspace</strong> — when nothing else matches.
                        </li>
                    </ol>
                    <p>
                        Use <strong>Preview</strong> below with a sample finding JSON to
                        verify routing before changing production senders. Create or edit
                        workspaces under <strong>Administration → Workspaces</strong> (first
                        tab); editor and HEC settings are on the <strong>Editor &amp; ingest</strong>
                        tab on the same page.
                    </p>
                </PageIntro>

                {error ? (
                    <Message appearance="error" onRequestRemove={() => setError("")}>
                        {error}
                    </Message>
                ) : null}
                {loading ? <WaitSpinner /> : null}

                <TwoColGrid>
                    <SectionBlock>
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                flexWrap: "wrap",
                                gap: 8,
                                marginBottom: 8,
                            }}
                        >
                            <Heading level={3} style={{ margin: 0 }}>
                                Assignment rules
                            </Heading>
                            <Button
                                label={showAddRule ? "Cancel" : "Add rule"}
                                appearance={showAddRule ? "secondary" : "primary"}
                                onClick={() => setShowAddRule((open) => !open)}
                            />
                        </div>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell width={72}>Priority</Table.HeadCell>
                                <Table.HeadCell>Name</Table.HeadCell>
                                <Table.HeadCell>Match</Table.HeadCell>
                                <Table.HeadCell>Workspace</Table.HeadCell>
                                <Table.HeadCell width={64}>On</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {rules.length ? (
                                    rules.map((row) => (
                                        <Table.Row key={row._key}>
                                            <Table.Cell>{row.priority}</Table.Cell>
                                            <Table.Cell>{row.name}</Table.Cell>
                                            <Table.Cell title={formatMatch(row.match_json)}>
                                                {formatMatch(row.match_json)}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {workspaceLabel(
                                                    workspaces.find(
                                                        (w) =>
                                                            w._key ===
                                                            row.target_stig_collection_id
                                                    )
                                                )}
                                            </Table.Cell>
                                            <Table.Cell>{row.enabled ? "yes" : "no"}</Table.Cell>
                                        </Table.Row>
                                    ))
                                ) : (
                                    <Table.Row>
                                        <Table.Cell colSpan={5}>
                                            No rules yet — ingest uses overrides and the
                                            Default workspace only.
                                        </Table.Cell>
                                    </Table.Row>
                                )}
                            </Table.Body>
                        </Table>

                        {showAddRule ? (
                            <FormCard>
                                <Heading level={4} style={{ margin: 0 }}>
                                    New rule
                                </Heading>
                                <FormRow $columns="1fr 120px">
                                    <ControlGroup label="Name" labelPosition="top">
                                        <Text
                                            value={ruleDraft.name}
                                            onChange={(_e, { value }) =>
                                                setRuleDraft({ ...ruleDraft, name: value })
                                            }
                                            placeholder="e.g. Windows 11 team A"
                                        />
                                    </ControlGroup>
                                    <ControlGroup
                                        label="Priority"
                                        labelPosition="top"
                                        help="Lower runs first"
                                    >
                                        <Text
                                            value={String(ruleDraft.priority)}
                                            onChange={(_e, { value }) =>
                                                setRuleDraft({ ...ruleDraft, priority: value })
                                            }
                                        />
                                    </ControlGroup>
                                </FormRow>
                                <ControlGroup label="Workspace" labelPosition="top">
                                    <Select
                                        value={ruleDraft.target_stig_collection_id}
                                        onChange={(_e, { value }) =>
                                            setRuleDraft({
                                                ...ruleDraft,
                                                target_stig_collection_id: value,
                                            })
                                        }
                                        filter
                                    >
                                        {workspaceOptions.map((opt) => (
                                            <Select.Option
                                                key={opt.value}
                                                label={opt.label}
                                                value={opt.value}
                                            />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <ControlGroup
                                    label="Match (JSON)"
                                    labelPosition="top"
                                    help='Keys: hostname, benchmark_id (STIG id). Example: {"hostname":"w11-*","benchmark_id":"Windows_11_STIG"}'
                                >
                                    <Text
                                        multiline
                                        value={ruleDraft.match_json}
                                        onChange={(_e, { value }) =>
                                            setRuleDraft({ ...ruleDraft, match_json: value })
                                        }
                                        style={{ minHeight: 88, width: "100%" }}
                                    />
                                </ControlGroup>
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 16,
                                        flexWrap: "wrap",
                                    }}
                                >
                                    <Switch
                                        value={ruleDraft.enabled}
                                        onClick={() =>
                                            setRuleDraft({
                                                ...ruleDraft,
                                                enabled: !ruleDraft.enabled,
                                            })
                                        }
                                        selected={ruleDraft.enabled}
                                    >
                                        Enabled
                                    </Switch>
                                    <Button
                                        appearance="primary"
                                        label="Save rule"
                                        onClick={saveRule}
                                    />
                                </div>
                            </FormCard>
                        ) : null}
                    </SectionBlock>

                    <SectionBlock>
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                flexWrap: "wrap",
                                gap: 8,
                                marginBottom: 8,
                            }}
                        >
                            <Heading level={3} style={{ margin: 0 }}>
                                Host × baseline overrides
                            </Heading>
                            <Button
                                label={showAddOverride ? "Cancel" : "Add override"}
                                appearance={showAddOverride ? "secondary" : "primary"}
                                onClick={() => setShowAddOverride((open) => !open)}
                            />
                        </div>
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>Hostname</Table.HeadCell>
                                <Table.HeadCell>STIG id</Table.HeadCell>
                                <Table.HeadCell>Workspace</Table.HeadCell>
                                <Table.HeadCell>Note</Table.HeadCell>
                            </Table.Head>
                            <Table.Body>
                                {overrides.length ? (
                                    overrides.map((row) => (
                                        <Table.Row key={row._key}>
                                            <Table.Cell>{row.hostname}</Table.Cell>
                                            <Table.Cell>{row.benchmark_id}</Table.Cell>
                                            <Table.Cell>
                                                {workspaceLabel(
                                                    workspaces.find(
                                                        (w) =>
                                                            w._key ===
                                                            row.target_stig_collection_id
                                                    )
                                                )}
                                            </Table.Cell>
                                            <Table.Cell>{row.note}</Table.Cell>
                                        </Table.Row>
                                    ))
                                ) : (
                                    <Table.Row>
                                        <Table.Cell colSpan={4}>
                                            No overrides — use rules or Default workspace.
                                        </Table.Cell>
                                    </Table.Row>
                                )}
                            </Table.Body>
                        </Table>

                        {showAddOverride ? (
                            <FormCard>
                                <Heading level={4} style={{ margin: 0 }}>
                                    New override
                                </Heading>
                                <FormRow $columns="1fr 1fr">
                                    <ControlGroup label="Hostname" labelPosition="top">
                                        <Text
                                            value={overrideDraft.hostname}
                                            onChange={(_e, { value }) =>
                                                setOverrideDraft({
                                                    ...overrideDraft,
                                                    hostname: value,
                                                })
                                            }
                                            placeholder="exact hostname from the event"
                                        />
                                    </ControlGroup>
                                    <ControlGroup
                                        label="STIG id"
                                        labelPosition="top"
                                        help="benchmark_id on the finding"
                                    >
                                        <Text
                                            value={overrideDraft.benchmark_id}
                                            onChange={(_e, { value }) =>
                                                setOverrideDraft({
                                                    ...overrideDraft,
                                                    benchmark_id: value,
                                                })
                                            }
                                            placeholder="Windows_11_STIG"
                                        />
                                    </ControlGroup>
                                </FormRow>
                                <ControlGroup label="Workspace" labelPosition="top">
                                    <Select
                                        value={overrideDraft.target_stig_collection_id}
                                        onChange={(_e, { value }) =>
                                            setOverrideDraft({
                                                ...overrideDraft,
                                                target_stig_collection_id: value,
                                            })
                                        }
                                        filter
                                    >
                                        {workspaceOptions.map((opt) => (
                                            <Select.Option
                                                key={opt.value}
                                                label={opt.label}
                                                value={opt.value}
                                            />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <ControlGroup label="Note" labelPosition="top">
                                    <Text
                                        value={overrideDraft.note}
                                        onChange={(_e, { value }) =>
                                            setOverrideDraft({ ...overrideDraft, note: value })
                                        }
                                        placeholder="Optional"
                                    />
                                </ControlGroup>
                                <Button
                                    appearance="primary"
                                    label="Save override"
                                    onClick={saveOverride}
                                />
                            </FormCard>
                        ) : null}
                    </SectionBlock>
                </TwoColGrid>

                <SectionBlock style={{ marginTop: 28, maxWidth: 960 }}>
                    <Heading level={3} style={{ marginTop: 0 }}>
                        Preview
                    </Heading>
                    <FormCard>
                        <ControlGroup
                            label="Sample finding event (JSON)"
                            labelPosition="top"
                            help="Paste a stig:finding body (assetName, benchmarkId / stig id, etc.)"
                        >
                            <Text
                                multiline
                                value={previewJson}
                                onChange={(_e, { value }) => setPreviewJson(value)}
                                style={{ minHeight: 120, width: "100%", fontFamily: "monospace" }}
                            />
                        </ControlGroup>
                        <Button appearance="primary" label="Resolve workspace" onClick={runPreview} />
                        {previewResult ? (
                            <Message appearance="info">
                                <strong>{previewResult.reason || "resolved"}</strong>
                                {" → "}
                                {workspaceLabel(
                                    workspaces.find(
                                        (w) => w._key === previewResult.stig_collection_id
                                    )
                                ) || previewResult.stig_collection_id}
                                {previewResult.assignment_rule_key
                                    ? ` (rule ${previewResult.assignment_rule_key})`
                                    : ""}
                            </Message>
                        ) : null}
                    </FormCard>
                </SectionBlock>
            </PagePad>
        </Shell>
    );
}
