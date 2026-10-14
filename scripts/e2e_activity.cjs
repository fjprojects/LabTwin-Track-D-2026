/* Real answer editing, activity synchronization and teacher reports using
 * disposable local accounts. Never point this fixture at production. */
const assert = require('node:assert/strict');
const { launchBrowser } = require('./e2e_browser.cjs');
const fs = require('node:fs');
const path = require('node:path');
const origin = process.env.LABTWIN_E2E_URL || 'http://127.0.0.1:8000';
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname));

async function api(route, token, data) {
  const response = await fetch(`${origin}/api/${route}`, { method: data === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
  assert.ok(response.ok, `${route}: HTTP ${response.status}`); return response.json();
}

(async () => {
  const stamp = Date.now();
  const teacher = await api('auth/register/', null, { username: `activity-teacher-${stamp}`, name: 'Synthetic Activity Teacher', role: 'teacher', password: 'Activity-Fixture-Password-94!' });
  const student = await api('auth/register/', null, { username: `activity-student-${stamp}`, name: 'Synthetic Activity Student', role: 'student', password: 'Activity-Fixture-Password-94!' });
  const room = (await api('classrooms/', teacher.token, { name: 'Disposable activity class' })).classroom;
  await api('classrooms/join/', student.token, { code: room.join_code });
  const course = (await api('learning/courses/', teacher.token, { classroom_id: room.id, name: 'Activity and editing fixture', language: 'Python' })).course;
  const topic = (await api(`learning/courses/${course.id}/topics/`, teacher.token, { name: 'Linked Lists' })).course.topics[0];
  const file = new FormData();
  file.append('file', new Blob(['Linked Lists\nThe head pointer is the reference to the first node. A linked list is a chain of nodes. A node is a container for data and a link.']), 'activity-notes.txt'); file.append('topic_id', topic.id);
  const uploaded = await fetch(`${origin}/api/learning/courses/${course.id}/materials/`, { method: 'POST', headers: { Authorization: `Bearer ${teacher.token}` }, body: file });
  assert.equal(uploaded.status, 201); assert.equal((await uploaded.json()).material.status, 'ready');
  const browser = await launchBrowser({ headless: true, ...(process.env.LABTWIN_E2E_CHROMIUM ? { executablePath: process.env.LABTWIN_E2E_CHROMIUM } : {}), args: ['--no-sandbox'] });
  const errors = [], payloads = [];
  try {
    const sc = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'], viewport: { width: 1366, height: 900 } });
    await sc.addInitScript(token => sessionStorage.setItem('labtwin_access_token', token), student.token);
    const page = await sc.newPage(); page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.url().includes('/activity-events/') && request.method() === 'POST') payloads.push(request.postData()); });
    await page.goto(origin); await page.getByRole('navigation').getByRole('button', { name: 'Assessments', exact: true }).click();
    await page.getByText('LabTwin cannot prevent tab switching.', { exact: false }).waitFor();
    await page.getByLabel('Question format', { exact: true }).selectOption('short_answer'); await page.getByLabel('Questions', { exact: true }).fill('1');
    const starting = page.waitForResponse(r => /\/courses\/\d+\/assessments\/$/.test(r.url()) && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Start assessment', exact: true }).click();
    const session = (await (await starting).json()).assessment;
    const editor = page.getByLabel('Your short answer', { exact: true }); await editor.waitFor();
    // This is the browser's actual clipboard and editing shortcut, not a
    // dispatched paste event with a manually assigned input value.
    await page.evaluate(() => navigator.clipboard.writeText('An intentionally incomplete answer.\nSecond line.'));
    await editor.focus(); await page.keyboard.press('Control+V');
    await page.waitForFunction(() => document.querySelector('[data-assessment-answer]')?.value.includes('Second line.'));
    assert.equal(await editor.inputValue(), 'An intentionally incomplete answer.\nSecond line.');
    await page.getByText('Allowed pastes: 1', { exact: true }).waitFor();
    assert.equal(await page.getByText('Blocked paste attempts: 0', { exact: true }).count(), 1);
    await page.keyboard.press('Control+A'); await page.keyboard.press('Control+C');
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await editor.inputValue());

    // Browser-generated blur and hidden events can overlap. The departure
    // counter only follows visibility transitions. Controlled visibility is
    // explicit here because headless browsers do not consistently hide tabs.
    await page.evaluate(() => {
      window.dispatchEvent(new Event('focus'));
      window.dispatchEvent(new Event('blur')); window.dispatchEvent(new Event('blur'));
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange')); document.dispatchEvent(new Event('visibilitychange'));
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('focus'));
    });
    await page.getByText('Tab switches: 1', { exact: true }).waitFor();
    await page.getByText('Window focus losses: 1', { exact: true }).waitFor();
    await page.waitForFunction(id => !sessionStorage.getItem(`labtwin_assessment_activity_${id}`), session.id);
    const evidence = await api(`learning/assessments/${session.id}/activity-events/`, student.token);
    assert.equal(evidence.tab_switches, 1); assert.equal(evidence.focus_losses, 1); assert.equal(evidence.allowed_pastes, 1);
    assert.ok(evidence.events.every(row => row.detail.observed_at));
    await page.reload(); await page.getByRole('navigation').getByRole('button', { name: 'Assessments', exact: true }).click();
    await page.getByText(/Saved assessments/).click();
    await page.getByRole('button', { name: /diagnostic · in_progress/ }).click();
    await page.getByText('Tab switches: 1', { exact: true }).waitFor();
    await page.getByText('Window focus losses: 1', { exact: true }).waitFor();
    const before = await api(`learning/courses/${course.id}/path/`, student.token);
    assert.equal(before.topics[0].attempts, 0, 'Activity must not create mastery evidence');

    // Lose a synchronization response after the server committed it, then
    // reconnect. The same persisted ID must be accepted exactly once.
    let lost = true;
    await page.route('**/activity-events/', async route => {
      if (route.request().method() === 'POST' && lost) { lost = false; await route.fetch(); await route.abort('failed'); }
      else await route.continue();
    });
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange'));
      Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.getByText(/Activity is waiting to sync/).waitFor();
    await page.unroute('**/activity-events/'); await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.waitForFunction(id => !sessionStorage.getItem(`labtwin_assessment_activity_${id}`), session.id);
    const retried = await api(`learning/assessments/${session.id}/activity-events/`, student.token);
    assert.equal(retried.tab_switches, 2); assert.equal(new Set(retried.events.map(row => row.event_id)).size, retried.events.length);
    assert.equal((await api(`learning/courses/${course.id}/path/`, student.token)).topics[0].attempts, 0);

    const tc = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await tc.addInitScript(token => sessionStorage.setItem('labtwin_access_token', token), teacher.token);
    const teacherPage = await tc.newPage(); teacherPage.on('pageerror', error => errors.push(error.message));
    await teacherPage.goto(origin); await teacherPage.getByRole('navigation').getByRole('button', { name: 'Assessments', exact: true }).click();
    const reportRow = teacherPage.getByRole('row').filter({ hasText: 'Synthetic Activity Student' });
    const cells = await reportRow.getByRole('cell').allTextContents();
    assert.equal(cells[2], '2'); assert.equal(cells[3], '1'); assert.equal(cells[4], '1 / 0');
    await reportRow.getByRole('button', { name: /Review assessment/ }).click();
    await teacherPage.getByText('Device-reported:', { exact: false }).first().waitFor();
    await teacherPage.getByText('paste allowed', { exact: true }).waitFor();
    assert.ok(payloads.every(body => !body.includes('An intentionally incomplete answer') && !body.includes('Second line.')));
    assert.deepEqual(errors, []);
    if (process.env.LABTWIN_UI_SCREENSHOTS) { fs.mkdirSync(process.env.LABTWIN_UI_SCREENSHOTS, { recursive: true }); await teacherPage.screenshot({ path: path.join(process.env.LABTWIN_UI_SCREENSHOTS, 'teacher-activity-timeline.png') }); }
    console.log('PASS: native answer copy/paste, multiline editing, controlled overlapping visibility/focus events, persisted counts after refresh, lost-response retry, teacher counts/timeline, metadata privacy and no activity mastery effect.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
