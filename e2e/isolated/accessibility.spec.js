const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const UI_TIMEOUT_MS = 60_000;

const UX3_VIEWS = [
  { path: 'stig_meta_collection_dashboard_ui', heading: 'Overview' },
  { path: 'stig_editor_ui', heading: 'Assess' },
  { path: 'stig_collection_review_ui', heading: 'Review' },
  { path: 'stig_collection_dashboard_ui', heading: 'Reports' },
  { path: 'stig_import_ui', heading: 'Import results' },
  { path: 'stig_library_ui', heading: 'STIG library' },
  { path: 'stig_hosts_ui', heading: 'Hosts' },
  { path: 'stig_documentation_ui', heading: 'STIG in Splunk' },
];

test.describe('Accessibility (axe)', () => {
  test.setTimeout(240_000);

  test('skip link moves focus to main content on Assess', async ({ page }) => {
    await page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });

    const skip = page.locator('#stig-skip-link');
    await expect(skip).toBeAttached();
    await skip.focus();
    await expect(skip).toBeFocused();

    await skip.click();
    const main = page.locator('#stig-main-content');
    await expect(main).toBeFocused({ timeout: UI_TIMEOUT_MS });
  });

  for (const view of UX3_VIEWS) {
    test(`axe: ${view.path} has no critical violations`, async ({ page }) => {
      await page.goto(appPath(view.path), { timeout: NAV_TIMEOUT_MS });
      await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });

      const results = await new AxeBuilder({ page })
        .include('#stig-ui-root')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const blocking = results.violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious',
      );
      expect(
        blocking,
        blocking.map((v) => `${v.id}: ${v.help} (${v.nodes.length} nodes)`).join('\n'),
      ).toEqual([]);
    });
  }
});
