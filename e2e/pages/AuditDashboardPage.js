const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

const AUDIT_TABLE_COLUMNS = [
  'action',
  'user',
  'object',
  'workspace_id',
  'entity_type',
  'entity_id',
];

class AuditDashboardPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  async open() {
    await this.page.goto(appPath('stig_audit_dashboard'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'STIG audit' })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.getByText('Recent audit actions', { exact: true })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  recentActionsTable() {
    const panel = this.page
      .locator('.dashboard-row')
      .filter({ hasText: 'Recent audit actions' })
      .first();
    return panel.locator('table').first();
  }

  async expectRecentActionsColumns() {
    const panel = this.page
      .locator('.dashboard-row')
      .filter({ hasText: 'Recent audit actions' })
      .first();
    await expect(panel).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    for (const column of AUDIT_TABLE_COLUMNS) {
      await expect(
        panel.locator('th').filter({ hasText: new RegExp(`^${column}$`, 'i') }).first(),
      ).toBeAttached({ timeout: NAV_TIMEOUT_MS });
    }
  }
}

module.exports = { AuditDashboardPage, AUDIT_TABLE_COLUMNS };
