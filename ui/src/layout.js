import styled, { css } from "styled-components";
import { variables, mixins } from "@splunk/themes";

export const Shell = styled.div.attrs({ className: "stig-themed-shell" })`
    ${mixins.reset("block")};
    box-sizing: border-box;
    position: relative;
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--stig-bg-page, ${variables.backgroundColorPage});
    color: var(--stig-fg, ${variables.contentColorDefault});
    font-family: ${variables.fontFamily};
`;

export const Header = styled.header.attrs({ className: "stig-themed-section" })`
    flex: 0 0 auto;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px 16px;
    padding: 16px 20px 12px;
    border-bottom: 1px solid var(--stig-border, ${variables.borderColor});
    background: var(--stig-bg-section, ${variables.backgroundColorSection});
`;

export const Brand = styled.div`
    min-width: 180px;
`;

export const BrandKicker = styled.div`
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--stig-fg-muted, ${variables.contentColorMuted});
    font-weight: 600;
`;

export const Toolbar = styled.div`
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 12px 16px;
    flex: 1;
`;

export const HeaderMeta = styled.div`
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--stig-fg-muted, ${variables.contentColorMuted});
    font-size: 12px;
`;

export const Body = styled.div`
    flex: 1;
    min-height: 0;
    display: flex;
    overflow: hidden;
`;

export const Pane = styled.div`
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
`;

export const ListPane = styled(Pane).attrs({ className: "stig-themed-section" })`
    width: 46%;
    min-width: 420px;
    max-width: 720px;
    border-right: 1px solid var(--stig-border, ${variables.borderColor});
    background: var(--stig-bg-section, ${variables.backgroundColorSection});
`;

export const DetailPane = styled(Pane).attrs({ className: "stig-themed-detail" })`
    flex: 1;
    overflow: auto;
    padding: 20px 24px 32px;
`;

export const PagePad = styled.div`
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 20px 24px 32px;
`;

export const PageIntro = styled.div`
    max-width: 960px;
    margin-bottom: 20px;
    font-size: 14px;
    line-height: 1.55;
    color: var(--stig-fg-muted, ${variables.contentColorMuted});

    p {
        margin: 0 0 10px;
    }
    ol {
        margin: 0;
        padding-left: 1.25rem;
    }
    li {
        margin-bottom: 6px;
    }
    code {
        font-size: 12px;
    }
`;

export const TwoColGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr));
    gap: 28px 36px;
    align-items: start;
    width: 100%;
    max-width: 1440px;
`;

export const SectionBlock = styled.section`
    min-width: 0;
`;

export const FormCard = styled.div`
    margin-top: 12px;
    padding: 16px 18px;
    border: 1px solid var(--stig-border, ${variables.borderColor});
    border-radius: 8px;
    background: var(--stig-bg-elevated, ${variables.backgroundColorSection});
    display: flex;
    flex-direction: column;
    gap: 14px;
`;

export const FormRow = styled.div`
    display: grid;
    grid-template-columns: ${(p) => p.$columns || "1fr"};
    gap: 12px 16px;
    align-items: end;

    @media (max-width: 640px) {
        grid-template-columns: 1fr;
    }
`;

export const FilterRow = styled.div`
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 6px 8px;
    padding: 6px 16px;
    border-bottom: 1px solid var(--stig-border, ${variables.borderColor});
`;

export const FindingList = styled.div`
    flex: 1;
    min-height: 0;
    overflow: auto;
    &:focus {
        outline: none;
    }
