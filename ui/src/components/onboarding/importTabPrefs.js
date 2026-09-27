const IMPORT_TAB_STORAGE_KEY = "stig_import_last_tab";

export const IMPORT_TAB_IDS = ["checklists", "baselines"];

export function readImportTabFromHash() {
    const id = (window.location.hash || "").replace(/^#/, "");
    return IMPORT_TAB_IDS.includes(id) ? id : null;
}

export function readStoredImportTab() {
    try {
        const id = localStorage.getItem(IMPORT_TAB_STORAGE_KEY);
        return IMPORT_TAB_IDS.includes(id) ? id : null;
    } catch (e) {
        return null;
    }
}

export function storeImportTab(tabId) {
    if (!IMPORT_TAB_IDS.includes(tabId)) {
        return;
    }
    try {
        localStorage.setItem(IMPORT_TAB_STORAGE_KEY, tabId);
    } catch (e) {
        /* ignore */
    }
}

export function defaultImportTabWhenCatalogEmpty(catalogEmpty) {
    if (catalogEmpty) {
        return "baselines";
    }
    return readStoredImportTab() || "checklists";
}
