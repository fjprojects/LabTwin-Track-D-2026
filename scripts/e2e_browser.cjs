/* Optional restricted-runtime adapter. Normal CI uses ordinary Playwright.
 * Chromium single-process mode needs a distinct browser per isolated context. */
const { chromium } = require('playwright');
exports.launchBrowser = async options => {
  if (process.env.LABTWIN_E2E_SINGLE_PROCESS !== '1') return chromium.launch(options);
  const instances = [];
  return {
    async newContext(config) {
      const browser = await chromium.launch({ ...options, args: [...(options.args || []), '--single-process', '--no-zygote'] });
      instances.push(browser); return browser.newContext(config);
    },
    async close() { await Promise.all(instances.map(browser => browser.close())); },
  };
};
