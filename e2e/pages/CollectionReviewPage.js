const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class CollectionReviewPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  baselineSelect() {
    return this.page.getByRole('combobox').nth(1);
  }

  ruleSelect() {
    return this.page.getByRole('combobox').nth(2);
  }

  async open() {
    await this.page.goto(appPath('stig_collection_review_ui'), {
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name
   */
  async selectWorkspace(name) {
    const select = this.workspaceSelect();
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(name)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} baselineLabelFragment e.g. Example_STIG
   */
  async selectBaseline(baselineLabelFragment) {
    const select = this.baselineSelect();
    await expect(select).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(baselineLabelFragment)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(baselineLabelFragment, {
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} ruleVersion e.g. EX-00-000001
   */
  async selectRule(ruleVersion) {
    const select = this.ruleSelect();
    await expect(select).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(ruleVersion)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(ruleVersion, { timeout: CONTROL_TIMEOUT_MS });
  }

  async waitForHostRow(hostname) {
    const row = this.page.getByRole('row').filter({ hasText: hostname });
    await expect(row).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    return row;
  }

  /**
   * @param {string} hostname
   */
  async expectWorkflowAcceptedForHost(hostname) {
    const row = await this.waitForHostRow(hostname);
    await expect(row.getByText('Accepted', { exact: true })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { CollectionReviewPage };
