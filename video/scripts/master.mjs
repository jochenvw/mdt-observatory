import {rename} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {project, ffmpeg, run, probe, measureAudio} from './tools.mjs';

export async function master() {
  const output = path.join(project, 'out', 'mdt-observatory-explainer.mp4');
  const temporary = path.join(project, 'out', 'mdt-observatory-mastering.mp4');
  const metadata = probe(output);
  const video = metadata.streams.find(stream => stream.codec_type === 'video');
  const colourReady = video.pix_fmt === 'yuv420p' && video.color_space === 'bt709' && video.color_range === 'tv';
  const levels = measureAudio(output);
  const audioReady = Math.abs(Number(levels.input_i) + 16) < .5 && Number(levels.input_tp) <= -1;
  if (colourReady && audioReady) {
    console.log('Projection master already uses limited-range BT.709 and normalized audio.');
    return;
  }
  // JPEG-backed browser renders can carry full-range BT.601 metadata. Convert
  // the pixels, not only the tag, for consistent playback on projectors.
  const inputRange = video.color_range === 'pc' ? 'full' : 'limited';
  const inputMatrix = video.color_space === 'bt709' ? 'bt709' : 'bt601';
  const picture = colourReady ? ['-c:v', 'copy'] : [
    '-vf', `scale=in_range=${inputRange}:out_range=limited:in_color_matrix=${inputMatrix}:out_color_matrix=bt709`,
    '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-pix_fmt', 'yuv420p',
    '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709',
    '-color_trc', 'bt709'];
  const sound = audioReady ? ['-c:a', 'copy'] : ['-af',
    `loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=${levels.input_i}:measured_TP=${levels.input_tp}:measured_LRA=${levels.input_lra}:measured_thresh=${levels.input_thresh}:offset=${levels.target_offset}:linear=true`,
    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000'];
  run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-i', output,
    ...picture, ...sound, '-movflags', '+faststart', temporary]);
  const converted = probe(temporary).streams.find(stream => stream.codec_type === 'video');
  assert.equal(converted.pix_fmt, 'yuv420p');
  assert.equal(converted.color_space, 'bt709');
  assert.equal(Number(converted.nb_frames), 4500);
  await rename(temporary, output);
  console.log('Created H.264 projection master: BT.709, normalized narration, fast-start MP4.');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await master();
