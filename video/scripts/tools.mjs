import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import encoder from '@ffmpeg-installer/ffmpeg';

export const project = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(import.meta.url);
const renderer = path.dirname(require.resolve('@remotion/renderer/package.json'));
const compositor = process.platform === 'win32' ? '@remotion/compositor-win32-x64-msvc' :
  process.platform === 'darwin' ? `@remotion/compositor-darwin-${process.arch}` :
    `@remotion/compositor-linux-${process.arch}-gnu`;
const bin = path.dirname(require.resolve(`${compositor}/package.json`, {paths: [renderer]}));
export const ffmpeg = encoder.path;
export const ffprobe = path.join(bin, process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe');
export const browserExecutable = process.env.MDT_VIDEO_BROWSER ?? chromium.executablePath();
export function run(command, args, options = {}) {
  const result = spawnSync(command, args, {encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, ...options});
  if (result.error) throw result.error;
  assert.equal(result.status, 0, `${path.basename(command)} failed:\n${result.stderr ?? ''}`);
  return result.stdout;
}
export function probe(file) {
  return JSON.parse(run(ffprobe, ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', file]));
}

export function measureAudio(file) {
  const result = spawnSync(ffmpeg, ['-hide_banner', '-i', file, '-vn', '-af',
    'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], {encoding: 'utf8'});
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr);
  const json = result.stderr.match(/\{\s*"input_i"[\s\S]*?\}/)?.[0];
  assert(json, 'Audio loudness measurements missing');
  return JSON.parse(json);
}
