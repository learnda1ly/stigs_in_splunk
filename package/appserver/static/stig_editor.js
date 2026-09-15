require([
    "jquery",
    "splunkjs/mvc",
    "splunkjs/ready!",
], function ($, mvc) {
    "use strict";

    var STATUS_LABELS = {
        not_reviewed: "Not Reviewed",
        open: "Open",
        not_a_finding: "Not a Finding",
        not_applicable: "Not Applicable",
    };

    var STATUS_KEYS = {
        "1": "not_reviewed",
        "2": "open",
        "3": "not_a_finding",
        "4": "not_applicable",
    };

    var service = mvc.createService({ owner: "nobody", app: "stigs_in_splunk" });

    function apiGet(path, query) {
        return new Promise(function (resolve, reject) {
            service.get(path, query || {}, function (err, res) {
                if (err) {
                    reject(err);
                    return;
                }
                resolve(parseBody(res));
            });
        });
    }

    function formatErr(err) {
        if (err == null) {
            return "unknown error";
        }
        if (typeof err === "string") {
            return err;
        }
        if (err.message) {
            return err.message;
        }
        if (err.error) {
            return String(err.error);
        }
        var data = err.data;
        if (data && data.messages && data.messages.length) {
            return data.messages
                .map(function (m) {
                    return m.text || m.message || "";
                })
                .filter(Boolean)
                .join("; ");
        }
        if (data && data.error) {
            return String(data.error);
        }
        if (typeof data === "string" && data) {
            return data;
        }
        if (err.status) {
            return "HTTP " + err.status;
        }
        try {
            return JSON.stringify(err);
        } catch (e) {
            return String(err);
        }
    }

    function csrfToken() {
        var token = "";
        document.cookie.split(";").forEach(function (part) {
            var cookie = part.trim();
            if (cookie.indexOf("splunkweb_csrf_token_") === 0) {
                token = decodeURIComponent(cookie.substring(cookie.indexOf("=") + 1));
            }
        });
        return token;
    }

    function apiPatch(path, body) {
        var url =
            "/en-US/splunkd/__raw/servicesNS/nobody/stigs_in_splunk/" +
            String(path).replace(/^\//, "");
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-Splunk-Form-Key": csrfToken(),
            },
            body: JSON.stringify(body),
        }).then(function (res) {
            return res.text().then(function (text) {
                var parsed = text;
                if (text && (text.charAt(0) === "{" || text.charAt(0) === "[")) {
                    try {
                        parsed = JSON.parse(text);
                    } catch (e) {
                        parsed = text;
                    }
                }
                if (!res.ok) {
                    throw new Error(formatErr(parsed) || "HTTP " + res.status);
                }
                return unwrapPayload(parsed);
            });
        });
    }

    function unwrapPayload(data) {
        if (data == null) {
            return data;
        }
        if (typeof data === "string") {
            var trimmed = data.trim();
            if (!trimmed) {
                return data;
            }
            if (trimmed.charAt(0) === "{" || trimmed.charAt(0) === "[") {
                try {
                    data = JSON.parse(trimmed);
                } catch (e) {
                    return data;
                }
            } else {
                return data;
            }
        }
        if (data && typeof data === "object" && data.entry && data.messages) {
            var entries = data.entry || [];
            if (entries.length === 1 && entries[0].content) {
                var content = entries[0].content;
                if (content && content.payload !== undefined) {
                    return unwrapPayload(content.payload);
                }
                return content;
            }
            return entries.map(function (entry) {
                return entry.content || entry;
            });
        }
        if (
            data &&
            typeof data === "object" &&
            !Array.isArray(data) &&
            data.payload !== undefined &&
            Object.keys(data).length === 1
        ) {
            return unwrapPayload(data.payload);
        }
        return data;
    }

    function parseBody(res) {
        if (!res) {
            return null;
        }
        if (res.data !== undefined && res.data !== null) {
            return unwrapPayload(res.data);
        }
        if (typeof res === "string") {
            return unwrapPayload(res);
        }
        return unwrapPayload(res);
    }

    function toast(msg, isError) {
        var el = $("#stig-toast");
        if (!el.length) {
            el = $('<div id="stig-toast" class="stig-toast"></div>').appendTo("body");
        }
        el.text(msg).toggleClass("error", !!isError).addClass("show");
        setTimeout(function () {
            el.removeClass("show");
        }, 2800);
    }

    function showSaveModal(title, detail) {
        $("#stig-save-modal").remove();
        var el = $(
            '<div class="stig-save-toast" id="stig-save-modal" role="status">' +
                "<strong>" +
                escapeHtml(title) +
                "</strong>" +
                (detail
                    ? "<span>" + escapeHtml(detail) + "</span>"
                    : "") +
                "</div>"
        );
        $("body").append(el);
        requestAnimationFrame(function () {
            el.addClass("show");
        });
        setTimeout(function () {
            el.removeClass("show");
            setTimeout(function () {
                $("#stig-save-modal").remove();
            }, 180);
        }, 1600);
    }

    var vimYank = { text: "", linewise: false };

    function vimLineBounds(text, pos) {
        pos = Math.max(0, Math.min(pos, text.length));
        var start = pos === 0 ? 0 : text.lastIndexOf("\n", pos - 1) + 1;
        var nl = text.indexOf("\n", pos);
        return { start: start, end: nl < 0 ? text.length : nl };
    }

    function vimLineStart(text, pos) {
        return vimLineBounds(text, pos).start;
    }

    function vimLineEnd(text, pos) {
        return vimLineBounds(text, pos).end;
    }

    function vimCol(text, pos) {
        return pos - vimLineStart(text, pos);
    }

    function vimIsBlankLine(text, pos) {
        var b = vimLineBounds(text, pos);
        return !/\S/.test(text.slice(b.start, b.end));
    }

    function vimFirstNonBlank(text, pos) {
        var b = vimLineBounds(text, pos);
        var i = b.start;
        while (i < b.end && /[ \t]/.test(text.charAt(i))) {
            i++;
        }
        return i;
    }

    function vimMoveVert(text, pos, delta, wantCol) {
        var col = wantCol == null ? vimCol(text, pos) : wantCol;
        var i = pos;
        var step;
        if (delta > 0) {
            for (step = 0; step < delta; step++) {
                var end = vimLineEnd(text, i);
                if (end >= text.length) {
                    break;
                }
                i = end + 1;
            }
        } else if (delta < 0) {
            for (step = 0; step < -delta; step++) {
                var start = vimLineStart(text, i);
                if (start <= 0) {
                    i = 0;
                    break;
                }
                i = vimLineStart(text, start - 1);
            }
        }
        var b = vimLineBounds(text, i);
        return { pos: Math.min(b.start + col, b.end), col: col };
    }

    function vimIsWord(ch) {
        return !!ch && /[A-Za-z0-9_]/.test(ch);
    }

    function vimIsSpace(ch) {
        return !!ch && /\s/.test(ch);
    }

    function vimNextWord(text, pos) {
        var n = text.length;
        if (pos >= n) {
            return n;
        }
        var ch = text.charAt(pos);
        if (vimIsWord(ch)) {
            while (pos < n && vimIsWord(text.charAt(pos))) {
                pos++;
            }
        } else if (!vimIsSpace(ch)) {
            while (pos < n && !vimIsWord(text.charAt(pos)) && !vimIsSpace(text.charAt(pos))) {
                pos++;
            }
        }
        while (pos < n && vimIsSpace(text.charAt(pos))) {
            pos++;
        }
        return pos;
    }

    function vimPrevWord(text, pos) {
        if (pos <= 0) {
            return 0;
        }
        pos -= 1;
        while (pos > 0 && vimIsSpace(text.charAt(pos))) {
            pos--;
        }
        if (vimIsWord(text.charAt(pos))) {
            while (pos > 0 && vimIsWord(text.charAt(pos - 1))) {
                pos--;
            }
        } else {
            while (pos > 0 && !vimIsWord(text.charAt(pos - 1)) && !vimIsSpace(text.charAt(pos - 1))) {
                pos--;
            }
        }
        return pos;
    }

    function vimWordEnd(text, pos) {
        var n = text.length;
        if (n === 0) {
            return 0;
        }
        var i = pos + 1;
        if (i >= n) {
            return n - 1;
        }
        while (i < n && vimIsSpace(text.charAt(i))) {
            i++;
        }
        if (i >= n) {
            return n - 1;
        }
        if (vimIsWord(text.charAt(i))) {
            while (i + 1 < n && vimIsWord(text.charAt(i + 1))) {
                i++;
            }
        } else {
            while (i + 1 < n && !vimIsWord(text.charAt(i + 1)) && !vimIsSpace(text.charAt(i + 1))) {
                i++;
            }
        }
        return i;
    }

    function vimNextParagraph(text, pos) {
        var n = text.length;
        if (pos >= n) {
            return n;
        }
        var i = pos;
        if (vimIsBlankLine(text, i)) {
            while (i < n && vimIsBlankLine(text, i)) {
                var blankEnd = vimLineEnd(text, i);
                if (blankEnd >= n) {
                    return n;
                }
                i = blankEnd + 1;
            }
        }
        while (i < n && !vimIsBlankLine(text, i)) {
            var paraEnd = vimLineEnd(text, i);
            if (paraEnd >= n) {
                return n;
            }
            i = paraEnd + 1;
        }
        return Math.min(i, n);
    }

    function vimPrevParagraph(text, pos) {
        if (pos <= 0) {
            return 0;
        }
        var i = vimLineStart(text, pos);
        var start;
        if (i > 0) {
            i = vimLineStart(text, i - 1);
        }
        if (!vimIsBlankLine(text, pos)) {
            while (i > 0 && !vimIsBlankLine(text, i)) {
                start = vimLineStart(text, i);
                if (start === 0) {
                    return 0;
                }
                i = vimLineStart(text, start - 1);
            }
            return i;
        }
        while (i > 0 && vimIsBlankLine(text, i)) {
            start = vimLineStart(text, i);
            if (start === 0) {
                return 0;
            }
            i = vimLineStart(text, start - 1);
        }
        while (i > 0 && !vimIsBlankLine(text, i)) {
            start = vimLineStart(text, i);
            if (start === 0) {
                return 0;
            }
            i = vimLineStart(text, start - 1);
        }
        return i;
    }

    function measureCaretBox(mirror, textarea, pos) {
        var style = window.getComputedStyle(textarea);
        var props = [
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
        var i;
        for (i = 0; i < props.length; i++) {
            mirror.style[props[i]] = style[props[i]];
        }
        mirror.style.boxSizing = "border-box";
        mirror.style.border = "0";
        mirror.style.height = "auto";
        mirror.style.minHeight = "0";
        mirror.style.maxHeight = "none";
        mirror.style.width = textarea.clientWidth + "px";
        var value = textarea.value;
        var ch = value.charAt(pos);
        mirror.textContent = "";
        mirror.appendChild(document.createTextNode(value.substring(0, pos)));
        var marker = document.createElement("span");
        marker.textContent = ch && ch !== "\n" && !/\s/.test(ch) ? ch : "\u00a0";
        mirror.appendChild(marker);
        return {
            top: marker.offsetTop,
            left: marker.offsetLeft,
            height: marker.offsetHeight || parseFloat(style.lineHeight) || 16,
            width: marker.offsetWidth || Math.max(10, Math.round(parseFloat(style.fontSize) * 0.7)),
            ch: ch,
        };
    }

    var VIM_FIELD_IDS = ["stig-finding", "stig-comments"];

    function vimPeerFieldId(id, dir) {
        var idx = VIM_FIELD_IDS.indexOf(id);
        if (idx < 0) {
            return null;
        }
        var step = dir < 0 ? VIM_FIELD_IDS.length - 1 : 1;
        return VIM_FIELD_IDS[(idx + step) % VIM_FIELD_IDS.length];
    }

    function attachVimField(el, hooks) {
        if (!el) {
            return null;
        }
        var state = {
            mode: "insert",
            count: 0,
            pendingOp: "",
            pendingG: false,
            pendingReplace: false,
            preferredCol: 0,
            undo: [],
        };
        var wrap = el.parentNode;
        if (!wrap || !wrap.classList.contains("stig-vim-wrap")) {
            wrap = document.createElement("div");
            wrap.className = "stig-vim-wrap";
            el.parentNode.insertBefore(wrap, el);
            wrap.appendChild(el);
        }
        var measure = wrap.querySelector(".stig-vim-measure");
        if (!measure) {
            measure = document.createElement("div");
            measure.className = "stig-vim-measure";
            measure.setAttribute("aria-hidden", "true");
            wrap.insertBefore(measure, el);
        }
        var lineBar = wrap.querySelector(".stig-vim-line");
        if (!lineBar) {
            lineBar = document.createElement("div");
            lineBar.className = "stig-vim-line";
            lineBar.setAttribute("aria-hidden", "true");
            wrap.insertBefore(lineBar, el);
        }
        var cursor = wrap.querySelector(".stig-vim-cursor");
        if (!cursor) {
            cursor = document.createElement("div");
            cursor.className = "stig-vim-cursor";
            cursor.setAttribute("aria-hidden", "true");
            wrap.insertBefore(cursor, el);
        }

        function enabled() {
            return hooks.isEnabled();
        }

        function text() {
            return el.value;
        }

        function caret() {
            return el.selectionStart == null ? 0 : el.selectionStart;
        }

        function hideCursor() {
            cursor.classList.remove("is-visible", "on-whitespace");
            lineBar.classList.remove("is-visible");
        }

        function paint(pos) {
            var value = text();
            pos = Math.max(0, Math.min(pos, value.length));
            state.preferredCol = vimCol(value, pos);
            if (!enabled() || state.mode !== "normal") {
                el.setSelectionRange(pos, pos);
                hideCursor();
                return;
            }
            var bounds = vimLineBounds(value, pos);
            var ch = value.charAt(pos);
            var atLineEnd = !ch || ch === "\n" || pos >= bounds.end;
            if (atLineEnd && bounds.end > bounds.start) {
                pos = bounds.end - 1;
                ch = value.charAt(pos);
            }
            el.setSelectionRange(pos, pos);
            var onWhitespace = !ch || ch === "\n" || /\s/.test(ch);
            var style = window.getComputedStyle(el);
            var cell = Math.max(10, Math.round(parseFloat(style.fontSize) * 0.7) || 10);
            var borderTop = parseFloat(style.borderTopWidth || "0");
            var borderLeft = parseFloat(style.borderLeftWidth || "0");
            var padLeft = parseFloat(style.paddingLeft || "0");
            var padRight = parseFloat(style.paddingRight || "0");
            var startBox = measureCaretBox(measure, el, bounds.start);
            var box;
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
            var endBox =
                bounds.end > bounds.start
                    ? measureCaretBox(measure, el, bounds.end - 1)
                    : startBox;
            var lineTop = Math.min(startBox.top, box.top, endBox.top);
            var lineBottom = Math.max(
                startBox.top + startBox.height,
                box.top + box.height,
                endBox.top + endBox.height
            );
            var top = box.top - el.scrollTop + borderTop;
            var left = box.left - el.scrollLeft + borderLeft;
            var height = Math.max(box.height, parseFloat(style.lineHeight) || cell);
            var width = Math.max(box.width, cell);
            var maxLeft = el.clientWidth - padRight - width + borderLeft;
            if (left > maxLeft) {
                left = Math.max(padLeft + borderLeft, maxLeft);
            }
            if (left < borderLeft) {
                left = borderLeft + padLeft;
            }
            var barTop = lineTop - el.scrollTop + borderTop;
            var barHeight = Math.max(lineBottom - lineTop, height);
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
                vimYank.text = yankText;
                vimYank.linewise = !!linewise;
            }
            if (next !== text()) {
                el.value = next;
                $(el).trigger("input");
            }
            paint(pos);
        }

        function takeCount() {
            var n = state.count;
            state.count = 0;
            return n;
        }

        function deleteRange(from, to, linewise) {
            var value = text();
            from = Math.max(0, Math.min(from, value.length));
            to = Math.max(from, Math.min(to, value.length));
            apply(value.slice(0, from) + value.slice(to), from, value.slice(from, to), linewise);
            return from;
        }

        function insertAt(pos, chunk, caretPos) {
            var value = text();
            apply(value.slice(0, pos) + chunk + value.slice(pos), caretPos, null, false);
        }

        function motion(key, count) {
            var value = text();
            var pos = caret();
            var i;
            var next;
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
                if (arguments[1]) {
                    var lines = value.split("\n");
                    var idx = Math.max(0, Math.min(lines.length - 1, arguments[1] - 1));
                    var offset = 0;
                    for (i = 0; i < idx; i++) {
                        offset += lines[i].length + 1;
                    }
                    return offset;
                }
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
            var value = text();
            var from = vimLineStart(value, pos);
            var endPos = pos;
            var i;
            for (i = 1; i < count; i++) {
                var end = vimLineEnd(value, endPos);
                if (end >= value.length) {
                    break;
                }
                endPos = end + 1;
            }
            var to = vimLineEnd(value, endPos);
            if (to < value.length) {
                to += 1;
            }
            return { from: from, to: to };
        }

        function runOp(op, from, to, linewise) {
            var value = text();
            from = Math.max(0, Math.min(from, to, value.length));
            to = Math.max(from, Math.min(to, value.length));
            if (from === to && !linewise) {
                return;
            }
            var chunk = value.slice(from, to);
            if (op === "y") {
                vimYank.text = chunk;
                vimYank.linewise = !!linewise;
                paint(from);
                return;
            }
            apply(value.slice(0, from) + value.slice(to), from, chunk, linewise);
            if (op === "c") {
                setMode("insert", from);
            }
        }

        function handleNormal(e) {
            var key = e.key;
            var value = text();
            var pos = caret();
            var count;
            var dest;
            var range;

            if (state.pendingReplace) {
                state.pendingReplace = false;
                if (key === "Escape") {
                    return true;
                }
                if (key.length === 1) {
                    var end = pos < value.length ? pos + 1 : pos;
                    apply(value.slice(0, pos) + key + value.slice(end), pos);
                }
                return true;
            }

            if (key >= "1" && key <= "9" && !state.pendingG) {
                state.count = (state.count || 0) * 10 + parseInt(key, 10);
                return true;
            }
            if (key === "0" && state.count) {
                state.count = state.count * 10;
                return true;
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
                    return true;
                }
                if (key === "t" || key === "T") {
                    switchPeer(key === "T" ? -1 : 1);
                    state.count = 0;
                    return true;
                }
            }

            if (key === "g") {
                state.pendingG = true;
                return true;
            }

            if (key === "d" || key === "c" || key === "y") {
                if (state.pendingOp === key) {
                    count = takeCount() || 1;
                    range = lineRange(pos, count);
                    runOp(key, range.from, range.to, true);
                    state.pendingOp = "";
                    return true;
                }
                if (!state.pendingOp) {
                    state.pendingOp = key;
                    return true;
                }
            }

            if (state.pendingOp) {
                count = takeCount();
                dest = motion(key, count);
                if (dest == null) {
                    state.pendingOp = "";
                    return true;
                }
                runOp(state.pendingOp, Math.min(pos, dest), Math.max(pos, dest) + (key === "e" ? 1 : 0), false);
                state.pendingOp = "";
                return true;
            }

            if (key === "Escape") {
                hooks.onLeave();
                return true;
            }
            if (key === ":") {
                hooks.onCommand();
                return true;
            }
            if (key === "i") {
                setMode("insert", pos);
                return true;
            }
            if (key === "a") {
                setMode("insert", Math.min(value.length, pos + (pos < vimLineEnd(value, pos) ? 1 : 0)));
                return true;
            }
            if (key === "I") {
                setMode("insert", vimFirstNonBlank(value, pos));
                return true;
            }
            if (key === "A") {
                setMode("insert", vimLineEnd(value, pos));
                return true;
            }
            if (key === "o") {
                snapshot();
                var after = vimLineEnd(value, pos);
                el.value = value.slice(0, after) + "\n" + value.slice(after);
                $(el).trigger("input");
                setMode("insert", after + 1);
                return true;
            }
            if (key === "O") {
                snapshot();
                var before = vimLineStart(value, pos);
                el.value = value.slice(0, before) + "\n" + value.slice(before);
                $(el).trigger("input");
                setMode("insert", before);
                return true;
            }
            if (key === "x" || key === "s") {
                count = takeCount() || 1;
                var to = Math.min(value.length, pos + count);
                deleteRange(pos, to, false);
                if (key === "s") {
                    setMode("insert", pos);
                }
                return true;
            }
            if (key === "X") {
                count = takeCount() || 1;
                deleteRange(Math.max(0, pos - count), pos, false);
                return true;
            }
            if (key === "D") {
                deleteRange(pos, vimLineEnd(value, pos), false);
                return true;
            }
            if (key === "C") {
                deleteRange(pos, vimLineEnd(value, pos), false);
                setMode("insert", pos);
                return true;
            }
            if (key === "S") {
                range = lineRange(pos, takeCount());
                runOp("c", range.from, range.to > range.from && text().charAt(range.to - 1) === "\n" ? range.to - 1 : range.to, true);
                return true;
            }
            if (key === "r") {
                state.pendingReplace = true;
                return true;
            }
            if (key === "p" || key === "P") {
                if (!vimYank.text) {
                    return true;
                }
                snapshot();
                var chunk = vimYank.text;
                var at;
                if (vimYank.linewise) {
                    if (key === "p") {
                        at = vimLineEnd(value, pos);
                        if (at < value.length) {
                            chunk = chunk.charAt(0) === "\n" ? chunk : "\n" + chunk.replace(/\n$/, "");
                            el.value = value.slice(0, at) + chunk + value.slice(at);
                            $(el).trigger("input");
                            paint(at + 1);
                        } else {
                            el.value =
                                value +
                                (value && value.slice(-1) !== "\n" ? "\n" : "") +
                                chunk.replace(/\n$/, "");
                            $(el).trigger("input");
                            paint(vimLineStart(el.value, el.value.length));
                        }
                    } else {
                        at = vimLineStart(value, pos);
                        if (chunk.slice(-1) !== "\n") {
                            chunk += "\n";
                        }
                        el.value = value.slice(0, at) + chunk + value.slice(at);
                        $(el).trigger("input");
                        paint(at);
                    }
                } else {
                    at = key === "p" ? Math.min(value.length, pos + 1) : pos;
                    el.value = value.slice(0, at) + chunk + value.slice(at);
                    $(el).trigger("input");
                    paint(at + chunk.length - (chunk.length ? 1 : 0));
                }
                return true;
            }
            if (key === "u") {
                var prev = state.undo.pop();
                if (prev) {
                    el.value = prev.text;
                    $(el).trigger("input");
                    paint(prev.pos);
                }
                return true;
            }

            count = takeCount();
            dest = motion(key, count);
            if (dest != null) {
                paint(dest);
                return true;
            }
            return true;
        }

        function switchPeer(dir) {
            if (!hooks.onSwitchField) {
                return false;
            }
            var next = vimPeerFieldId(el.id, dir);
            if (!next) {
                return false;
            }
            hooks.onSwitchField(next, state.mode);
            return true;
        }

        var blurTimer = 0;

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
            if (state.mode !== "insert") {
                setMode(state.mode, caret());
            } else {
                setMode("insert", caret());
            }
        }

        function onBlur() {
            hideCursor();
            window.clearTimeout(blurTimer);
            blurTimer = window.setTimeout(function () {
                var next = document.activeElement;
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

        el.addEventListener("keydown", onKeydown, true);
        $(el)
            .on("focus.stigVimField", onFocus)
            .on("blur.stigVimField", onBlur)
            .on("mouseup.stigVimField", onMouseup)
            .on("scroll.stigVimField", function () {
                if (enabled() && state.mode === "normal") {
                    paint(caret());
                }
            });

        el._stigVim = {
            setMode: setMode,
            syncEnabled: function () {
                if (!enabled()) {
                    setMode("insert", caret());
                    el.classList.remove("stig-vim-normal");
                    hideCursor();
                    hooks.onMode("normal");
                    return;
                }
                setMode(state.mode, caret());
            },
            mode: function () {
                return state.mode;
            },
        };
        return el._stigVim;
    }

    var VIM_STORAGE_KEY = "stigs_in_splunk.vim_mode";

    function parseBool(raw) {
        raw = String(raw == null ? "" : raw).trim().toLowerCase();
        return raw === "1" || raw === "true" || raw === "yes";
    }

    function extractVimEnabled(raw) {
        if (raw == null) {
            return null;
        }
        if (typeof raw === "boolean") {
            return raw;
        }
        if (typeof raw === "number") {
            return raw !== 0;
        }
        if (typeof raw === "string") {
            var text = raw.trim().toLowerCase();
            if (!text) {
                return null;
            }
            if (text === "1" || text === "true" || text === "yes") {
                return true;
            }
            if (text === "0" || text === "false" || text === "no") {
                return false;
            }
            return null;
        }
        if (typeof raw !== "object") {
            return null;
        }
        if (Object.prototype.hasOwnProperty.call(raw, "vim_mode")) {
            return extractVimEnabled(raw.vim_mode);
        }
        if (raw.value != null && typeof raw.value !== "object") {
            return extractVimEnabled(raw.value);
        }
        var entry = raw.entry && raw.entry[0];
        var content = entry && entry.content;
        if (content && typeof content === "object") {
            if (Object.prototype.hasOwnProperty.call(content, "vim_mode")) {
                return extractVimEnabled(content.vim_mode);
            }
            if (content.value != null && typeof content.value !== "object") {
                return extractVimEnabled(content.value);
            }
        } else if (content != null) {
            return extractVimEnabled(content);
        }
        return null;
    }

    function readLocalVim() {
        try {
            var stored = window.localStorage.getItem(VIM_STORAGE_KEY);
            if (stored == null) {
                return null;
            }
            return parseBool(stored);
        } catch (e) {
            return null;
        }
    }

    function writeLocalVim(enabled) {
        try {
            window.localStorage.setItem(VIM_STORAGE_KEY, enabled ? "true" : "false");
        } catch (e) {
            /* ignore quota / private-mode failures */
        }
    }

    function loadRemoteVimSetting() {
        return apiGet("stig_settings")
            .then(function (raw) {
                return extractVimEnabled(raw);
            })
            .catch(function () {
                return null;
            });
    }

    function persistVimSetting(enabled) {
        writeLocalVim(enabled);
        return apiPatch("stig_settings", { vim_mode: !!enabled });
    }

    function loadVimSetting() {
        var local = readLocalVim();
        if (local != null) {
            return Promise.resolve(local);
        }
        return loadRemoteVimSetting().then(function (remote) {
            return remote == null ? false : remote;
        });
    }

    function StigEditor() {
        this.root = document.getElementById("stig-editor-root");
        this.collections = [];
        this.checklists = [];
        this.hostsById = {};
        this.rulesByKey = {};
        this.items = [];
        this.filtered = [];
        this.selectedIndex = -1;
        this.statusFilter = null;
        this.validityFilter = null;
        this.searchQuery = "";
        this.vimMode = "normal";
        this.vimLayer = "nav";
        this.vimEnabled = false;
        this.pendingSave = false;
        this.viewMode = "all";
        this.currentCollectionId = "";
        this.currentHostId = "";
        this.currentRuleKey = "";
        var self = this;
        this.renderShell();
        this.bindKeys();
        this.fitLayout();
        $(window).on("resize.stigEditor", function () {
            self.fitLayout();
        });
        setTimeout(function () {
            self.fitLayout();
        }, 0);
        setTimeout(function () {
            self.fitLayout();
        }, 300);
        loadVimSetting().then(function (enabled) {
            self.setVimEnabled(enabled, { persist: false });
        });
        this.loadCollections();
    }

    StigEditor.prototype.fitLayout = function () {
        var root = this.root;
        if (!root) {
            return;
        }
        document.body.classList.add("stig-editor-page");
        var header = document.querySelector(".dashboard-header");
        if (header) {
            header.style.display = "none";
        }
        var top = root.getBoundingClientRect().top;
        var height = Math.max(240, window.innerHeight - top);
        root.style.height = height + "px";
        root.style.maxHeight = height + "px";
        root.style.minHeight = "0";
        root.style.overflow = "hidden";
        root.style.display = "flex";
        root.style.flexDirection = "column";
        var main = root.querySelector(".stig-main");
        if (main) {
            main.style.flex = "1 1 auto";
            main.style.minHeight = "0";
            main.style.height = "auto";
            main.style.overflow = "hidden";
        }
        var pane = root.querySelector(".stig-list-pane");
        if (pane) {
            pane.style.display = "flex";
            pane.style.flexDirection = "column";
            pane.style.minHeight = "0";
            pane.style.height = "100%";
            pane.style.overflow = "hidden";
        }
        var list = document.getElementById("stig-rule-list");
        if (list) {
            list.style.flex = "1 1 auto";
            list.style.minHeight = "0";
            list.style.height = "100%";
            list.style.overflowY = "auto";
            list.style.overflowX = "hidden";
        }
    };

    StigEditor.prototype.renderShell = function () {
        this.root.innerHTML =
            '<div class="stig-toolbar">' +
            '<div><label>Collection</label><select id="stig-collection"></select></div>' +
            '<div><label>Host</label><select id="stig-host" disabled></select></div>' +
            '<button type="button" class="stig-btn stig-btn-secondary" id="stig-jump-rule">Rule…</button>' +
            '<input type="search" class="stig-search" id="stig-search" placeholder="Filter (/) …" />' +
            '<div class="stig-status-filters" id="stig-filters"></div>' +
            '<div class="stig-status-filters" id="stig-validity-filters"></div>' +
            '<button type="button" class="stig-btn stig-btn-secondary" id="stig-validate">Validate</button>' +
            '<button type="button" class="stig-vim-mode is-off" id="stig-vim-mode" title="Toggle vim-style keys">VIM OFF</button>' +
            '<a class="stig-toolbar-meta" href="stig_settings">Configuration</a>' +
            '<span class="stig-toolbar-meta" id="stig-meta"></span>' +
            "</div>" +
            '<div class="stig-main">' +
            '<div class="stig-list-pane stig-view-all" id="stig-list-pane">' +
            '<div class="stig-list-header" id="stig-list-header"></div>' +
            '<ul class="stig-rule-list" id="stig-rule-list" tabindex="0"></ul>' +
            "</div>" +
            '<div class="stig-detail-pane" id="stig-detail"></div>' +
            "</div>";

        var self = this;
        this.renderListHeader();
        $("#stig-collection").on("change", function () {
            self.onCollectionChange(this.value);
        });
        $("#stig-host").on("change", function () {
            self.onHostChange(this.value);
        });
        $("#stig-jump-rule").on("click", function () {
            self.openJump("rule");
        });
        $("#stig-search").on("input", function () {
            self.searchQuery = this.value.trim().toLowerCase();
            self.applyFilter();
        });
        $("#stig-rule-list").on("click", "li", function () {
            var idx = parseInt(this.getAttribute("data-idx"), 10);
            self.selectIndex(idx);
        });

        var filters = $("#stig-filters");
        filters.append(
            '<button type="button" class="stig-filter-btn active" data-status="">All</button>'
        );
        Object.keys(STATUS_LABELS).forEach(function (st) {
            filters.append(
                '<button type="button" class="stig-filter-btn" data-status="' +
                    st +
                    '">' +
                    STATUS_LABELS[st] +
                    "</button>"
            );
        });
        filters.on("click", "button", function () {
            filters.find("button").removeClass("active");
            $(this).addClass("active");
            self.statusFilter = $(this).data("status") || null;
            self.applyFilter();
        });

        var validity = $("#stig-validity-filters");
        validity.append(
            '<button type="button" class="stig-filter-btn active" data-valid="">All</button>' +
                '<button type="button" class="stig-filter-btn" data-valid="complete">Completed</button>' +
                '<button type="button" class="stig-filter-btn" data-valid="incomplete">Incomplete</button>'
        );
        validity.on("click", "button", function () {
            validity.find("button").removeClass("active");
            $(this).addClass("active");
            self.validityFilter = $(this).data("valid") || null;
            self.applyFilter();
        });
        $("#stig-validate").on("click", function () {
            self.validateCurrent();
        });

        $("#stig-detail").html(
            '<div class="stig-detail-empty">Select a collection to edit reviews.</div>'
        );
        $("#stig-vim-mode").on("click", function () {
            self.setVimEnabled(!self.vimEnabled);
        });
    };

    StigEditor.prototype.setVimEnabled = function (enabled, opts) {
        opts = opts || {};
        this.vimEnabled = !!enabled;
        if (!this.vimEnabled) {
            this.vimMode = "normal";
            this.vimLayer = "nav";
            this.closeVimCommand();
        }
        this.refreshVimFields();
        writeLocalVim(this.vimEnabled);
        if (opts.persist !== false) {
            persistVimSetting(this.vimEnabled).catch(function () {
                /* localStorage already has the preference */
            });
        }
        this.updateVimBadge();
    };

    StigEditor.prototype.updateVimBadge = function () {
        var el = $("#stig-vim-mode");
        if (!this.vimEnabled) {
            el.addClass("is-off").removeClass("insert").text("VIM OFF");
            el.attr("title", "Vim keys are off. Click to enable.");
            return;
        }
        el.removeClass("is-off insert nav");
        if (this.vimLayer === "insert") {
            el.addClass("insert").text("INSERT");
            el.attr("title", "Typing in the field. Esc = field NORMAL. Click to disable vim.");
        } else if (this.vimLayer === "text") {
            el.text("NORMAL");
            el.attr("title", "Vim normal in this field. o opens a line. Esc = NAV. Click to disable vim.");
        } else {
            el.addClass("nav").text("NAV");
            el.attr("title", "Finding navigation. o sets Open. i edits details. Click to disable vim.");
        }
    };

    StigEditor.prototype.refreshVimFields = function () {
        ["stig-finding", "stig-comments"].forEach(function (id) {
            var node = document.getElementById(id);
            if (node && node._stigVim) {
                node._stigVim.syncEnabled();
            }
        });
    };

    StigEditor.prototype.activeVimField = function () {
        var ae = document.activeElement;
        return ae && ae._stigVim ? ae._stigVim : null;
    };

    StigEditor.prototype.setViewMode = function (mode) {
        this.viewMode = mode;
        var pane = $("#stig-list-pane");
        pane.removeClass("stig-view-host stig-view-all stig-view-rule");
        pane.addClass("stig-view-" + mode);
        this.renderListHeader();
    };

    StigEditor.prototype.renderListHeader = function () {
        var html = "<span>Done</span><span>Status</span>";
        if (this.viewMode === "all" || this.viewMode === "rule") {
            html += "<span>Host</span>";
        }
        if (this.viewMode !== "rule") {
            html += "<span>Rule</span>";
        }
        html += "<span>Title</span>";
        $("#stig-list-header").html(html);
    };

    StigEditor.prototype.setMeta = function (text) {
        $("#stig-meta").text(text || "");
    };

    StigEditor.prototype.reviewIsValid = function (rev) {
        return Boolean(
            String((rev && rev.finding_details) || "").trim() ||
                String((rev && rev.comments) || "").trim()
        );
    };

    StigEditor.prototype.updateCounts = function () {
        var self = this;
        var total = this.items.length;
        var done = 0;
        this.items.forEach(function (item) {
            if (self.reviewIsValid(item.review)) {
                done += 1;
            }
        });
        this.setMeta(
            done +
                " completed · " +
                (total - done) +
                " incomplete" +
                (this.filtered.length !== total
                    ? " · " + this.filtered.length + " shown"
                    : "")
        );
    };

    StigEditor.prototype.hostName = function (hostId) {
        var host = this.hostsById[hostId] || {};
        return host.hostname || hostId || "?";
    };

    StigEditor.prototype.checklistById = function (id) {
        return (
            this.checklists.find(function (c) {
                return c._key === id;
            }) || {}
        );
    };

    StigEditor.prototype.hostForReview = function (rev) {
        var cl = this.checklistById(rev.checklist_id);
        return this.hostsById[cl.host_id] || {};
    };

    StigEditor.prototype.lookupRule = function (rev) {
        return (
            this.rulesByKey[rev.rule_id] ||
            this.rulesByKey[(rev.rule_id || "") + "|" + (rev.group_id || "")] ||
            {}
        );
    };

    StigEditor.prototype.toItems = function (reviews) {
        var self = this;
        return reviews.map(function (rev) {
            return {
                review: rev,
                rule: self.lookupRule(rev),
                dirty: false,
                savedFinding: rev.finding_details || "",
                savedComments: rev.comments || "",
            };
        });
    };

    StigEditor.prototype.mergeRules = function (rules) {
        var self = this;
        (rules || []).forEach(function (r) {
            var k = (r.rule_id || "") + "|" + (r.group_id || "");
            self.rulesByKey[k] = r;
            if (r.rule_id) {
                self.rulesByKey[r.rule_id] = r;
            }
        });
    };

    StigEditor.prototype.loadRulesForChecklists = function (checklists) {
        var self = this;
        var ids = [];
        (checklists || []).forEach(function (cl) {
            if (cl.baseline_id && ids.indexOf(cl.baseline_id) < 0) {
                ids.push(cl.baseline_id);
            }
        });
        return Promise.all(
            ids.map(function (id) {
                return apiGet("stig_baselines/" + id + "/rules");
            })
        ).then(function (sets) {
            sets.forEach(function (rules) {
                self.mergeRules(Array.isArray(rules) ? rules : []);
            });
        });
    };

    StigEditor.prototype.loadCollections = function () {
        var self = this;
        var sel = $("#stig-collection");
        sel.html('<option value="">Loading…</option>');
        apiGet("stig_collections")
            .then(function (data) {
                self.collections = Array.isArray(data) ? data : [];
                if (!self.collections.length) {
                    sel.html('<option value="">No collections in KV store</option>');
                    self.setMeta("KV store is empty");
                    return;
                }
                sel.empty().append('<option value="">— select —</option>');
                self.collections.forEach(function (c) {
                    sel.append(
                        $("<option></option>").val(c._key).text(c.name || c._key)
                    );
                });
            })
            .catch(function (err) {
                toast("Failed to load collections: " + err, true);
                sel.html('<option value="">Error</option>');
            });
    };

    StigEditor.prototype.onCollectionChange = function (collectionId) {
        this.currentCollectionId = collectionId || "";
        this.currentHostId = "";
        this.currentRuleKey = "";
        var sel = $("#stig-host");
        sel.prop("disabled", true).html('<option value="">Loading…</option>');
        this.items = [];
        this.filtered = [];
        this.renderList();
        $("#stig-detail").html(
            '<div class="stig-detail-empty">Loading collection…</div>'
        );
        if (!collectionId) {
            sel.html('<option value="">— select collection first —</option>');
            return;
        }
        var self = this;
        Promise.all([
            apiGet("stig_checklists", { stig_collection_id: collectionId }),
            apiGet("stig_hosts", { stig_collection_id: collectionId }),
        ])
            .then(function (results) {
                self.checklists = Array.isArray(results[0]) ? results[0] : [];
                var hosts = Array.isArray(results[1]) ? results[1] : [];
                self.hostsById = {};
                hosts.forEach(function (h) {
                    self.hostsById[h._key] = h;
                });
                sel.empty().append(
                    '<option value="">All hosts (collection findings)</option>'
                );
                hosts.forEach(function (h) {
                    sel.append(
                        $("<option></option>").val(h._key).text(h.hostname || h._key)
                    );
                });
                sel.prop("disabled", false);
                self.loadCollectionFindings();
            })
            .catch(function (err) {
                toast("Failed to load hosts: " + err, true);
            });
    };

    StigEditor.prototype.onHostChange = function (hostId) {
        this.currentHostId = hostId || "";
        this.currentRuleKey = "";
        if (!hostId) {
            this.loadCollectionFindings();
            return;
        }
        this.loadHostFindings(hostId);
    };

    StigEditor.prototype.showItems = function (reviews, mode, meta) {
        this.setViewMode(mode);
        this.items = this.toItems(reviews);
        this.items.sort(function (a, b) {
            var ha = a.review.rule_version || a.rule.rule_version || "";
            var hb = b.review.rule_version || b.rule.rule_version || "";
            var c = ha.localeCompare(hb, undefined, { numeric: true });
            if (c !== 0) {
                return c;
            }
            return (a.review.checklist_id || "").localeCompare(
                b.review.checklist_id || ""
            );
        });
        if (meta) {
            this.setMeta(meta);
        }
        this.applyFilter();
        if (this.filtered.length) {
            this.selectIndex(0);
        }
    };

    StigEditor.prototype.loadCollectionFindings = function () {
        var collectionId = this.currentCollectionId;
        if (!collectionId) {
            return;
        }
        var self = this;
        this.currentHostId = "";
        $("#stig-host").val("");
        $("#stig-rule-list").html('<li class="stig-loading">Loading findings…</li>');
        Promise.all([
            apiGet("stig_reviews", { stig_collection_id: collectionId }),
            this.loadRulesForChecklists(this.checklists),
        ])
            .then(function (results) {
                var reviews = Array.isArray(results[0]) ? results[0] : [];
                var allowed = {};
                self.checklists.forEach(function (cl) {
                    allowed[cl._key] = true;
                });
                reviews = reviews.filter(function (r) {
                    return allowed[r.checklist_id];
                });
                self.showItems(
                    reviews,
                    "all",
                    reviews.length + " findings · all hosts"
                );
            })
            .catch(function (err) {
                toast("Failed to load findings: " + err, true);
            });
    };

    StigEditor.prototype.loadHostFindings = function (hostId) {
        var self = this;
        var cls = this.checklists.filter(function (cl) {
            return cl.host_id === hostId;
        });
        if (!cls.length) {
            toast("No checklist for that host", true);
            return;
        }
        $("#stig-rule-list").html('<li class="stig-loading">Loading host…</li>');
        Promise.all(
            cls
                .map(function (cl) {
                    return apiGet("stig_reviews", { checklist_id: cl._key });
                })
                .concat([this.loadRulesForChecklists(cls)])
        )
            .then(function (results) {
                var reviews = [];
                for (var i = 0; i < cls.length; i += 1) {
                    reviews = reviews.concat(
                        Array.isArray(results[i]) ? results[i] : []
                    );
                }
                self.showItems(
                    reviews,
                    "host",
                    reviews.length +
                        " rules · " +
                        self.hostName(hostId)
                );
            })
            .catch(function (err) {
                toast("Failed to load host reviews: " + err, true);
            });
    };

    StigEditor.prototype.loadRuleAcrossHosts = function (ruleVersion, ruleId) {
        var collectionId = this.currentCollectionId;
        if (!collectionId) {
            toast("Select a collection first", true);
            return;
        }
        var self = this;
        this.currentRuleKey = ruleVersion || ruleId || "";
        $("#stig-rule-list").html('<li class="stig-loading">Loading rule…</li>');
        var query = { stig_collection_id: collectionId };
        if (ruleVersion) {
            query.rule_version = ruleVersion;
        } else if (ruleId) {
            query.rule_id = ruleId;
        }
        Promise.all([
            apiGet("stig_reviews", query),
            this.loadRulesForChecklists(this.checklists),
        ])
            .then(function (results) {
                var reviews = Array.isArray(results[0]) ? results[0] : [];
                if (!reviews.length && (ruleVersion || ruleId)) {
                    return apiGet("stig_reviews", {
                        stig_collection_id: collectionId,
                    }).then(function (all) {
                        all = Array.isArray(all) ? all : [];
                        return all.filter(function (r) {
                            return (
                                r.rule_version === ruleVersion ||
                                r.rule_id === ruleId
                            );
                        });
                    });
                }
                return reviews;
            })
            .then(function (reviews) {
                self.showItems(
                    reviews,
                    "rule",
                    (ruleVersion || ruleId || "Rule") +
                        " · " +
                        reviews.length +
                        " hosts"
                );
            })
            .catch(function (err) {
                toast("Failed to load rule: " + err, true);
            });
    };

    StigEditor.prototype.applyFilter = function () {
        var q = this.searchQuery;
        var st = this.statusFilter;
        var self = this;
        this.filtered = this.items.filter(function (item) {
            var rev = item.review;
            if (st && rev.status !== st) {
                return false;
            }
            if (self.validityFilter === "complete" && !self.reviewIsValid(rev)) {
                return false;
            }
            if (self.validityFilter === "incomplete" && self.reviewIsValid(rev)) {
                return false;
            }
            if (!q) {
                return true;
            }
            var rule = item.rule;
            var host = self.hostForReview(rev);
            var hay =
                (rev.rule_id || "") +
                " " +
                (rev.group_id || "") +
                " " +
                (rule.rule_version || rev.rule_version || "") +
                " " +
                (rule.rule_title || "") +
                " " +
                (host.hostname || "") +
                " " +
                (rev.finding_details || "") +
                " " +
                (rev.comments || "");
            return hay.toLowerCase().indexOf(q) >= 0;
        });
        if (
            this.selectedIndex >= this.filtered.length ||
            (this.selectedIndex >= 0 &&
                this.filtered[this.selectedIndex] !== this.currentItem())
        ) {
            this.selectedIndex = this.filtered.length ? 0 : -1;
        }
        this.renderList();
        this.renderDetail();
        this.updateCounts();
    };

    StigEditor.prototype.currentItem = function () {
        if (this.selectedIndex < 0 || this.selectedIndex >= this.filtered.length) {
            return null;
        }
        return this.filtered[this.selectedIndex];
    };

    StigEditor.prototype.refreshCurrentRow = function () {
        var item = this.currentItem();
        if (!item) {
            return;
        }
        var li = document.querySelector(
            '#stig-rule-list li.stig-rule-row[data-idx="' + this.selectedIndex + '"]'
        );
        if (!li) {
            this.renderList();
            return;
        }
        var complete = this.reviewIsValid(item.review);
        li.classList.toggle("dirty", !!item.dirty);
        li.classList.toggle("is-complete", complete);
        li.classList.toggle("is-incomplete", !complete);
        var done = li.querySelector(".stig-col-done");
        if (done) {
            done.textContent = complete ? "✓" : "";
            done.setAttribute(
                "title",
                complete
                    ? "Completed — finding details or comments are present"
                    : "Incomplete — both finding details and comments are empty"
            );
        }
        var statusCell = li.querySelector(".stig-col-status");
        if (statusCell) {
            var existing = statusCell.querySelector(".stig-dirty-dot");
            if (item.dirty && !existing) {
                var dot = document.createElement("span");
                dot.className = "stig-dirty-dot";
                dot.setAttribute(
                    "title",
                    "Unsaved finding details or comments — write with Save"
                );
                dot.textContent = "●";
                statusCell.appendChild(dot);
            } else if (!item.dirty && existing) {
                existing.parentNode.removeChild(existing);
            }
        }
    };

    StigEditor.prototype.scrollRowIntoView = function (row) {
        var list = document.getElementById("stig-rule-list");
        if (!list || !row) {
            return;
        }
        var listRect = list.getBoundingClientRect();
        var rowRect = row.getBoundingClientRect();
        if (rowRect.top < listRect.top) {
            list.scrollTop -= listRect.top - rowRect.top;
        } else if (rowRect.bottom > listRect.bottom) {
            list.scrollTop += rowRect.bottom - listRect.bottom;
        }
    };

    StigEditor.prototype.renderList = function () {
        var list = $("#stig-rule-list");
        var scrollTop = list.prop("scrollTop") || 0;
        list.empty();
        var self = this;
        this.filtered.forEach(function (item, idx) {
            var rev = item.review;
            var rule = item.rule;
            var st = rev.status || "not_reviewed";
            var host = self.hostForReview(rev);
            var complete = self.reviewIsValid(rev);
            var li = $("<li></li>")
                .addClass("stig-rule-row")
                .attr("data-idx", idx)
                .toggleClass("selected", idx === self.selectedIndex)
                .toggleClass("dirty", item.dirty)
                .toggleClass("is-complete", complete)
                .toggleClass("is-incomplete", !complete);
            var doneCell = $("<span></span>")
                .addClass("stig-col-done")
                .attr(
                    "title",
                    complete
                        ? "Completed — finding details or comments are present"
                        : "Incomplete — both finding details and comments are empty"
                )
                .text(complete ? "✓" : "");
            li.append(doneCell);
            var statusCell = $("<span></span>").addClass("stig-col-status");
            statusCell.append(
                $("<span></span>")
                    .addClass("stig-badge stig-badge-" + st)
                    .text(STATUS_LABELS[st] || st)
            );
            if (item.dirty) {
                statusCell.append(
                    $("<span></span>")
                        .addClass("stig-dirty-dot")
                        .attr(
                            "title",
                            "Unsaved finding details or comments — write with Save"
                        )
                        .text("●")
                );
            }
            li.append(statusCell);
            if (self.viewMode === "all" || self.viewMode === "rule") {
                li.append(
                    $("<span></span>")
                        .addClass("stig-col-host")
                        .text(host.hostname || host._key || "?")
                );
            }
            if (self.viewMode !== "rule") {
                li.append(
                    $("<span></span>")
                        .addClass("stig-rule-id stig-col-id")
                        .text(
                            rule.rule_version ||
                                rev.rule_version ||
                                rev.rule_id ||
                                "—"
                        )
                );
            }
            li.append(
                $("<span></span>")
                    .addClass("stig-rule-title stig-col-title")
                    .text(rule.rule_title || rev.rule_id || "Untitled rule")
            );
            list.append(li);
        });
        if (!this.filtered.length) {
            list.html('<li class="stig-loading">No matching findings.</li>');
        }
        list.prop("scrollTop", scrollTop);
    };

    StigEditor.prototype.renderDetail = function () {
        var pane = $("#stig-detail");
        var item = this.currentItem();
        if (!item) {
            pane.html('<div class="stig-detail-empty">No finding selected.</div>');
            return;
        }
        var rev = item.review;
        var rule = item.rule;
        var host = this.hostForReview(rev);
        var st = rev.status || "not_reviewed";
        var self = this;

        pane.html(
            '<div class="stig-detail-header">' +
                "<h2>" +
                escapeHtml(rule.rule_title || rev.rule_id || "Rule") +
                "</h2>" +
                '<div class="stig-detail-meta">' +
                "<span><strong>Host:</strong> " +
                escapeHtml(host.hostname || "—") +
                "</span>" +
                "<span><strong>Version:</strong> " +
                escapeHtml(rule.rule_version || rev.rule_version || "—") +
                "</span>" +
                "<span><strong>Rule:</strong> " +
                escapeHtml(rev.rule_id || "—") +
                "</span>" +
                "<span><strong>Group:</strong> " +
                escapeHtml(rev.group_id || rule.group_id || "—") +
                "</span>" +
                "<span><strong>Severity:</strong> " +
                escapeHtml(rule.severity || "—") +
                "</span>" +
                "<span><strong>Valid:</strong> " +
                (this.reviewIsValid(rev) ? "yes" : "no") +
                "</span>" +
                "</div></div>" +
                (this.reviewIsValid(rev)
                    ? '<div class="stig-valid-banner is-complete">Completed — finding details or comments are present.</div>'
                    : '<div class="stig-valid-banner is-incomplete">Incomplete — add finding details or comments, then Write.</div>') +
                '<div class="stig-field"><label>Status (saves immediately)</label>' +
                '<select id="stig-status-select">' +
                optionStatuses(st) +
                "</select></div>" +
                '<div class="stig-field"><label>Check content</label>' +
                '<div class="stig-pre-block">' +
                escapeHtml(rule.check_content || "(no check content in baseline)") +
                "</div></div>" +
                '<div class="stig-field"><label>Fix text</label>' +
                '<div class="stig-pre-block">' +
                escapeHtml(rule.fix_text || "—") +
                "</div></div>" +
                '<div class="stig-field"><label>Finding details (must be written)</label>' +
                '<textarea id="stig-finding" rows="4"></textarea></div>' +
                '<div class="stig-field"><label>Comments (must be written)</label>' +
                '<textarea id="stig-comments" rows="3"></textarea></div>' +
                '<div class="stig-actions">' +
                '<button type="button" class="stig-btn" id="stig-save">Write</button>' +
                '<button type="button" class="stig-btn stig-btn-secondary" id="stig-revert">Revert</button>' +
                '<span id="stig-save-hint"></span>' +
                "</div>"
        );

        $("#stig-finding").val(rev.finding_details || "");
        $("#stig-comments").val(rev.comments || "");

        $("#stig-status-select").on("change", function () {
            self.setStatus(this.value);
        });
        $("#stig-finding, #stig-comments").on("input", function () {
            var sx = window.scrollX;
            var sy = window.scrollY;
            var patch = {};
            patch[this.id === "stig-finding" ? "finding_details" : "comments"] =
                this.value;
            self.markTextDirty(item, patch);
            if (window.scrollX !== sx || window.scrollY !== sy) {
                window.scrollTo(sx, sy);
            }
        });

        ["stig-finding", "stig-comments"].forEach(function (id) {
            attachVimField(document.getElementById(id), {
                isEnabled: function () {
                    return self.vimEnabled;
                },
                onMode: function (mode) {
                    self.setVimLayer(mode === "insert" ? "insert" : "text");
                },
                onCommand: function () {
                    self.openVimCommand();
                },
                onLeave: function () {
                    self.enterNav();
                },
                onSwitchField: function (id, mode) {
                    var next = document.getElementById(id);
                    if (!next) {
                        return;
                    }
                    next.focus();
                    if (next._stigVim) {
                        next._stigVim.setMode(mode === "normal" ? "normal" : "insert");
                    }
                    self.setVimLayer(mode === "insert" ? "insert" : "text");
                },
            });
        });

        $("#stig-save").on("click", function () {
            self.saveCurrent();
        });
        $("#stig-revert").on("click", function () {
            item.review.finding_details = item.savedFinding;
            item.review.comments = item.savedComments;
            item.dirty = false;
            self.renderDetail();
            self.renderList();
        });
        $("#stig-save-hint").text(
            item.dirty ? "Unwritten finding details or comments" : ""
        );
    };

    StigEditor.prototype.markTextDirty = function (item, patch) {
        if (patch.finding_details !== undefined) {
            item.review.finding_details = patch.finding_details;
        }
        if (patch.comments !== undefined) {
            item.review.comments = patch.comments;
        }
        item.dirty =
            (item.review.finding_details || "") !== (item.savedFinding || "") ||
            (item.review.comments || "") !== (item.savedComments || "");
        this.refreshCurrentRow();
        this.updateValidityBanner(item.review);
        this.updateCounts();
        $("#stig-save-hint").text(
            item.dirty ? "Unwritten finding details or comments" : ""
        );
    };

    StigEditor.prototype.updateValidityBanner = function (rev) {
        var banner = $(".stig-valid-banner");
        if (!banner.length) {
            return;
        }
        var ok = this.reviewIsValid(rev);
        banner
            .toggleClass("is-complete", ok)
            .toggleClass("is-incomplete", !ok)
            .text(
                ok
                    ? "Completed — finding details or comments are present."
                    : "Incomplete — add finding details or comments, then Write."
            );
        $(".stig-detail-meta strong")
            .filter(function () {
                return $(this).text() === "Valid:";
            })
            .parent()
            .contents()
            .last()
            .replaceWith(ok ? " yes" : " no");
    };

    StigEditor.prototype.validateCurrent = function () {
        var ids = [];
        var self = this;
        if (this.currentHostId) {
            this.checklists.forEach(function (c) {
                if (c.host_id === self.currentHostId && c._key) {
                    ids.push(c._key);
                }
            });
        } else {
            this.checklists.forEach(function (c) {
                if (c._key && ids.indexOf(c._key) < 0) {
                    ids.push(c._key);
                }
            });
        }
        if (!ids.length) {
            toast("Select a collection first.", true);
            return;
        }
        $("#stig-validate").prop("disabled", true);
        Promise.all(
            ids.map(function (id) {
                return apiPatch("stig_checklists/" + id + "/validate", {});
            })
        )
            .then(function (results) {
                var total = 0;
                var valid = 0;
                results.forEach(function (r) {
                    total += r.total || 0;
                    valid += r.valid || 0;
                });
                var byKey = {};
                results.forEach(function (r) {
                    (r.reviews || []).forEach(function (rev) {
                        byKey[rev._key] = rev;
                    });
                });
                self.items.forEach(function (item) {
                    var next = byKey[item.review._key];
                    if (next) {
                        item.review.valid = next.valid;
                    }
                });
                self.applyFilter();
                showSaveModal(
                    "Checklist validated",
                    valid + " of " + total + " findings are completed (valid)."
                );
            })
            .catch(function (err) {
                toast("Validate failed: " + formatErr(err), true);
            })
            .finally(function () {
                $("#stig-validate").prop("disabled", false);
            });
    };

    StigEditor.prototype.setStatus = function (status) {
        var item = this.currentItem();
        if (!item || this.pendingSave) {
            return;
        }
        var previous = item.review.status;
        item.review.status = status;
        $("#stig-status-select").val(status);
        this.renderList();
        var self = this;
        this.pendingSave = true;
        apiPatch("stig_reviews/" + item.review._key, { status: status })
            .then(function (updated) {
                item.review.status = updated.status || status;
                item.review.updated_at = updated.updated_at;
                showSaveModal(
                    "Status saved",
                    (item.rule.rule_version || item.review.rule_id || "") +
                        " → " +
                        (STATUS_LABELS[item.review.status] || item.review.status)
                );
                self.renderList();
            })
            .catch(function (err) {
                item.review.status = previous;
                $("#stig-status-select").val(previous);
                self.renderList();
                toast("Status save failed: " + formatErr(err), true);
            })
            .finally(function () {
                self.pendingSave = false;
            });
    };

    StigEditor.prototype.saveCurrent = function () {
        var item = this.currentItem();
        if (!item || this.pendingSave) {
            return;
        }
        if (!item.dirty) {
            showSaveModal("Nothing to write", "Finding details and comments are unchanged.");
            return;
        }
        var patch = {
            finding_details: $("#stig-finding").val(),
            comments: $("#stig-comments").val(),
        };
        var self = this;
        this.pendingSave = true;
        $("#stig-save").prop("disabled", true);
        apiPatch("stig_reviews/" + item.review._key, patch)
            .then(function (updated) {
                item.review = updated;
                item.savedFinding = updated.finding_details || "";
                item.savedComments = updated.comments || "";
                item.dirty = false;
                showSaveModal(
                    "Wrote finding",
                    item.rule.rule_version || item.review.rule_id || item.review._key
                );
                self.renderList();
                self.renderDetail();
                self.enterNav();
            })
            .catch(function (err) {
                toast("Write failed: " + formatErr(err), true);
            })
            .finally(function () {
                self.pendingSave = false;
                $("#stig-save").prop("disabled", false);
            });
    };

    StigEditor.prototype.selectIndex = function (idx) {
        if (idx < 0 || idx >= this.filtered.length) {
            return;
        }
        this.selectedIndex = idx;
        this.renderList();
        this.renderDetail();
        var row = document.querySelector("#stig-rule-list li.stig-rule-row.selected");
        this.scrollRowIntoView(row);
    };

    StigEditor.prototype.moveSelection = function (delta) {
        if (!this.filtered.length) {
            return;
        }
        var next = this.selectedIndex < 0 ? 0 : this.selectedIndex + delta;
        next = Math.max(0, Math.min(this.filtered.length - 1, next));
        this.selectIndex(next);
    };

    StigEditor.prototype.setVimMode = function (mode) {
        if (mode === "insert") {
            this.setVimLayer("insert");
            return;
        }
        if (this.activeVimField()) {
            this.setVimLayer("text");
            return;
        }
        this.setVimLayer("nav");
    };

    StigEditor.prototype.setVimLayer = function (layer) {
        this.vimLayer = layer === "insert" || layer === "text" ? layer : "nav";
        this.vimMode = this.vimLayer === "insert" ? "insert" : "normal";
        this.updateVimBadge();
    };

    StigEditor.prototype.inFieldLayer = function () {
        return this.vimEnabled && (this.vimLayer === "insert" || this.vimLayer === "text");
    };

    StigEditor.prototype.enterNav = function () {
        var ae = document.activeElement;
        if (ae && ae._stigVim) {
            ae.blur();
        }
        this.setVimLayer("nav");
        var list = document.getElementById("stig-rule-list");
        if (list && list.focus) {
            list.focus();
        }
    };

    StigEditor.prototype.vimCommandOpen = function () {
        return $("#stig-vim-cmd").length > 0;
    };

    StigEditor.prototype.closeVimCommand = function () {
        $("#stig-vim-cmd").remove();
    };

    StigEditor.prototype.runVimCommand = function (cmd) {
        cmd = String(cmd || "").replace(/^:+/, "").trim();
        if (!cmd || cmd === "w" || cmd === "write" || cmd === "wq") {
            if (cmd) {
                this.saveCurrent();
            }
            return;
        }
        toast("Not an editor command: :" + cmd, true);
    };

    StigEditor.prototype.openVimCommand = function () {
        var self = this;
        this.closeVimCommand();
        var bar = $(
            '<div class="stig-vim-cmd" id="stig-vim-cmd">' +
                "<span>:</span>" +
                '<input type="text" id="stig-vim-cmd-input" autocomplete="off" spellcheck="false" aria-label="Vim command">' +
                "</div>"
        );
        $(this.root).append(bar);
        var input = $("#stig-vim-cmd-input");
        input.on("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                var cmd = String(input.val() || "").trim();
                self.closeVimCommand();
                self.runVimCommand(cmd);
            } else if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                self.closeVimCommand();
                self.enterNav();
            }
        });
        setTimeout(function () {
            input.trigger("focus");
        }, 0);
    };

    StigEditor.prototype.isEditingField = function () {
        var ae = document.activeElement;
        if (!ae) {
            return false;
        }
        var tag = ae.tagName;
        return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    };

    StigEditor.prototype.jumpChoices = function (kind) {
        var self = this;
        if (kind === "collection") {
            return this.collections.map(function (c) {
                return {
                    id: c._key,
                    label: c.name || c._key,
                    sub: c.description || "",
                };
            });
        }
        if (kind === "host") {
            var rows = [
                {
                    id: "",
                    label: "All hosts",
                    sub: "Every finding in this collection",
                },
            ];
            Object.keys(this.hostsById).forEach(function (id) {
                var h = self.hostsById[id];
                rows.push({
                    id: id,
                    label: h.hostname || id,
                    sub: h.fqdn || h.ip_address || "",
                });
            });
            return rows;
        }
        var seen = {};
        var rules = [];
        this.items.forEach(function (item) {
            var ver = item.rule.rule_version || item.review.rule_version || "";
            var rid = item.review.rule_id || "";
            var key = ver || rid;
            if (!key || seen[key]) {
                return;
            }
            seen[key] = true;
            rules.push({
                id: key,
                label: ver || rid,
                sub: item.rule.rule_title || rid,
                ruleId: rid,
                ruleVersion: ver,
            });
        });
        return rules;
    };

    StigEditor.prototype.openJump = function (kind) {
        var self = this;
        if (kind !== "collection" && !this.currentCollectionId) {
            toast("Select a collection first", true);
            return;
        }
        var title =
            kind === "collection"
                ? "Go to collection"
                : kind === "host"
                  ? "Go to host"
                  : "Go to rule (all hosts)";
        var choices = this.jumpChoices(kind);
        if (kind === "rule" && !choices.length) {
            toast("Load a collection first so rules can be indexed", true);
            return;
        }
        $("#stig-jump").remove();
        var html =
            '<div class="stig-jump-overlay" id="stig-jump">' +
            '<div class="stig-jump-panel">' +
            "<h3>" +
            escapeHtml(title) +
            "</h3>" +
            '<input type="search" id="stig-jump-input" placeholder="Start typing…" autocomplete="off" />' +
            '<ul class="stig-jump-list" id="stig-jump-list"></ul>' +
            "</div></div>";
        $("body").append(html);
        var input = $("#stig-jump-input");
        var active = 0;
        var visible = [];

        function render() {
            var q = input.val().trim().toLowerCase();
            visible = choices.filter(function (c) {
                if (!q) {
                    return true;
                }
                return (
                    (c.label || "").toLowerCase().indexOf(q) >= 0 ||
                    (c.sub || "").toLowerCase().indexOf(q) >= 0
                );
            });
            if (active >= visible.length) {
                active = visible.length ? visible.length - 1 : 0;
            }
            var list = $("#stig-jump-list");
            list.empty();
            visible.forEach(function (c, idx) {
                var li = $("<li></li>")
                    .toggleClass("active", idx === active)
                    .append(document.createTextNode(c.label));
                if (c.sub) {
                    li.append(
                        $("<div></div>").addClass("muted").text(c.sub)
                    );
                }
                li.on("click", function () {
                    pick(c);
                });
                list.append(li);
            });
            if (!visible.length) {
                list.append('<li class="muted">No matches</li>');
            }
        }

        function pick(choice) {
            $("#stig-jump").remove();
            if (kind === "collection") {
                $("#stig-collection").val(choice.id).trigger("change");
                return;
            }
            if (kind === "host") {
                $("#stig-host").val(choice.id).trigger("change");
                return;
            }
            self.loadRuleAcrossHosts(choice.ruleVersion, choice.ruleId);
        }

        function close() {
            $("#stig-jump").remove();
        }

        input.on("input", render);
        input.on("keydown", function (e) {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                active = Math.min(visible.length - 1, active + 1);
                render();
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                active = Math.max(0, active - 1);
                render();
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (visible[active]) {
                    pick(visible[active]);
                }
            } else if (e.key === "Escape") {
                e.preventDefault();
                close();
            }
        });
        $("#stig-jump").on("click", function (e) {
            if (e.target.id === "stig-jump") {
                close();
            }
        });
        render();
        input.trigger("focus");
    };

    StigEditor.prototype.showHelp = function () {
        var vimRows = this.vimEnabled
            ? "<tr><td><kbd>Esc</kbd></td><td>INSERT → field NORMAL (stay in details). Again → NAV</td></tr>" +
              "<tr><td><kbd>i</kbd></td><td>NAV → insert in finding details</td></tr>" +
              "<tr><td><kbd>o</kbd></td><td>NAV: status Open. Field NORMAL: open a line. INSERT: type o</td></tr>" +
              "<tr><td><kbd>{</kbd> / <kbd>}</kbd></td><td>NAV: previous / next finding. Field: paragraphs</td></tr>" +
              "<tr><td><kbd>g</kbd><kbd>g</kbd> / <kbd>G</kbd></td><td>First / last finding (NAV)</td></tr>" +
              "<tr><td><kbd>g</kbd><kbd>h</kbd></td><td>Go to host (type a name; All hosts = every finding)</td></tr>" +
              "<tr><td><kbd>g</kbd><kbd>c</kbd></td><td>Go to collection</td></tr>" +
              "<tr><td><kbd>g</kbd><kbd>r</kbd></td><td>Go to rule across all hosts</td></tr>" +
              "<tr><td><kbd>1</kbd>–<kbd>4</kbd> <kbd>n</kbd><kbd>f</kbd><kbd>a</kbd></td><td>Status in NAV (saves immediately)</td></tr>" +
              "<tr><td><kbd>:</kbd><kbd>w</kbd></td><td>Write finding details / comments</td></tr>" +
              "<tr><td><kbd>h</kbd><kbd>j</kbd><kbd>k</kbd><kbd>l</kbd> <kbd>w</kbd><kbd>b</kbd></td><td>Motions in field NORMAL</td></tr>" +
              "<tr><td><kbd>Tab</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd></td><td>Finding details ↔ comments (stays in the field layer)</td></tr>" +
              "<tr><td><kbd>g</kbd><kbd>t</kbd> / <kbd>g</kbd><kbd>T</kbd></td><td>Same switch in field NORMAL</td></tr>"
            : "<tr><td colspan=\"2\">Vim keys are off. Click the <strong>VIM OFF</strong> badge or enable them under Configuration.</td></tr>";
        var html =
            '<div class="stig-help-overlay" id="stig-help">' +
            '<div class="stig-help-panel">' +
            "<h3>Keyboard shortcuts</h3>" +
            "<table>" +
            vimRows +
            "<tr><td><kbd>Ctrl</kbd>+<kbd>s</kbd></td><td>Write finding details / comments</td></tr>" +
            "<tr><td><kbd>/</kbd></td><td>Filter</td></tr>" +
            "<tr><td><kbd>?</kbd></td><td>This help</td></tr>" +
            "</table>" +
            '<p>The red dot means finding details or comments are not written yet. Status saves as soon as it changes.</p>' +
            '<p><button type="button" class="stig-btn" id="stig-help-close">Close</button></p>' +
            "</div></div>";
        $("body").append(html);
        $("#stig-help-close, .stig-help-overlay").on("click", function (e) {
            if (e.target.id === "stig-help-close" || e.target.id === "stig-help") {
                $("#stig-help").remove();
            }
        });
    };

    StigEditor.prototype.bindKeys = function () {
        var self = this;
        var pendingG = false;

        $(document).on("keydown.stigEditor", function (e) {
            if ($("#stig-help").length) {
                if (e.key === "Escape") {
                    $("#stig-help").remove();
                }
                return;
            }
            if ($("#stig-jump").length) {
                return;
            }

            if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                e.preventDefault();
                self.closeVimCommand();
                self.saveCurrent();
                return;
            }
            if (self.vimCommandOpen()) {
                return;
            }
            if (self.inFieldLayer()) {
                return;
            }

            if (self.isEditingField()) {
                if (e.key === "Escape") {
                    $(document.activeElement).blur();
                    self.enterNav();
                }
                return;
            }

            if (e.key === "?") {
                e.preventDefault();
                self.showHelp();
                return;
            }

            if (e.key === "/") {
                e.preventDefault();
                $("#stig-search").focus();
                return;
            }

            if (!self.vimEnabled) {
                return;
            }

            if (e.key === "i") {
                e.preventDefault();
                var f = document.getElementById("stig-finding");
                if (f) {
                    f.focus();
                    if (f._stigVim) {
                        f._stigVim.setMode("insert");
                    }
                }
                return;
            }

            if (e.key === ":") {
                e.preventDefault();
                self.openVimCommand();
                return;
            }

            if (pendingG) {
                pendingG = false;
                e.preventDefault();
                if (e.key === "g") {
                    if (self.filtered.length) {
                        self.selectIndex(0);
                    }
                } else if (e.key === "h") {
                    self.openJump("host");
                } else if (e.key === "c") {
                    self.openJump("collection");
                } else if (e.key === "r") {
                    self.openJump("rule");
                }
                return;
            }

            if (e.key === "}") {
                e.preventDefault();
                self.moveSelection(1);
                return;
            }
            if (e.key === "{") {
                e.preventDefault();
                self.moveSelection(-1);
                return;
            }
            if (e.key === "G") {
                e.preventDefault();
                if (self.filtered.length) {
                    self.selectIndex(self.filtered.length - 1);
                }
                return;
            }
            if (e.key === "g") {
                pendingG = true;
                setTimeout(function () {
                    pendingG = false;
                }, 500);
                return;
            }

            if (STATUS_KEYS[e.key]) {
                e.preventDefault();
                self.setStatus(STATUS_KEYS[e.key]);
                return;
            }
            var quick = {
                o: "open",
                n: "not_reviewed",
                f: "not_a_finding",
                a: "not_applicable",
            };
            if (quick[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                self.setStatus(quick[e.key]);
            }
        });
    };

    function optionStatuses(selected) {
        return Object.keys(STATUS_LABELS)
            .map(function (st) {
                return (
                    '<option value="' +
                    st +
                    '"' +
                    (st === selected ? " selected" : "") +
                    ">" +
                    STATUS_LABELS[st] +
                    "</option>"
                );
            })
            .join("");
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    new StigEditor();
});
