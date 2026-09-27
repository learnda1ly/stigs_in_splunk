const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const {
  workspaceCombobox,
  selectWorkspaceOption,
  expectWorkspaceOptionSelected,
} = require('../helpers/workspaceSelect');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class EditorPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return workspaceCombobox(this.page);
  }

  async open() {
    await this.page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without the "(default)" suffix).
   */
  async selectWorkspace(name) {
    await selectWorkspaceOption(this.page, this.workspaceSelect(), name, CONTROL_TIMEOUT_MS);
  }

  /**
   * @param {string} name
   */
  async expectWorkspaceSelected(name) {
    await expectWorkspaceOptionSelected(this.workspaceSelect(), name, CONTROL_TIMEOUT_MS);
  }
}

module.exports = { EditorPage };
