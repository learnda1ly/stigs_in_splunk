export function vimLineBounds(text, pos) {
    pos = Math.max(0, Math.min(pos, text.length));
    const start = pos === 0 ? 0 : text.lastIndexOf("\n", pos - 1) + 1;
    const nl = text.indexOf("\n", pos);
    return { start, end: nl < 0 ? text.length : nl };
}

export function vimLineStart(text, pos) {
    return vimLineBounds(text, pos).start;
}

export function vimLineEnd(text, pos) {
    return vimLineBounds(text, pos).end;
}

export function vimCol(text, pos) {
    return pos - vimLineStart(text, pos);
}

export function vimIsBlankLine(text, pos) {
    const b = vimLineBounds(text, pos);
    return !/\S/.test(text.slice(b.start, b.end));
}

export function vimFirstNonBlank(text, pos) {
    const b = vimLineBounds(text, pos);
    let i = b.start;
    while (i < b.end && /[ \t]/.test(text.charAt(i))) {
        i++;
    }
    return i;
}

export function vimMoveVert(text, pos, delta, wantCol) {
    const col = wantCol == null ? vimCol(text, pos) : wantCol;
    let i = pos;
    let step;
    if (delta > 0) {
        for (step = 0; step < delta; step++) {
            const end = vimLineEnd(text, i);
            if (end >= text.length) {
                break;
            }
            i = end + 1;
        }
    } else if (delta < 0) {
        for (step = 0; step < -delta; step++) {
            const start = vimLineStart(text, i);
            if (start <= 0) {
                i = 0;
                break;
            }
            i = vimLineStart(text, start - 1);
        }
    }
    const b = vimLineBounds(text, i);
    return { pos: Math.min(b.start + col, b.end), col };
}

export function vimIsWord(ch) {
    return !!ch && /[A-Za-z0-9_]/.test(ch);
}

export function vimIsSpace(ch) {
    return !!ch && /\s/.test(ch);
}

export function vimNextWord(text, pos) {
    const n = text.length;
    if (pos >= n) {
        return n;
    }
    const ch = text.charAt(pos);
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

export function vimPrevWord(text, pos) {
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

export function vimWordEnd(text, pos) {
    const n = text.length;
    if (n === 0) {
        return 0;
    }
    let i = pos + 1;
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

export function vimNextParagraph(text, pos) {
    const n = text.length;
    if (pos >= n) {
        return n;
    }
    let i = pos;
    if (vimIsBlankLine(text, i)) {
        while (i < n && vimIsBlankLine(text, i)) {
            const blankEnd = vimLineEnd(text, i);
            if (blankEnd >= n) {
                return n;
            }
            i = blankEnd + 1;
        }
    }
    while (i < n && !vimIsBlankLine(text, i)) {
        const paraEnd = vimLineEnd(text, i);
        if (paraEnd >= n) {
            return n;
        }
        i = paraEnd + 1;
    }
    return Math.min(i, n);
}

export function vimPrevParagraph(text, pos) {
    if (pos <= 0) {
        return 0;
    }
    let i = vimLineStart(text, pos);
    let start;
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
