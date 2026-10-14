/* Run with the existing disposable scripts/e2e_server.py, never production. */
const assert = require('node:assert/strict');
const { launchBrowser } = require('./e2e_browser.cjs');

(async () => {
  const base = process.env.LABTWIN_E2E_BASE_URL || 'http://127.0.0.1:8000';
  if (!['localhost', '127.0.0.1'].includes(new URL(base).hostname)) {
    throw new Error('Topic fixtures must only use a disposable local test server.');
  }
  const browser = await launchBrowser({ headless: true,
    ...(process.env.LABTWIN_E2E_CHROMIUM ? { executablePath: process.env.LABTWIN_E2E_CHROMIUM } : {}),
    args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const pageErrors = [], topicRequests = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('request', request => {
    if (/\/courses\/\d+\/topics\/$/.test(request.url()) && request.method() === 'POST') topicRequests.push(request);
  });
  try {
    const suffix = Date.now();
    const registration = await page.request.post(`${base}/api/auth/register/`, {
      data: { username: `topic-e2e-${suffix}`, password: `Temporary-Topic-${suffix}!`, name: 'Temporary Topic Teacher', role: 'teacher' }
    });
    assert.equal(registration.status(), 200);
    const account = await registration.json();
    const headers = { Authorization: `Bearer ${account.token}` };
    async function fixture(path, data) {
      const response = await page.request.post(`${base}/api/${path}`, { headers, data });
      assert.equal(response.status(), 201, `Fixture ${path} could not be created`);
      return response.json();
    }
    const { classroom } = await fixture('classrooms/', { name: 'Temporary topic class' });
    const { course } = await fixture('learning/courses/', { classroom_id: classroom.id, name: 'Java OOP', language: 'Java' });
    const { course: other } = await fixture('learning/courses/', { classroom_id: classroom.id, name: 'Second course', language: 'Java' });
    await context.addInitScript(token => sessionStorage.setItem('labtwin_access_token', token), account.token);
    await page.goto(base);
    await page.getByRole('navigation').getByRole('button', { name: 'Course Materials', exact: true }).click();
    await page.getByLabel('Current course', { exact: true }).selectOption(String(course.id));
    const section = page.locator('section.classroomBox').filter({ has: page.getByRole('heading', { name: 'Course topics and settings', exact: true }) });
    const name = section.getByLabel('New topic', { exact: true });
    const prerequisite = section.getByLabel('Prerequisite', { exact: true });
    const add = section.getByRole('button', { name: 'Add topic', exact: true });
    function responseFor(id = course.id) {
      return page.waitForResponse(response => response.url().endsWith(`/courses/${id}/topics/`) && response.request().method() === 'POST');
    }
    async function submit(value, expected = 201, id = course.id) {
      await name.fill(value);
      const response = responseFor(id);
      await add.click();
      const result = await response;
      assert.equal(result.status(), expected);
      await add.waitFor({ state: 'visible' });
      return result;
    }
    await submit('  Polymorphism  ');
    await prerequisite.locator('option', { hasText: 'Polymorphism' }).waitFor({ state: 'attached' });
    const topicId = Number(await prerequisite.locator('option', { hasText: 'Polymorphism' }).getAttribute('value'));
    assert.equal(await name.inputValue(), '');

    let before = topicRequests.length;
    await name.fill(' Polymorphism ');
    await add.click();
    await section.getByRole('alert').filter({ hasText: 'already exists in this course' }).waitFor();
    await add.click();
    assert.equal(topicRequests.length, before, 'Known duplicates must not send repeated POST requests');
    await name.fill('   ');
    await add.click();
    await section.getByRole('alert').filter({ hasText: 'Enter a topic name' }).waitFor();
    assert.equal(topicRequests.length, before, 'Whitespace-only names must not reach the server');

    await prerequisite.selectOption(String(topicId));
    const overriding = await submit('Overriding');
    assert.deepEqual(overriding.request().postDataJSON(), { name: 'Overriding', prerequisites: [topicId] });
    assert.equal(await prerequisite.inputValue(), '');

    before = topicRequests.length;
    await name.fill('Constructors');
    const rapidResponse = responseFor();
    await add.evaluate(button => {
      button.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      button.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    assert.equal((await rapidResponse).status(), 201);
    await prerequisite.locator('option', { hasText: 'Constructors' }).waitFor({ state: 'attached' });
    assert.equal(topicRequests.length, before + 1, 'Rapid submissions must create only one request');

    // A different client can create a topic after this form loaded. The actual
    // server 400 must render beside the topic form and refresh the topic list.
    await fixture(`learning/courses/${course.id}/topics/`, { name: 'Abstraction' });
    const rejected = await submit('Abstraction', 400);
    assert.match((await rejected.json()).error, /already exists in this course/);
    await section.getByRole('alert').filter({ hasText: 'already exists in this course' }).waitFor();
    await prerequisite.locator('option', { hasText: 'Abstraction' }).waitFor({ state: 'attached' });
    before = topicRequests.length;
    await add.click();
    assert.equal(topicRequests.length, before, 'Refreshed duplicate must not be sent again');

    await prerequisite.selectOption(String(topicId));
    await page.getByLabel('Current course', { exact: true }).selectOption(String(other.id));
    assert.equal(await prerequisite.inputValue(), '');
    await submit('Polymorphism', 201, other.id);
    assert.deepEqual(pageErrors, []);
    console.log('PASS: real topic form creates valid topics/prerequisites, rejects blank/known duplicates before POST, renders and recovers from a real backend 400, prevents rapid repeated submissions and preserves course isolation.');
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
