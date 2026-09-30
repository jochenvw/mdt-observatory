# MDT Observatory film

A three-minute, 1920 x 1080, 25 fps English explainer with a Microsoft-inspired
visual treatment: Segoe UI, blue-and-white surfaces, generous spacing, restrained
motion and explicit human control. This is not a Microsoft-branded or endorsed
product. No Microsoft logo, commercial music, stock footage or cloned voice is used.

## Reproduce

From the repository root, prepare the actual application:

```powershell
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
Set-Location video
npm ci
npx playwright install chromium
npm run capture
npm run assets
az login
$env:AZURE_SPEECH_ENDPOINT = 'https://YOUR-SPEECH-RESOURCE.cognitiveservices.azure.com/'
npm run audio
npm test
npm run render
npm run inspect
```

Output: `out\mdt-observatory-explainer.mp4`. Narration, storyboard, captions and
`audio-timing.json` are also written to `out`. The source project contains copies
of `narration.md`, `storyboard.md` and `captions.srt`.

The dependency lock targets the protected npm proxy used on the authoring machine.
If its metadata returns upstream Azure DevOps tarball paths, regenerate the lock
with `npm install --package-lock-only --ignore-scripts`, then run
`node scripts\normalize-registry.mjs` before `npm ci`. This preserves package
versions and integrity hashes and does not change package execution policy.
FFmpeg is provided as a platform binary by `@ffmpeg-installer/ffmpeg`; FFprobe
comes from Remotion's compositor. No binary-download install hook is needed.
Remotion has separate free and company licence terms; confirm eligibility for
your organization's use before commercial distribution. See the installed
`remotion\LICENSE.md` and <https://www.remotion.dev/license>.

## Source footage and clinical boundaries

`npm run capture` starts the real FastAPI app on a free loopback port, with a
new SQLite database in `captures`, and drives the real React interface using
Playwright. It never targets the hosted room. The server inherits no model or
telemetry configuration and is stopped after capture. Python dependencies must
already be installed in the repository's `.venv`.

The source is the repository's original synthetic CRC-2026-001 case: nine liver
sites, response after treatment, vascular constraints and an indeterminate lung
nodule. Capture opens all seven specialty desks and their source records,
inspects evidence, sends radiology guidance, requests targeted follow-up, and
uses the actual required concurrence controls. It verifies the decision was
captured on one plan version without blocking friction. It does not edit the
workflow, fabricate evidence or resolve questions by elapsed time.
Screenshots use a 1920 x 1080 viewport at double pixel density for sharp crops;
browser motion is recorded at 1920 x 1080.

`captures\manifest.json` identifies screenshots, recording offsets, phases and
concurrence actors. Generated snapshots retain the full record locally and are
Git-ignored. `assets\generated\record.json` contains the plan used to ground
editorial overlays. Conversation cards are labelled paraphrases of public
positions, not a fabricated chat transcript or hidden model reasoning.

The film is explicitly **scripted rehearsal**, not live AI inference. Six
required clinician-input controls are exercised by capture automation; pathology
support is automatic under the application's demo policy. These are simulated
reviews of synthetic data, not approvals by real clinicians.

The actual outcome screen reports failed document drafting because no model is
connected. That failure is retained in the film. The English letter and
English/German patient excerpts are separately labelled **illustrations**, not
successful app output or medically approved documents. The case's recorded
language remains English; the German excerpt illustrates the language capability,
not an in-app language switch. No clinical claim of time savings is presented as
a measured result. The film says the aim is to focus meeting time on judgement.

## Preview, timing and editing

```powershell
npm run preview
npm run render -- --stills
npm run render -- --no-captions
npm run render -- --no-music
```

