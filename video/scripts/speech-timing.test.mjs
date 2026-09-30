import test from 'node:test';
import assert from 'node:assert/strict';
import {timeSpeech} from './speech-timing.mjs';

const story = {scenes: [{id: 'sample', from: 20, duration: 15, cues: [
  {at: .7, text: 'First thought.'}, {at: 8, text: 'Second thought.'},
]}]};
const speech = [
  {id: 'sample-1', duration: 6.8, voice: 'en-US-Ava:DragonHDLatestNeural', rate: 1},
  {id: 'sample-2', duration: 7, voice: 'en-US-Ava:DragonHDLatestNeural', rate: 1},
];

test('natural pacing shifts cues within the scene without changing audio speed', () => {
  const result = timeSpeech(story, speech);
  assert.equal(result[0].duration, speech[0].duration);
  assert.equal(result[1].duration, speech[1].duration);
  assert(result.every(cue => cue.rate === 1));
  assert(result[0].start >= 20.5);
  assert(result[1].start < 28);
  assert(result[1].start >= result[0].start + result[0].duration + .24 - 1e-8);
  assert(result[1].start + result[1].duration <= 34.7 + 1e-8);
});

test('overlong narration fails instead of accelerating or clipping a voice', () => {
  assert.throws(() => timeSpeech(story, speech.map(cue => ({...cue, duration: 10}))),
    /Shorten the script; never accelerate/);
});

test('missing or invalid durations cannot produce a success-shaped timing manifest', () => {
  assert.throws(() => timeSpeech(story, []), /Missing speech duration/);
  assert.throws(() => timeSpeech(story, speech.map(cue => ({...cue, duration: '7'}))),
    /Missing speech duration/);
});
