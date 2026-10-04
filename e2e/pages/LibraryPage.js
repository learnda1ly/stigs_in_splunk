const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

/** Documented selectors for STIG library coverage */
const SELECTORS = {
  viewPath: 'stig_library_ui',
  workspaceFilterCombobox: 'role=combobox (library workspace filter; option "All visible catalogs")',
  benchmarksTable: 'role=table with columnheader "STIG / benchmark"',
  benchmarkStigCell: 'benchmarks table strong text (stig_id)',
  benchmarkFileInput: '#add-revisions input[type="file"] >> nth=1',
};

class LibraryPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceFilterSelect() {
    return this.page.getByRole('combobox').first();
  }

  benchmarksTable() {
    return this.page.getByRole('table').filter({
      has: this.page.getByRole('columnheader', { name: 'STIG / benchmark' }),
    });
  }

  async open() {
    await this.page.goto(appPath(SELECTORS.viewPath), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'STIG library', level: 1 })).toBeVisible(
      {
        timeout: NAV_TIMEOUT_MS,
      },
    );
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await expect(this.benchmarksTable()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without "(default)" suffix).
   */
  async selectWorkspaceFilter(name) {
    const select = this.workspaceFilterSelect();
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(name)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} stigId e.g. Example_STIG
   * @param {string} [title] optional benchmark title from fixture
   */
  async expectBenchmarkVisible(stigId, title) {
    const table = this.benchmarksTable();
    await expect(table.getByText(stigId, { exact: true })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
    if (title) {
      await expect(table.getByText(title)).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    }
  }

  benchmarkImportInput() {
    return this.page.locator(SELECTORS.benchmarkFileInput);
  }

  /**
   * @param {string} absolutePath
   */
  async uploadBenchmarkFile(absolutePath) {
    await expect(this.page.getByRole('heading', { name: 'Add revisions' })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
    await this.benchmarkImportInput().setInputFiles(absolutePath);
  }

  /**
   * @param {string} [label] STIG title or id expected in the success banner
   */
  async expectImportSucceeded(label) {
    await expect(this.page.getByText(/Import failed/i)).toHaveCount(0);
    const banner = this.page
      .getByText(/^Imported baseline .+\.$|^Matched existing baseline \(.+\)\.$/)
      .first();
    await expect(banner).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    if (label) {
      await expect(banner).toContainText(label, { timeout: CONTROL_TIMEOUT_MS });
    }
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { LibraryPage, SELECTORS };
