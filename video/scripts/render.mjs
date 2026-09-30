import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia, renderStill, openBrowser} from '@remotion/renderer';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {project, browserExecutable} from './tools.mjs';
import {master} from './master.mjs';

const out = path.join(project, 'out');
await mkdir(out, {recursive: true});
const serveUrl = await bundle({
  entryPoint: path.join(project, 'src', 'index.ts'),
  publicDir: path.join(project, 'assets'),
  outDir: path.join(out, 'bundle'),
});
const inputProps = {captions: !process.argv.includes('--no-captions'), music: !process.argv.includes('--no-music')};
const browser = await openBrowser('chrome', {browserExecutable});
try {
  const composition = await selectComposition({serveUrl, id: 'MDTObservatory',
    inputProps, puppeteerInstance: browser, browserExecutable});
  if (process.argv.includes('--stills')) {
    const times = [5, 12, 19, 27, 34, 44, 53, 58, 61.5, 64.5, 67.5, 70.5, 73.5,
      80, 86, 94, 103, 109, 114, 121, 128, 134, 139, 142, 147, 152, 157, 162, 168, 176, 179.5];
    const frames = path.join(out, 'stills');
    await mkdir(frames, {recursive: true});
    for (const [index, time] of times.entries()) {
      await renderStill({composition, serveUrl, inputProps, puppeteerInstance: browser,
        browserExecutable, frame: Math.round(time * composition.fps), imageFormat: 'png',
        output: path.join(frames, `${String(index).padStart(2, '0')}-${String(time).replace('.', '_')}s.png`)});
      console.log(`Inspected layout frame ${time}s`);
    }
    await writeFile(path.join(out, 'stills.json'), JSON.stringify(times));
  } else {
    let last = -1;
    await renderMedia({
      composition, serveUrl, inputProps, puppeteerInstance: browser, browserExecutable,
      codec: 'h264', audioCodec: 'aac', audioBitrate: '192k', crf: 18,
      pixelFormat: 'yuv420p', x264Preset: 'fast', imageFormat: 'jpeg', jpegQuality: 95,
      concurrency: 3,
      outputLocation: path.join(out, 'mdt-observatory-explainer.mp4'),
      onProgress: ({progress}) => {
        const percent = Math.floor(progress * 100);
        if (percent >= last + 5) { console.log(`Render ${percent}%`); last = percent; }
      },
    });
    await master();
    console.log(path.join(out, 'mdt-observatory-explainer.mp4'));
  }
} finally {
  await browser.close({silent: true});
}
