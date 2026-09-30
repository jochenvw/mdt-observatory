import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {createWriteStream} from 'node:fs';
import {mkdir, writeFile, copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../../', import.meta.url));
const project = path.join(root, 'video');
const captures = path.join(project, 'captures');
const generated = path.join(project, 'assets', 'generated');
await mkdir(captures, {recursive: true});
await mkdir(generated, {recursive: true});
const port = await new Promise((resolve, reject) => {
  const listener = net.createServer();
  listener.on('error', reject);
  listener.listen(0, '127.0.0.1', () => {
    const address = listener.address();
    assert(address && typeof address !== 'string');
    listener.close(() => resolve(address.port));
  });
});
const base = `http://127.0.0.1:${port}`;
const env = {...process.env, MDT_STORAGE_BACKEND: 'sqlite',
  MDT_DB_PATH: path.join(captures, `capture-${Date.now()}.db`),
  MDT_STEP_DELAY: '0.23', MDT_PRESENTER_TOKEN: '', MDT_SECURE_COOKIE: 'false'};
// Capture never talks to cloud services or modifies a presenter's active meeting.
for (const key of Object.keys(env)) {
  if (/^(AZURE_OPENAI|APPLICATIONINSIGHTS|CONTAINER_APP_NAME|OTEL_)/.test(key)) delete env[key];
}
const log = createWriteStream(path.join(captures, 'server.log'));
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin',
  process.platform === 'win32' ? 'python.exe' : 'python');
const server = spawn(python, ['-m', 'uvicorn', 'mdt.app:app', '--host',
  '127.0.0.1', '--port', String(port)], {cwd: root, env, stdio: ['ignore', 'pipe', 'pipe']});
