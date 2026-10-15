/* Lost replies and browser refresh must preserve synthetic saved work exactly
 * once. Requires the disposable local test server; never production. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { launchBrowser } = require('./e2e_browser.cjs');
const origin = process.env.LABTWIN_E2E_URL || 'http://127.0.0.1:8000';
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname));

async function api(route, token, data, expected = 200) {
  const response = await fetch(`${origin}/api/${route}`, {
    method: data === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  });
  assert.equal(response.status, expected, `${route}: HTTP ${response.status}`);
  return response.json();
}

(async () => {
  const stamp = Date.now(), password = 'Synthetic-Recovery-Fixture-94!';
  const teacher = await api('auth/register/', null, { username: `recovery-teacher-${stamp}`, name: 'Synthetic Recovery Teacher', role: 'teacher', password });
  const student = await api('auth/register/', null, { username: `recovery-student-${stamp}`, name: 'Synthetic Recovery Student', role: 'student', password });
  const practiceStudent = await api('auth/register/', null, { username: `recovery-practice-${stamp}`, name: 'Synthetic Practice Student', role: 'student', password });
  const room = (await api('classrooms/', teacher.token, { name: 'Disposable recovery class' }, 201)).classroom;
  for (const account of [student, practiceStudent]) await api('classrooms/join/', account.token, { code: room.join_code });
  const course = (await api('learning/courses/', teacher.token, { classroom_id: room.id, name: 'Recovery fixture course', language: 'Python' }, 201)).course;
  const topic = (await api(`learning/courses/${course.id}/topics/`, teacher.token, { name: 'Pointers' }, 201)).course.topics[0];
  for (const [prompt, accepted] of [
    ['Which pointer identifies the first node of a linked list?', 'head'],
    ['What link value marks the end of a linked list?', 'null'],
  ]) await api(`learning/topics/${topic.id}/bank/`, teacher.token, {
    kind: 'short_answer', prompt, answer: { accepted: [accepted] },
    explanation: `The teacher's accepted answer is ${accepted}.`,
  }, 201);
  const browser = await launchBrowser({ headless: true, args: ['--no-sandbox'],
    ...(process.env.LABTWIN_E2E_CHROMIUM ? { executablePath: process.env.LABTWIN_E2E_CHROMIUM } : {}) });
  const errors = [], requestIds = [];
  const screenshot = async (page, name) => {
    if (!process.env.LABTWIN_UI_SCREENSHOTS) return;
    fs.mkdirSync(process.env.LABTWIN_UI_SCREENSHOTS, { recursive: true });
    await page.screenshot({ path: path.join(process.env.LABTWIN_UI_SCREENSHOTS, name + '.png'), fullPage: true });
  };
  async function pageFor(account) {
    const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await context.addInitScript(token => sessionStorage.setItem('labtwin_access_token', token), account.token);
    const page = await context.newPage(); page.setDefaultTimeout(20000);
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin); return page;
  }
  const nav = (page, name) => page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
  async function loseOneReply(page, questionId) {
    let lost = false;
    await page.route(`**/questions/${questionId}/attempts/`, async route => {
      if (route.request().method() !== 'POST') return route.continue();
      requestIds.push(JSON.parse(route.request().postData()).request_id);
      if (!lost) { lost = true; await route.fetch(); await route.abort('failed'); }
      else await route.continue();
    });
  }
  try {
    const page = await pageFor(student);
    await nav(page, 'Assessments');
    await page.getByLabel('Question format', { exact: true }).selectOption('short_answer');
    await page.getByLabel('Questions', { exact: true }).fill('2');
    const starting = page.waitForResponse(r => /\/courses\/\d+\/assessments\/$/.test(r.url()) && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Start assessment', exact: true }).click();
    const session = (await (await starting).json()).assessment;
    assert.equal(session.questions.length, 2);
    const editors = page.getByLabel('Your short answer', { exact: true });
    const savedAnswer = 'Saved response\nSecond line.', draft = 'Unsubmitted draft\nKeep this work.';
    await editors.nth(0).fill(savedAnswer); await editors.nth(1).fill(draft);
    await loseOneReply(page, session.questions[0].id);
    await page.getByRole('button', { name: 'Submit answer 1', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: /connection|timed out/i }).waitFor();
    await page.getByRole('button', { name: 'Submit answer 1', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('[data-assessment-answer]')[0]?.disabled);
    assert.equal(await editors.nth(0).inputValue(), savedAnswer);
    assert.equal(await editors.nth(1).inputValue(), draft);
    assert.equal(requestIds.length, 2); assert.equal(requestIds[0], requestIds[1], 'Retry must reuse the same request ID');
    const attempts = await api(`learning/questions/${session.questions[0].id}/attempts/`, student.token);
    assert.equal(attempts.attempts.length, 1, 'Lost reply must not duplicate an attempt');
    assert.equal((await api(`learning/courses/${course.id}/path/`, student.token)).topics[0].attempts, 0, 'Unreviewed open answers must not receive mastery credit');
    await page.getByRole('button', { name: 'Refresh assessment status', exact: true }).click();
    await page.getByRole('button', { name: 'Refresh assessment status', exact: true }).waitFor();
    assert.equal(await editors.nth(1).inputValue(), draft);
    await page.reload(); await nav(page, 'Assessments');
    await page.getByText(/Saved assessments/).click();
    await page.getByRole('button', { name: /diagnostic · in_progress/ }).click();
    await page.waitForFunction(() => document.querySelectorAll('[data-assessment-answer]')[0]?.disabled);
    assert.equal(await editors.nth(0).inputValue(), savedAnswer);
    assert.equal(await editors.nth(1).inputValue(), draft);
    await page.getByText('Awaiting teacher review', { exact: true }).waitFor();
    await screenshot(page, 'assessment-restored-desktop');
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      await screenshot(page, `assessment-restored-${width}`);
    }
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.getByRole('button', { name: 'Submit answer 2', exact: true }).click();
    await page.getByRole('heading', { name: 'Assessment report', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: /^Submit answer/ }).count(), 0);
    const completed = (await api(`learning/assessments/${session.id}/`, student.token)).assessment;
    await page.getByRole('button', { name: 'Refresh assessment status', exact: true }).click();
    const reopened = (await api(`learning/assessments/${session.id}/`, student.token)).assessment;
    assert.equal(reopened.completed_at, completed.completed_at);
    await api(`learning/questions/${session.questions[0].id}/attempts/`, student.token, { request_id: crypto.randomUUID(), answer: 'changed response' }, 409);
    assert.equal((await api(`learning/questions/${session.questions[0].id}/attempts/`, student.token)).attempts.length, 1);

    const tp = await pageFor(teacher); await nav(tp, 'Assessments');
    await tp.getByRole('button', { name: `Review assessment ${session.id}`, exact: true }).click();
    const work = tp.getByRole('region', { name: 'Saved assessment answers', exact: true });
    await work.getByText(savedAnswer, { exact: true }).waitFor();
    await work.getByText(draft, { exact: true }).waitFor();
    await screenshot(tp, 'teacher-saved-assessment-answers');

    const pp = await pageFor(practiceStudent); await nav(pp, 'Practice');
    await pp.getByLabel('Practice format', { exact: true }).selectOption('short_answer');
    const generating = pp.waitForResponse(r => /\/courses\/\d+\/practice\/$/.test(r.url()) && r.request().method() === 'POST');
    await pp.getByRole('button', { name: 'Get adaptive question', exact: true }).click();
    const question = (await (await generating).json()).question;
    await pp.getByLabel('Your short answer', { exact: true }).fill('A saved practice response.');
    await loseOneReply(pp, question.id);
    await pp.getByRole('button', { name: 'Submit practice', exact: true }).click();
    await pp.getByRole('alert').filter({ hasText: /connection|timed out/i }).waitFor();
    await pp.getByRole('button', { name: 'Submit practice', exact: true }).click();
    await pp.getByText('Score:', { exact: false }).first().waitFor();
    assert.equal(await pp.getByLabel('Your short answer', { exact: true }).inputValue(), 'A saved practice response.');
    assert.equal(requestIds.length, 4); assert.equal(requestIds[2], requestIds[3]);
    assert.equal((await api(`learning/questions/${question.id}/attempts/`, practiceStudent.token)).attempts.length, 1);
    assert.deepEqual(errors, []);
    console.log('PASS: assessment answer/feedback/draft restoration, lost-reply retry IDs in assessment and practice, exactly one saved attempt, no unreviewed mastery credit, immutable completion time, completed-answer lock, teacher saved-work review, and responsive recovery controls.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
