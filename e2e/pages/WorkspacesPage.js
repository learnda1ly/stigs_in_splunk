const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const ROW_TIMEOUT_MS = 30_000;

class WorkspacesPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  async open() {
    await this.page.goto(appPath('configuration'), { timeout: NAV_TIMEOUT_MS });
    await this.page.getByRole('tab', { name: 'Workspaces' }).click();
    await expect(this.page.getByRole('columnheader', { name: 'Name' })).toBeVisible({
      timeout: ROW_TIMEOUT_MS,
    });
  }

  /**
   * @param {{ name: string, description?: string, isDefault?: boolean }} opts
   */
  async createWorkspace({ name, description = '', isDefault = false }) {
    await this.page.getByRole('button', { name: 'Add', exact: true }).click();
    const dialog = this.page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: ROW_TIMEOUT_MS });
    await expect(dialog).toContainText('Add workspace');

    const fields = dialog.getByRole('textbox');
    await fields.nth(0).fill(name);
    if (description) {
      await fields.nth(1).fill(description);
    }

    const defaultCheckbox = dialog.getByRole('checkbox');
    if (isDefault) {
      await defaultCheckbox.check();
    } else {
      await defaultCheckbox.uncheck();
    }

    await dialog.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(dialog).toBeHidden({ timeout: ROW_TIMEOUT_MS });
    await this.expectRow(name, { isDefault });
  }

  /**
   * @param {string} name
   * @param {{ isDefault?: boolean }} [opts]
   */
  async expectRow(name, { isDefault = false } = {}) {
    const row = this.page.getByRole('row', { name: new RegExp(name) });
    await expect(row.first()).toBeVisible({ timeout: ROW_TIMEOUT_MS });
    await expect(row.first()).toContainText(name);
    if (isDefault) {
      await expect(row.first().getByRole('cell').nth(2)).toHaveText('1', {
        timeout: ROW_TIMEOUT_MS,
      });
    }
  }

  /**
   * @param {string} name
   */
  async deleteWorkspace(name) {
    const row = this.page.getByRole('row', { name: new RegExp(name) });
    await expect(row.first()).toBeVisible({ timeout: ROW_TIMEOUT_MS });
    await row.first().getByTestId('delete-button').click();

    const confirm = this.page.getByRole('dialog').filter({ hasText: 'Delete workspace' });
    await expect(confirm).toBeVisible({ timeout: ROW_TIMEOUT_MS });
    await confirm.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(row.first()).toBeHidden({ timeout: ROW_TIMEOUT_MS });
  }
}

module.exports = { WorkspacesPage };
