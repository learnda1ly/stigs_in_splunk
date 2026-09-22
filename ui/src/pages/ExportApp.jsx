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
import {
    apiFetch,
    apiGet,
    downloadBase64,
    downloadText,
    unwrap,
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

function safeName(value) {
    return String(value || "item").replace(/[^A-Za-z0-9._-]+/g, "_");
}

function fileNameFor(row, fmt) {
    const host = safeName(row.hostname || row._key);
    const stig = safeName(row.stig_id || row.baseline_title || "stig");
    const ver = safeName(row.baseline_version || "");
    let name = host + "_" + stig;
    if (ver) {
        name += "_" + ver;
    }
    return name + "." + (fmt === "ckl" ? "ckl" : "cklb");
}

function enrichRows(checklists, hosts, baselines, collections) {
    const hostMap = {};
    const baseMap = {};
    const collMap = {};
    (hosts || []).forEach((h) => {
        if (h && h._key) {
            hostMap[h._key] = h;
        }
    });
    (baselines || []).forEach((b) => {
        if (b && b._key) {
            baseMap[b._key] = b;
        }
    });
    (collections || []).forEach((c) => {
        if (c && c._key) {
            collMap[c._key] = c;
        }
    });
    return (checklists || []).map((cl) => {
        const host = hostMap[cl.host_id] || {};
        const baseline = baseMap[cl.baseline_id] || {};
        const coll = collMap[cl.stig_collection_id] || {};
        return {
            _key: cl._key,
            stig_collection_id: cl.stig_collection_id,
            collection_name: coll.name || "",
            host_id: cl.host_id,
            hostname: host.hostname || "",
            baseline_id: cl.baseline_id,
            baseline_title: baseline.title || "",
            stig_id: baseline.stig_id || "",
            baseline_version: baseline.version || "",
            review_count: cl.review_count || 0,
            valid_count: cl.valid_count || 0,
            package_ids: cl.package_ids || [],
        };
    });
}

export default function ExportApp() {
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState("");
    const [format, setFormat] = useState("cklb");
    const [rows, setRows] = useState([]);
    const [selected, setSelected] = useState({});
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [banner, setBanner] = useState(null);

    const load = (cid) => {
        setLoading(true);
        const query = cid ? { stig_collection_id: cid } : {};
        Promise.all([
            apiGet("stig_checklists", query),
            apiGet("stig_hosts", query),
            apiGet("stig_baselines"),
            apiGet("stig_collections"),
        ])
            .then(([checklists, hosts, baselines, colls]) => {
                setCollections(Array.isArray(colls) ? colls : []);
                setRows(
                    enrichRows(
                        Array.isArray(checklists) ? checklists : [],
                        Array.isArray(hosts) ? hosts : [],
                        Array.isArray(baselines) ? baselines : [],
                        Array.isArray(colls) ? colls : []
                    )
                );
                setSelected({});
            })
            .catch((err) =>
                setBanner({ type: "error", text: "Failed to load checklists: " + err.message })
            )
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        load("");
    }, []);

    const selectedIds = useMemo(
        () => Object.keys(selected).filter((k) => selected[k]),
        [selected]
    );

    const allChecked = rows.length > 0 && selectedIds.length === rows.length;

    const downloadIds = (ids) => {
        if (!ids.length) {
            setBanner({ type: "warning", text: "Select at least one checklist." });
            return;
        }
        setBusy(true);
        setBanner({
            type: "info",
            text:
                "Exporting " +
                ids.length +
                " checklist" +
                (ids.length === 1 ? "" : "s") +
                "…",
        });
        let work;
        if (ids.length === 1) {
            const row = rows.find((r) => r._key === ids[0]) || {};
            work = apiFetch("stig_checklists/" + ids[0] + "/export", {
                query: { format },
            }).then((content) => {
                const text =
                    typeof content === "string"
                        ? content
                        : JSON.stringify(content, null, 2);
                downloadText(
                    fileNameFor(row, format),
                    text,
                    format === "ckl" ? "application/xml" : "application/json"
                );
            });
        } else {
            // Full workspace download only: partial multi-select keeps export_bulk + checklist_ids.
            const allInWorkspace =
                collectionId && ids.length === rows.length && rows.length > 0;
            const bulkPath = allInWorkspace
                ? "stig_collections/" + collectionId + "/archive/" + format
                : "stig_checklists/export_bulk";
            const bulkBody = allInWorkspace
                ? {}
                : { checklist_ids: ids, format };
            work = apiFetch(bulkPath, {
                method: "POST",
                body: bulkBody,
            }).then((payload) => {
                const doc = unwrap(payload);
                if (!doc || !doc.content_base64) {
                    throw new Error("bulk export returned no zip");
                }
                downloadBase64(
                    doc.filename || "stig-checklists.zip",
                    doc.content_base64,
                    "application/zip"
                );
            });
        }
        work
            .then(() => setBanner({ type: "success", text: "Download started." }))
            .catch((err) =>
                setBanner({ type: "error", text: "Export failed: " + err.message })
            )
            .finally(() => setBusy(false));
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Export checklists
                    </Heading>
                </Brand>
                <Toolbar>
                    <ControlGroup label="Workspace" labelPosition="top">
                        <Select
                            value={collectionId}
                            onChange={(e, { value }) => {
                                setCollectionId(value);
                                load(value);
                            }}
                            placeholder="All collections"
                            filter
                        >
                            <Select.Option label="All collections" value="" />
                            {collections.map((c) => (
                                <Select.Option
                                    key={c._key}
                                    label={workspaceLabel(c)}
                                    value={c._key}
                                />
                            ))}
                        </Select>
                    </ControlGroup>
                    <ControlGroup label="Format" labelPosition="top">
                        <Select
                            value={format}
                            onChange={(e, { value }) => setFormat(value)}
                        >
                            <Select.Option label="CKLB (JSON)" value="cklb" />
                            <Select.Option label="CKL (XML)" value="ckl" />
                        </Select>
                    </ControlGroup>
                    <Button
                        appearance="primary"
                        disabled={busy}
                        onClick={() => downloadIds(selectedIds)}
                        label="Download selected"
                    />
                    <Button
                        appearance="secondary"
                        disabled={busy || !rows.length}
                        onClick={() => downloadIds(rows.map((r) => r._key))}
                        label="Download all in view"
                    />
                </Toolbar>
                <HeaderMeta>
                    <span>
                        {rows.length} checklist{rows.length === 1 ? "" : "s"}
                    </span>
                    <Link to={viewUrl("stig_editor_ui")}>Editor</Link>
                    <Link to={viewUrl("stig_import_ui")}>Import</Link>
                    <Link to={viewUrl("configuration")}>Configuration</Link>
                    <Link to={viewUrl("stig_export")}>Classic</Link>
                </HeaderMeta>
            </Header>
            <PagePad>
                <p style={{ maxWidth: 720, marginTop: 0 }}>
                    Each checklist is one host and one baseline.{" "}
                    <code>package_id</code> is stored on findings (reviews), not on
                    the checklist, so another Splunk search can fill it later.
                </p>
                {banner ? (
                    <Message
                        appearance={banner.type}
                        onRequestRemove={() => setBanner(null)}
                    >
                        {banner.text}
                    </Message>
                ) : null}
                {loading ? (
                    <div style={{ padding: 40 }}>
                        <WaitSpinner size="medium" />
                    </div>
                ) : (
                    <Table stripeRows>
                        <Table.Head>
                            <Table.HeadCell>
                                <Switch
                                    selected={allChecked}
                                    appearance="checkbox"
                                    onClick={() => {
                                        if (allChecked) {
                                            setSelected({});
                                            return;
                                        }
                                        const next = {};
                                        rows.forEach((r) => {
                                            next[r._key] = true;
                                        });
                                        setSelected(next);
                                    }}
                                />
                            </Table.HeadCell>
                            <Table.HeadCell>Host</Table.HeadCell>
                            <Table.HeadCell>Baseline</Table.HeadCell>
                            <Table.HeadCell>Collection</Table.HeadCell>
                            <Table.HeadCell>Completed</Table.HeadCell>
                            <Table.HeadCell>Package IDs</Table.HeadCell>
                            <Table.HeadCell />
                        </Table.Head>
                        <Table.Body>
                            {rows.length ? (
                                rows.map((row) => (
                                    <Table.Row key={row._key}>
                                        <Table.Cell>
                                            <Switch
                                                selected={!!selected[row._key]}
                                                appearance="checkbox"
                                                onClick={() =>
                                                    setSelected((prev) => ({
                                                        ...prev,
                                                        [row._key]: !prev[row._key],
                                                    }))
                                                }
                                            />
                                        </Table.Cell>
                                        <Table.Cell>
                                            {row.hostname || row.host_id || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {(row.stig_id ||
                                                row.baseline_title ||
                                                "—") +
                                                (row.baseline_version
                                                    ? " " + row.baseline_version
                                                    : "")}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {row.collection_name || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {(row.valid_count || 0) +
                                                " / " +
                                                (row.review_count || 0)}
                                        </Table.Cell>
                                        <Table.Cell>
                                            {(row.package_ids || []).join(", ") || "—"}
                                        </Table.Cell>
                                        <Table.Cell>
                                            <Button
                                                appearance="secondary"
                                                disabled={busy}
                                                onClick={() => downloadIds([row._key])}
                                                label="Download"
                                            />
                                        </Table.Cell>
                                    </Table.Row>
                                ))
                            ) : (
                                <Table.Row>
                                    <Table.Cell align="center" colSpan={7}>
                                        No checklists found.
                                    </Table.Cell>
                                </Table.Row>
                            )}
                        </Table.Body>
                    </Table>
                )}
                <Actions>
                    <span />
                </Actions>
            </PagePad>
        </Shell>
    );
}
