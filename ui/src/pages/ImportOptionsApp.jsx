import React, { useCallback, useEffect, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import {
    apiFetch,
    apiGet,
    defaultWorkspaceId,
    isAllWorkspaces,
} from "../api";
import WorkspaceSelect from "../components/WorkspaceSelect";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";
import {
    DEFAULT_IMPORT_OPTIONS,
    normalizeImportOptions,
} from "../status";

const WORKFLOW_IMPORT_OPTIONS = [
    { label: "Saved (draft)", value: "saved" },
    { label: "Submitted", value: "submitted" },
    { label: "Accepted", value: "accepted" },
    { label: "Keep existing", value: "keep_existing" },
];

const INCLUDE_UNREVIEWED_OPTIONS = [
    { label: "Never", value: "never" },
    { label: "When detail or comment present", value: "with_comments" },
    { label: "Always", value: "always" },
];

const UNREVIEWED_COMMENT_OPTIONS = [
    { label: "Informational", value: "informational" },
    { label: "Not reviewed", value: "not_reviewed" },
];

const EMPTY_TEXT_OPTIONS = [
    { label: "Ignore (keep existing)", value: "ignored" },
    { label: "Replace with placeholder", value: "replaced" },
    { label: "Imported (clear)", value: "imported" },
];

export default function ImportOptionsApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [policy, setPolicy] = useState(DEFAULT_IMPORT_OPTIONS);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [saved, setSaved] = useState("");

    const loadPolicy = useCallback(async (cid) => {
        if (!cid || isAllWorkspaces(cid)) {
            setPolicy(DEFAULT_IMPORT_OPTIONS);
            return;
        }
        const body = await apiGet("stig_collections/" + cid + "/import_options");
        setPolicy(
            normalizeImportOptions(
                (body && body.import_options) || DEFAULT_IMPORT_OPTIONS
            )
        );
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const colls = await apiGet("stig_collections");
            setWorkspaces(colls || []);
            const cid = defaultWorkspaceId(colls || []);
            setCollectionId(cid);
            await loadPolicy(cid);
        } catch (err) {
            setError(String(err && err.message ? err.message : err));
        } finally {
            setLoading(false);
        }
    }, [loadPolicy]);

    useEffect(() => {
        load();
    }, [load]);

    const onWorkspaceChange = async (e, { value }) => {
        setCollectionId(value);
        setSaved("");
        setError("");
        try {
            await loadPolicy(value);
        } catch (err) {
            setError(String(err && err.message ? err.message : err));
        }
    };

    const patchStatusPerResult = (key, value) => {
        setPolicy((prev) => ({
            ...prev,
            status_per_result: { ...prev.status_per_result, [key]: value },
        }));
        setSaved("");
    };

    const patchField = (field, value) => {
        setPolicy((prev) => ({ ...prev, [field]: value }));
        setSaved("");
    };

    const onSave = async () => {
        if (!collectionId || isAllWorkspaces(collectionId)) {
            return;
        }
        setSaving(true);
        setError("");
        setSaved("");
        try {
            await apiFetch("stig_collections/" + collectionId + "/import_options", {
                method: "PATCH",
                body: { import_options: policy },
            });
            setSaved("Saved import options for this workspace.");
            await loadPolicy(collectionId);
        } catch (err) {
            setError(String(err && err.message ? err.message : err));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Import options
                    </Heading>
                </Brand>
            </Header>
            <PagePad>
                <p style={{ maxWidth: 820 }}>
                    Defaults for checklist and scan imports, including HEC and Watcher-shaped
                    automation. Aligns with STIG Manager collection import options (user guide
                    §2.9.1.4.4).
                </p>
                {loading ? <WaitSpinner /> : null}
                {error ? (
                    <Message type="error" style={{ marginBottom: 12 }}>
                        {error}
                    </Message>
                ) : null}
                {saved ? (
                    <Message type="success" style={{ marginBottom: 12 }}>
                        {saved}
                    </Message>
                ) : null}
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <WorkspaceSelect
                            workspaces={workspaces}
                            value={collectionId}
                            onChange={onWorkspaceChange}
                            style={{ minWidth: 280 }}
                        />
                    </ControlGroup>
                    <Button
                        label={saving ? "Saving…" : "Save"}
                        onClick={onSave}
                        disabled={saving || !collectionId || isAllWorkspaces(collectionId)}
                    />
                </Toolbar>
                <Heading level={4}>Review status per result</Heading>
                {["fail", "pass", "notapplicable"].map((key) => (
                    <ControlGroup
                        key={key}
                        label={key === "notapplicable" ? "Not applicable" : key}
                        labelPosition="top"
                        style={{ maxWidth: 360, marginBottom: 8 }}
                    >
                        <Select
                            value={policy.status_per_result[key]}
                            onChange={(e, { value }) => patchStatusPerResult(key, value)}
                        >
                            {WORKFLOW_IMPORT_OPTIONS.map((opt) => (
                                <Select.Option
                                    key={opt.value}
                                    label={opt.label}
                                    value={opt.value}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                ))}
                <Heading level={4} style={{ marginTop: 24 }}>
                    Unreviewed rules
                </Heading>
                <ControlGroup label="Include unreviewed" labelPosition="top">
                    <Select
                        value={policy.include_unreviewed}
                        onChange={(e, { value }) =>
                            patchField("include_unreviewed", value)
                        }
                    >
                        {INCLUDE_UNREVIEWED_OPTIONS.map((opt) => (
                            <Select.Option
                                key={opt.value}
                                label={opt.label}
                                value={opt.value}
                            />
                        ))}
                    </Select>
                </ControlGroup>
                <ControlGroup label="Unreviewed with comment" labelPosition="top">
                    <Select
                        value={policy.unreviewed_with_comment}
                        onChange={(e, { value }) =>
                            patchField("unreviewed_with_comment", value)
                        }
                    >
                        {UNREVIEWED_COMMENT_OPTIONS.map((opt) => (
                            <Select.Option
                                key={opt.value}
                                label={opt.label}
                                value={opt.value}
                            />
                        ))}
                    </Select>
                </ControlGroup>
                <Heading level={4} style={{ marginTop: 24 }}>
                    Empty text fields
                </Heading>
                <ControlGroup label="Empty detail text" labelPosition="top">
                    <Select
                        value={policy.empty_detail}
                        onChange={(e, { value }) => patchField("empty_detail", value)}
                    >
                        {EMPTY_TEXT_OPTIONS.map((opt) => (
                            <Select.Option
                                key={opt.value}
                                label={opt.label}
                                value={opt.value}
                            />
                        ))}
                    </Select>
                </ControlGroup>
                <ControlGroup label="Empty comment text" labelPosition="top">
                    <Select
                        value={policy.empty_comment}
                        onChange={(e, { value }) => patchField("empty_comment", value)}
                    >
                        {EMPTY_TEXT_OPTIONS.map((opt) => (
                            <Select.Option
                                key={opt.value}
                                label={opt.label}
                                value={opt.value}
                            />
                        ))}
                    </Select>
                </ControlGroup>
                <Heading level={4} style={{ marginTop: 24 }}>
                    Overrides
                </Heading>
                <ControlGroup label="Allow per-import customization" labelPosition="left">
                    <Switch
                        selected={policy.allow_customize_per_import}
                        onClick={() =>
                            patchField(
                                "allow_customize_per_import",
                                !policy.allow_customize_per_import
                            )
                        }
                    />
                </ControlGroup>
                <ControlGroup
                    label="Lock options for HEC / reconcile automation"
                    labelPosition="left"
                >
                    <Switch
                        selected={policy.lock_automation_import_options}
                        onClick={() =>
                            patchField(
                                "lock_automation_import_options",
                                !policy.lock_automation_import_options
                            )
                        }
                    />
                </ControlGroup>
            </PagePad>
        </Shell>
    );
}
