/* Requires the disposable scripts/e2e_server.py server and a face/blank Y4M
 * video. A real local MediaPipe model is used; detector results are not mocked.
 * Never run this against production student data. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const origin = process.env.LABTWIN_E2E_URL || 'http://127.0.0.1:8000';
const videoFile = process.env.LABTWIN_CAMERA_TEST_VIDEO;
assert.ok(videoFile && fs.existsSync(videoFile), 'Set LABTWIN_CAMERA_TEST_VIDEO to a face/blank Y4M video.');

async function api(path, token, data, method = 'POST') {
  const response = await fetch(`${origin}/api/${path}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, ...(method === 'GET' ? {} : { body: JSON.stringify(data || {}) }) });
  const body = await response.json(); assert.ok(response.ok, `${path}: ${response.status} ${body.error || ''}`); return body;
}
(async () => {
  const stamp = Date.now();
  const teacher = await api('auth/register/', null, { username: `camera-teacher-${stamp}`, name: 'Camera Test Teacher', role: 'teacher', password: 'Camera-Test-Password-92!' });
  const student = await api('auth/register/', null, { username: `camera-student-${stamp}`, name: 'Camera Test Student', role: 'student', password: 'Camera-Test-Password-92!' });
  const room = (await api('classrooms/', teacher.token, { name: `Camera class ${stamp}`, subject: 'Data Structures' })).classroom;
  await api('classrooms/join/', student.token, { code: room.join_code });
  const course = (await api('learning/courses/', teacher.token, { classroom_id: room.id, name: 'Camera test course', language: 'C' })).course;
  const topicData = await api(`learning/courses/${course.id}/topics/`, teacher.token, { name: 'Linked Lists' });
  const topic = topicData.course.topics[0];
  const material = new FormData();
  material.append('file', new Blob(['Linked Lists\nThe head pointer is the reference to the first node. A linked list is a chain of nodes. A node is a container for data and a link.']), 'camera-course-notes.txt');
  material.append('topic_id', topic.id);
  const upload = await fetch(`${origin}/api/learning/courses/${course.id}/materials/`, { method: 'POST', headers: { Authorization: `Bearer ${teacher.token}` }, body: material });
  assert.equal(upload.status, 201);
  const launch = { headless: true, ...(process.env.LABTWIN_E2E_CHROMIUM ? { executablePath: process.env.LABTWIN_E2E_CHROMIUM } : {}), args: ['--no-sandbox', '--single-process', '--no-zygote', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${videoFile}`] };
  const browser = await chromium.launch(launch);
  let studentBrowser;
  const errors = [], payloads = [];
  try {
    const tc = await browser.newContext({ viewport: { width: 1365, height: 900 } });
    await tc.addInitScript(token => sessionStorage.setItem('labtwin_access_token', token), teacher.token);
    const tp = await tc.newPage(); tp.on('pageerror', error => errors.push(error.message));
    await tp.goto(origin); await tp.getByRole('navigation').getByRole('button', { name: 'Assessments', exact: true }).click();
    const eyeSetting = tp.getByLabel('Allow optional eyes-closed, own-words prompts');
    await Promise.all([tp.waitForResponse(response => response.url().endsWith(`/courses/${course.id}/`) && response.request().method() === 'PATCH'), eyeSetting.check()]);

    // Separate processes also support restricted single-process Chromium builds
    // that cannot host multiple isolated browser contexts in one process.
    studentBrowser = await chromium.launch(launch);
    const sc = await studentBrowser.newContext({ permissions: ['camera'], viewport: { width: 1365, height: 900 } });
    await sc.addInitScript(token => {
      sessionStorage.setItem('labtwin_access_token', token);
      // Observe, without altering, real worker outputs and browser tracks.
      const OriginalWorker = window.Worker; window.cameraSamples = { visible: 0, absent: 0 };
      window.Worker = class extends OriginalWorker { constructor(...args) { super(...args); this.addEventListener('message', event => { if (event.data.type === 'sample') window.cameraSamples[event.data.pose ? 'visible' : 'absent']++; }); } };
      const media = navigator.mediaDevices, original = media.getUserMedia.bind(media); window.cameraTracks = [];
      media.getUserMedia = async constraints => {
        if (window.cameraPermissionDenied) throw new DOMException('Permission denied for camera test', 'NotAllowedError');
        if (window.delayCameraPermission) await new Promise(resolve => { window.resolveCameraPermission = resolve; });
        const stream = await original(constraints); window.cameraTracks.push(...stream.getTracks()); return stream;
      };
    }, student.token);
    const page = await sc.newPage(); page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.url().includes('/camera-events/')) payloads.push(request.postData() || ''); });
    await page.goto(origin); await page.getByRole('navigation').getByRole('button', { name: 'Assessments', exact: true }).click();
    await page.getByLabel('Questions', { exact: true }).fill('1'); await page.getByLabel('Question format', { exact: true }).selectOption('quiz');
    await page.getByRole('button', { name: 'Start assessment', exact: true }).click();
    const camera = page.getByRole('region', { name: 'Assessment camera', exact: true });
    await camera.waitFor(); assert.equal(await page.evaluate(() => window.cameraTracks.length), 0);
    await camera.getByLabel(/I agree to the optional local camera/).check();
    await camera.getByLabel(/Offer optional eyes-closed/).check();
    await page.evaluate(() => { window.cameraPermissionDenied = true; });
    await camera.getByRole('button', { name: 'Turn on assessment camera', exact: true }).click();
    await camera.getByRole('alert').filter({ hasText: 'Camera permission was denied' }).waitFor();
    assert.equal(await page.evaluate(() => window.cameraTracks.length), 0);
    assert.ok(await page.getByRole('button', { name: 'Submit answer 1', exact: true }).isVisible());
    await page.evaluate(() => { window.cameraPermissionDenied = false; });
    await camera.getByRole('button', { name: 'Turn on assessment camera', exact: true }).click();
    await camera.getByRole('button', { name: 'Recalibrate camera', exact: true }).waitFor({ timeout: 60000 });
    await camera.getByRole('complementary', { name: 'Camera instruction' }).waitFor({ timeout: 60000 });
    await camera.getByText(/Keeping your eyes open is equally acceptable/).waitFor();
    if (process.env.LABTWIN_CAMERA_SCREENSHOT) await page.screenshot({ path: process.env.LABTWIN_CAMERA_SCREENSHOT, fullPage: true });
    assert.ok(await page.evaluate(() => window.cameraSamples.visible > 0 && window.cameraSamples.absent > 0), 'Actual model must recognize a face and face absence.');
    await camera.getByLabel('Optional reasoning explanation').fill('I follow the links from the first node to reason about the list.');
    await camera.getByRole('button', { name: 'Save reasoning explanation', exact: true }).click();
    await camera.getByRole('complementary', { name: 'Camera instruction' }).waitFor({ state: 'hidden' });
    await camera.getByRole('button', { name: 'Stop assessment camera', exact: true }).click();
    assert.ok(await page.evaluate(() => window.cameraTracks.every(track => track.readyState === 'ended')));
    await page.evaluate(() => { window.delayCameraPermission = true; });
    await camera.getByRole('button', { name: 'Turn on assessment camera', exact: true }).click();
    await camera.getByRole('button', { name: 'Stop assessment camera', exact: true }).click();
    await page.evaluate(() => { window.delayCameraPermission = false; window.resolveCameraPermission(); });
    await page.waitForFunction(() => window.cameraTracks.length >= 2 && window.cameraTracks.every(track => track.readyState === 'ended'));
    console.log('Real camera model, consent, automatic cue, optional eye closure, explanation and stop checks passed.');

    await tp.getByRole('button', { name: 'Refresh assessment activity', exact: true }).click();
    await tp.getByRole('button', { name: /Review assessment/ }).first().click();
    await tp.getByText('I follow the links from the first node to reason about the list.', { exact: true }).waitFor();
    assert.ok(!payloads.some(body => /data:image|landmarks|frame|clipboard/.test(body)));
    assert.equal(errors.length, 0, errors.join('\n'));

    // Active capture must stop after access is removed, without recording a
    // cheating verdict or requiring a failed assessment submission first.
    await camera.getByRole('button', { name: 'Turn on assessment camera', exact: true }).click();
    await camera.getByRole('button', { name: 'Recalibrate camera', exact: true }).waitFor({ timeout: 60000 });
    await api(`classrooms/${room.id}/students/${student.account.student_id}/`, teacher.token, {}, 'DELETE');
    await page.waitForFunction(() => window.cameraTracks.every(track => track.readyState === 'ended'), null, { timeout: 15000 });
    console.log('Teacher evidence, metadata privacy and enrollment-removal camera revocation passed.');
    await sc.close(); await tc.close();
  } finally { await studentBrowser?.close(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
