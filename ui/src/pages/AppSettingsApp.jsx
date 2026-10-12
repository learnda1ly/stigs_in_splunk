import React, { useCallback, useEffect, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import Text from "@splunk/react-ui/Text";
import TextArea from "@splunk/react-ui/TextArea";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, viewUrl } from "../api";
import { refreshAppThemeFromServer } from "../themes/settings";
import { THEME_PRESET_IDS } from "../themes/presets";
import {
    Brand,
    BrandKicker,
    Header,
    PageIntro,
    PagePad,
    SectionBlock,
    Shell,
    Toolbar,
} from "../layout";

const THEME_OPTIONS = THEME_PRESET_IDS.map((id) => ({
    label: id.replace(/_/g, " "),
    value: id,
}));

const emptyDraft = () => ({
    ui_theme_preset: "tokyo_night",
    ui_theme_custom: "",
    governance_enabled: true,
    vim_mode: false,
    trust_event_collection_id: false,
    ingest_index: "stig",
    ingest_sourcetype: "stig:finding",
    hec_url: "https://localhost:8088/services/collector/event",
    reconcile_earliest: "-15m",
});

export default function AppSettingsApp() {
    const [draft, setDraft] = useState(emptyDraft);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const data = await apiGet("stig_settings");
            const row = data && typeof data === "object" ? data : {};
            setDraft({
                ui_theme_preset: row.ui_theme_preset || "tokyo_night",
                ui_theme_custom: row.ui_theme_custom || "",
                governance_enabled:
                    row.governance_enabled !== false &&
                    row.governance_enabled !== "0" &&
                    row.governance_enabled !== 0,
                vim_mode: !!row.vim_mode,
                trust_event_collection_id: !!row.trust_event_collection_id,
                ingest_index: row.ingest_index || "stig",
                ingest_sourcetype: row.ingest_sourcetype || "stig:finding",
                hec_url:
                    row.hec_url ||
                    "https://localhost:8088/services/collector/event",
                reconcile_earliest: row.reconcile_earliest || "-15m",
            });
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    async function save() {
        setSaving(true);
        setError("");
        setInfo("");
        try {
            await apiFetch("stig_settings", {
                method: "POST",
                body: {
                    ...draft,
                    governance_enabled: draft.governance_enabled,
                },
            });
            await refreshAppThemeFromServer();
            setInfo("Settings saved.");
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setSaving(false);
        }
    }

    function setField(field, value) {
        setDraft((d) => ({ ...d, [field]: value }));
    }

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>Admin</BrandKicker>
                    <Heading level={1}>Editor &amp; ingest</Heading>
                </Brand>
                <Toolbar>
                    <Button label="Refresh" onClick={load} disabled={loading} />
                    <Button
                        appearance="primary"
                        label="Save"
                        onClick={save}
                        disabled={saving || loading}
                    />
                </Toolbar>
            </Header>
            <PagePad>
                <PageIntro>
                    Workspaces, hosts, baselines, and RMF packages are configured in{" "}
                    <Link to={viewUrl("stig_configuration_ui")}>Governance</Link>
                    .
                    HEC token is set in Splunk Data inputs (stig_findings), not here.
                </PageIntro>
                {loading ? <WaitSpinner /> : null}
                {error ? (
                    <Message type="error" style={{ marginTop: 12 }}>{error}</Message>
                ) : null}
                {info ? (
                    <Message type="info" style={{ marginTop: 12 }}>{info}</Message>
                ) : null}
                <SectionBlock>
                    <Heading level={2}>Editor</Heading>
                    <ControlGroup label="Editor theme" labelPosition="top">
                        <Select
                            value={draft.ui_theme_preset}
                            onChange={(e, { value }) =>
                                setField("ui_theme_preset", value)
                            }
                        >
                            {THEME_OPTIONS.map((opt) => (
                                <Select.Option
                                    key={opt.value}
                                    label={opt.label}
                                    value={opt.value}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                    <ControlGroup label="Custom theme JSON" labelPosition="top">
                        <TextArea
                            value={draft.ui_theme_custom}
                            onChange={(_, { value }) =>
                                setField("ui_theme_custom", value)
                            }
                            rows={4}
                        />
                    </ControlGroup>
                    <ControlGroup label="Review governance" labelPosition="left">
                        <Switch
                            selected={draft.governance_enabled}
                            onClick={() =>
                                setField(
                                    "governance_enabled",
                                    !draft.governance_enabled
                                )
                            }
                        />
                    </ControlGroup>
                    <ControlGroup label="Vim keyboard shortcuts" labelPosition="left">
                        <Switch
                            selected={draft.vim_mode}
                            onClick={() => setField("vim_mode", !draft.vim_mode)}
                        />
                    </ControlGroup>
                </SectionBlock>
                <SectionBlock>
                    <Heading level={2}>Finding ingest (HEC)</Heading>
                    <ControlGroup label="Trust collectionId on events" labelPosition="left">
                        <Switch
                            selected={draft.trust_event_collection_id}
                            onClick={() =>
                                setField(
                                    "trust_event_collection_id",
                                    !draft.trust_event_collection_id
                                )
                            }
                        />
                    </ControlGroup>
                    <ControlGroup label="Index" labelPosition="top">
                        <Text
                            value={draft.ingest_index}
                            onChange={(_, { value }) =>
                                setField("ingest_index", value)
                            }
                        />
                    </ControlGroup>
                    <ControlGroup label="Sourcetype" labelPosition="top">
                        <Text
                            value={draft.ingest_sourcetype}
                            onChange={(_, { value }) =>
                                setField("ingest_sourcetype", value)
                            }
                        />
                    </ControlGroup>
                    <ControlGroup label="HEC URL" labelPosition="top">
                        <Text
                            value={draft.hec_url}
                            onChange={(_, { value }) => setField("hec_url", value)}
                        />
                    </ControlGroup>
                    <ControlGroup label="Reconcile window" labelPosition="top">
                        <Text
                            value={draft.reconcile_earliest}
                            onChange={(_, { value }) =>
                                setField("reconcile_earliest", value)
                            }
                        />
                    </ControlGroup>
                </SectionBlock>
            </PagePad>
        </Shell>
    );
}
