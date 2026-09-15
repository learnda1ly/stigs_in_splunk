import {
    vimCol,
    vimFirstNonBlank,
    vimLineBounds,
    vimLineEnd,
    vimLineStart,
    vimMoveVert,
    vimNextParagraph,
    vimNextWord,
    vimPrevParagraph,
    vimPrevWord,
    vimWordEnd,
} from "./motions";

const yank = { text: "", linewise: false };

const FIELD_IDS = ["stig-finding", "stig-comments"];

function peerFieldId(id, dir) {
    const idx = FIELD_IDS.indexOf(id);
    if (idx < 0) {
        return null;
    }
    const step = dir < 0 ? FIELD_IDS.length - 1 : 1;
    return FIELD_IDS[(idx + step) % FIELD_IDS.length];
}

const STYLE_PROPS = [
    "direction",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "fontStyle",
    "fontVariant",
    "fontWeight",
    "fontStretch",
    "fontSize",
    "fontFamily",
    "lineHeight",
    "letterSpacing",
    "textAlign",
    "textTransform",
    "textIndent",
    "whiteSpace",
    "wordBreak",
    "wordSpacing",
    "tabSize",
];

function measureCaretBox(mirror, textarea, pos) {
    const style = window.getComputedStyle(textarea);
    STYLE_PROPS.forEach((prop) => {
        mirror.style[prop] = style[prop];
    });
    mirror.style.boxSizing = "border-box";
    mirror.style.border = "0";
    mirror.style.height = "auto";
    mirror.style.minHeight = "0";
    mirror.style.maxHeight = "none";
    mirror.style.width = textarea.clientWidth + "px";
    const value = textarea.value;
    const ch = value.charAt(pos);
    mirror.textContent = "";
    mirror.appendChild(document.createTextNode(value.substring(0, pos)));
    const marker = document.createElement("span");
    marker.textContent = ch && ch !== "\n" && !/\s/.test(ch) ? ch : "\u00a0";
    mirror.appendChild(marker);
    return {
        top: marker.offsetTop,
        left: marker.offsetLeft,
        height: marker.offsetHeight || parseFloat(style.lineHeight) || 16,
        width: marker.offsetWidth || Math.max(10, Math.round(parseFloat(style.fontSize) * 0.7)),
        ch,
    };
}

function emitInput(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
}

