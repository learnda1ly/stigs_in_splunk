import React, { useCallback, useEffect, useRef, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Heading from "@splunk/react-ui/Heading";
import Message from "@splunk/react-ui/Message";
import Table from "@splunk/react-ui/Table";
import Text from "@splunk/react-ui/Text";
import WaitSpinner from "@splunk/react-ui/WaitSpinner";
import { apiFetch, apiGet, apiUpload } from "../../api";
import { SectionBlock } from "../../layout";

function baselineLabel(row) {
    if (!row) {
        return "—";
    }
    const parts = [
        row.title || row.stig_id || row._key,
        row.version ? "v" + row.version : "",
        row.release_info || "",
    ].filter(Boolean);
    return parts.join(" · ") || row._key;
}

export default function BaselinesStep({ canWrite, canAdmin }) {
    const fileRef = useRef(null);
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [info, setInfo] = useState("");
    const [busyKey, setBusyKey] = useState("");
    const [filter, setFilter] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const list = await apiGet("stig_baselines");
            setRows(Array.isArray(list) ? list : []);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const visible = rows.filter((row) => {
        const q = filter.trim().toLowerCase();
        if (!q) {
            return true;
        }
        return baselineLabel(row).toLowerCase().includes(q);
    });

    async function onFileChange(event) {
        const file = event.target.files && event.target.files[0];
        event.target.value = "";
        if (!file || !canWrite) {
            return;
        }
        setBusyKey("import");
        setError("");
        try {
            const xml = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = () =>
                    reject(reader.error || new Error("read failed"));
                reader.readAsText(file);
            });
            await apiUpload("stig_baselines/import", {
                query: { format: "xccdf", source_uri: file.name },
                contentType: "application/xml",
                body: xml,
            });
            setInfo("Baseline imported from " + file.name + ".");
            await load();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    async function removeBaseline(row) {
        if (!canAdmin) {
            setError("stig_admin is required to delete baselines.");
            return;
        }
        const label = baselineLabel(row);
        if (!window.confirm("Delete baseline \"" + label + "\"?")) {
            return;
        }
        setBusyKey(row._key);
        setError("");
        try {
            await apiFetch("stig_baselines/" + encodeURIComponent(row._key), {
                method: "DELETE",
            });
            setInfo("Baseline deleted.");
            await load();
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusyKey("");
        }
    }

    return (
        <SectionBlock>
            <Heading level={2}>STIG baselines</Heading>
            {loading ? <WaitSpinner /> : null}
            {error ? (
                <Message type="error" style={{ marginTop: 12 }}>{error}</Message>
            ) : null}
            {info ? (
                <Message type="info" style={{ marginTop: 12 }}>{info}</Message>
            ) : null}
            <div style={{ marginTop: 16, display: "flex", gap: 12, flexWrap: "wrap" }}>
                <Text
                    placeholder="Filter baselines"
                    value={filter}
                    onChange={(_, { value }) => setFilter(value)}
                />
                {canWrite ? (
                    <>
                        <input
                            ref={fileRef}
                            type="file"
                            accept=".xml,.xccdf"
                            style={{ display: "none" }}
                            onChange={onFileChange}
                        />
                        <Button
                            label="Import XCCDF"
                            disabled={busyKey === "import"}
                            onClick={() => fileRef.current && fileRef.current.click()}
                        />
                    </>
                ) : null}
            </div>
            <Table style={{ marginTop: 16 }}>
                <Table.Head>
                    <Table.HeadCell>Baseline</Table.HeadCell>
                    <Table.HeadCell>STIG id</Table.HeadCell>
                    <Table.HeadCell width={120}>Actions</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {visible.map((row) => (
                        <Table.Row key={row._key}>
                            <Table.Cell>{baselineLabel(row)}</Table.Cell>
                            <Table.Cell>{row.stig_id || "—"}</Table.Cell>
                            <Table.Cell>
                                {canAdmin ? (
                                    <Button
                                        label="Remove"
                                        appearance="destructive"
                                        disabled={busyKey === row._key}
                                        onClick={() => removeBaseline(row)}
                                    />
                                ) : (
                                    "—"
                                )}
                            </Table.Cell>
                        </Table.Row>
                    ))}
                </Table.Body>
            </Table>
        </SectionBlock>
    );
}
