const { launchBrowser } = require('./e2e_browser.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { join } = require('node:path');
const artifactRoot = process.env.LABTWIN_E2E_ARTIFACT_ROOT || require('node:os').tmpdir();
const signalingOnly = process.env.LABTWIN_E2E_SIGNALING_ONLY === '1';

(async () => {
  const browser = await launchBrowser({ headless: true, ...(process.env.LABTWIN_E2E_CHROMIUM ? { executablePath: process.env.LABTWIN_E2E_CHROMIUM } : {}), args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--allow-loopback-in-peer-connection', '--disable-features=WebRtcHideLocalIpsWithMdns'] });
  const teacherContext = await browser.newContext({ acceptDownloads: true });
  const studentContext = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  await studentContext.addInitScript(() => {
    function stream(label, audio) {
      const canvas = document.createElement('canvas'); canvas.width=320; canvas.height=180;
      const draw = () => { const c=canvas.getContext('2d'); c.fillStyle=label==='screen'?'#17354d':'#17645c'; c.fillRect(0,0,320,180); c.fillStyle='white'; c.font='24px sans-serif'; c.fillText(`Test ${label}`,30,80); c.fillText(new Date().toLocaleTimeString(),30,120); };
      draw(); const timer=setInterval(draw,100); const media=canvas.captureStream(10);
      media.getVideoTracks()[0].addEventListener('ended',()=>clearInterval(timer));
      if(audio) { const ctx=new AudioContext(); const oscillator=ctx.createOscillator(); const dest=ctx.createMediaStreamDestination(); oscillator.connect(dest); oscillator.start(); media.addTrack(dest.stream.getAudioTracks()[0]); }
      return media;
    }
    navigator.mediaDevices.getDisplayMedia = async () => stream('screen',false);
    navigator.mediaDevices.getUserMedia = async () => stream('camera',true);
  });
  const teacher=await teacherContext.newPage(), student=await studentContext.newPage();
  const errors=[]; teacher.on('pageerror',e=>errors.push(e.message)); student.on('pageerror',e=>errors.push(e.message));
  const suffix=Date.now();
  async function waitForMedia() {
    if (signalingOnly) {
      await teacher.waitForFunction(() => [...document.querySelectorAll('video')].filter(v => v.srcObject?.getVideoTracks().length).length >= 2 && document.querySelector('audio')?.srcObject?.getAudioTracks().length, {}, {timeout:30000});
    } else {
      await teacher.waitForFunction(()=>[...document.querySelectorAll('video')].filter(v=>v.readyState>=2).length>=2,{},{timeout:30000});
      await teacher.waitForFunction(()=>document.querySelector('audio')?.readyState>=2,{},{timeout:10000});
    }
  }
  async function register(page, role, name) {
    await page.goto('http://127.0.0.1:8000');
    await page.getByRole('button',{name:'New here? Create an account'}).click();
    await page.getByLabel('Your name',{exact:true}).fill(name);
    await page.getByLabel('Username',{exact:true}).fill(`${role}-${suffix}`);
    await page.getByLabel('Password',{exact:true}).fill('Safe-Classroom-Password-93!');
    await page.getByLabel('I am a').selectOption(role);
    await page.getByRole('button',{name:'Create account',exact:true}).click();
    await page.getByRole('heading',{name:'Dashboard',exact:true}).waitFor();
    await page.getByRole('navigation').getByRole('button',{name:role==='teacher'?'Classes':'My Courses',exact:true}).click();
  }
  try {
    await register(teacher,'teacher','Test Teacher');
    await teacher.getByLabel('Class name').fill('CSE Semester 3'); await teacher.getByLabel('Subject',{exact:true}).fill('Data Structures Lab');
    await teacher.getByRole('button',{name:'Create class',exact:true}).click();
    await teacher.locator('.joinCode').waitFor(); const code=await teacher.locator('.joinCode').innerText();
    await teacher.getByText('Create an assignment',{exact:true}).click();
    await teacher.getByLabel('Title',{exact:true}).fill('Addition and viva');
    await teacher.getByLabel('Instructions',{exact:true}).fill('Print 5 and explain your program.');
    await teacher.getByLabel('Viva question',{exact:true}).fill('Why does your program print 5?');
    await teacher.getByLabel('Expected output',{exact:true}).fill('5');
    await teacher.getByLabel('Require screen sharing',{exact:true}).check();
    await teacher.getByRole('button',{name:'Publish assignment to class',exact:true}).click();
    await teacher.getByRole('heading',{name:'Addition and viva · Python',exact:true}).waitFor();
    await teacher.getByText('Create an assignment',{exact:true}).click();
    console.log('Teacher class and assignment created.');
    await register(student,'student','Test Student');
    await student.getByLabel('Class code',{exact:true}).fill(code); await student.getByRole('button',{name:'Join class',exact:true}).click();
    await student.getByRole('button',{name:'Open assignments',exact:true}).click();
    await student.getByRole('button',{name:'Start / resume assignment',exact:true}).click();
    await student.getByLabel('Your Python code',{exact:true}).fill('print(5)');
    await student.getByRole('button',{name:'Copy code',exact:true}).click();
    assert.equal(await student.evaluate(()=>navigator.clipboard.readText()),'print(5)');
    await student.evaluate(()=>navigator.clipboard.writeText('\n# pasted note'));
    await student.getByRole('button',{name:'Paste code',exact:true}).click();
    await student.waitForFunction(()=>document.querySelector('[data-assessment-field=code]')?.value==='print(5)\n# pasted note');
    assert.equal(await student.getByLabel('Your Python code',{exact:true}).inputValue(),'print(5)\n# pasted note');
    await student.getByRole('button',{name:'Start screen sharing',exact:true}).click();
    await student.getByRole('button',{name:'Stop screen sharing',exact:true}).waitFor();
    await student.getByRole('button',{name:'Answer viva',exact:true}).click();
    await student.getByRole('button',{name:'Stop camera / microphone',exact:true}).waitFor();
    await student.getByLabel('Your viva answer',{exact:true}).fill('The print function outputs the value 5.');
    await student.evaluate(() => {
      const textarea=document.querySelector('[data-assessment-field=viva_answer]');
      const clip=new DataTransfer(); clip.setData('text/plain','sample');
      textarea.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,clipboardData:clip}));
      Object.defineProperty(document,'hidden',{value:true,configurable:true}); document.dispatchEvent(new Event('visibilitychange'));
      Object.defineProperty(document,'hidden',{value:false,configurable:true}); document.dispatchEvent(new Event('visibilitychange'));
    });
    await student.getByText(/Please return to the viva and explain in your own words/).waitFor();
    // Existing live camera consent is separate from consent to local reminders
    // and optional eyes-closed checks. Neither teacher nor student opted in here.
    assert.equal(await student.getByText(/close your eyes briefly/).count(), 0);
    await teacher.getByRole('button',{name:'Watch live',exact:true}).waitFor({timeout:20000});
    const firstWatch=await teacher.getByRole('button',{name:'Watch live',exact:true}).elementHandle();
    await firstWatch.click();
    await waitForMedia();
    await student.getByText('Teacher watching: Test Teacher',{exact:true}).waitFor();
    await student.getByRole('navigation').getByRole('button',{name:'Ask LabTwin',exact:true}).click();
    await student.getByRole('button',{name:'Stop all sharing',exact:true}).waitFor();
    await student.getByRole('navigation').getByRole('button',{name:'My Courses',exact:true}).click();
    await student.getByRole('button',{name:'Stop screen sharing',exact:true}).waitFor();
    assert.equal(await student.getByLabel('Your viva answer',{exact:true}).inputValue(),'The print function outputs the value 5.');
    await teacher.locator('.classroomColumns').getByRole('button',{name:'Refresh',exact:true}).click();
    await teacher.getByRole('cell',{name:'Test Student @student-',exact:false}).waitFor();
    console.log(signalingOnly ? 'Screen/camera/audio consent and WebRTC offer/answer tracks verified; media transport excluded in this restricted network.' : 'Both real WebRTC video streams received; viva reminder and events recorded.');
    await teacher.screenshot({path:join(artifactRoot, 'teacher-classroom-preview.png'),fullPage:true});
    await student.getByRole('button',{name:'Submit code and viva',exact:true}).click();
    await student.getByText('Test score: 100%',{exact:true}).waitFor({timeout:15000});
    await firstWatch.waitForElementState('hidden',{timeout:10000});
    await teacher.getByRole('button',{name:'Refresh reports',exact:true}).click();
    await teacher.getByRole('button',{name:'View full report',exact:true}).first().click();
    await teacher.getByText('page hidden',{exact:false}).last().waitFor();
    await teacher.getByLabel('Teacher score (0–100)').fill('92'); await teacher.getByLabel('Teacher feedback',{exact:true}).fill('Clear explanation.');
    await teacher.getByRole('button',{name:'Save teacher review',exact:true}).click();
    await teacher.getByText('Review saved.',{exact:true}).waitFor();
    const downloadPromise=teacher.waitForEvent('download'); await teacher.getByRole('button',{name:'Download CSV report',exact:true}).click();
    const download=await downloadPromise; await download.saveAs(join(artifactRoot, 'e2e-classroom-reports.csv'));
    const csv=fs.readFileSync(join(artifactRoot, 'e2e-classroom-reports.csv'),'utf8'); assert(csv.includes('Test Student')); assert(csv.includes('92')); assert(csv.includes('Clear explanation.'));
    await student.getByRole('button',{name:'My submissions',exact:true}).click();
    await student.locator('details').filter({has:student.getByText('Clear explanation.',{exact:true})}).locator('summary').click();
    await student.getByText('Clear explanation.',{exact:true}).waitFor();
    await teacher.setViewportSize({width:390,height:844});
    console.log('Mobile layout:',JSON.stringify(await teacher.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('*')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(el=>({tag:el.tagName,class:el.className,right:el.getBoundingClientRect().right}))}))));
    await teacher.screenshot({path:join(artifactRoot, 'teacher-classroom-mobile.png'),fullPage:true});
    assert.equal(await teacher.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    assert.deepEqual(errors,[]);
    console.log('Submission, report events, teacher review, student history, CSV, and mobile layout passed.');
    await teacher.setViewportSize({width:1280,height:900});
    await student.getByRole('button',{name:'Save and close',exact:true}).click();
    await teacher.getByText('Create an assignment',{exact:true}).click();
    await teacher.getByLabel('Title',{exact:true}).fill('No paste lab');
    await teacher.getByLabel('Instructions',{exact:true}).fill('Write the answer yourself and print 5.');
    await teacher.getByLabel('Expected output',{exact:true}).fill('5');
    await teacher.getByLabel('Allow copy/paste into the answer',{exact:true}).uncheck();
    await teacher.getByLabel('Require camera and microphone for viva',{exact:true}).uncheck();
    await teacher.getByRole('button',{name:'Publish assignment to class',exact:true}).click();
    await teacher.getByRole('heading',{name:'No paste lab · Python',exact:true}).waitFor();
    await student.getByRole('button',{name:'Refresh assignments',exact:true}).click();
    const noPaste = student.locator('article.classroomTile').filter({has:student.getByRole('heading',{name:'No paste lab · Python',exact:true})});
    await noPaste.getByRole('button',{name:'Start / resume assignment',exact:true}).click();
    await student.getByLabel('Your Python code',{exact:true}).fill('print(5)');
    assert.equal(await student.getByRole('button',{name:'Paste code',exact:true}).isDisabled(),true);
    assert.equal(await student.evaluate(()=>{
      const textarea=document.querySelector('[data-assessment-field=code]'); const clip=new DataTransfer(); clip.setData('text/plain','blocked');
      const event=new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:clip}); textarea.dispatchEvent(event); return event.defaultPrevented;
    }),true);
    await student.getByRole('button',{name:'Submit code and viva',exact:true}).click();
    await student.getByText('Test score: 100%',{exact:true}).waitFor();
    await teacher.getByRole('button',{name:'Refresh reports',exact:true}).click();
    const blockedReport = teacher.getByRole('row').filter({hasText:'No paste lab'});
    await blockedReport.getByRole('button',{name:'View full report',exact:true}).click();
    await teacher.getByText(/coding · paste blocked · code/).waitFor();
    console.log('Copy/paste buttons and blocked-paste policy/report passed.');
    await student.getByRole('button',{name:'Save and close',exact:true}).click();
    const addition=student.locator('article.classroomTile').filter({has:student.getByRole('heading',{name:'Addition and viva · Python',exact:true})});
    await addition.getByRole('button',{name:'Start / resume assignment',exact:true}).click();
    await student.getByLabel('Your Python code',{exact:true}).fill('print(5)');
    await student.getByRole('button',{name:'Start screen sharing',exact:true}).click();
    await student.getByRole('button',{name:'Answer viva',exact:true}).click();
    await student.getByRole('button',{name:'Stop camera / microphone',exact:true}).waitFor();
    await student.getByRole('navigation').getByRole('button',{name:'Ask LabTwin',exact:true}).click();
    await student.getByRole('button',{name:'Stop all sharing',exact:true}).click();
    await student.getByRole('button',{name:'Stop all sharing',exact:true}).waitFor({state:'hidden'});
    await student.getByRole('navigation').getByRole('button',{name:'My Courses',exact:true}).click();
    await student.getByRole('button',{name:'Start screen sharing',exact:true}).waitFor();
    await student.getByRole('button',{name:'Start screen sharing',exact:true}).click();
    await student.getByRole('button',{name:'Turn on camera / microphone',exact:true}).click();
    await student.getByRole('button',{name:'Stop camera / microphone',exact:true}).waitFor();
    await teacher.getByText('Test Student · Addition and viva · Screen on · Camera on',{exact:true}).waitFor();
    await teacher.getByRole('button',{name:'Watch live',exact:true}).waitFor();
    await teacher.getByRole('button',{name:'Watch live',exact:true}).click();
    await waitForMedia();
    teacher.once('dialog',dialog=>dialog.accept());
    await teacher.getByRole('button',{name:'Remove',exact:true}).click();
    await student.getByRole('button',{name:'Start screen sharing',exact:true}).waitFor({timeout:10000});
    await teacher.waitForFunction(()=>!document.querySelector('video'),{},{timeout:10000});
    assert.deepEqual(errors,[]);
    console.log('Removing the student stopped capture and closed the teacher connection.');
  } catch (error) {
    await teacher.screenshot({path:join(artifactRoot, 'classroom-failure.png'),fullPage:true});
    console.error('Remaining teacher media:', await teacher.locator('video').evaluateAll(nodes => nodes.map(v => ({label:v.parentElement.innerText,tracks:v.srcObject?.getTracks().map(t=>({kind:t.kind,state:t.readyState})),ready:v.readyState}))));
    throw error;
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
