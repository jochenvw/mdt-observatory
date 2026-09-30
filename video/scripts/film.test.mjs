import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, access} from 'node:fs/promises';
import path from 'node:path';
import {project, probe} from './tools.mjs';

const json = async (...parts) => JSON.parse(await readFile(path.join(project, ...parts), 'utf8'));
const story = await json('src', 'story.json');
const timing = await json('assets', 'generated', 'timing.json');
const captions = await json('assets', 'generated', 'captions.json');
const capture = await json('captures', 'manifest.json');

test('the nine chapters cover exactly 180 seconds at projection resolution', () => {
  assert.equal(story.width, 1920);
  assert.equal(story.height, 1080);
  assert.equal(story.fps, 25);
  assert.equal(story.scenes.length, 9);
  let end = 0;
  for (const scene of story.scenes) {
    assert.equal(scene.from, end);
    end += scene.duration;
  }
  assert.equal(end, 180);
});

test('caption text equals narration and follows measured, non-overlapping speech', async () => {
  const expected = story.scenes.flatMap(scene => scene.cues.map(cue => cue.text)).join(' ');
  assert.equal(captions.map(cue => cue.text).join(' '), expected);
  let end = 0;
  for (const cue of timing) {
    assert(cue.start >= end);
    assert(cue.duration <= cue.maxSeconds);
    end = cue.start + cue.duration;
    if (cue.file) {
      assert(!cue.voice.includes('Desktop'), 'Robotic desktop speech must not return');
      assert.equal(cue.rate, 1, 'The narrator must remain at native speaking pace');
      const file = path.join(project, 'assets', 'generated', cue.file);
      assert(Math.abs(Number(probe(file).format.duration) - cue.duration) < .03);
    }
  }
  assert(end < 180);
});

test('the real capture reached consensus through version-bound review', async () => {
  assert.equal(capture.mode, 'rehearsal');
  assert.equal(capture.synthetic, true);
  assert.equal(capture.states.discussion.phase, 'TARGETED_DISCUSSION');
  assert(capture.states.discussion.openQuestions > 0);
  assert.equal(capture.states.final.phase, 'DECISION_CAPTURED');
  const final = await json('assets', 'generated', 'record.json');
  assert.equal(final.caseId, 'CASE-MDT-CRC-BRAF-2026-001');
  assert(final.plan.conditions.length > 0);
  assert.equal(Object.keys(final.concurrences).length, 7);
  for (const vote of Object.values(final.concurrences)) assert.equal(vote.plan_version, final.plan.version);
  assert(Object.values(final.concurrences).some(vote => vote.actor === 'human'));
  assert(Object.values(final.concurrences).some(vote => vote.actor === 'agent'));
  assert.equal(final.communications.patient.status, 'FAILED');
  assert.equal(final.communications.clinician.status, 'FAILED');
});

test('every required application surface and real motion asset exists', async () => {
  const names = ['central', 'wall', 'patient-summary', 'chair', 'radiology', 'oncology',
    'pathology', 'surgery', 'research', 'protocol', 'patient', 'evidence', 'friction',
    'human-guidance', 'human-return', 'proposal', 'consensus', 'outcome', 'followup', 'documents-status'];
  for (const name of names) {
    assert(capture.images.some(image => image.name === name), `Missing capture: ${name}`);
    await access(path.join(project, 'assets', 'generated', `${name}.png`));
  }
  for (const name of ['guidance', 'activity']) {
    const file = path.join(project, 'assets', 'generated', `${name}.mp4`);
    assert(Number(probe(file).format.duration) > 3);
  }
});
