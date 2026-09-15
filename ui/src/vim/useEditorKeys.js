import { useEffect } from "react";

const STATUS_KEYS = {
    1: "not_reviewed",
    2: "open",
    3: "not_a_finding",
    4: "not_applicable",
};

const QUICK = {
    o: "open",
    n: "not_reviewed",
    f: "not_a_finding",
    a: "not_applicable",
};

function isEditingField(el) {
    if (!el) {
        return false;
    }
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

export function useEditorKeys(ctxRef) {
    useEffect(() => {
        let pendingG = false;
        let gTimer = 0;

        const onKey = (e) => {
            const ctx = ctxRef.current;
            if (!ctx) {
                return;
            }
            if (ctx.helpOpen) {
                if (e.key === "Escape") {
                    e.preventDefault();
                    ctx.setHelpOpen(false);
                }
                return;
            }
            if (ctx.jump) {
                return;
            }
            if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
                e.preventDefault();
                ctx.setCmdOpen(false);
                ctx.onWrite();
                return;
            }
            if (ctx.cmdOpen) {
                return;
            }
            if (ctx.vimEnabled && (ctx.vimLayer === "insert" || ctx.vimLayer === "text")) {
                return;
            }
            if (isEditingField(document.activeElement) && !document.activeElement._stigVim) {
                if (e.key === "Escape") {
                    document.activeElement.blur();
                    ctx.enterNav();
                }
                return;
            }
            if (e.key === "?") {
                e.preventDefault();
                ctx.setHelpOpen(true);
                return;
            }
            if (e.key === "/") {
                e.preventDefault();
                ctx.focusSearch();
                return;
            }
            if (!ctx.vimEnabled) {
                return;
            }
            if (e.key === "i") {
                e.preventDefault();
                ctx.focusFinding("insert");
                return;
            }
            if (e.key === ":") {
                e.preventDefault();
                ctx.setCmdOpen(true);
                return;
            }
            if (pendingG) {
                pendingG = false;
                window.clearTimeout(gTimer);
                e.preventDefault();
                if (e.key === "g") {
                    ctx.selectRelative("first");
                } else if (e.key === "h") {
                    ctx.openJump("host");
                } else if (e.key === "c") {
                    ctx.openJump("collection");
                } else if (e.key === "r") {
                    ctx.openJump("rule");
                }
                return;
            }
            if (e.key === "}") {
                e.preventDefault();
                ctx.selectRelative(1);
                return;
            }
            if (e.key === "{") {
                e.preventDefault();
                ctx.selectRelative(-1);
                return;
            }
            if (e.key === "G") {
                e.preventDefault();
                ctx.selectRelative("last");
                return;
            }
            if (e.key === "g") {
                pendingG = true;
                gTimer = window.setTimeout(() => {
                    pendingG = false;
                }, 500);
                return;
            }
            if (STATUS_KEYS[e.key]) {
                e.preventDefault();
                ctx.onStatus(STATUS_KEYS[e.key]);
                return;
            }
            if (QUICK[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                ctx.onStatus(QUICK[e.key]);
            }
        };

        document.addEventListener("keydown", onKey);
        return () => {
            document.removeEventListener("keydown", onKey);
            window.clearTimeout(gTimer);
        };
    }, [ctxRef]);
}
