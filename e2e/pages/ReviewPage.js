const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class ReviewPage {
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

  findingField() {
    return this.page.locator('#stig-finding');
  }

  commentsField() {
    return this.page.locator('#stig-comments');
  }

  rejectFeedbackField() {
    return this.page.getByPlaceholder('Optional feedback when rejecting');
  }

  async open(query = '') {
    const suffix = query ? `?${query}` : '';
    await this.page.goto(appPath('stig_editor_ui') + suffix, {
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without the "(default)" suffix).
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

  async expectWorkspaceSelected(name) {
    await expect(this.workspaceSelect()).toContainText(name, {
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  async expectHostSelected(hostname) {
    await expect(this.hostSelect()).toContainText(hostname, {
      timeout: CONTROL_TIMEOUT_MS,
    });
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
  }

  async waitForFindingList() {
    const row = this.page.locator('button[data-key]').first();
    await expect(row).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} [ruleVersion] e.g. EX-00-000001
   */
  async selectFinding(ruleVersion) {
    await this.waitForFindingList();
    const row = ruleVersion
      ? this.page.locator('button[data-key]').filter({
          hasText: new RegExp(escapeRegExp(ruleVersion)),
        })
      : this.page.locator('button[data-key]').first();
    await expect(row.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await row.first().click();
    await expect(this.findingField()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} statusKey not_reviewed | open | not_a_finding | not_applicable
   */
  async selectStatus(statusKey) {
    const select = this.page.getByRole('combobox', { name: /Status/i });
    await select.click();
    const labels = {
      not_reviewed: 'Not Reviewed',
      open: 'Open',
      not_a_finding: 'Not a Finding',
      not_applicable: 'Not Applicable',
    };
    const label = labels[statusKey] || statusKey;
    await this.page.getByRole('option', { name: label, exact: true }).click();
  }

  async fillFinding(text) {
    const field = this.findingField();
    await field.fill(text);
  }

  async fillComments(text) {
    const field = this.commentsField();
    await field.fill(text);
  }

  writeButton() {
    return this.page.getByRole('button', { name: 'Write', exact: true });
  }

  submitButton() {
    return this.page.getByRole('button', { name: 'Submit', exact: true });
  }

  acceptButton() {
    return this.page.getByRole('button', { name: 'Accept', exact: true });
  }

  rejectButton() {
    return this.page.getByRole('button', { name: 'Reject', exact: true });
  }

  async clickWrite() {
    const btn = this.writeButton();
    await expect(btn).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await btn.click();
    const success = this.page.getByText('Wrote finding details and comments.');
    const failure = this.page.getByText(/Write failed:/);
    try {
      await expect(success).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    } catch (writeError) {
      if (await failure.isVisible().catch(() => false)) {
        const message = (await failure.textContent()) || '';
        expect(
          message,
          'BUG STIG-MEMBER-WRITE-404: workspace member with stig_user cannot Write; API returns {"error":"not found"} when stig_write capability is missing from the Splunk role (check authorize.conf / role_stig_user merge)',
        ).not.toMatch(/not found/i);
      }
      throw writeError;
    }
  }

  async clickSubmit() {
    const btn = this.submitButton();
    await expect(btn).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await btn.click();
    await expect(this.page.getByText(/Review submit/)).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  async fillRejectFeedback(text) {
    await this.rejectFeedbackField().fill(text);
  }

  async clickReject() {
    const btn = this.rejectButton();
    await expect(btn).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await btn.click();
    await expect(this.page.getByText(/Review reject/)).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  async clickAccept() {
    const btn = this.acceptButton();
    await expect(btn).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await btn.click();
    await expect(this.page.getByText(/Review accept/)).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} feedback
   */
  async expectRejectFeedbackVisible(feedback) {
    await expect(this.page.getByText(`Reject feedback: ${feedback}`)).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { ReviewPage };
