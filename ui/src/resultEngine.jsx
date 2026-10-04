import React from "react";
import styled from "styled-components";

const ORIGIN_LABELS = {
    manual: "Manual",
    automated: "Automated",
    override: "Override",
};

const ORIGIN_ICONS = {
    manual: "👤",
    automated: "⚙",
    override: "↪",
};

const ORIGIN_PALETTE = {
    manual: { bg: "#e8eaed", fg: "#3c444d" },
    automated: { bg: "#d1ecf1", fg: "#0c5460" },
    override: { bg: "#fff3cd", fg: "#856404" },
};

const Pill = styled.span`
    display: inline-block;
    max-width: 100%;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    background: ${(p) => p.$bg};
    color: ${(p) => p.$fg};
`;

export function parseResultEngine(raw) {
    if (raw == null || raw === "") {
        return null;
    }
    if (typeof raw === "object") {
        return raw;
    }
    try {
        const obj = JSON.parse(String(raw));
        return obj && typeof obj === "object" ? obj : null;
    } catch (err) {
        return null;
    }
}

export function resultEngineOrigin(raw) {
    const engine = parseResultEngine(raw);
    if (!engine) {
        return "manual";
    }
    const overrides = engine.overrides;
    if (Array.isArray(overrides) && overrides.length > 0) {
        return "override";
    }
    if (String(engine.product || "").trim()) {
        return "automated";
    }
    return "manual";
}

export function resultEngineSummary(raw) {
    const engine = parseResultEngine(raw);
    const origin = resultEngineOrigin(raw);
    if (!engine) {
        return ORIGIN_LABELS.manual;
    }
    const product = String(engine.product || "").trim();
    if (origin === "override") {
        return product ? `${ORIGIN_LABELS.override} (${product})` : ORIGIN_LABELS.override;
    }
    if (origin === "automated") {
        return product ? `${ORIGIN_LABELS.automated}: ${product}` : ORIGIN_LABELS.automated;
    }
    return ORIGIN_LABELS.manual;
}

export function resultEngineTooltip(raw) {
    const engine = parseResultEngine(raw);
    if (!engine) {
        return "Review entered manually in the editor.";
    }
    const lines = [resultEngineSummary(raw)];
    if (engine.version) {
        lines.push(`Version: ${engine.version}`);
    }
    if (engine.time) {
        lines.push(`Time: ${engine.time}`);
    }
    if (engine.type) {
        lines.push(`Type: ${engine.type}`);
    }
    const checkContent = engine.checkContent;
    if (checkContent && checkContent.location) {
        lines.push(`Check content: ${checkContent.location}`);
    }
    const overrides = engine.overrides;
    if (Array.isArray(overrides) && overrides.length) {
        overrides.forEach((entry, index) => {
            if (!entry || typeof entry !== "object") {
                return;
            }
            const bits = [];
            if (entry.authority) {
                bits.push(`by ${entry.authority}`);
            }
            if (entry.oldResult || entry.newResult) {
                bits.push(`${entry.oldResult || "?"} → ${entry.newResult || "?"}`);
            }
            if (entry.remark) {
                bits.push(entry.remark);
            }
            if (bits.length) {
                lines.push(`Override ${index + 1}: ${bits.join("; ")}`);
            }
        });
    }
    return lines.join("\n");
}

export function formatResultEngineDetail(raw) {
    const engine = parseResultEngine(raw);
    if (!engine) {
        return "—";
    }
    return JSON.stringify(engine, null, 2);
}

export function ResultEngineOriginChip({ raw, origin: originProp }) {
    const origin = originProp || resultEngineOrigin(raw);
    const pal = ORIGIN_PALETTE[origin] || ORIGIN_PALETTE.manual;
    const title = resultEngineTooltip(raw);
    return (
        <Pill $bg={pal.bg} $fg={pal.fg} title={title}>
            {ORIGIN_ICONS[origin] || ""} {ORIGIN_LABELS[origin] || origin}
        </Pill>
    );
}

export function ResultEngineIcon({ raw, origin: originProp }) {
    const origin = originProp || resultEngineOrigin(raw);
    const title = resultEngineTooltip(raw);
    return (
        <span title={title} aria-label={title} style={{ flexShrink: 0, width: "1.25em" }}>
            {ORIGIN_ICONS[origin] || ""}
        </span>
    );
}
