const { test, expect } = require('@playwright/test');
const { appPath } = require('./fixtures/splunk');

test('stig editor UI root is visible', async ({ page }) => {
  await page.goto(appPath('stig_editor_ui'));
  await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: 60_000 });
});
