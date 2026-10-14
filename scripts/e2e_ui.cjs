/* Real UI/API checks on the disposable local server only. Never production. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { launchBrowser } = require('./e2e_browser.cjs');

(async () => {
  const base = process.env.LABTWIN_E2E_BASE_URL || 'http://127.0.0.1:8000';
  if (!['127.0.0.1', 'localhost'].includes(new URL(base).hostname)) throw new Error('UI fixtures require the disposable local test server.');
  const browser = await launchBrowser({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'],
    ...(process.env.LABTWIN_E2E_CHROMIUM ? { executablePath: process.env.LABTWIN_E2E_CHROMIUM } : {}) });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'labtwin-ui-pdf-'));
  async function api(token, route, data, expected = 201) {
    const response = await page.request.post(base + '/api/' + route, { headers: { Authorization: 'Bearer ' + token }, data });
    assert.equal(response.status(), expected, route + ': ' + await response.text());
    return response.json();
  }
  async function read(token, route) {
    const response = await page.request.get(base + '/api/' + route, { headers: { Authorization: 'Bearer ' + token } });
    assert.equal(response.status(), 200, route + ': ' + await response.text());
    return response.json();
  }
  async function signIn(account) {
    await page.goto(base);
    await page.evaluate(token => sessionStorage.setItem('labtwin_access_token', token), account.token);
    await page.reload();
    await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor();
  }
  const nav = name => page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
  async function screenshot(name) {
    if (!process.env.LABTWIN_UI_SCREENSHOTS) return;
    fs.mkdirSync(process.env.LABTWIN_UI_SCREENSHOTS, { recursive: true });
    await page.screenshot({ path: path.join(process.env.LABTWIN_UI_SCREENSHOTS, name + '.png'), fullPage: false });
  }
  async function noOverflow() {
    await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth + 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, 'Page has horizontal overflow');
  }
  async function accountLayout(role) {
    for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 1280, height: 720 },
      { width: 900, height: 480 }, { width: 390, height: 844 }, { width: 320, height: 568 }]) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => window.scrollTo(0, 0));
      await noOverflow();
      for (const label of ['Recovery phone', 'Sign out']) {
        const box = await page.locator('.sidebarFooter').getByRole('button', { name: label, exact: true }).boundingBox();
        assert(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1,
          role + ' ' + label + ' is inaccessible at ' + viewport.width + 'x' + viewport.height);
      }
      const navBox = await page.getByRole('navigation').boundingBox();
      const footerBox = await page.locator('.sidebarFooter').boundingBox();
      assert(navBox.y + navBox.height <= footerBox.y + 1, 'Navigation overlaps account controls');
      await page.getByRole('navigation').getByRole('button', { name: 'Demo Mode', exact: true }).scrollIntoViewIfNeeded();
      await screenshot(role + '-' + viewport.width + 'x' + viewport.height);
    }
    await page.setViewportSize({ width: 1366, height: 768 });
  }
  async function ask(text) {
    await page.getByLabel('Your question', { exact: true }).fill(text);
    const response = page.waitForResponse(r => /\/courses\/\d+\/ask\/$/.test(r.url()) && r.request().method() === 'POST');
    await page.getByRole('main').getByRole('button', { name: 'Ask LabTwin', exact: true }).click();
    const result = await response;
    assert.equal(result.status(), 200);
    await page.locator('.answerCard').first().waitFor();
    return result.json();
  }
  try {
    const stamp = Date.now();
    async function register(role) {
      const response = await page.request.post(base + '/api/auth/register/', { data: {
        username: 'ui-' + role + '-' + stamp, password: 'Temporary-UI-' + stamp + '!',
        name: 'Temporary ' + role + ' with a long account name', role } });
      assert.equal(response.status(), 200);
      return response.json();
    }
    const teacher = await register('teacher');
    const student = await register('student');
    const { classroom } = await api(teacher.token, 'classrooms/', { name: 'Disposable UI class' });
    const { course } = await api(teacher.token, 'learning/courses/', { classroom_id: classroom.id, name: 'Java OOP UI Course', language: 'Java' });
    const added = await api(teacher.token, 'learning/courses/' + course.id + '/topics/', { name: 'Dynamic Method Dispatch' });
    const topicId = added.course.topics[0].id;
    await api(teacher.token, 'learning/courses/' + course.id + '/topics/', { name: 'Overriding', prerequisites: [topicId] });
    await api(student.token, 'classrooms/join/', { code: classroom.join_code }, 200);

    const filename = path.join(folder, 'Java-OOP-UI-Notes.pdf');
    const generated = spawnSync(process.env.LABTWIN_E2E_PYTHON || 'python', ['-c', [
      'import sys',
      'from reportlab.pdfgen import canvas',
      'c = canvas.Canvas(sys.argv[1])',
      'for page in range(1, 7):',
      ' c.drawString(40, 800, "Java OOP UI Notes")',
      ' if page == 6:',
      '  c.drawString(40, 760, "Dynamic Method Dispatch")',
      '  c.drawString(40, 730, "Dynamic method dispatch selects an overridden method at runtime.")',
      '  c.drawString(40, 700, "The actual object determines the implementation called.")',
      ' else:',
      '  c.drawString(40, 740, "Background notes section " + str(page))',
      ' c.showPage()',
      'c.save()'
    ].join('\n'), filename], { encoding: 'utf8' });
    assert.equal(generated.status, 0, generated.stderr || 'PDF fixture creation failed');
    const uploaded = await page.request.post(base + '/api/learning/courses/' + course.id + '/materials/', {
      headers: { Authorization: 'Bearer ' + teacher.token }, multipart: {
        topic_id: String(topicId), file: { name: 'Java-OOP-UI-Notes.pdf', mimeType: 'application/pdf', buffer: fs.readFileSync(filename) }
      }
    });
    assert.equal(uploaded.status(), 201, await uploaded.text());
    assert.equal((await uploaded.json()).material.status, 'ready');

    await signIn(teacher);
    await accountLayout('teacher');
    await nav('Course Materials');
    const topics = page.locator('.topicSettings');
    await topics.getByText('Selected course:', { exact: false }).waitFor();
    await topics.getByRole('list', { name: 'Existing course topics' }).waitFor();
    await topics.locator('li').filter({ has: page.getByText('Overriding', { exact: true }) }).getByText('Prerequisites: Dynamic Method Dispatch', { exact: true }).waitFor();
    await topics.getByLabel('New topic', { exact: true }).fill('Encapsulation');
    await topics.getByRole('button', { name: 'Add topic', exact: true }).click();
    await topics.getByRole('status').filter({ hasText: 'Added "Encapsulation"' }).waitFor();
    await topics.locator('li').getByText('Encapsulation', { exact: true }).waitFor();
    await topics.getByLabel('New topic', { exact: true }).fill(' Encapsulation ');
    await topics.getByRole('alert').filter({ hasText: 'already exists in this course' }).waitFor();
    assert.equal(await topics.getByLabel('New topic', { exact: true }).getAttribute('aria-invalid'), 'true');
    await screenshot('teacher-topics');

    await nav('Ask LabTwin');
    const teacherAnswer = await ask('Dynamic method dispatch on page 6');
    assert.equal(teacherAnswer.mode, 'source_excerpts');
    assert(teacherAnswer.citations.length > 0);
    assert(teacherAnswer.citations.every(c => c.page_number === 6));
    assert.equal(await page.getByRole('button', { name: 'Check my understanding', exact: true }).count(), 0);
    await page.locator('.answerCard').first().getByText('Source excerpts', { exact: true }).waitFor();
    const passage = page.locator('.answerCard').first().locator('details.sourceExcerpt').first();
    assert.equal(await passage.getAttribute('open'), null, 'Copied excerpts should start collapsed');
    await passage.locator('summary').focus();
    await page.keyboard.press('Enter');
    await passage.getByText('Dynamic method dispatch selects an overridden method at runtime.', { exact: false }).waitFor();
    const forbidden = await api(teacher.token, 'learning/exchanges/' + teacherAnswer.id + '/check/', {}, 403);
    assert.match(forbidden.error, /signed-in student/);
    const sourceId = teacherAnswer.citations[0].id;
    await page.locator('.answerCard').first().getByRole('link', { name: /Source:.*Page 6/ }).first().click();
    const dialog = page.getByRole('dialog');
    await dialog.locator('iframe').waitFor();
    assert.match(await dialog.locator('iframe').getAttribute('src'), /#page=6&zoom=page-width$/);
    const sourceData = await read(teacher.token, 'learning/sources/' + sourceId + '/');
    assert.equal(sourceData.source.page_number, 6);
    assert.match(sourceData.text, /Dynamic method dispatch/);
    for (const size of [{ width: 1366, height: 768 }, { width: 390, height: 844 }, { width: 320, height: 568 }]) {
      await page.setViewportSize(size);
      await dialog.locator('.sourceModalBody').evaluate(element => { element.scrollTop = element.scrollHeight; });
      const close = await dialog.getByRole('button', { name: 'Close source', exact: true }).boundingBox();
      assert(close && close.y >= 0 && close.y + close.height <= size.height, 'Close source must stay in view');
      await noOverflow();
      await screenshot('source-page6-' + size.width);
    }
    await dialog.getByRole('button', { name: 'Close source', exact: true }).click();
    await page.setViewportSize({ width: 1366, height: 768 });
    await api(teacher.token, 'learning/topics/' + topicId + '/bank/', {
      title: 'Dispatch timing check', kind: 'short_answer', difficulty: 1, language: 'Java',
      prompt: 'When does dynamic method dispatch select an overridden method?',
      answer: { accepted: ['runtime'] }, explanation: 'An overridden method is selected at runtime.',
      source_ids: [sourceId]
    });
    await api(teacher.token, 'learning/topics/' + topicId + '/bank/', {
      title: 'MCQ dispatch phase', kind: 'quiz', difficulty: 1, language: 'Java',
      prompt: "Select the phase in which an object's actual class controls a Java call.",
      options: ['Runtime', 'Compilation'], answer: { correct_index: 0 },
      explanation: 'The actual object controls method selection at runtime.', source_ids: [sourceId]
    });
    await api(teacher.token, 'learning/topics/' + topicId + '/bank/', {
      title: 'Execution phase response', kind: 'short_answer', difficulty: 1, language: 'Java',
      prompt: 'Give the one-word phase: compile-time or runtime.',
      answer: { accepted: ['runtime'] }, explanation: 'The method is selected at runtime.', source_ids: [sourceId]
    });
    await page.locator('.sidebarFooter').getByRole('button', { name: 'Sign out', exact: true }).click();
    await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor();

    await signIn(student);
    await accountLayout('student');
    await nav('Ask LabTwin');
    await ask('Dynamic method dispatch on page 6');
    await page.locator('.answerCard').first().getByRole('button', { name: 'Check my understanding', exact: true }).click();
    await page.getByLabel('Your understanding-check answer', { exact: true }).fill('runtime');
    await page.getByRole('button', { name: 'Submit understanding check', exact: true }).click();
    await page.locator('.answerCard').first().getByText('Correct', { exact: true }).waitFor();
    const afterCheck = await read(student.token, 'learning/topics/' + topicId + '/');
    assert(afterCheck.evidence.some(e => e.kind === 'conversation' && e.score === 100));
    await page.reload();
    await nav('Ask LabTwin');
    await page.locator('.answerCard').first().getByText('Source excerpts', { exact: true }).waitFor();
    await page.locator('.answerCard').first().getByRole('button', { name: 'Check my understanding', exact: true }).waitFor();
    const restored = await read(student.token, 'learning/topics/' + topicId + '/');
    assert.equal(restored.score, afterCheck.score, 'Conversation mastery must survive reload');

    const sessions = [];
    for (const format of ['quiz', 'short_answer']) {
      await nav('Assessments');
      await page.getByLabel('Assessment scope', { exact: true }).selectOption(String(topicId));
      await page.getByLabel('Question format', { exact: true }).selectOption(format);
      await page.getByLabel('Questions', { exact: true }).fill('1');
      const pending = page.waitForResponse(r => r.url().endsWith('/courses/' + course.id + '/assessments/') && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Start assessment', exact: true }).click();
      const response = await pending;
      assert.equal(response.status(), 201, await response.text());
      sessions.push((await response.json()).assessment.id);
      if (format === 'quiz') await page.getByRole('radio').first().check();
      else await page.getByLabel('Your short answer', { exact: true }).fill('runtime');
      await page.getByRole('button', { name: 'Submit answer 1', exact: true }).click();
      await page.locator('.practiceResult').getByText('Correct', { exact: true }).waitFor();
      await page.getByRole('heading', { name: 'Assessment report', exact: true }).waitFor();
      await page.setViewportSize({ width: 390, height: 844 });
      await noOverflow();
      await screenshot('student-assessment-' + format);
      await page.setViewportSize({ width: 1366, height: 768 });
    }
    const beforeReload = await read(student.token, 'learning/topics/' + topicId + '/');
    await page.reload();
    const afterReload = await read(student.token, 'learning/topics/' + topicId + '/');
    assert.equal(afterReload.score, beforeReload.score);
    assert.equal(afterReload.evidence.length, beforeReload.evidence.length);
    for (const id of sessions) {
      const saved = await read(student.token, 'learning/assessments/' + id + '/');
      assert.equal(saved.assessment.status, 'completed');
      assert.equal(saved.assessment.report.score, 100);
    }
    await nav('Ask LabTwin');
    await ask('Explain quantum entanglement');
    await page.locator('.answerCard').first().getByText('More material needed', { exact: true }).waitFor();
    assert.equal(await page.locator('.answerCard').first().getByRole('button', { name: 'Check my understanding' }).count(), 0);
    await page.locator('.sidebarFooter').getByRole('button', { name: 'Sign out', exact: true }).click();
    await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: teacher/student sidebar visibility at six viewports; real sign-out; topic success/prerequisites/duplicates; teacher role protection; student understanding-check feedback and persisted mastery; PDF page 6 and fixed Close source; MCQ/short-answer reports and persistence; unsupported state; no horizontal page overflow.');
  } catch (error) {
    await screenshot('ui-failure');
    throw error;
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