`;

export const FindingRow = styled.button`
    display: grid;
    grid-template-columns: ${(p) =>
        p.$showHostname
            ? "22px minmax(68px, 84px) minmax(60px, 72px) minmax(72px, 110px) minmax(0, 1fr)"
            : "22px minmax(68px, 84px) minmax(60px, 72px) minmax(0, 1fr)"};
    gap: 8px;
    align-items: center;
    width: 100%;
    text-align: left;
    border: 0;
    border-bottom: 1px solid ${variables.neutral200};
    background: transparent;
    padding: 10px 14px;
    cursor: pointer;
    color: inherit;
    font: inherit;
    & > * {
        min-width: 0;
    }
    &:hover {
        background: var(--stig-row-hover, ${variables.interactiveColorOverlayHover});
    }
    ${(p) =>
        p.$selected &&
        css`
            background: var(--stig-row-selected, ${variables.interactiveColorOverlayHover});
            box-shadow: inset 3px 0 0 var(--stig-accent, ${variables.accentColorDefault});
        `}
`;

export const FindingTitle = styled.span`
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
`;

export const MetaLine = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin: 8px 0 14px;
    color: var(--stig-fg-muted, ${variables.contentColorMuted});
    font-size: 12px;
`;

export const PreBlock = styled.pre`
    white-space: pre-wrap;
    word-break: break-word;
    margin: 0;
    padding: 12px 14px;
    border: 1px solid var(--stig-border, ${variables.borderColor});
    border-radius: 4px;
    background: var(--stig-bg-elevated, ${variables.backgroundColorPage});
    color: var(--stig-fg, inherit);
    font-size: 12px;
    line-height: 1.45;
    max-height: 180px;
    overflow: auto;
`;

export const FieldStack = styled.div`
    display: flex;
    flex-direction: column;
    gap: 14px;
`;

export const Actions = styled.div`
    display: flex;
    gap: 10px;
    align-items: center;
    margin-top: 8px;
    padding-top: 14px;
    border-top: 1px solid ${variables.borderColor};
`;

export const Empty = styled.div`
    padding: 48px 24px;
    text-align: center;
    color: ${variables.contentColorMuted};
`;

export const ProgressTrack = styled.div`
    display: block;
    box-sizing: border-box;
    height: 6px;
    border-radius: 99px;
    background: ${variables.neutral200};
    overflow: hidden;
    min-width: 120px;
    width: 100%;
`;

export const DropZone = styled.div`
    box-sizing: border-box;
    border: 2px dashed ${variables.borderColor};
    border-radius: 8px;
    background: ${variables.backgroundColorSection};
    padding: 36px 24px;
    text-align: center;
    color: ${variables.contentColorMuted};
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
    &:hover,
    &.is-over {
        border-color: ${variables.accentColorDefault};
        background: ${variables.interactiveColorOverlayHover};
        color: ${variables.contentColorDefault};
    }
    &.is-disabled {
        cursor: not-allowed;
        opacity: 0.65;
    }
`;

export const DropTitle = styled.div`
    font-size: 16px;
    font-weight: 600;
    color: ${variables.contentColorDefault};
    margin-bottom: 6px;
`;

export const DropHint = styled.div`
    font-size: 13px;
`;

function clampPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
        return 0;
    }
    return Math.min(100, Math.max(0, Math.round(n)));
}

/** Inline width: dashboard CSS can override styled width rules; tooltip uses title on track. */
export const ProgressFill = styled.div.attrs((props) => ({
    style: {
        width: clampPct(props.$pct) + "%",
    },
}))`
    display: block;
    box-sizing: border-box;
    height: 100%;
    min-width: 0;
    max-width: 100%;
    background: ${variables.accentColorDefault};
    background-color: var(--splunk-color-accent, #65a637);
    border-radius: inherit;
    transition: width 0.12s ease-out;
`;

export const VimBadge = styled.button`
    border: 1px solid ${variables.borderColor};
    background: ${variables.neutral200};
    color: inherit;
    padding: 4px 10px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    cursor: pointer;
    &.is-off {
        opacity: 0.7;
    }
    &.insert {
        background: #155724;
        color: #fff;
        border-color: #155724;
    }
    &.nav {
        background: #1e3a5f;
        color: #fff;
        border-color: #1e3a5f;
    }
`;