`src\story.json` is the source of truth for narration, scene timing and storyboard.
The nine contiguous chapters cover 180 seconds. Edit the visual treatment in
`src\Movie.tsx` and `src\style.css`. Motion is frame-derived and reproducible;
there are no random animations or wall-clock-dependent React renders.
Rendering also masters the file to limited-range BT.709 H.264, normalizes audio
to approximately -16 LUFS with a -1.5 dBTP ceiling, and writes fast-start
metadata for predictable projector playback. `npm run master` reapplies that
step to an existing render without rerendering the composition.

After changing narration or timing, run `npm run audio`, then `npm test`.
Sentence-level captions use measured speech-file durations. Cue start times can
move within their chapter to preserve the voice's natural pace and pauses. Audio
is never accelerated to fit. If the chapter is still too long, generation fails
explicitly and the script must be shortened. Captions contain the exact narration.
To recapture after application changes, rebuild the frontend,
then repeat `npm run capture` and `npm run assets` before rendering.

Remotion uses Playwright's installed Chromium by default. Set `MDT_VIDEO_BROWSER`
to an installed compatible Chromium executable if required. Segoe UI is used
when installed; Arial is the fallback. No proprietary font files are distributed.
Rendering uses three concurrent browser pages to limit load on shared machines.

## Voice and sound

The supplied cut uses **Microsoft Azure Speech, Ava / DragonHDLatestNeural**:
the latest generally available DragonHD base model offered by the selected
resource. It replaces the original Windows desktop narrator. The service
generates conversational prosody at native speed; there is no pitch shifting,
tempo compression, automatic rate increase or voice cloning.

Set `AZURE_SPEECH_ENDPOINT` to an existing Azure Speech or AI Services custom
endpoint that offers the selected HD voice, and authenticate with `az login`.
The CLI identity needs permission to synthesize speech on that resource. The
script checks the resource's live voice catalogue and refuses an unavailable
or non-HD voice. Tokens stay in memory; no keys, tokens or resource identifiers
are stored in source. No resources or role assignments are created.

The default is `en-US-Ava:DragonHDLatestNeural`. `MDT_VIDEO_VOICE` can select
another generally available `DragonHDLatestNeural` voice. The narrator uses
48 kHz PCM, restrained expressive variation and explicit pronunciation of MDT
as letters. The film sends only its synthetic demonstration narration to Azure,
not the case record, repository code or clinical documents.

`audio\neural-cache` retains generated clips by text/voice hash for repeatable
renders without repeat synthesis calls. Delete the specific cached clip if you
intentionally want a fresh take from the latest service model. Generation never
falls back to a desktop voice.

For a professionally recorded or licensed voice, replace the named WAV files in
`audio` and update their measured durations in `audio\speech-results.json`.
Keep `rate` equal to `1`, set `file` to the replacement WAV filename and preserve
the exact script, or update `src\story.json` to match. If supplying new text,
update or remove the previous generation's `textHash`. Then use:

```powershell
npm run audio -- --reuse
```

Once the HD clips have been generated, `--reuse` also rebuilds captions and
timing offline, without cloud credentials. For a render without speech,
explicitly run `npm run audio -- --silent`. This
produces timed captions and ambient audio and records that no narration was used.
It is not a silent fallback from a failed voice-generation run.

`scripts\audio.mjs` synthesizes an original, quiet ambient bed and sparse chapter
tones with sine waves. It contains no downloaded music or third-party samples.

## Inspection

`npm test` type-checks the composition and checks chapter duration, exact caption
text, native-speed audio timing, overlong-speech failures, required captures, real motion assets and concurrence
provenance. `npm run render -- --stills` renders key moments for layout review.
`npm run inspect` decodes all 4,500 frames, checks codec, dimensions, frame rate,
audio, duration and luma statistics, and creates contact sheets covering the
complete movie every two seconds. Review those images for framing and readability;
statistics alone cannot establish visual quality.

Captured screenshots, source recordings, generated audio, databases, final
movies, render bundles and inspection frames are excluded from Git. Keep the
project sources and lockfile; regenerate the assets through the commands above.
No deployment or clinical runtime changes are required.
