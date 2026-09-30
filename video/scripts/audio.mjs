import {readFile, writeFile, mkdir, copyFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {synthesize} from './neural-speech.mjs';
import {timeSpeech} from './speech-timing.mjs';

const project = fileURLToPath(new URL('../', import.meta.url));
const story = JSON.parse(await readFile(path.join(project, 'src', 'story.json'), 'utf8'));
const audio = path.join(project, 'audio');
const generated = path.join(project, 'assets', 'generated');
const out = path.join(project, 'out');
for (const folder of [audio, generated, out]) await mkdir(folder, {recursive: true});
const cues = story.scenes.flatMap(scene => scene.cues.map((cue, i) => ({
  id: `${scene.id}-${i + 1}`,
  scene: scene.id,
  text: cue.text,
  start: scene.from + cue.at,
  maxSeconds: (scene.cues[i + 1]?.at ?? scene.duration - 0.25) - cue.at - 0.18,
})));
await writeFile(path.join(audio, 'speech-input.json'), JSON.stringify(cues, null, 2));
let results;
if (process.argv.includes('--silent')) {
  results = cues.map(cue => ({id: cue.id, duration: cue.maxSeconds, voice: null, rate: null}));
  console.warn('Explicit silent mode: rendering captions without speech.');
} else {
  if (!process.argv.includes('--reuse')) {
    results = await synthesize(cues, audio);
  } else {
    results = JSON.parse((await readFile(path.join(audio, 'speech-results.json'), 'utf8')).replace(/^\uFEFF/, ''));
  }
}
for (const cue of cues) {
  const result = results.find(item => item.id === cue.id);
  assert(result, `Missing narration: ${cue.id}`);
  assert(!result.voice?.includes('Desktop'), 'Desktop TTS is not suitable for this film.');
  if (result.textHash) {
    assert.equal(result.textHash, createHash('sha256').update(cue.text).digest('hex'),
      `Narration text changed for ${cue.id}; regenerate its neural speech.`);
  }
}
const timing = timeSpeech(story, results);
for (const cue of timing) {
  if (cue.file) {
    const source = results.find(item => item.id === cue.id)?.file ?? cue.file;
    await copyFile(path.join(audio, source), path.join(generated, cue.file));
  }
}

// Original additive-synthesis bed: no samples, loops or third-party music.
const sampleRate = 24000;
const length = sampleRate * story.duration;
const data = Buffer.alloc(length * 2);
const chords = [[130.813, 164.814, 195.998, 246.942], [110, 130.813, 164.814, 195.998],
  [87.307, 130.813, 174.614, 220], [97.999, 146.832, 195.998, 246.942]];
for (let i = 0; i < length; i++) {
  const t = i / sampleRate;
  const phrase = t % 12;
  const fade = Math.min(t / 3, (story.duration - t) / 3, 1);
  const chord = chords[Math.floor(t / 12) % chords.length];
  const padEnvelope = Math.sin(Math.PI * phrase / 12) ** 2;
  let sample = chord.reduce((sum, f, index) => sum + Math.sin(2 * Math.PI * f * t + index)
    * (0.68 + 0.32 * Math.sin(t * 0.37 + index)) / chord.length, 0) * 0.026 * padEnvelope;
  for (const scene of story.scenes.slice(1)) {
    const delta = t - scene.from;
    if (delta >= 0 && delta < 1.2) {
      sample += Math.sin(2 * Math.PI * 659.255 * delta) * Math.exp(-delta * 7)
        * Math.min(delta * 80, 1) * 0.026;
    }
  }
  data.writeInt16LE(Math.round(sample * fade * 32767), i * 2);
}
const header = Buffer.alloc(44);
header.write('RIFF', 0); header.writeUInt32LE(36 + data.length, 4); header.write('WAVEfmt ', 8);
header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
header.writeUInt32LE(sampleRate, 24); header.writeUInt32LE(sampleRate * 2, 28);
header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34); header.write('data', 36);
header.writeUInt32LE(data.length, 40);
await writeFile(path.join(audio, 'ambient.wav'), Buffer.concat([header, data]));
await copyFile(path.join(audio, 'ambient.wav'), path.join(generated, 'ambient.wav'));
await writeFile(path.join(generated, 'timing.json'), JSON.stringify(timing, null, 2));
await writeFile(path.join(out, 'audio-timing.json'), JSON.stringify(timing, null, 2));
const stamp = seconds => {
  const ms = Math.round(seconds * 1000);
  return `${String(Math.floor(ms / 3600000)).padStart(2, '0')}:${String(Math.floor(ms / 60000) % 60).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`;
};
const wrap = text => {
  const words = text.split(' ');
  const lines = [''];
  for (const word of words) {
    if (lines.at(-1).length + word.length + 1 > 62) lines.push(word);
    else lines[lines.length - 1] += `${lines.at(-1) ? ' ' : ''}${word}`;
  }
  return lines.join('\n');
};
// Sentence-level cues are bound to measured audio duration, not estimated words.
const subtitles = timing.map(cue => ({text: cue.text,
  start: cue.start, end: cue.start + cue.duration}));
const srt = subtitles.map((cue, i) =>
  `${i + 1}\n${stamp(cue.start)} --> ${stamp(cue.end)}\n${wrap(cue.text)}\n`).join('\n');
await writeFile(path.join(generated, 'captions.json'), JSON.stringify(subtitles, null, 2));
const voices = [...new Set(timing.map(cue => cue.voice).filter(Boolean))];
const voiceNote = voices.length ?
  `English. ${voices.join(', ')}. Native pacing; the pipeline applies no voice cloning or time compression.` :
  'No narration generated. Timed captions and ambient audio only.';
for (const dir of [project, out]) {
  await writeFile(path.join(dir, 'captions.srt'), srt);
  await writeFile(path.join(dir, 'narration.md'),
    `# MDT Observatory - narration\n\n${voiceNote}\n\n` +
    story.scenes.map(scene => `## ${stamp(scene.from).slice(0, 8)} - ${scene.title}\n\n` +
      scene.cues.map(cue => cue.text).join('\n\n')).join('\n\n'));
  await writeFile(path.join(dir, 'storyboard.md'),
    '# MDT Observatory - storyboard\n\nMicrosoft-inspired editorial treatment; not Microsoft endorsement. ' +
    'All app footage is synthetic, deterministic rehearsal. Public position cards are editorial paraphrases. ' +
    'Letter illustrations are not generated application documents or approved clinical text.\n\n' +
    story.scenes.map(scene => `## ${stamp(scene.from).slice(0, 8)} - ${scene.title}\n\n` +
      `Duration: ${scene.duration}s.\n\n${scene.visual}`).join('\n\n'));
}
console.log(`Prepared ${timing.length} speech clips, ${subtitles.length} captions and original ambient audio.`);
