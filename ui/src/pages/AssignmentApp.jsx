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
    Header,
    PagePad,
    Shell,
    Toolbar,
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

function parseMatch(raw) {
    if (!raw) {
        return {};
    }
    if (typeof raw === "object") {
        return raw;
    }
    try {
        return JSON.parse(raw);
    } catch (e) {
        return {};
    }
}

export default function AssignmentApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [rules, setRules] = useState([]);
    const [overrides, setOverrides] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [ruleDraft, setRuleDraft] = useState(emptyRule);
    const [overrideDraft, setOverrideDraft] = useState(emptyOverride);
    const [previewJson, setPreviewJson] = useState(
        '{"assetName":"w11-team-a-host01","benchmarkId":"Windows_11_STIG","source_product":"evaluate-stig"}'
    );
    const [previewResult, setPreviewResult] = useState(null);

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
            setRuleDraft({ ...emptyRule, target_stig_collection_id: ruleDraft.target_stig_collection_id });
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
            await load();
        } catch (err) {
            setError(String(err.message || err));
        }
    }

    async function runPreview() {
        setError("");
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
                    <BrandKicker>STIGs in Splunk</BrandKicker>
                    <Heading level={1}>Workspace assignment</Heading>
                </Brand>
                <Toolbar>
                    <Actions>
                        <Button label="Refresh" onClick={load} />
                    </Actions>
                </Toolbar>
            </Header>
            <PagePad>
                {error ? <Message type="error">{error}</Message> : null}
                {loading ? <WaitSpinner /> : null}

                <Heading level={3}>Assignment rules</Heading>
                <Table>
                    <Table.Head>
                        <Table.HeadCell>Priority</Table.HeadCell>
                        <Table.HeadCell>Name</Table.HeadCell>
                        <Table.HeadCell>Workspace</Table.HeadCell>
                        <Table.HeadCell>Enabled</Table.HeadCell>
                    </Table.Head>
                    <Table.Body>
                        {rules.map((row) => (
                            <Table.Row key={row._key}>
                                <Table.Cell>{row.priority}</Table.Cell>
                                <Table.Cell>{row.name}</Table.Cell>
                                <Table.Cell>
                                    {workspaceLabel(
                                        workspaces.find((w) => w._key === row.target_stig_collection_id)
                                    )}
                                </Table.Cell>
                                <Table.Cell>{row.enabled ? "yes" : "no"}</Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>

                <ControlGroup label="New rule" help="Lower priority numbers run first.">
                    <Text
                        value={ruleDraft.name}
                        onChange={(_e, { value }) => setRuleDraft({ ...ruleDraft, name: value })}
                        placeholder="Rule name"
                    />
                    <Text
                        value={String(ruleDraft.priority)}
                        onChange={(_e, { value }) => setRuleDraft({ ...ruleDraft, priority: value })}
                        placeholder="Priority"
                    />
                    <Select
                        value={ruleDraft.target_stig_collection_id}
                        onChange={(_e, { value }) =>
                            setRuleDraft({ ...ruleDraft, target_stig_collection_id: value })
                        }
                    >
                        {workspaceOptions.map((opt) => (
                            <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                        ))}
                    </Select>
                    <Text
                        value={ruleDraft.match_json}
                        onChange={(_e, { value }) => setRuleDraft({ ...ruleDraft, match_json: value })}
                        placeholder='{"hostname":"w11-team-a-*","benchmark_id":"Windows_11_STIG"}'
                    />
                    <Switch
                        value={ruleDraft.enabled}
                        onClick={() => setRuleDraft({ ...ruleDraft, enabled: !ruleDraft.enabled })}
                        selected={ruleDraft.enabled}
                    >
                        Enabled
                    </Switch>
                    <Button label="Add rule" onClick={saveRule} />
                </ControlGroup>

                <Heading level={3}>Host × baseline overrides</Heading>
                <Table>
                    <Table.Head>
                        <Table.HeadCell>Hostname</Table.HeadCell>
                        <Table.HeadCell>STIG id</Table.HeadCell>
                        <Table.HeadCell>Workspace</Table.HeadCell>
                        <Table.HeadCell>Note</Table.HeadCell>
                    </Table.Head>
                    <Table.Body>
                        {overrides.map((row) => (
                            <Table.Row key={row._key}>
                                <Table.Cell>{row.hostname}</Table.Cell>
                                <Table.Cell>{row.benchmark_id}</Table.Cell>
                                <Table.Cell>
                                    {workspaceLabel(
                                        workspaces.find((w) => w._key === row.target_stig_collection_id)
                                    )}
                                </Table.Cell>
                                <Table.Cell>{row.note}</Table.Cell>
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>

                <ControlGroup label="New override">
                    <Text
                        value={overrideDraft.hostname}
                        onChange={(_e, { value }) =>
                            setOverrideDraft({ ...overrideDraft, hostname: value })
                        }
                        placeholder="hostname"
                    />
                    <Text
                        value={overrideDraft.benchmark_id}
                        onChange={(_e, { value }) =>
                            setOverrideDraft({ ...overrideDraft, benchmark_id: value })
                        }
                        placeholder="benchmark_id / STIG id"
                    />
                    <Select
                        value={overrideDraft.target_stig_collection_id}
                        onChange={(_e, { value }) =>
                            setOverrideDraft({ ...overrideDraft, target_stig_collection_id: value })
                        }
                    >
                        {workspaceOptions.map((opt) => (
                            <Select.Option key={opt.value} label={opt.label} value={opt.value} />
                        ))}
                    </Select>
                    <Text
                        value={overrideDraft.note}
                        onChange={(_e, { value }) => setOverrideDraft({ ...overrideDraft, note: value })}
                        placeholder="Note"
                    />
                    <Button label="Add override" onClick={saveOverride} />
                </ControlGroup>

                <Heading level={3}>Preview</Heading>
                <ControlGroup label="Sample event JSON">
                    <Text
                        multiline
                        value={previewJson}
                        onChange={(_e, { value }) => setPreviewJson(value)}
                    />
                    <Button label="Resolve" onClick={runPreview} />
                    {previewResult ? (
                        <Message type="info">
                            {previewResult.reason} →{" "}
                            {workspaceLabel(
                                workspaces.find((w) => w._key === previewResult.stig_collection_id)
                            ) || previewResult.stig_collection_id}
                        </Message>
                    ) : null}
                </ControlGroup>
            </PagePad>
        </Shell>
    );
}
