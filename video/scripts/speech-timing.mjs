import assert from 'node:assert/strict';

export function timeSpeech(story, results, gap = .24) {
  return story.scenes.flatMap(scene => {
    const items = scene.cues.map((cue, i) => {
      const id = `${scene.id}-${i + 1}`;
      const audio = results.find(result => result.id === id);
      assert(audio && Number.isFinite(audio.duration) && audio.duration > 0, `Missing speech duration for ${id}`);
      return {...cue, ...audio, id, scene: scene.id};
    });
    const required = items.reduce((sum, cue) => sum + cue.duration, 0) + gap * (items.length - 1);
    const available = scene.duration - .8;
    assert(required <= available,
      `${scene.id}: natural speech needs ${required.toFixed(2)}s; ${available.toFixed(2)}s available. Shorten the script; never accelerate the voice.`);
    let limit = scene.from + scene.duration - .3;
    const latest = [];
    for (let i = items.length - 1; i >= 0; i--) {
      latest[i] = limit - items[i].duration;
      limit = latest[i] - gap;
    }
    let earliest = scene.from + .5;
    const scheduled = items.map((cue, i) => {
      const start = Math.max(earliest, Math.min(scene.from + cue.at, latest[i]));
      earliest = start + cue.duration + gap;
      return {...cue, start, requestedStart: scene.from + cue.at,
        file: cue.voice ? `${cue.id}.wav` : null};
    });
    return scheduled.map((cue, i) => ({
      ...cue, maxSeconds: (scheduled[i + 1]?.start ?? scene.from + scene.duration) - cue.start - .18,
    }));
  });
}
