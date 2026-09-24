const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class ReviewRequirementsPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  async open() {
    await this.page.goto(appPath('stig_review_requirements_ui'), {
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.getByRole('button', { name: 'Save', exact: true })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  /**
   * @param {string} name Workspace collection name (without "(default)" suffix).
   */
  async selectWorkspace(name) {
    const select = this.workspaceSelect();
    await select.click();
    const option = this.page.getByRole('option', {
      name: new RegExp(escapeRegExp(name)),
    });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
  }

  requireFindingDetailsCheckbox() {
    return this.page.getByRole('checkbox').first();
  }

  minFindingDetailsLengthInput() {
    return this.page.getByRole('textbox').first();
  }

  /**
   * @param {boolean} enabled
   */
  async setRequireFindingDetails(enabled) {
    const box = this.requireFindingDetailsCheckbox();
    await expect(box).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    if (enabled) {
      await box.check();
    } else {
      await box.uncheck();
    }
    if (enabled) {
      await expect(box).toBeChecked({ timeout: CONTROL_TIMEOUT_MS });
    } else {
      await expect(box).not.toBeChecked({ timeout: CONTROL_TIMEOUT_MS });
    }
  }

  /**
   * @param {number} length
   */
  async setMinFindingDetailsLength(length) {
    const field = this.minFindingDetailsLengthInput();
    await expect(field).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    await field.fill(String(length));
    await expect(field).toHaveValue(String(length));
  }

  async save() {
    await this.page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(this.page.getByText('Saved review requirements for this workspace.')).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  async expectSavedOrPersisted(workspaceName, minLength = 20) {
    try {
      await expect(this.page.getByText('Saved review requirements for this workspace.')).toBeVisible({
        timeout: 5000,
      });
    } catch {
      await this.page.reload();
      await expect(this.page.locator('#stig-ui-root')).toBeVisible({
        timeout: NAV_TIMEOUT_MS,
      });
      await expect(this.page.getByRole('button', { name: 'Save', exact: true })).toBeVisible({
        timeout: NAV_TIMEOUT_MS,
      });
      await this.selectWorkspace(workspaceName);
      await this.expectRequireFindingDetailsOn(true, minLength);
    }
  }

  /**
   * @param {boolean} [on]
   * @param {number} [minLength]
   */
  async expectRequireFindingDetailsOn(on = true, minLength = 20) {
    const box = this.requireFindingDetailsCheckbox();
    if (on) {
      await expect(box).toBeChecked({ timeout: CONTROL_TIMEOUT_MS });
    } else {
      await expect(box).not.toBeChecked({ timeout: CONTROL_TIMEOUT_MS });
    }
    if (on) {
      await expect(this.minFindingDetailsLengthInput()).toHaveValue(String(minLength), {
        timeout: CONTROL_TIMEOUT_MS,
      });
    }
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { ReviewRequirementsPage };
