const { escapeRegExp } = require('./workspaceSelect');

/**
 * Splunk app side nav (default.xml).
 * @param {import('@playwright/test').Page} page
 */
async function ensureAppNavExpanded(page) {
  const shrink = page.getByRole('switch', { name: 'Menu shrink' });
  if (await shrink.isChecked().catch(() => false)) {
    await shrink.click();
  }
}

function appNavScope(page) {
  const appNav = page.locator('.navWrapper, [data-test="app-nav"], .appNavWrapper').first();
  return appNav;
}

/**
 * Expand a nav collection flyout so child view labels become visible.
 * @param {import('@playwright/test').Page} page
 * @param {string} collectionLabel e.g. "Content", "Workspace"
 */
async function expandNavCollection(page, collectionLabel) {
  const scope = appNavScope(page);
  const root = (await scope.count()) > 0 ? scope : page;
  const group = root.getByRole('menuitem', {
    name: new RegExp(`^${escapeRegExp(collectionLabel)}`),
  });
  await group.hover();
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} label Top-level or child view label from default.xml
 */
async function expectNavLabelVisible(page, label) {
  await ensureAppNavExpanded(page);
  const scope = appNavScope(page);
  const root = (await scope.count()) > 0 ? scope : page;
  await root.getByRole('link', { name: new RegExp(`^${escapeRegExp(label)}`) }).first().waitFor({
    state: 'visible',
    timeout: 60_000,
  });
}

module.exports = {
  appNavScope,
  expandNavCollection,
  ensureAppNavExpanded,
  expectNavLabelVisible,
};
