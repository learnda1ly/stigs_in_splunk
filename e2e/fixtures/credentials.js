const fs = require('fs');
const path = require('path');

const CREDENTIALS_FILE = path.join(__dirname, '..', '.auth', 'credentials.json');

/**
 * Admin credentials for Splunk Web login and management REST (8089).
 * Prefers env vars; falls back to gitignored e2e/.auth/credentials.json on the worker.
 */
function loadAdminCredentials() {
  let user = process.env.SPLUNK_ADMIN_USER || process.env.SPLUNK_USERNAME || 'admin';
  let password = process.env.SPLUNK_ADMIN_PASSWORD || process.env.SPLUNK_PASSWORD || '';

  if (!password && fs.existsSync(CREDENTIALS_FILE)) {
    const data = JSON.parse(fs.readFileSync(CREDENTIALS_FILE, 'utf8'));
    user = data.user || data.username || user;
    password = data.password || password;
  }

  return { user, password: password || undefined };
}

function requireAdminCredentials() {
  const creds = loadAdminCredentials();
  if (!creds.user || !creds.password) {
    throw new Error(
      'Splunk admin credentials required: set SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD ' +
        '(SPLUNK_PASSWORD is also accepted) or create e2e/.auth/credentials.json with ' +
        '{"user":"admin","password":"..."}.',
    );
  }
  return creds;
}

function restAuthHeader() {
  const { user, password } = requireAdminCredentials();
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`,
  };
}

module.exports = {
  loadAdminCredentials,
  requireAdminCredentials,
  restAuthHeader,
};
