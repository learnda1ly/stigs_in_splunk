const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

/** Documented selectors for labels-hosts coverage */
const SELECTORS = {
  viewPath: 'stig_labels_ui',
  workspaceCombobox: 'role=combobox (first)',
  addLabelButton: 'role=button[name="Add label"]',
  newLabelNameField: 'New label heading parent panel first textbox',
  createLabelButton: 'role=button[name="Create label"]',
  filterHostsByLabelCombobox: 'role=combobox (nth=1, Filter hosts by label)',
  hostAssignmentTable: 'role=table with Select + Hostname headers',
  perHostLabelToggle: 'checkbox in host row under label column header',
};

class LabelsPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  filterByLabelSelect() {
    return this.page.getByRole('combobox').nth(1);
  }

  hostAssignmentTable() {
    return this.page.getByRole('table').filter({
      has: this.page.getByRole('columnheader', { name: 'Select' }),
    });
  }

  async open() {
    await this.page.goto(appPath(SELECTORS.viewPath), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Asset labels', level: 1 })).toBeVisible(
      {
        timeout: NAV_TIMEOUT_MS,
      },
    );
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
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
    await expect(this.page.getByRole('heading', { name: 'Assign labels to hosts' })).toBeVisible(
      {
        timeout: CONTROL_TIMEOUT_MS,
      },
    );
  }

  /**
   * @param {string} labelName
   */
  async createLabel(labelName) {
    await this.page.getByRole('button', { name: 'Add label' }).click();
    const panel = this.page.getByRole('heading', { name: 'New label' }).locator('..');
    await panel.getByRole('textbox').first().fill(labelName);
    await panel.getByRole('button', { name: 'Create label' }).click();
    await expect(
      this.hostAssignmentTable().getByRole('columnheader', { name: labelName }),
    ).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * Toggle the per-host label column switch (assigns one label to one host).
   * @param {string} hostname
   * @param {string} labelName
   * @param {boolean} [assign=true]
   */
  async setHostLabelToggle(hostname, labelName, assign = true) {
    const table = this.hostAssignmentTable();
    const row = table.getByRole('row').filter({ hasText: hostname }).first();
    await expect(row).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });

    const headers = table.getByRole('columnheader');
    const count = await headers.count();
    let columnIndex = -1;
    for (let i = 0; i < count; i += 1) {
      const label = (await headers.nth(i).innerText()).trim();
      if (label === labelName) {
        columnIndex = i;
        break;
      }
    }
    if (columnIndex < 0) {
      throw new Error(`Label column not found: ${labelName}`);
    }

    const cell = row.getByRole('cell').nth(columnIndex);
    const toggle = cell.getByRole('checkbox').or(cell.getByRole('switch'));
    const selected = await toggle.getAttribute('aria-checked');
    const isOn = selected === 'true';
    if (assign !== isOn) {
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-checked', assign ? 'true' : 'false', {
        timeout: CONTROL_TIMEOUT_MS,
      });
    }
  }

  /**
   * @param {string} labelName Pass empty string for "All hosts".
   */
  async filterHostsByLabel(labelName) {
    const select = this.filterByLabelSelect();
    await select.click();
    const optionName = labelName ? labelName : 'All hosts';
    await this.page.getByRole('option', { name: optionName, exact: true }).click();
    await expect(select).toContainText(optionName, { timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} hostname
   */
  async expectHostInAssignmentTable(hostname) {
    const row = this.hostAssignmentTable().getByRole('row').filter({ hasText: hostname });
    await expect(row.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} hostname
   */
  async expectHostAbsentFromAssignmentTable(hostname) {
    const row = this.hostAssignmentTable().getByRole('row').filter({ hasText: hostname });
    await expect(row).toHaveCount(0, { timeout: CONTROL_TIMEOUT_MS });
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { LabelsPage, SELECTORS: { ...SELECTORS, page: 'LabelsPage' } };
