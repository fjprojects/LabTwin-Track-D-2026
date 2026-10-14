/* One isolated server lifetime for browser suites. No production URLs or DB.
 * Also works in environments where different shell cells cannot share ports. */
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'labtwin-browser-check-'));
const env = { ...process.env, LABTWIN_E2E_URL: 'http://127.0.0.1:8000', LABTWIN_E2E_BASE_URL: 'http://127.0.0.1:8000',
  LABTWIN_E2E_DATABASE: path.join(fixture, 'db.sqlite3'), LABTWIN_E2E_VECTOR_ROOT: path.join(fixture, 'vectors'), LABTWIN_E2E_MEDIA_ROOT: path.join(fixture, 'media') };
const scripts = process.argv.slice(2);
if (!scripts.length || scripts.some(script => !/^scripts\/e2e_[a-z_]+\.cjs$/.test(script))) throw new Error('Specify the repository browser test scripts.');
const server = spawn(process.env.LABTWIN_E2E_PYTHON || 'python', ['scripts/e2e_server.py'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
let output = '';
const log = process.env.LABTWIN_E2E_SERVER_LOG ? fs.createWriteStream(process.env.LABTWIN_E2E_SERVER_LOG, { mode: 0o600 }) : null;
server.stdout.on('data', chunk => { output += chunk; log?.write(chunk); });
server.stderr.on('data', chunk => log?.write(chunk));
(async () => {
  try {
    await new Promise((resolve, reject) => {
      const deadline = setTimeout(() => { clearInterval(watch); reject(new Error('Disposable server startup timed out')); }, 60000);
      const watch = setInterval(() => { if (output.includes('test server ready')) { clearInterval(watch); clearTimeout(deadline); resolve(); } }, 100);
      server.once('error', reject);
      server.once('exit', code => { clearInterval(watch); clearTimeout(deadline); reject(new Error(`Disposable server exited ${code}`)); });
    });
    for (const script of scripts) {
      await new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [script], { cwd: root, env, stdio: 'inherit' });
        child.on('error', reject); child.on('exit', code => code === 0 ? resolve() : reject(new Error(`${script}: exit ${code}`)));
      });
    }
  } finally {
    if (server.exitCode === null && server.signalCode === null) { server.kill('SIGTERM'); await new Promise(resolve => server.once('exit', resolve)); }
    log?.end(); fs.rmSync(fixture, { recursive: true, force: true });
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
