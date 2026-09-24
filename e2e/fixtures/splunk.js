/**
 * @param {string} view Splunk app view name (e.g. stig_editor_ui, configuration)
 * @returns {string} Path under /en-US/app/stigs_in_splunk/
 */
function appPath(view) {
  return `/en-US/app/stigs_in_splunk/${view}`;
}

module.exports = {
  appPath,
};
