const { test } = require('@playwright/test');
const { AuditDashboardPage } = require('../pages/AuditDashboardPage');

test.use({ trace: 'off', video: 'off' });

test.describe('STIG audit dashboard', () => {
  test.setTimeout(120_000);

  test('recent actions table exposes audit fields', async ({ page }) => {
    const audit = new AuditDashboardPage(page);
    await audit.open();
    await audit.expectRecentActionsColumns();
  });
});
