const path = require('path');

const ADMIN_STORAGE_STATE_PATH = path.join(__dirname, '..', '.auth', 'admin.json');

function getSplunkBaseUrl() {
  return process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000';
}

module.exports = {
  ADMIN_STORAGE_STATE_PATH,
  getSplunkBaseUrl,
};
