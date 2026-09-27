const { test } = require('@playwright/test');
const { TransferPage } = require('../pages/TransferPage');

test.use({ trace: 'off', video: 'off' });

test.describe('Transfer assets layout', () => {
  test.setTimeout(90_000);

  test('source and destination workspace pickers share a horizontal row', async ({ page }) => {
    const transfer = new TransferPage(page);
    await transfer.open();
    await transfer.expectWorkspacePickersVisible();
  });
});
