import React, { useEffect, useMemo, useState } from "react";
import styled from "styled-components";
import { variables } from "@splunk/themes";
import Button from "@splunk/react-ui/Button";

const Overlay = styled.div`
    position: fixed;
    inset: 0;
    z-index: 10050;
    background: rgba(15, 23, 42, 0.45);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 12vh;
`;

const Panel = styled.div`
    width: min(560px, 92vw);
    max-height: 70vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: ${variables.backgroundColorSection};
    color: ${variables.contentColorDefault};
    border: 1px solid ${variables.borderColor};
    border-radius: 6px;
    padding: 16px 18px;
`;

const JumpInput = styled.input`
    width: 100%;
    box-sizing: border-box;
    margin: 8px 0 12px;
    padding: 8px 10px;
    font: inherit;
`;

const JumpList = styled.ul`
    list-style: none;
    margin: 0;
    padding: 0;
    overflow: auto;
    max-height: 46vh;
`;

const JumpItem = styled.li`
    padding: 8px 10px;
    cursor: pointer;
    background: ${(p) => (p.$active ? variables.interactiveColorOverlayHover : "transparent")};
    .muted {
        color: ${variables.contentColorMuted};
        font-size: 12px;
    }
`;

const HelpTable = styled.table`
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    td {
        padding: 6px 8px;
        vertical-align: top;
        border-bottom: 1px solid ${variables.borderColor};
    }
    kbd {
        font-family: ui-monospace, monospace;
        background: ${variables.neutral200};
        padding: 1px 5px;
        border-radius: 3px;
    }
`;

const CmdBar = styled.div`
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: ${variables.backgroundColorSection};
    border-top: 1px solid ${variables.borderColor};
    font-family: ui-monospace, monospace;
    input {
        flex: 1;
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        outline: none;
    }
`;

export function JumpOverlay({ title, choices, onPick, onClose }) {
    const [query, setQuery] = useState("");
    const [active, setActive] = useState(0);
    const visible = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) {
            return choices;
        }
        return choices.filter(
            (c) =>
                (c.label || "").toLowerCase().indexOf(q) >= 0 ||
                (c.sub || "").toLowerCase().indexOf(q) >= 0
        );
    }, [choices, query]);

    useEffect(() => {
        setActive(0);
    }, [query]);

    const pick = (choice) => {
        if (choice) {
            onPick(choice);
        }
    };

    return (
        <Overlay onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
            <Panel>
                <strong>{title}</strong>
                <JumpInput
                    autoFocus
                    value={query}
                    placeholder="Start typing…"
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Escape") {
                            e.preventDefault();
                            onClose();
                        } else if (e.key === "ArrowDown") {
                            e.preventDefault();
                            setActive((i) => Math.min(visible.length - 1, i + 1));
                        } else if (e.key === "ArrowUp") {
                            e.preventDefault();
                            setActive((i) => Math.max(0, i - 1));
                        } else if (e.key === "Enter") {
                            e.preventDefault();
                            pick(visible[active]);
                        }
                    }}
                />
                <JumpList>
                    {visible.map((c, idx) => (
                        <JumpItem
                            key={c.id + ":" + idx}
                            $active={idx === active}
                            onMouseDown={(e) => {
                                e.preventDefault();
                                pick(c);
                            }}
                        >
                            {c.label}
                            {c.sub ? <div className="muted">{c.sub}</div> : null}
                        </JumpItem>
                    ))}
                </JumpList>
            </Panel>
        </Overlay>
    );
}

export function HelpOverlay({ vimEnabled, onClose }) {
    return (
        <Overlay onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
            <Panel>
                <strong>Keyboard shortcuts</strong>
                <HelpTable>
                    <tbody>
                        {vimEnabled ? (
                            <>
                                <tr>
                                    <td>
                                        <kbd>Esc</kbd>
                                    </td>
                                    <td>INSERT → field NORMAL. Again → NAV</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>i</kbd>
                                    </td>
                                    <td>NAV → insert in finding details</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>o</kbd>
                                    </td>
                                    <td>
                                        NAV: status Open. Field NORMAL: open a line.
                                        INSERT: type o
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>{"{"}</kbd> / <kbd>{"}"}</kbd>
                                    </td>
                                    <td>NAV: previous / next finding. Field: paragraphs</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>g</kbd>
                                        <kbd>g</kbd> / <kbd>G</kbd>
                                    </td>
                                    <td>First / last finding (NAV)</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>g</kbd>
                                        <kbd>h</kbd>
                                    </td>
                                    <td>Go to host</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>g</kbd>
                                        <kbd>c</kbd>
                                    </td>
                                    <td>Go to collection</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>g</kbd>
                                        <kbd>r</kbd>
                                    </td>
                                    <td>Go to rule across all hosts</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>1</kbd>–<kbd>4</kbd> <kbd>o</kbd>
                                        <kbd>n</kbd>
                                        <kbd>f</kbd>
                                        <kbd>a</kbd>
                                    </td>
                                    <td>Status in NAV (saves immediately)</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>:</kbd>
                                        <kbd>w</kbd>
                                    </td>
                                    <td>Write finding details / comments</td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>Tab</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd>
                                    </td>
                                    <td>
                                        Finding details ↔ comments (stays in the field
                                        layer)
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <kbd>g</kbd>
                                        <kbd>t</kbd> / <kbd>g</kbd>
                                        <kbd>T</kbd>
                                    </td>
                                    <td>Same switch in field NORMAL</td>
                                </tr>
                            </>
                        ) : (
                            <tr>
                                <td colSpan={2}>
                                    Vim keys are off. Click the VIM OFF badge or enable
                                    them under Configuration.
                                </td>
                            </tr>
                        )}
                        <tr>
                            <td>
                                <kbd>Ctrl</kbd>+<kbd>s</kbd>
                            </td>
                            <td>Write finding details / comments</td>
                        </tr>
                        <tr>
                            <td>
                                <kbd>/</kbd>
                            </td>
                            <td>Filter</td>
                        </tr>
                        <tr>
                            <td>
                                <kbd>?</kbd>
                            </td>
                            <td>This help</td>
                        </tr>
                    </tbody>
                </HelpTable>
                <p>
                    The red dot means finding details or comments are not written yet.
                    Status saves as soon as it changes.
                </p>
                <Button appearance="primary" onClick={onClose} label="Close" />
            </Panel>
        </Overlay>
    );
}

export function VimCommandBar({ onRun, onCancel }) {
    const [cmd, setCmd] = useState("");
    return (
        <CmdBar>
            <span>:</span>
            <input
                id="stig-vim-cmd-input"
                autoFocus
                value={cmd}
                autoComplete="off"
                spellCheck={false}
                aria-label="Vim command"
                onChange={(e) => setCmd(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === "Enter") {
                        e.preventDefault();
                        e.stopPropagation();
                        onRun(cmd);
                    } else if (e.key === "Escape") {
                        e.preventDefault();
                        e.stopPropagation();
                        onCancel();
                    }
                }}
            />
        </CmdBar>
    );
}
