const { expect } = require('@playwright/test');

/** Matches `WorkspaceSelect` default `allLabel` in ui/src/components/WorkspaceSelect.jsx */
const ALL_WORKSPACES_LABEL = 'All workspaces';

/** Splunk `ControlGroup` label on workspace-scoped toolbars */
const WORKSPACE_COMBOBOX_NAME = 'Workspace';

const CONTROL_TIMEOUT_MS = 30_000;

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Primary workspace filter on SplunkUI toolbars (Editor, Hosts, Export, …).
 * @param {import('@playwright/test').Page} page
 */
function workspaceCombobox(page) {
  return page.locator('#stig-ui-root').getByRole('combobox', { name: WORKSPACE_COMBOBOX_NAME });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} combobox
 */
async function openWorkspaceOptions(page, combobox) {
  await combobox.click();
  await expect(page.getByRole('option').first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} combobox
 * @param {string} workspaceName Display name without "(default)" suffix.
 * @param {number} [timeoutMs]
 */
async function selectWorkspaceOption(page, combobox, workspaceName, timeoutMs = CONTROL_TIMEOUT_MS) {
  await openWorkspaceOptions(page, combobox);
  const option = page.getByRole('option', {
    name: new RegExp(escapeRegExp(workspaceName)),
  });
  await expect(option.first()).toBeVisible({ timeout: timeoutMs });
  await option.first().click();
  await expect(combobox).toContainText(workspaceName, { timeout: timeoutMs });
}

/**
 * @param {import('@playwright/test').Locator} combobox
 * @param {string} workspaceName
 * @param {number} [timeoutMs]
 */
async function expectWorkspaceOptionSelected(combobox, workspaceName, timeoutMs = CONTROL_TIMEOUT_MS) {
  await expect(combobox).toContainText(workspaceName, { timeout: timeoutMs });
}

/**
 * Asserts the aggregate workspace choice is offered (requires 2+ readable workspaces).
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} combobox
 */
async function expectAllWorkspacesOptionListed(page, combobox) {
  await openWorkspaceOptions(page, combobox);
  await expect(
    page.getByRole('option', { name: ALL_WORKSPACES_LABEL, exact: true }),
  ).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  await page.keyboard.press('Escape');
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} combobox
 */
async function expectAllWorkspacesOptionAbsent(page, combobox) {
  await openWorkspaceOptions(page, combobox);
  await expect(
    page.getByRole('option', { name: ALL_WORKSPACES_LABEL, exact: true }),
  ).toHaveCount(0);
  await page.keyboard.press('Escape');
}

module.exports = {
  ALL_WORKSPACES_LABEL,
  WORKSPACE_COMBOBOX_NAME,
  CONTROL_TIMEOUT_MS,
  escapeRegExp,
  workspaceCombobox,
  openWorkspaceOptions,
  selectWorkspaceOption,
  expectWorkspaceOptionSelected,
  expectAllWorkspacesOptionListed,
  expectAllWorkspacesOptionAbsent,
};
