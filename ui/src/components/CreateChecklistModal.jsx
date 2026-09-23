import React, { useEffect, useMemo, useState } from "react";
import Button from "@splunk/react-ui/Button";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Modal from "@splunk/react-ui/Modal";
import RadioList from "@splunk/react-ui/RadioList";
import Select from "@splunk/react-ui/Select";
import Text from "@splunk/react-ui/Text";
import { apiFetch, apiGet, defaultWorkspaceId, viewUrlWithQuery, workspaceLabel } from "../api";

const ASSET_TYPES = ["Computing", "Non-Computing"];

/**
 * Create host (optional) + assign baseline → open STIG Editor on the new checklist.
 */
export default function CreateChecklistModal({
    open,
    onClose,
    baselineId,
    baselineLabel,
    defaultCollectionId = "",
}) {
    const [workspaces, setWorkspaces] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [hostMode, setHostMode] = useState("new");
    const [existingHostId, setExistingHostId] = useState("");
    const [hosts, setHosts] = useState([]);
    const [hostname, setHostname] = useState("");
    const [ipAddress, setIpAddress] = useState("");
    const [fqdn, setFqdn] = useState("");
    const [macAddress, setMacAddress] = useState("");
    const [role, setRole] = useState("None");
    const [assetType, setAssetType] = useState("Computing");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        if (!open) {
            return;
        }
        setError("");
        apiGet("stig_collections")
            .then((rows) => {
                const list = Array.isArray(rows) ? rows : [];
                setWorkspaces(list);
                const initial =
                    defaultCollectionId ||
                    defaultWorkspaceId(list) ||
                    (list[0] && list[0]._key) ||
                    "";
                setCollectionId(initial);
            })
            .catch((err) => setError(String(err.message || err)));
    }, [open, defaultCollectionId]);

    useEffect(() => {
        if (!open || !collectionId) {
            setHosts([]);
            setExistingHostId("");
            return;
        }
        apiGet("stig_hosts", { stig_collection_id: collectionId })
            .then((rows) => {
                const list = Array.isArray(rows) ? rows : [];
                setHosts(list);
                if (list.length) {
                    setExistingHostId(list[0]._key);
                }
            })
            .catch(() => setHosts([]));
    }, [open, collectionId]);

    const title = useMemo(() => {
        const base = baselineLabel || baselineId || "baseline";
        return "Create checklist — " + base;
    }, [baselineId, baselineLabel]);

    const resetAndClose = () => {
        if (!busy) {
            onClose();
        }
    };

    const submit = () => {
        if (!baselineId) {
            setError("No baseline selected.");
            return;
        }
        if (!collectionId) {
            setError("Select a workspace.");
            return;
        }
        setBusy(true);
        setError("");
        const ensureHost = () => {
            if (hostMode === "existing") {
                if (!existingHostId) {
                    throw new Error("Select a host.");
                }
                return Promise.resolve(existingHostId);
            }
            const name = hostname.trim();
            if (!name) {
                throw new Error("Hostname is required for a new host.");
            }
            return apiFetch("stig_hosts", {
                method: "POST",
                body: {
                    stig_collection_id: collectionId,
                    hostname: name,
                    ip_address: ipAddress.trim(),
                    fqdn: fqdn.trim(),
                    mac_address: macAddress.trim(),
                    role: role.trim() || "None",
                    asset_type: assetType,
                },
            }).then((rec) => rec._key);
        };

        ensureHost()
            .then((hostId) =>
                apiFetch("stig_hosts/" + encodeURIComponent(hostId) + "/stigs", {
                    method: "POST",
                    body: { baseline_id: baselineId },
                }).then((doc) => ({ hostId, doc }))
            )
            .then(({ hostId, doc }) => {
                const checklistId = doc._key || doc.checklist_id || "";
                window.location.assign(
                    viewUrlWithQuery("stig_editor_ui", {
                        stig_collection_id: collectionId,
                        host_id: hostId,
                        checklist_id: checklistId,
                    })
                );
            })
            .catch((err) => {
                setError(String(err.message || err));
                setBusy(false);
            });
    };

    return (
        <Modal open={open} onRequestClose={resetAndClose}>
            <Modal.Header title={title} onRequestClose={resetAndClose} />
            <Modal.Body>
                <p style={{ marginTop: 0, maxWidth: 520 }}>
                    Creates a host (or uses an existing one), assigns this baseline, and
                    opens the STIG Editor on the new checklist.
                </p>
                {error ? (
                    <p style={{ color: "var(--splunk-color-negative, #dc3545)" }}>{error}</p>
                ) : null}
                <ControlGroup label="Workspace" labelPosition="top">
                    <Select
                        value={collectionId}
                        onChange={(e, { value }) => setCollectionId(value)}
                        disabled={busy}
                        filter
                    >
                        {workspaces.map((ws) => (
                            <Select.Option
                                key={ws._key}
                                label={workspaceLabel(ws)}
                                value={ws._key}
                            />
                        ))}
                    </Select>
                </ControlGroup>
                <ControlGroup label="Host" labelPosition="top">
                    <RadioList
                        value={hostMode}
                        onChange={(e, { value }) => setHostMode(value)}
                        disabled={busy}
                    >
                        <RadioList.Option value="new" label="New host" />
                        <RadioList.Option
                            value="existing"
                            label="Existing host"
                            disabled={!hosts.length}
                        />
                    </RadioList>
                </ControlGroup>
                {hostMode === "existing" ? (
                    <ControlGroup label="Select host" labelPosition="top">
                        <Select
                            value={existingHostId}
                            onChange={(e, { value }) => setExistingHostId(value)}
                            disabled={busy}
                            filter
                        >
                            {hosts.map((h) => (
                                <Select.Option
                                    key={h._key}
                                    label={(h.hostname || h._key) + (h.ip_address ? " · " + h.ip_address : "")}
                                    value={h._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                ) : (
                    <>
                        <ControlGroup label="Hostname" labelPosition="top" required>
                            <Text
                                value={hostname}
                                onChange={(e, { value }) => setHostname(value)}
                                disabled={busy}
                                placeholder="e.g. web-01.example.mil"
                            />
                        </ControlGroup>
                        <div
                            style={{
                                display: "grid",
                                gridTemplateColumns: "1fr 1fr",
                                gap: 12,
                            }}
                        >
                            <ControlGroup label="IP address" labelPosition="top">
                                <Text
                                    value={ipAddress}
                                    onChange={(e, { value }) => setIpAddress(value)}
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="FQDN" labelPosition="top">
                                <Text
                                    value={fqdn}
                                    onChange={(e, { value }) => setFqdn(value)}
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="MAC address" labelPosition="top">
                                <Text
                                    value={macAddress}
                                    onChange={(e, { value }) => setMacAddress(value)}
                                    disabled={busy}
                                />
                            </ControlGroup>
                            <ControlGroup label="Role" labelPosition="top">
                                <Text
                                    value={role}
                                    onChange={(e, { value }) => setRole(value)}
                                    disabled={busy}
                                />
                            </ControlGroup>
                        </div>
                        <ControlGroup label="Asset type" labelPosition="top">
                            <Select
                                value={assetType}
                                onChange={(e, { value }) => setAssetType(value)}
                                disabled={busy}
                            >
                                {ASSET_TYPES.map((t) => (
                                    <Select.Option key={t} label={t} value={t} />
                                ))}
                            </Select>
                        </ControlGroup>
                    </>
                )}
            </Modal.Body>
            <Modal.Footer>
                <Button appearance="secondary" onClick={resetAndClose} disabled={busy} label="Cancel" />
                <Button appearance="primary" onClick={submit} disabled={busy} label={busy ? "Creating…" : "Create & open editor"} />
            </Modal.Footer>
        </Modal>
    );
}
