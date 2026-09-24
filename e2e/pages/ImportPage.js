const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

/** Documented selectors for baseline import coverage */
const SELECTORS = {
  viewPath: 'stig_import_ui',
  baselinesTab: 'role=tab[name="Baselines"]',
  checklistsWorkspaceCombobox: '#checklists >> role=combobox (first)',
  baselinesDropTitle: 'text=Drop DISA zip or benchmark files here',
  benchmarkFileInput: '#baselines input[type="file"] >> nth=1',
  importSuccessBanner:
    'Message containing "Imported baseline" or "Matched existing baseline" or minimal_benchmark.xml',
};

class ImportPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  baselinesPanel() {
    return this.page.locator('#baselines');
  }

  workspaceSelect() {
    return this.page.locator('#checklists').getByRole('combobox').first();
  }

  benchmarkFileInput() {
    return this.baselinesPanel().locator('input[type="file"]').nth(1);
  }

  async open() {
    await this.page.goto(appPath(SELECTORS.viewPath), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Import', level: 2 })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({ timeout: NAV_TIMEOUT_MS });
  }

  async openBaselinesTab() {
    await this.page.getByRole('tab', { name: 'Baselines' }).click();
    await expect(this.page.getByText('Drop DISA zip or benchmark files here')).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} name Workspace collection name (without "(default)" suffix).
   */
  async selectWorkspace(name) {
    await this.page.getByRole('tab', { name: 'Checklists' }).click();
    const select = this.workspaceSelect();
    await expect(select).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(name)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
    await this.openBaselinesTab();
  }

  /**
   * @param {string} absolutePath
   */
  async uploadBenchmarkFile(absolutePath) {
    await this.benchmarkFileInput().setInputFiles(absolutePath);
  }

  /**
   * @param {string} [label] STIG title or id expected in the success banner
   */
  async expectImportSucceeded(label) {
    await expect(this.page.getByText(/Import failed/i)).toHaveCount(0);
    const banner = this.page.getByText(/Imported baseline|Matched existing baseline/i).first();
    await expect(banner).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    if (label) {
      await expect(banner).toContainText(label, { timeout: CONTROL_TIMEOUT_MS });
    }
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { ImportPage, SELECTORS };
