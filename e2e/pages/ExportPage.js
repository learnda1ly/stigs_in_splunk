const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class ExportPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  formatSelect() {
    return this.page.getByRole('combobox').nth(1);
  }

  async open() {
    await this.page.goto(appPath('stig_export_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Export checklists' })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without the "(default)" suffix).
   */
  async selectWorkspace(name) {
    const rowsReady = this.page.waitForResponse(
      (response) =>
        response.url().includes('stig_checklists') && response.status() === 200,
      { timeout: CONTROL_TIMEOUT_MS },
    );
    const select = this.workspaceSelect();
    await select.click();
    const option = this.page.getByRole('option', { name: new RegExp(escapeRegExp(name)) });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
    await rowsReady;
    await expect(this.page.getByRole('cell', { name: name }).first()).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  /**
   * @param {'cklb' | 'ckl'} format
   */
  async selectFormat(format) {
    const select = this.formatSelect();
    await select.click();
    const label = format === 'ckl' ? 'CKL (XML)' : 'CKLB (JSON)';
    const option = this.page.getByRole('option', { name: label });
    await expect(option).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.click();
  }

  /**
   * @returns {Promise<import('@playwright/test').Download>}
   */
  async downloadAllInView() {
    const downloadPromise = this.page.waitForEvent('download');
    await this.page.getByRole('button', { name: 'Download all in view' }).click();
    const download = await downloadPromise;
    const suggested = download.suggestedFilename();
    expect(suggested && suggested.length > 0).toBeTruthy();
    return download;
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { ExportPage };
