const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const { workspaceCombobox, selectWorkspaceOption } = require('../helpers/workspaceSelect');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

/** Documented selectors for labels-hosts coverage */
const SELECTORS = {
  viewPath: 'stig_hosts_ui',
  workspaceCombobox: 'role=combobox (first)',
  addHostButton: 'role=button[name="Add host"]',
  hostnameField: 'role=textbox nth(1) after opening Add host (after Filter field)',
  createHostButton: 'role=button[name="Create host"]',
  hostsTable: 'role=table with Hostname column header',
};

class HostsPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return workspaceCombobox(this.page);
  }

  hostsTable() {
    return this.page.getByRole('table').filter({
      has: this.page.getByRole('columnheader', { name: 'Hostname' }),
    });
  }

  async open() {
    await this.page.goto(appPath(SELECTORS.viewPath), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Hosts', level: 2 })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without "(default)" suffix).
   */
  async selectWorkspace(name) {
    await selectWorkspaceOption(this.page, this.workspaceSelect(), name, CONTROL_TIMEOUT_MS);
  }

  /**
   * @param {string} hostname
   */
  async createHost(hostname) {
    await this.page.getByRole('button', { name: 'Add host' }).click();
    // Toolbar "Filter" is the first textbox; add-host "Hostname" is the second.
    await this.page.getByRole('textbox').nth(1).fill(hostname);
    await this.page.getByRole('button', { name: 'Create host' }).click();
    await this.expectHostRowVisible(hostname);
  }

  /**
   * @param {string} hostname
   */
  async expectHostRowVisible(hostname) {
    const row = this.hostsTable().getByRole('row').filter({ hasText: hostname });
    await expect(row.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }
}

module.exports = { HostsPage, SELECTORS: { ...SELECTORS, page: 'HostsPage' } };