export function attachVimField(el, hooks) {
    if (!el) {
        return null;
    }
    const state = {
        mode: "insert",
        count: 0,
        pendingOp: "",
        pendingG: false,
        pendingReplace: false,
        preferredCol: 0,
        undo: [],
    };
    let wrap = el.parentNode;
    if (!wrap || !wrap.classList.contains("stig-vim-wrap")) {
        wrap = document.createElement("div");
        wrap.className = "stig-vim-wrap";
        el.parentNode.insertBefore(wrap, el);
        wrap.appendChild(el);
    }
    let measure = wrap.querySelector(".stig-vim-measure");
    if (!measure) {
        measure = document.createElement("div");
        measure.className = "stig-vim-measure";
        measure.setAttribute("aria-hidden", "true");
        wrap.insertBefore(measure, el);
    }
    let lineBar = wrap.querySelector(".stig-vim-line");
    if (!lineBar) {
        lineBar = document.createElement("div");
        lineBar.className = "stig-vim-line";
        lineBar.setAttribute("aria-hidden", "true");
        wrap.insertBefore(lineBar, el);
    }
    let cursor = wrap.querySelector(".stig-vim-cursor");
    if (!cursor) {
        cursor = document.createElement("div");
        cursor.className = "stig-vim-cursor";
        cursor.setAttribute("aria-hidden", "true");
        wrap.insertBefore(cursor, el);
    }

    const enabled = () => hooks.isEnabled();
    const text = () => el.value;
    const caret = () => (el.selectionStart == null ? 0 : el.selectionStart);

    function hideCursor() {
        cursor.classList.remove("is-visible", "on-whitespace");
        lineBar.classList.remove("is-visible");
    }

    function paint(pos) {
        let value = text();
        pos = Math.max(0, Math.min(pos, value.length));
        state.preferredCol = vimCol(value, pos);
        if (!enabled() || state.mode !== "normal") {
            el.setSelectionRange(pos, pos);
            hideCursor();
            return;
        }
        const bounds = vimLineBounds(value, pos);
        let ch = value.charAt(pos);
        let atLineEnd = !ch || ch === "\n" || pos >= bounds.end;
        if (atLineEnd && bounds.end > bounds.start) {
            pos = bounds.end - 1;
            ch = value.charAt(pos);
        }
        el.setSelectionRange(pos, pos);
        let onWhitespace = !ch || ch === "\n" || /\s/.test(ch);
        const style = window.getComputedStyle(el);
        const cell = Math.max(10, Math.round(parseFloat(style.fontSize) * 0.7) || 10);
        const borderTop = parseFloat(style.borderTopWidth || "0");
        const borderLeft = parseFloat(style.borderLeftWidth || "0");
        const padLeft = parseFloat(style.paddingLeft || "0");
        const padRight = parseFloat(style.paddingRight || "0");
        const startBox = measureCaretBox(measure, el, bounds.start);
        let box;
        if (bounds.start === bounds.end) {
            box = startBox;
            box.width = cell;
        } else if (atLineEnd) {
            box = measureCaretBox(measure, el, bounds.end - 1);
            box.left += box.width;
            box.width = cell;
            onWhitespace = true;
        } else {
            box = measureCaretBox(measure, el, pos);
        }
        const endBox =
            bounds.end > bounds.start
                ? measureCaretBox(measure, el, bounds.end - 1)
                : startBox;
        const lineTop = Math.min(startBox.top, box.top, endBox.top);
        const lineBottom = Math.max(
            startBox.top + startBox.height,
            box.top + box.height,
            endBox.top + endBox.height
        );
        let top = box.top - el.scrollTop + borderTop;
        let left = box.left - el.scrollLeft + borderLeft;
        const height = Math.max(box.height, parseFloat(style.lineHeight) || cell);
        const width = Math.max(box.width, cell);
        const maxLeft = el.clientWidth - padRight - width + borderLeft;
        if (left > maxLeft) {
            left = Math.max(padLeft + borderLeft, maxLeft);
        }
        if (left < borderLeft) {
            left = borderLeft + padLeft;
        }
        const barTop = lineTop - el.scrollTop + borderTop;
        const barHeight = Math.max(lineBottom - lineTop, height);
        if (barTop + barHeight > 0 && barTop < el.offsetHeight) {
            lineBar.style.top = barTop + "px";
            lineBar.style.left = borderLeft + "px";
            lineBar.style.width = el.clientWidth + "px";
            lineBar.style.height = barHeight + "px";
            lineBar.classList.add("is-visible");
        } else {
            lineBar.classList.remove("is-visible");
        }
        if (top + height <= 0 || top >= el.offsetHeight) {
            cursor.classList.remove("is-visible", "on-whitespace");
            return;
        }
        cursor.style.top = top + "px";
        cursor.style.left = left + "px";
        cursor.style.height = height + "px";
        cursor.style.width = width + "px";
        cursor.textContent = "";
        cursor.classList.add("is-visible");
        cursor.classList.toggle("on-whitespace", onWhitespace);
    }

    function setMode(mode, pos) {
        state.mode = mode;
        state.count = 0;
        state.pendingOp = "";
        state.pendingG = false;
        state.pendingReplace = false;
        el.classList.toggle("stig-vim-normal", enabled() && mode === "normal");
        if (pos == null) {
            pos = caret();
        }
        paint(pos);
        if (document.activeElement === el) {
            hooks.onMode(mode);
        }
    }

    function snapshot() {
        state.undo.push({ text: text(), pos: caret() });
        if (state.undo.length > 80) {
            state.undo.shift();
        }
    }

    function apply(next, pos, yankText, linewise) {
        snapshot();
        if (yankText != null) {
            yank.text = yankText;
            yank.linewise = !!linewise;
        }
        if (next !== text()) {
            el.value = next;
            emitInput(el);
        }
        paint(pos);
    }

    function takeCount() {
        const n = state.count;
        state.count = 0;
        return n;
    }

    function deleteRange(from, to, linewise) {
        const value = text();
        from = Math.max(0, Math.min(from, value.length));
        to = Math.max(from, Math.min(to, value.length));
        apply(value.slice(0, from) + value.slice(to), from, value.slice(from, to), linewise);
        return from;
    }

    function motion(key, count) {
        const value = text();
        let pos = caret();
        let i;
        let next;
        count = count || 1;
        if (key === "h" || key === "ArrowLeft" || key === "Backspace") {
            return Math.max(0, pos - count);
        }
        if (key === "l" || key === "ArrowRight" || key === " ") {
            return Math.min(value.length, pos + count);
        }
        if (key === "j" || key === "ArrowDown") {
            next = vimMoveVert(value, pos, count, state.preferredCol);
            state.preferredCol = next.col;
            return next.pos;
        }
        if (key === "k" || key === "ArrowUp") {
            next = vimMoveVert(value, pos, -count, state.preferredCol);
            state.preferredCol = next.col;
            return next.pos;
        }
        if (key === "0") {
            return vimLineStart(value, pos);
        }
        if (key === "^") {
            return vimFirstNonBlank(value, pos);
        }
        if (key === "$") {
            return vimLineEnd(value, pos);
        }
        if (key === "w") {
            for (i = 0; i < count; i++) {
                pos = vimNextWord(value, pos);
            }
            return pos;
        }
        if (key === "b") {
            for (i = 0; i < count; i++) {
                pos = vimPrevWord(value, pos);
            }
            return pos;
        }
        if (key === "e") {
            for (i = 0; i < count; i++) {
                pos = vimWordEnd(value, pos);
            }
            return pos;
        }
        if (key === "}") {
            for (i = 0; i < count; i++) {
                pos = vimNextParagraph(value, pos);
            }
            return pos;
        }
        if (key === "{") {
            for (i = 0; i < count; i++) {
                pos = vimPrevParagraph(value, pos);
            }
            return pos;
        }
        if (key === "G") {
            return value.length;
        }
        if (key === "gg") {
            return 0;
        }
        if (key === "Enter") {
            next = vimMoveVert(value, pos, count, 0);
            return vimFirstNonBlank(value, next.pos);
        }
        return null;
    }

    function lineRange(pos, count) {
        const value = text();
        const from = vimLineStart(value, pos);
        let endPos = pos;
        let i;
        for (i = 1; i < count; i++) {
            const end = vimLineEnd(value, endPos);
            if (end >= value.length) {
                break;
            }
            endPos = end + 1;
        }
        let to = vimLineEnd(value, endPos);
        if (to < value.length) {
            to += 1;
        }
        return { from, to };
    }

    function runOp(op, from, to, linewise) {
        const value = text();
        from = Math.max(0, Math.min(from, to, value.length));
        to = Math.max(from, Math.min(to, value.length));
        if (from === to && !linewise) {
            return;
        }
        const chunk = value.slice(from, to);
        if (op === "y") {
            yank.text = chunk;
            yank.linewise = !!linewise;
            paint(from);
            return;
        }
        apply(value.slice(0, from) + value.slice(to), from, chunk, linewise);
        if (op === "c") {
            setMode("insert", from);
        }
    }

    function handleNormal(e) {
        const key = e.key;
        const value = text();
        const pos = caret();
        let count;
        let dest;
        let range;

        if (state.pendingReplace) {
            state.pendingReplace = false;
            if (key === "Escape") {
                return;
            }
            if (key.length === 1) {
                const end = pos < value.length ? pos + 1 : pos;
                apply(value.slice(0, pos) + key + value.slice(end), pos);
            }
            return;
        }
        if (key >= "1" && key <= "9" && !state.pendingG) {
            state.count = (state.count || 0) * 10 + parseInt(key, 10);
            return;
        }
        if (key === "0" && state.count) {
            state.count = state.count * 10;
            return;
        }
        if (state.pendingG) {
            state.pendingG = false;
            if (key === "g") {
                dest = motion("gg", 1);
                if (state.pendingOp) {
                    runOp(state.pendingOp, Math.min(pos, dest), Math.max(pos, dest), false);
                    state.pendingOp = "";
                } else {
                    paint(dest);
                }
                state.count = 0;
            } else if (key === "t" || key === "T") {
                switchPeer(key === "T" ? -1 : 1);
                state.count = 0;
            }
            return;
        }
        if (key === "g") {
            state.pendingG = true;
            return;
        }
        if (key === "d" || key === "c" || key === "y") {
            if (state.pendingOp === key) {
                count = takeCount() || 1;
                range = lineRange(pos, count);
                runOp(key, range.from, range.to, true);
                state.pendingOp = "";
                return;
            }
            if (!state.pendingOp) {
                state.pendingOp = key;
                return;
            }
        }
        if (state.pendingOp) {
            dest = motion(key, takeCount());
            if (dest == null) {
                state.pendingOp = "";
                return;
            }
            runOp(
                state.pendingOp,
                Math.min(pos, dest),
                Math.max(pos, dest) + (key === "e" ? 1 : 0),
                false
            );
            state.pendingOp = "";
            return;
        }
        if (key === "Escape") {
            hooks.onLeave();
            return;
        }
        if (key === ":") {
            hooks.onCommand();
            return;
        }
        if (key === "i") {
            setMode("insert", pos);
            return;
        }
        if (key === "a") {
            setMode(
                "insert",
                Math.min(value.length, pos + (pos < vimLineEnd(value, pos) ? 1 : 0))
            );
            return;
        }
        if (key === "I") {
            setMode("insert", vimFirstNonBlank(value, pos));
            return;
        }
        if (key === "A") {
            setMode("insert", vimLineEnd(value, pos));
            return;
        }
        if (key === "o") {
            snapshot();
            const after = vimLineEnd(value, pos);
            el.value = value.slice(0, after) + "\n" + value.slice(after);
            emitInput(el);
            setMode("insert", after + 1);
            return;
        }
        if (key === "O") {
            snapshot();
            const before = vimLineStart(value, pos);
            el.value = value.slice(0, before) + "\n" + value.slice(before);
            emitInput(el);
            setMode("insert", before);
            return;
        }
        if (key === "x" || key === "s") {
            count = takeCount() || 1;
            deleteRange(pos, Math.min(value.length, pos + count), false);
            if (key === "s") {
                setMode("insert", pos);
            }
            return;
        }
        if (key === "X") {
            count = takeCount() || 1;
            deleteRange(Math.max(0, pos - count), pos, false);
            return;
        }
        if (key === "D") {
            deleteRange(pos, vimLineEnd(value, pos), false);
            return;
        }
        if (key === "C") {
            deleteRange(pos, vimLineEnd(value, pos), false);
            setMode("insert", pos);
            return;
        }
        if (key === "S") {
            range = lineRange(pos, takeCount());
            runOp(
                "c",
                range.from,
                range.to > range.from && text().charAt(range.to - 1) === "\n"
                    ? range.to - 1
                    : range.to,
                true
            );
            return;
        }
        if (key === "r") {
            state.pendingReplace = true;
            return;
        }
        if (key === "p" || key === "P") {
            if (!yank.text) {
                return;
            }
            snapshot();
            let chunk = yank.text;
            let at;
            if (yank.linewise) {
                if (key === "p") {
                    at = vimLineEnd(value, pos);
                    if (at < value.length) {
                        chunk = chunk.charAt(0) === "\n" ? chunk : "\n" + chunk.replace(/\n$/, "");
                        el.value = value.slice(0, at) + chunk + value.slice(at);
                        emitInput(el);
                        paint(at + 1);
                    } else {
                        el.value =
                            value +
                            (value && value.slice(-1) !== "\n" ? "\n" : "") +
                            chunk.replace(/\n$/, "");
                        emitInput(el);
                        paint(vimLineStart(el.value, el.value.length));
                    }
                } else {
                    at = vimLineStart(value, pos);
                    if (chunk.slice(-1) !== "\n") {
                        chunk += "\n";
                    }
                    el.value = value.slice(0, at) + chunk + value.slice(at);
                    emitInput(el);
                    paint(at);
                }
            } else {
                at = key === "p" ? Math.min(value.length, pos + 1) : pos;
                el.value = value.slice(0, at) + chunk + value.slice(at);
                emitInput(el);
                paint(at + chunk.length - (chunk.length ? 1 : 0));
            }
            return;
        }
        if (key === "u") {
            const prev = state.undo.pop();
            if (prev) {
                el.value = prev.text;
                emitInput(el);
                paint(prev.pos);
            }
            return;
        }
        dest = motion(key, takeCount());
        if (dest != null) {
            paint(dest);
        }
    }

    function switchPeer(dir) {
        if (!hooks.onSwitchField) {
            return false;
        }
        const next = peerFieldId(el.id, dir);
        if (!next) {
            return false;
        }
        hooks.onSwitchField(next, state.mode);
        return true;
    }

    let blurTimer = 0;

    function onKeydown(e) {
        if (!enabled() || e.ctrlKey || e.metaKey || e.altKey) {
            return;
        }
        if (e.key === "Tab") {
            e.preventDefault();
            e.stopPropagation();
            switchPeer(e.shiftKey ? -1 : 1);
            return;
        }
        if (state.mode === "insert") {
            if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                setMode("normal", caret());
            }
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        handleNormal(e);
    }

    function onFocus() {
        if (!enabled()) {
            hooks.onMode("insert");
            return;
        }
        setMode(state.mode === "normal" ? "normal" : "insert", caret());
    }

    function onBlur() {
        hideCursor();
        window.clearTimeout(blurTimer);
        blurTimer = window.setTimeout(() => {
            const next = document.activeElement;
            if (next && (next.id === "stig-vim-cmd-input" || next._stigVim)) {
                return;
            }
            hooks.onLeave();
        }, 0);
    }

    function onMouseup() {
        if (enabled() && state.mode === "normal") {
            paint(caret());
        }
    }

    function onScroll() {
        if (enabled() && state.mode === "normal") {
            paint(caret());
        }
    }

    el.addEventListener("keydown", onKeydown, true);
    el.addEventListener("focus", onFocus);
    el.addEventListener("blur", onBlur);
    el.addEventListener("mouseup", onMouseup);
    el.addEventListener("scroll", onScroll);

    el._stigVim = {
        setMode,
        mode: () => state.mode,
        syncEnabled: () => {
            if (!enabled()) {
                setMode("insert", caret());
                el.classList.remove("stig-vim-normal");
                hideCursor();
                return;
            }
            setMode(state.mode, caret());
        },
        destroy: () => {
            window.clearTimeout(blurTimer);
            el.removeEventListener("keydown", onKeydown, true);
            el.removeEventListener("focus", onFocus);
            el.removeEventListener("blur", onBlur);
            el.removeEventListener("mouseup", onMouseup);
            el.removeEventListener("scroll", onScroll);
            delete el._stigVim;
        },
    };
    return el._stigVim;
}
