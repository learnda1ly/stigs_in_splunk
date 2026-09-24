const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

const INCOMPLETE_TEXT =
  /Incomplete — update finding details\/comments to match workspace requirements/;
const COMPLETE_TEXT = /Completed — review meets workspace requirements/;

class EditorRequirementsProbe {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  hostSelect() {
    return this.page.getByRole('combobox').nth(1);
  }

  submitButton() {
    return this.page.getByRole('button', { name: 'Submit', exact: true });
  }

  writeButton() {
    return this.page.getByRole('button', { name: 'Write', exact: true });
  }

  findingDetailsField() {
    return this.page.locator('#stig-finding');
  }

  async open() {
    await this.page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
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
    await this.waitForFindingsLoaded();
  }

  /**
   * @param {string} hostname
   */
  async selectHost(hostname) {
    const select = this.hostSelect();
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(`^${escapeRegExp(hostname)}$`),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(hostname, { timeout: CONTROL_TIMEOUT_MS });
    await this.waitForFindingsLoaded();
  }

  async waitForFindingsLoaded() {
    await expect(this.page.getByText(/completed · .* incomplete/)).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  async selectFirstFinding() {
    const row = this.page.getByRole('button', { name: /Example rule|EX-00-000001|SV-000001/i });
    await expect(row.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await row.first().click();
    await expect(this.findingDetailsField()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  async expectReviewIncomplete() {
    const submitDisabled = await this.submitButton().isDisabled();
    const warningVisible = await this.page.getByText(INCOMPLETE_TEXT).isVisible();
    expect(submitDisabled || warningVisible).toBeTruthy();
    if (warningVisible) {
      await expect(this.page.getByText(INCOMPLETE_TEXT)).toBeVisible();
    } else {
      await expect(this.submitButton()).toBeDisabled();
    }
  }

  /**
   * @param {string} text
   */
  async fillFindingDetails(text) {
    const field = this.findingDetailsField();
    await field.click();
    await field.fill(text);
  }

  async clickWrite() {
    await expect(this.writeButton()).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await this.writeButton().click();
  }

  async expectReviewComplete() {
    await expect(this.page.getByText(COMPLETE_TEXT)).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
    await expect(this.submitButton()).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { EditorRequirementsProbe, INCOMPLETE_TEXT, COMPLETE_TEXT };
