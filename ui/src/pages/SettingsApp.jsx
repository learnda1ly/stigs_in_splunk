import React, { useEffect, useState } from "react";
import Button from "@splunk/react-ui/Button";
import Card from "@splunk/react-ui/Card";
import ControlGroup from "@splunk/react-ui/ControlGroup";
import Heading from "@splunk/react-ui/Heading";
import Link from "@splunk/react-ui/Link";
import Message from "@splunk/react-ui/Message";
import Switch from "@splunk/react-ui/Switch";
import Text from "@splunk/react-ui/Text";
import { apiFetch, formatErr, viewUrl } from "../api";
import {
    Brand,
    BrandKicker,
    Header,
    HeaderMeta,
    PagePad,
    Shell,
} from "../layout";
import {
    extractVimEnabled,
    persistVimSetting,
    readLocalVim,
} from "../vim/settings";

const DEFAULTS = {
    ingest_index: "stig",
    ingest_sourcetype: "stig:finding",
    hec_url: "https://localhost:8088/services/collector/event",
    hec_token: "",
    reconcile_earliest: "-15m",
};

export default function SettingsApp() {
    const [vim, setVim] = useState(false);
    const [ingest, setIngest] = useState(DEFAULTS);
    const [busy, setBusy] = useState(false);
    const [banner, setBanner] = useState(null);

    useEffect(() => {
        const local = readLocalVim();
        if (local != null) {
            setVim(local);
        }
        apiFetch("stig_settings")
            .then((raw) => {
                if (!raw || typeof raw !== "object") {
                    return;
                }
                if (readLocalVim() == null) {
                    const remote = extractVimEnabled(raw);
                    if (remote != null) {
                        setVim(!!remote);
                    }
                }
                setIngest({
                    ingest_index: raw.ingest_index || DEFAULTS.ingest_index,
                    ingest_sourcetype: raw.ingest_sourcetype || DEFAULTS.ingest_sourcetype,
                    hec_url: raw.hec_url || DEFAULTS.hec_url,
                    hec_token: raw.hec_token || "",
                    reconcile_earliest: raw.reconcile_earliest || DEFAULTS.reconcile_earliest,
                });
            })
            .catch(() => {
                /* local preference is enough */
            });
    }, []);

    const save = () => {
        setBusy(true);
        persistVimSetting(vim)
            .then(() =>
                apiFetch("stig_settings", {
                    method: "POST",
                    body: {
                        vim_mode: !!vim,
                        ingest_index: ingest.ingest_index,
                        ingest_sourcetype: ingest.ingest_sourcetype,
                        hec_url: ingest.hec_url,
                        hec_token: ingest.hec_token,
                        reconcile_earliest: ingest.reconcile_earliest,
                    },
                })
            )
            .then(() => {
                setBanner({
                    type: "success",
                    text: "Saved. HEC token is used by file import; Watcher/Eval-STIG should post to the HEC input.",
                });
            })
            .catch((err) => {
                const detail = formatErr(err);
                setBanner({
                    type: err && err.local ? "warning" : "error",
                    text: err && err.local
                        ? "Saved vim in this browser. Server save failed: " + detail
                        : "Save failed: " + detail,
                });
            })
            .finally(() => setBusy(false));
    };

    const setField = (key) => (e, { value }) => {
        setIngest((prev) => ({ ...prev, [key]: value }));
    };

    return (
        <Shell>
            <Header>
                <Brand>
                    <BrandKicker>STIG in Splunk</BrandKicker>
                    <Heading level={2} style={{ margin: 0 }}>
                        Configuration
                    </Heading>
                </Brand>
                <HeaderMeta>
                    <Link to={viewUrl("stig_editor_ui")}>Editor</Link>
                    <Link to={viewUrl("stig_import_ui")}>Import</Link>
                    <Link to={viewUrl("stig_settings")}>Classic</Link>
                </HeaderMeta>
            </Header>
            <PagePad>
                {banner ? (
                    <Message
                        appearance={banner.type}
                        onRequestRemove={() => setBanner(null)}
                    >
                        {banner.text}
                    </Message>
                ) : null}
                <Card style={{ maxWidth: 720, marginBottom: 20 }}>
                    <Card.Header title="Editor" />
                    <Card.Body>
                        <Switch
                            appearance="toggle"
                            selected={vim}
                            onClick={() => setVim(!vim)}
                        >
                            Enable vim-style keyboard shortcuts
                        </Switch>
                        <p style={{ marginTop: 16, lineHeight: 1.5 }}>
                            Three layers: <strong>INSERT</strong> (typing), field{" "}
                            <strong>NORMAL</strong> (motions in finding details /
                            comments), and <strong>NAV</strong> (move between findings).
                        </p>
                    </Card.Body>
                </Card>
                <Card style={{ maxWidth: 720 }}>
                    <Card.Header title="Finding ingest (HEC)" />
                    <Card.Body>
                        <p style={{ marginTop: 0, lineHeight: 1.5 }}>
                            Evaluate-STIG and STIGMan Watcher should POST JSON findings to
                            the HEC input <code>stig_findings</code> (
                            <code>sourcetype=stig:finding</code>, <code>index=stig</code>
                            ). Each event must include asset, STIG revision, and rule
                            content so a checklist can be exported later. A scheduled
                            search (<code>STIG reconcile findings to KV</code>) maintains
                            KV current state. Incoming findings overwrite matches unless
                            the review has <code>ingest_lock</code>.
                        </p>
                        <ControlGroup label="Index">
                            <Text
                                value={ingest.ingest_index}
                                onChange={setField("ingest_index")}
                            />
                        </ControlGroup>
                        <ControlGroup label="Sourcetype">
                            <Text
                                value={ingest.ingest_sourcetype}
                                onChange={setField("ingest_sourcetype")}
                            />
                        </ControlGroup>
                        <ControlGroup label="HEC URL">
                            <Text value={ingest.hec_url} onChange={setField("hec_url")} />
                        </ControlGroup>
                        <ControlGroup label="HEC token">
                            <Text
                                value={ingest.hec_token}
                                onChange={setField("hec_token")}
                                type="password"
                                placeholder="From Settings → Data Inputs → HTTP Event Collector"
                            />
                        </ControlGroup>
                        <ControlGroup label="Reconcile window">
                            <Text
                                value={ingest.reconcile_earliest}
                                onChange={setField("reconcile_earliest")}
                            />
                        </ControlGroup>
                        <div style={{ marginTop: 16 }}>
                            <Button
                                appearance="primary"
                                disabled={busy}
                                onClick={save}
                                label="Save settings"
                            />
                        </div>
                    </Card.Body>
                </Card>
            </PagePad>
        </Shell>
    );
}