server.stdout.pipe(log);
server.stderr.pipe(log);
const errors = [];
let browser;
const manifest = {synthetic: true, mode: 'rehearsal', width: 1920, height: 1080, screenshotScale: 2,
  capturedAt: new Date().toISOString(), images: [], clips: [], states: {}};
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));
try {
  server.on('error', error => errors.push(error.message));
  let ready = false;
  for (let attempt = 0; attempt < 120; attempt++) {
    if (server.exitCode !== null || errors.length) throw new Error(`Server failed: ${errors.join('; ')}; see captures/server.log`);
    try { ready = (await fetch(`${base}/readyz`)).ok; } catch { /* Startup may not have bound the port yet. */ }
    if (ready) break;
    await wait(250);
  }
  assert(ready, 'Local capture server did not become ready');
  browser = await chromium.launch();
  const context = await browser.newContext({
    baseURL: base, viewport: {width: 1920, height: 1080},
    deviceScaleFactor: 2, colorScheme: 'light',
    recordVideo: {dir: path.join(captures, 'recordings'), size: {width: 1920, height: 1080}},
  });
  const page = await context.newPage();
  const started = Date.now();
  const elapsed = () => (Date.now() - started) / 1000;
  page.on('pageerror', error => errors.push(error.message));
  const state = async () => {
    const response = await context.request.get('/api/meeting');
    assert(response.ok(), `State request failed: ${response.status()}`);
    return response.json();
  };
  const settled = async () => {
    for (let i = 0; i < 600; i++) {
      const meeting = await state();
      assert.notEqual(meeting.phase, 'ERROR', meeting.error);
      if (!meeting.busy) return meeting;
      await wait(150);
    }
    throw new Error('Meeting failed to settle');
  };
  const shot = async (name, selector) => {
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(1100);
    const target = selector ? page.locator(selector) : page;
    const output = path.join(captures, `${name}.png`);
    await target.screenshot({path: output});
    await copyFile(output, path.join(generated, `${name}.png`));
    manifest.images.push({name, file: `${name}.png`, at: elapsed(), selector: selector ?? 'viewport'});
    console.log(`Captured ${name}`);
  };
  const nav = async role => {
    await page.getByTestId(`view-${role}`).click();
    await page.waitForTimeout(250);
  };
  const markState = async name => {
    const meeting = await state();
    manifest.states[name] = {phase: meeting.phase, planVersion: meeting.plan?.version ?? null,
      openQuestions: meeting.frictions.filter(f => !f.resolved).length,
      concurrences: Object.values(meeting.concurrences).map(vote => ({
        role: vote.role, actor: vote.actor, planVersion: vote.plan_version,
      }))};
    await writeFile(path.join(captures, `${name}-state.json`), JSON.stringify(meeting, null, 2));
    return meeting;
  };
  await page.goto(`${base}/?scoutTheme=light`);
  await page.getByTestId('start-case').waitFor({state: 'visible'});
  await page.locator('input[type="radio"][value="CASE-MDT-CRC-BRAF-2026-001"]').check();
  await shot('catalog');
  await page.getByRole('combobox').first().selectOption('rehearsal');
  await page.getByTestId('start-case').click();
  await page.waitForTimeout(1100);
  await shot('central-active');
  const activityStart = elapsed();
  await nav('wall');
  await shot('wall-active');
  await page.waitForTimeout(3200);
  const initial = await settled();
  manifest.clips.push({name: 'activity', from: activityStart, duration: Math.min(9, elapsed() - activityStart)});
  assert.equal(initial.phase, 'TARGETED_DISCUSSION');
  assert.equal(initial.mode, 'rehearsal');
  assert.equal(initial.case.id, 'CASE-MDT-CRC-BRAF-2026-001');
  await markState('discussion');
  await shot('wall');
  await nav('central');
  await shot('central');
  await shot('patient-summary', '[data-testid="case-rail"]');
  await page.getByRole('button', {name: 'View case record', exact: true}).first().click();
  await page.getByRole('dialog').waitFor();
  await shot('dossier');
  await page.keyboard.press('Escape');
  await nav('chair');
  await shot('chair');
  const friction = page.getByTestId('friction-panel');
  if (await friction.count()) {
    await friction.scrollIntoViewIfNeeded();
    await shot('friction');
  } else {
    await shot('friction');
  }
  for (const role of ['radiology', 'oncology', 'surgery', 'pathology', 'research', 'protocol', 'patient']) {
    await nav(role);
    await shot(role);
    const summary = page.locator('summary').filter({hasText: /clinical workspace and source records/});
    await summary.click();
    const clinical = page.getByTestId(`clinical-${role}`);
    await clinical.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, -70));
    await shot(`${role}-source`);
    await summary.click();
  }
  await nav('research');
  await page.getByRole('button', {name: /evidence/i}).first().click();
  await page.getByRole('dialog').waitFor();
  await shot('evidence');
  const abstract = page.getByRole('dialog').getByRole('heading', {name: /CAIRO5.*original/i}).first();
  await abstract.evaluate(element => element.scrollIntoView({block: 'start'}));
  await shot('evidence-access');
  await page.keyboard.press('Escape');
  await nav('radiology');
  await shot('human-before');
  const guidance = 'Review all nine liver sites, vessel margins and the indeterminate lung nodule before clearance planning.';
  const guidanceStart = elapsed();
  await page.locator('#guidance-radiology').pressSequentially(guidance, {delay: 35});
  await shot('human-guidance');
  await page.getByTestId('send-guidance').click();
  const steered = await settled();
  assert(steered.roles.radiology.position.human_intervention);
  await shot('human-return');
  manifest.clips.push({name: 'guidance', from: guidanceStart, duration: elapsed() - guidanceStart});
  await markState('steered');
  await nav('chair');
  await page.getByRole('button', {name: 'Request targeted round', exact: true}).click();
  const proposed = await settled();
  assert.equal(proposed.phase, 'CONCURRENCE');
  await markState('proposal');
  await shot('proposal');
  await nav('central');
  await shot('concurrence-start');
  for (const role of Object.keys(proposed.roles)) {
    if (!(role in (await state()).concurrences)) {
      await nav(role);
      const button = page.getByRole('button', {name: 'Concur', exact: true});
      await button.scrollIntoViewIfNeeded();
      await shot(`review-${role}`);
      await button.click();
      await page.waitForTimeout(350);
    }
  }
  const final = await settled();
  assert.equal(final.phase, 'DECISION_CAPTURED');
  assert.equal(Object.keys(final.concurrences).length, 7);
  assert(final.frictions.every(f => !f.blocking || f.resolved));
  await nav('central');
  await shot('consensus');
  await nav('wall');
  await shot('wall-final');
  await nav('outcome');
  await shot('outcome');
  await page.getByTestId('outcome-actions').scrollIntoViewIfNeeded();
  await shot('followup');
  await page.getByTestId('document-card-patient').scrollIntoViewIfNeeded();
  await shot('documents-status');
  await page.getByTestId('open-document-patient').click();
  await shot('patient-document-status');
  await page.getByTestId('outcome-back').click();
  await page.getByTestId('open-document-clinician').click();
  await shot('clinician-document-status');
  await markState('final');
  await writeFile(path.join(generated, 'record.json'), JSON.stringify({
    caseId: final.case.id,
    plan: final.plan,
    concurrences: final.concurrences,
    frictions: final.frictions,
    communications: Object.fromEntries(Object.entries(final.communications).map(([audience, doc]) =>
      [audience, {status: doc.status, language: doc.language}])),
    guidance,
    positions: Object.fromEntries(Object.entries(initial.roles).map(([role, value]) =>
      [role, value.position])),
  }, null, 2));
  assert.deepEqual(errors, [], 'Browser raised errors');
  const recording = page.video();
  await context.close();
  assert(recording);
  const recordingPath = await recording.path();
  await copyFile(recordingPath, path.join(captures, 'walkthrough.webm'));
  manifest.clips.push({name: 'walkthrough', file: 'walkthrough.webm'});
  await writeFile(path.join(captures, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`Capture complete: ${manifest.images.length} images, verified decision, one browser recording.`);
} finally {
  if (browser) await browser.close();
  server.kill();
  await Promise.race([new Promise(resolve => server.once('exit', resolve)), wait(5000)]);
  log.end();
}
