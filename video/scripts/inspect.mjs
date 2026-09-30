import {readFile, writeFile, mkdir, readdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {project, ffmpeg, ffprobe, run, probe, measureAudio} from './tools.mjs';

const out = path.join(project, 'out');
const inspection = path.join(out, 'inspection');
await mkdir(inspection, {recursive: true});
const film = path.join(out, 'mdt-observatory-explainer.mp4');
const metadata = probe(film);
const video = metadata.streams.find(stream => stream.codec_type === 'video');
const audio = metadata.streams.find(stream => stream.codec_type === 'audio');
assert.equal(video.width, 1920);
assert.equal(video.height, 1080);
assert.equal(video.codec_name, 'h264');
assert.equal(video.r_frame_rate, '25/1');
assert.equal(video.pix_fmt, 'yuv420p');
assert.equal(Number(video.nb_frames), 4500);
assert.equal(audio.codec_name, 'aac');
assert(Math.abs(Number(metadata.format.duration) - 180) < .1);
// Decode the entire file, rather than checking only the MP4 header.
run(ffmpeg, ['-v', 'error', '-xerror', '-i', film, '-f', 'null', '-']);
const report = run(ffprobe, ['-v', 'error', '-show_entries',
  'stream=index,codec_name,width,height,nb_frames,r_frame_rate,duration', '-of', 'json', film]);
await writeFile(path.join(inspection, 'media.json'), report);
// The bundled encoder deliberately has a small filter set. Analyze decoded raw
// pixels without depending on optional system FFmpeg filters or image packages.
const gray = run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-i', film,
  '-vf', 'scale=160:90', '-pix_fmt', 'gray', '-an', '-f', 'rawvideo', 'pipe:1'],
{encoding: null, maxBuffer: 96 * 1024 * 1024});
const pixels = 160 * 90;
assert.equal(gray.length, 4500 * pixels, 'Every rendered frame must be examined');
const luma = [];
const variation = [];
for (let frame = 0; frame < 4500; frame++) {
  let total = 0;
  let squared = 0;
  for (let i = frame * pixels; i < (frame + 1) * pixels; i++) {
    total += gray[i];
    squared += gray[i] ** 2;
  }
  const mean = total / pixels;
  luma.push(mean);
  variation.push(Math.sqrt(squared / pixels - mean ** 2));
}
assert(luma.every(value => value > 20 && value < 253), 'Unexpected black/blank frame');
assert(variation.every(value => value > 3), 'Unexpected uniform frame');

// Every two seconds of the final encode, not just the composition's keyframes.
const thumbnails = run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-i', film,
  '-vf', 'scale=640:360', '-r', '1/2', '-pix_fmt', 'rgb24', '-an', '-f', 'rawvideo', 'pipe:1'],
{encoding: null, maxBuffer: 96 * 1024 * 1024});
const thumbBytes = 640 * 360 * 3;
const thumbCount = thumbnails.length / thumbBytes;
assert(Number.isInteger(thumbCount) && thumbCount >= 90);
const sheetWidth = 1944;
const sheetHeight = 1104;
for (let sheet = 0; sheet < Math.ceil(thumbCount / 9); sheet++) {
  const rgb = Buffer.alloc(sheetWidth * sheetHeight * 3, 241);
  for (let tile = 0; tile < 9 && sheet * 9 + tile < thumbCount; tile++) {
    const index = sheet * 9 + tile;
    const x = 6 + (tile % 3) * 646;
    const y = 6 + Math.floor(tile / 3) * 366;
    for (let row = 0; row < 360; row++) {
      const start = index * thumbBytes + row * 640 * 3;
      thumbnails.copy(rgb, ((y + row) * sheetWidth + x) * 3, start, start + 640 * 3);
    }
  }
  run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
    '-pixel_format', 'rgb24', '-video_size', `${sheetWidth}x${sheetHeight}`, '-i', 'pipe:0',
    '-frames:v', '1', path.join(inspection, `sheet-${String(sheet + 1).padStart(2, '0')}.png`)],
  {input: rgb});
}
const audioLevels = measureAudio(film);
assert(Number(audioLevels.input_tp) < 0, 'Audio clips above full scale');
assert(Number(audioLevels.input_i) > -30, 'Narration is too quiet');
assert(Math.abs(Number(audioLevels.input_i) + 16) < 1, 'Projection narration must be near -16 LUFS');
const timing = JSON.parse(await readFile(path.join(out, 'audio-timing.json'), 'utf8'));
assert(timing.every(cue => cue.duration > 0 && cue.start + cue.duration < 180));
for (let i = 1; i < timing.length; i++) {
  assert(timing[i - 1].start + timing[i - 1].duration <= timing[i].start, 'Speech overlap');
}
const sheets = (await readdir(inspection)).filter(name => /^sheet-.*\.png$/.test(name));
await writeFile(path.join(inspection, 'report.json'), JSON.stringify({
  duration: Number(metadata.format.duration), resolution: [video.width, video.height],
  fps: 25, decodedFrames: luma.length, minMeanLuma: Math.min(...luma),
  maxMeanLuma: Math.max(...luma), minLumaDeviation: Math.min(...variation),
  captionCues: timing.length, audio: audioLevels,
  contactSheets: sheets, note: 'Contact sheets must also be visually reviewed; statistics do not prove text legibility.',
}, null, 2));
console.log(`Decoded all 4500 frames. ${sheets.length} contact sheets ready for visual review.`);
