import React, { useCallback, useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Select from "@splunk/react-ui/Select";
import Switch from "@splunk/react-ui/Switch";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, defaultWorkspaceId, workspaceLabel } from "../api";
import {
    Brand,
    BrandKicker,
    Header,
    PagePad,
    Shell,
    Toolbar,
} from "../layout";
import {
    DEFAULT_REVIEW_REQUIREMENTS,
    STATUS_LABELS,
    normalizeReviewRequirements,
} from "../status";

const STATUS_OPTIONS = Object.keys(STATUS_LABELS).map((key) => ({
    label: STATUS_LABELS[key],
    value: key,
}));

export default function ReviewRequirementsApp() {
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [policy, setPolicy] = useState(DEFAULT_REVIEW_REQUIREMENTS);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [saved, setSaved] = useState("");

    const workspaceOptions = useMemo(
        () =>
            (workspaces || []).map((row) => ({
                label: workspaceLabel(row),
                value: row._key,
            })),
        [workspaces]
    );

    const loadPolicy = useCallback(async (cid) => {
        if (!cid) {
            setPolicy(DEFAULT_REVIEW_REQUIREMENTS);
            return;
        }
        const body = await apiGet(
            "stig_collections/" + cid + "/review_requirements"
        );
        setPolicy(
            normalizeReviewRequirements(
                (body && body.review_requirements) || DEFAULT_REVIEW_REQUIREMENTS
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

    const patchField = (field, value) => {
        setPolicy((prev) => ({ ...prev, [field]: value }));
        setSaved("");
    };

    const toggleStatusScope = (status) => {
        setPolicy((prev) => {
            const list = prev.applies_to_statuses || [];
            const next = list.indexOf(status) >= 0
                ? list.filter((s) => s !== status)
                : list.concat([status]);
            return { ...prev, applies_to_statuses: next };
        });
        setSaved("");
    };

    const onSave = async () => {
        if (!collectionId) {
            return;
        }
        setSaving(true);
        setError("");
        setSaved("");
        try {
            await apiFetch(
                "stig_collections/" + collectionId + "/review_requirements",
                {
                    method: "PATCH",
                    body: { review_requirements: policy },
                }
            );
            setSaved("Saved review requirements for this workspace.");
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
                    Review requirements
                </Brand>
            </Header>
            <PagePad>
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
                        <Select
                            value={collectionId}
                            onChange={onWorkspaceChange}
                            style={{ minWidth: 280 }}
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
                    <Button
                        label={saving ? "Saving…" : "Save"}
                        onClick={onSave}
                        disabled={!collectionId || saving}
                    />
                </Toolbar>
                <Heading level={3}>Validation policy</Heading>
                <p style={{ maxWidth: 720, opacity: 0.85 }}>
                    Controls when a review counts as complete for progress, submit,
                    and PATCH validation. Empty scope applies to all statuses. With no
                    flags set, the default matches legacy behavior: finding details
                    or comments must be non-empty.
                </p>
                <ControlGroup
                    label="Require finding details"
                    labelPosition="left"
                    help="When enabled, trimmed finding details must meet the minimum length."
                >
                    <Switch
                        selected={policy.require_finding_details}
                        onClick={() =>
                            patchField(
                                "require_finding_details",
                                !policy.require_finding_details
                            )
                        }
                    />
                </ControlGroup>
                <ControlGroup label="Minimum finding details length">
                    <Text
                        value={String(policy.min_finding_details_length || 0)}
                        onChange={(e, { value }) =>
                            patchField(
                                "min_finding_details_length",
                                parseInt(value, 10) || 0
                            )
                        }
                        style={{ width: 120 }}
                    />
                </ControlGroup>
                <ControlGroup
                    label="Require comments"
                    labelPosition="left"
                    help="When enabled, trimmed comments must meet the minimum length."
                >
                    <Switch
                        selected={policy.require_comments}
                        onClick={() =>
                            patchField(
                                "require_comments",
                                !policy.require_comments
                            )
                        }
                    />
                </ControlGroup>
                <ControlGroup label="Minimum comments length">
                    <Text
                        value={String(policy.min_comments_length || 0)}
                        onChange={(e, { value }) =>
                            patchField(
                                "min_comments_length",
                                parseInt(value, 10) || 0
                            )
                        }
                        style={{ width: 120 }}
                    />
                </ControlGroup>
                <Heading level={4}>Apply only to statuses (optional)</Heading>
                <p style={{ maxWidth: 720, opacity: 0.85 }}>
                    Leave all unchecked to apply the policy to every status. When
                    any are selected, only those statuses are validated.
                </p>
                {STATUS_OPTIONS.map((opt) => (
                    <ControlGroup key={opt.value} label={opt.label} labelPosition="left">
                        <Switch
                            selected={
                                (policy.applies_to_statuses || []).indexOf(
                                    opt.value
                                ) >= 0
                            }
                            onClick={() => toggleStatusScope(opt.value)}
                        />
                    </ControlGroup>
                ))}
            </PagePad>
        </Shell>
    );
}
