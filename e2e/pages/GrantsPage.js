const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const {
  workspaceCombobox,
  selectWorkspaceOption,
  escapeRegExp,
} = require('../helpers/workspaceSelect');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class GrantsPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  async open() {
    await this.page.goto(appPath('stig_grants_ui'), {
      timeout: NAV_TIMEOUT_MS,
      waitUntil: 'domcontentloaded',
    });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: /Workspace grants/i })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  workspaceSelect() {
    return workspaceCombobox(this.page);
  }

  /**
   * @param {string} name Workspace collection name (display label without "(default)" suffix).
   */
  async selectWorkspace(name) {
    const select = this.workspaceSelect();
    await expect(select).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await selectWorkspaceOption(this.page, select, name, CONTROL_TIMEOUT_MS);
    await expect(this.page.getByRole('button', { name: 'Add grant', exact: true })).toBeEnabled({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  newGrantHeading() {
    return this.page.getByRole('heading', { name: 'New grant', exact: true });
  }

  newGrantPanel() {
    return this.newGrantHeading().locator('xpath=ancestor::div[1]');
  }

  async openNewGrantForm() {
    await this.page.getByRole('button', { name: 'Add grant', exact: true }).click();
    await expect(this.newGrantHeading()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} principal e.g. user:stig_pw_assessor
   * @param {'Member' | 'Manager' | 'Owner' | 'Restricted'} roleLabel Short role label matching Select option text
   */
  async saveGrant(principal, roleLabel) {
    const panel = this.newGrantPanel();
    const principalField = panel.getByRole('textbox', { name: 'Principal' });
    await principalField.click();
    await principalField.press('Control+a');
    await principalField.fill(principal);
    await expect(principalField).toHaveValue(principal, { timeout: CONTROL_TIMEOUT_MS });

    const roleSelect = panel.getByRole('combobox', { name: 'Grant role' });
    await roleSelect.click();
    const roleOption = this.page.getByRole('option', {
      name: new RegExp(`^${escapeRegExp(roleLabel)}`, 'i'),
    });
    await expect(roleOption.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await roleOption.first().click();

    await panel.getByRole('button', { name: 'Save grant', exact: true }).click();
    const savedRow = this.page.getByRole('row').filter({ hasText: principal });
    await expect(
      this.page.getByText('Grant saved.', { exact: true }).or(savedRow.first()),
    ).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} principal
   * @param {string} grantRole lowercase role value shown in table (member, manager, …)
   */
  async expectGrantRow(principal, grantRole) {
    const row = this.page.getByRole('row').filter({ hasText: principal });
    await expect(row.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await expect(row.first()).toContainText(principal);
    await expect(row.first()).toContainText(grantRole);
  }
}

module.exports = { GrantsPage };
