const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class TransferPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  sourceWorkspaceSelect() {
    return this.page
      .locator('#stig-ui-root')
      .getByRole('combobox', { name: 'Source workspace' });
  }

  destinationWorkspaceSelect() {
    return this.page
      .locator('#stig-ui-root')
      .getByRole('combobox', { name: 'Destination workspace' });
  }

  async open() {
    await this.page.goto(appPath('stig_transfer_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({ timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Transfer assets' })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  /** Horizontal transfer form: source and destination pickers visible together. */
  async expectWorkspacePickersVisible() {
    const source = this.sourceWorkspaceSelect();
    const dest = this.destinationWorkspaceSelect();
    await expect(source).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await expect(dest).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    const sourceBox = await source.boundingBox();
    const destBox = await dest.boundingBox();
    expect(sourceBox).toBeTruthy();
    expect(destBox).toBeTruthy();
    const verticallySeparated =
      Math.abs(sourceBox.y - destBox.y) > Math.min(sourceBox.height, destBox.height) * 0.75;
    expect(verticallySeparated).toBe(false);
  }
}

module.exports = { TransferPage };
