import React, { useEffect, useRef } from "react";
import styled from "styled-components";
import { variables } from "@splunk/themes";
import { attachVimField } from "./attachField";

const Area = styled.textarea`
    display: block;
    width: 100%;
    box-sizing: border-box;
    min-height: ${(p) => p.$minHeight || 120}px;
    resize: vertical;
    padding: 8px;
    border: 1px solid ${variables.borderColor};
    border-radius: 3px;
    font-family: ui-monospace, "Splunk Platform Mono", monospace;
    font-size: 12px;
    line-height: 1.45;
    background: transparent;
    color: inherit;
    &:focus {
        outline: 2px solid ${variables.focusColor};
        outline-offset: -1px;
    }
    &.stig-vim-normal {
        caret-color: transparent;
        box-shadow: inset 3px 0 0 #c9a227;
    }
`;

export default function VimField({
    id,
    value,
    onChange,
    enabled,
    onMode,
    onCommand,
    onLeave,
    onSwitchField,
    minHeight,
    requestedMode,
}) {
    const ref = useRef(null);

    useEffect(() => {
        const el = ref.current;
        if (!el) {
            return undefined;
        }
        const api = attachVimField(el, {
            isEnabled: () => enabled,
            onMode,
            onCommand,
            onLeave,
            onSwitchField,
        });
        return () => {
            if (api && api.destroy) {
                api.destroy();
            }
        };
    }, [enabled, onMode, onCommand, onLeave, onSwitchField]);

    useEffect(() => {
        const el = ref.current;
        if (el && el._stigVim) {
            el._stigVim.syncEnabled();
        }
    }, [enabled]);

    useEffect(() => {
        const el = ref.current;
        if (!el) {
            return;
        }
        if (el.value !== (value || "")) {
            el.value = value || "";
        }
    }, [value]);

    useEffect(() => {
        const el = ref.current;
        if (!el || !requestedMode || !el._stigVim) {
            return;
        }
        el.focus();
        el._stigVim.setMode(requestedMode.mode, requestedMode.pos);
    }, [requestedMode]);

    return (
        <Area
            id={id}
            ref={ref}
            defaultValue={value}
            $minHeight={minHeight}
            onChange={(e) => onChange(e.target.value)}
            spellCheck={false}
        />
    );
}
