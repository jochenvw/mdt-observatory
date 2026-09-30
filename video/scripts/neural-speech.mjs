import {readFile, writeFile, mkdir, rename, copyFile, stat} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
import {probe} from './tools.mjs';

const escapeXml = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');

function credential() {
  // A constant CLI command keeps the selected development identity explicit.
  // Access tokens remain in memory and are never written or logged.
  const result = spawnSync(
    'az account get-access-token --resource https://cognitiveservices.azure.com/ --output json',
    {shell: true, encoding: 'utf8', windowsHide: true},
  );
  if (result.error) throw result.error;
  assert.equal(result.status, 0, 'Azure CLI authentication failed. Run az login with access to the Speech resource.');
  const value = JSON.parse(result.stdout);
  assert(typeof value.accessToken === 'string' && value.accessToken.length > 0);
  return value.accessToken;
}

export async function synthesize(cues, audio) {
  assert(process.env.AZURE_SPEECH_ENDPOINT,
    'Set AZURE_SPEECH_ENDPOINT to your Azure Speech/AI Services custom endpoint. Desktop speech is not a fallback.');
  const endpoint = new URL(process.env.AZURE_SPEECH_ENDPOINT);
  assert(endpoint.protocol === 'https:' && endpoint.hostname.endsWith('.cognitiveservices.azure.com')
    && !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash,
  'Use a Microsoft Azure custom endpoint without credentials or query parameters.');
  const voice = process.env.MDT_VIDEO_VOICE ?? 'en-US-Ava:DragonHDLatestNeural';
  assert(voice.endsWith(':DragonHDLatestNeural'), 'This film requires a natural DragonHD voice, not desktop TTS.');
  const headers = {Authorization: `Bearer ${credential()}`};
  const catalogueResponse = await fetch(new URL('/tts/cognitiveservices/voices/list', endpoint), {
    headers, signal: AbortSignal.timeout(30000),
  });
  assert(catalogueResponse.ok, `Voice discovery failed: HTTP ${catalogueResponse.status}`);
  const catalogue = await catalogueResponse.json();
  const selected = catalogue.find(item => item.ShortName === voice);
  assert(selected && selected.Status === 'GA' && selected.VoiceType === 'NeuralHD',
    `The selected resource does not offer ${voice} as a generally available HD voice.`);
  const locale = selected.Locale;
  const cache = path.join(audio, 'neural-cache');
  await mkdir(cache, {recursive: true});
  const results = [];
  for (const cue of cues) {
    const spoken = escapeXml(cue.text).replaceAll('MDT', '<say-as interpret-as="characters">MDT</say-as>');
    const ssml = `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="${escapeXml(locale)}">` +
      `<voice name="${escapeXml(voice)}" parameters="temperature=0.5">${spoken}</voice></speak>`;
    const key = createHash('sha256').update(`${voice}\n${ssml}`).digest('hex');
    const file = path.join(cache, `${key}.wav`);
    let cached = true;
    try {
      await readFile(file);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      cached = false;
    }
    if (!cached) {
      const response = await fetch(new URL('/tts/cognitiveservices/v1', endpoint), {
        method: 'POST',
        headers: {...headers, 'Content-Type': 'application/ssml+xml',
          'X-Microsoft-OutputFormat': 'riff-48khz-16bit-mono-pcm', 'User-Agent': 'MDT-Observatory-Film'},
        body: ssml, signal: AbortSignal.timeout(90000),
      });
      assert(response.ok, `HD speech failed for ${cue.id}: HTTP ${response.status}. No voice fallback was used.`);
      const data = Buffer.from(await response.arrayBuffer());
      assert(data.length > 1000 && data.toString('ascii', 0, 4) === 'RIFF'
        && data.toString('ascii', 8, 12) === 'WAVE', `Invalid speech audio for ${cue.id}`);
      const temporary = `${file}.partial`;
      await writeFile(temporary, data);
      await rename(temporary, file);
    }
    const info = probe(file);
    const duration = Number(info.format.duration);
    assert(Number.isFinite(duration) && duration > 0 && duration < 30, `Invalid duration for ${cue.id}`);
    assert.equal(info.streams[0].sample_rate, '48000');
    await copyFile(file, path.join(audio, `${cue.id}.wav`));
    results.push({id: cue.id, duration, voice, rate: 1,
      provider: 'Microsoft Azure Speech', model: 'DragonHDLatestNeural',
      naturalPace: true, textHash: createHash('sha256').update(cue.text).digest('hex'),
      generatedAt: (await stat(file)).mtime.toISOString(), file: `${cue.id}.wav`});
    console.log(`${cue.id}: ${duration.toFixed(2)}s, ${cached ? 'cached' : 'Azure HD'}, native pace`);
  }
  await writeFile(path.join(audio, 'speech-results.json'), JSON.stringify(results, null, 2));
  return results;
}
