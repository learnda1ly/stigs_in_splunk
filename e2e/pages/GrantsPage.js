const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

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
    await this.page.goto(appPath('stig_grants_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: /Workspace grants/i })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  /**
   * @param {string} name Workspace collection name (display label without "(default)" suffix).
   */
  async selectWorkspace(name) {
    const select = this.workspaceSelect();
    await expect(select).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(name)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
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
    const principalField = panel.getByRole('textbox').first();
    await principalField.fill(principal);

    const roleSelect = panel.getByRole('combobox').first();
    await roleSelect.click();
    const roleOption = this.page.getByRole('option', {
      name: new RegExp(`^${escapeRegExp(roleLabel)}`, 'i'),
    });
    await expect(roleOption.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await roleOption.first().click();

    await panel.getByRole('button', { name: 'Save grant', exact: true }).click();
    await expect(this.page.getByText('Grant saved.', { exact: true })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
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

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { GrantsPage };
