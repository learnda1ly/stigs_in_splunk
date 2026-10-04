const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const { selectWorkspaceOption } = require('../helpers/workspaceSelect');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

/** Documented selectors for checklist import coverage */
const SELECTORS = {
  viewPath: 'stig_import_ui',
  checklistsWorkspaceCombobox: '#checklists >> role=combobox (first)',
};

class ImportPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.locator('#checklists').getByRole('combobox').first();
  }

  async open() {
    await this.page.goto(appPath(SELECTORS.viewPath), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Import results', level: 2 })).toBeVisible(
      {
        timeout: NAV_TIMEOUT_MS,
      },
    );
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({ timeout: NAV_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without "(default)" suffix).
   */
  async selectWorkspace(name) {
    const select = this.workspaceSelect();
    await expect(select).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await selectWorkspaceOption(this.page, select, name, CONTROL_TIMEOUT_MS);
  }
}

module.exports = { ImportPage, SELECTORS };
