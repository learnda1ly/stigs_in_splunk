const fs = require('fs');

const TEST_PASSWORD = 'PlaywrightTest!2026';
const ASSESSOR_USER = 'stig_pw_assessor';
const REVIEWER_USER = 'stig_pw_reviewer';

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  `${(process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089')}/servicesNS/nobody/stigs_in_splunk`;

const AUTH_USERS_URL = 'https://127.0.0.1:8089/services/authentication/users';

function restAuthHeader() {
  const user = process.env.SPLUNK_ADMIN_USER;
  const password = process.env.SPLUNK_ADMIN_PASSWORD;
  if (!user || !password) {
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required');
  }
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`,
  };
}

function adminCredentials() {
  const user = process.env.SPLUNK_ADMIN_USER;
  const password = process.env.SPLUNK_ADMIN_PASSWORD;
  if (!user || !password) {
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required');
  }
  return { user, password };
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} username
 * @param {string} [password]
 */
async function splunkLogin(page, username, password = TEST_PASSWORD) {
  await page.goto('/en-US/account/login', { timeout: 60_000 });
  await page.locator('input[name=username]').fill(username);
  await page.locator('input[name=password]').fill(password);
  await page.locator('input[type=submit].splButton-primary').first().click();
  await page.waitForURL((url) => !url.pathname.includes('/account/login'), {
    timeout: 60_000,
  });
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function splunkLoginAdmin(page) {
  const { user, password } = adminCredentials();
  await splunkLogin(page, user, password);
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 */
async function ensureSplunkUsers(request) {
  const headers = restAuthHeader();
  for (const name of [ASSESSOR_USER, REVIEWER_USER]) {
    const response = await request.post(AUTH_USERS_URL, {
      headers: { ...headers, 'Content-Type': 'application/x-www-form-urlencoded' },
      form: {
        name,
        password: TEST_PASSWORD,
        roles: 'stig_user',
      },
      ignoreHTTPSErrors: true,
    });
    if (!response.ok() && response.status() !== 409 && response.status() !== 400) {
      throw new Error(`Failed to ensure user ${name}: HTTP ${response.status()}`);
    }
  }
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} workspaceName
 */
async function findCollectionIdByName(request, workspaceName) {
  const headers = restAuthHeader();
  const response = await request.get(`${REST_BASE}/stig_collections?output_mode=json`, {
    headers,
    ignoreHTTPSErrors: true,
  });
  if (!response.ok()) {
    throw new Error(`list collections failed: HTTP ${response.status()}`);
  }
  const rows = await response.json();
  const match = Array.isArray(rows) ? rows.find((row) => row.name === workspaceName) : null;
  if (!match?._key) {
    throw new Error(`workspace not found: ${workspaceName}`);
  }
  return match._key;
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} collectionId
 * @param {string} hostname
 */
async function findHostId(request, collectionId, hostname) {
  const headers = restAuthHeader();
  const response = await request.get(
    `${REST_BASE}/stig_hosts?output_mode=json&stig_collection_id=${encodeURIComponent(collectionId)}`,
    { headers, ignoreHTTPSErrors: true },
  );
  if (!response.ok()) {
    throw new Error(`list hosts failed: HTTP ${response.status()}`);
  }
  const rows = await response.json();
  const match = Array.isArray(rows)
    ? rows.find((row) => row.hostname === hostname && row.stig_collection_id === collectionId)
    : null;
  if (!match?._key) {
    throw new Error(`host not found: ${hostname} in ${collectionId}`);
  }
  return match._key;
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} collectionId
 * @param {string} [stigId]
 */
async function findBaselineId(request, collectionId, stigId = 'Example_STIG') {
  const headers = restAuthHeader();
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = await request.get(`${REST_BASE}/stig_baselines?output_mode=json`, {
      headers,
      ignoreHTTPSErrors: true,
    });
    if (!response.ok()) {
      throw new Error(`list baselines failed: HTTP ${response.status()}`);
    }
    const rows = await response.json();
    const matches = Array.isArray(rows)
      ? rows.filter(
          (row) => row.stig_id === stigId && String(row.stig_collection_id) === String(collectionId),
        )
      : [];
    if (matches.length) {
      const preferred = matches.find(
        (row) =>
          row.source_filename === 'minimal_benchmark.xml' ||
          String(row.source_uri || '').includes('minimal_benchmark'),
      );
      const chosen = preferred || matches[matches.length - 1];
      if (chosen._key) {
        return chosen._key;
      }
    }
    await new Promise((resolve) => {
      setTimeout(resolve, 500);
    });
  }
  throw new Error(`baseline not found: ${stigId} in ${collectionId}`);
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} collectionId
 */
async function deleteWorkspaceCascade(request, collectionId) {
  if (!collectionId) {
    return false;
  }
  const headers = restAuthHeader();
  const response = await request.delete(
    `${REST_BASE}/stig_collections/${encodeURIComponent(collectionId)}?cascade=true&output_mode=json`,
    { headers, ignoreHTTPSErrors: true },
  );
  return response.ok();
}

/**
 * @param {import('@playwright/test').Download} download
 * @param {string} hostname
 */
async function expectDownloadContainsHost(download, hostname) {
  const filePath = await download.path();
  if (!filePath) {
    throw new Error('download path missing');
  }
  const raw = fs.readFileSync(filePath, 'utf8');
  if (!raw.includes(hostname)) {
    throw new Error(`export did not contain hostname ${hostname}`);
  }
}

module.exports = {
  TEST_PASSWORD,
  ASSESSOR_USER,
  REVIEWER_USER,
  splunkLogin,
  splunkLoginAdmin,
  ensureSplunkUsers,
  findCollectionIdByName,
  findHostId,
  findBaselineId,
  deleteWorkspaceCascade,
  expectDownloadContainsHost,
};
