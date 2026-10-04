import { defaultWorkspaceId, isAllWorkspaces, WORKSPACE_ALL } from "./api";

const STORAGE_KEY = "stigs_in_splunk.stig_collection_id";

export function readWorkspaceIdFromUrl() {
    try {
        return new URLSearchParams(window.location.search || "").get("stig_collection_id") || "";
    } catch (e) {
        return "";
    }
}

export function readStoredWorkspaceId() {
    try {
        return window.localStorage.getItem(STORAGE_KEY) || "";
    } catch (e) {
        return "";
    }
}

/** Persist workspace selection to localStorage and the URL query (without navigation). */
export function persistWorkspaceSelection(collectionId) {
    const id =
        collectionId && !isAllWorkspaces(collectionId) ? String(collectionId) : "";
    try {
        if (id) {
            window.localStorage.setItem(STORAGE_KEY, id);
        } else {
            window.localStorage.removeItem(STORAGE_KEY);
        }
    } catch (e) {
        /* ignore quota / private mode */
    }
    try {
        const url = new URL(window.location.href);
        if (id) {
            url.searchParams.set("stig_collection_id", id);
        } else if (collectionId === WORKSPACE_ALL) {
            url.searchParams.delete("stig_collection_id");
        } else {
            url.searchParams.delete("stig_collection_id");
        }
        const next = url.pathname + url.search + url.hash;
        if (next !== window.location.pathname + window.location.search + window.location.hash) {
            window.history.replaceState({}, "", next);
        }
    } catch (e) {
        /* ignore */
    }
}

/**
 * Resolve workspace id: URL → localStorage → default workspace.
 * @param {Array<{_key?: string}>} workspaces
 * @param {string} [urlOverride]
 */
export function resolveSharedWorkspaceId(workspaces, urlOverride) {
    const list = Array.isArray(workspaces) ? workspaces : [];
    const valid = (id) => id && list.some((row) => row && row._key === id);
    const fromUrl = urlOverride != null ? urlOverride : readWorkspaceIdFromUrl();
    if (valid(fromUrl)) {
        return fromUrl;
    }
    const fromStore = readStoredWorkspaceId();
    if (valid(fromStore)) {
        return fromStore;
    }
    return defaultWorkspaceId(list) || "";
}
