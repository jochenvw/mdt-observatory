import {readFile, writeFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {project, ffmpeg, run, probe} from './tools.mjs';

const captures = path.join(project, 'captures');
const generated = path.join(project, 'assets', 'generated');
await mkdir(generated, {recursive: true});
const manifest = JSON.parse(await readFile(path.join(captures, 'manifest.json'), 'utf8'));
assert(manifest.synthetic && manifest.mode === 'rehearsal');
for (const name of ['activity', 'guidance']) {
  const clip = manifest.clips.find(item => item.name === name);
  assert(clip?.duration >= 3, `Missing recorded motion for ${name}; run npm run capture`);
  const output = path.join(generated, `${name}.mp4`);
  run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-ss', String(clip.from), '-i',
    path.join(captures, 'walkthrough.webm'), '-t', String(clip.duration), '-an',
    '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-pix_fmt', 'yuv420p',
    '-r', '25', '-movflags', '+faststart', output]);
  assert.equal(probe(output).streams[0].width, 1920);
  console.log(`Prepared ${name}: ${clip.duration.toFixed(1)}s of real application video`);
}
await writeFile(path.join(generated, 'clips.json'), JSON.stringify(
  manifest.clips.filter(clip => clip.duration).map(clip => ({
    name: clip.name, duration: clip.duration,
  })), null, 2));
