# Verification record

## Three-case integration - 2026-09-17

The two distinct narratives in `case_2.md` are separately selectable alongside
the original colorectal case. Case records, specialist contexts, evidence,
friction, proposals and memory cards are case-bound. Academic framing names were
removed from repository sources; older generated audit artifacts were relocated
outside the repository without rewriting their contents.

| Gate | Evidence |
|---|---|
| Quality | Ruff and mypy pass; 220 Python tests including seven browser cases; 121 frontend tests and production build pass |
| Source fidelity | Original clinical YAML retained; both additional narratives and source tables compared against sanitized source; updated SHA-256 provenance |
| Clinical limits | Sparse eleven-site mapping, disappearing lesions, unvalidated perioperative risks, renal staging discrepancy and hypothetical outcomes retained |
| Isolation | All seven roles tested for each added case; concurrent cases, foreign-source rejection, memory scoping and durable completed workflows covered |
| Live protocol | Real SDK with mocked transport verifies case-bound tool loops and applicability gates; duplicate source representations are losslessly referenced within the unchanged 48,000-token budget |
| Presentation | Three selected-ID submissions, all fourteen added specialty contexts, both themes, full records and mobile tested; clinical risk-model and response data remain visible |
| Packaging | Wheel includes all three dossiers and additional evidence; repository-owned file scan including ignored artifacts finds no framing contributor names |
| Release | Exact-image Bicep/ARM/what-if pass, eight policies inspected, no deletions; healthy single active revision/replica with unchanged private Blob and scoped identity roles |
| Cloud acceptance | Authenticated three-case catalog, seven roles in both themes, mobile and record/resume paths pass; added-case assets exercised with browser-only local fixtures |
| Room preservation | Existing live room `4bc0d93e-9e37-471c-b139-3ccb09aeacc7` remains TARGETED_DISCUSSION, 274 events, with byte-identical export; no cloud test meeting replaced it |

Deployed image:

```text
acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:37eb593b248118957c21657c5f53b8ef80a617c807a8ab87d52c69610eb28083
```

Revision: `mdt-observatory-vnet--r20260917151534-a56132`.
No additional real-model cloud meeting was created for acceptance. Local workflow
and real-SDK mocked-transport checks cover the added runtime bindings; browser-only
fixtures verify the deployed frontend without altering the presenter's room.

These checks validate software behavior and source fidelity, not clinical safety,
medical correctness, model efficacy or regulatory readiness. Source publication
access is recorded honestly; the added independently verified articles are
abstract-only, not claimed full-protocol review.

## Timeout recovery and clinical-error presentation - 2026-09-17

The current room's oncology audit records `APITimeoutError` at 12:36:12 UTC,
followed by successful publication after an explicit retry at 12:49:54 UTC.
The request client had a 30-second timeout and no timeout retry. The audit
establishes a request timeout, not whether upstream latency or networking caused
it. The room was already healthy when this incident was investigated.

The presentation regex missed acronym-led exception names, and the engine copied
every activity summary into the next clinical question. Both paths are fixed:
operational events stay in audit/activity, and legacy error-bearing traces
produce visible clinician-readable alerts without rewriting persisted records.

| Gate | Evidence |
|---|---|
| Quality | Ruff and strict mypy pass; 179 Python tests including all five browser tests; 83 frontend tests and production build pass |
| Request handling | Real SDK with mocked transport verifies actual dispatched 90-second read, 10-second connect/pool and 30-second write limits; one timeout/connection retry, no SDK retries |
| Recovery boundaries | Both request stages recover or exhaust explicitly; no completed-tool replay or rehearsal fallback; pacing, finite 429 budgets, active deadline cancellation and client cleanup retained |
| Workflow | Failure blocks synthesis and preserves the clinical question, while the original exception remains in audit/activity |
| Browser | Exact reported string becomes an alert, not a next-question block; exception/fallback wording absent from clinical DOM; raw fixture unchanged |
| Azure | Exact-image ARM validation and what-if pass; one healthy active revision/replica and unchanged private Blob/identity gates |
| Cloud verification | Seven roles, both themes, mobile and a read-only replay of the reported legacy snapshot pass against deployed assets |
| Preservation | Current live room `4bc0d93e-9e37-471c-b139-3ccb09aeacc7` remains TARGETED_DISCUSSION with 274 events and a byte-identical export; no clinical commands or new model meetings issued |

Preceding timeout-release image:

```text
acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:1be329961488d0196d3a9cccab52101dd412c01d8f83f979e4546bffd901d528
```

Revision: `mdt-observatory-vnet--r20260917140552-8829a1`.
Screenshots remain in ignored `artifacts`. Historical preservation exports
containing older source attribution are retained outside the repository in the
private session archive.

## Live activity desks and case selection - 2026-09-17

This release put public assessments, newest-first activity and human
controls ahead of detailed source records, with a terse right-hand case rail.
Seven specialty identities and light/dark themes remain distinct.

| Gate | Evidence |
|---|---|
| Application checks | Ruff, strict mypy, 164 Python tests including all five browser tests, 76 frontend tests and production build pass |
| First-screen behavior | All seven role headers, attention cues, guidance controls and case-record access fit the desktop view; activity begins above y=530 at 1440x900; required concurrence controls remain in view |
| Updates | Newest-first event order, stable existing entry nodes, preserved drafts/scroll, 900 ms entry animation and reduced-motion suppression verified in the browser |
| Case selection | Protected catalog exposes only the configured CRC case; selected-ID fidelity, unknown-ID no-mutation, active-round exclusion, resume and explicit execution-mode preservation verified |
| Clinical safeguards | Role failures remain immediate; stale votes require the current proposal; human and agent concurrence remain distinct; full assessments, conditions and source records remain inspectable |
| Infrastructure | Exact-image Bicep/ARM validation and what-if pass with no deletions; scoped identity roles and private Blob gates unchanged |
| Cloud UI | Authenticated, read-only acceptance across all seven roles in both themes, mobile, catalog, resume and inspection drawers; no clinical commands or page errors |
| Current-room preservation | Live room `4bc0d93e-9e37-471c-b139-3ccb09aeacc7` retained in TARGETED_DISCUSSION with 274 events; export byte-identical before release, after replacement and after browser acceptance |

Preceding activity-desk release image:

```text
acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:c6b57bcdccceb97172eb650c3744d04831a5bcde08b723e17b4736898d5425ef
```

Revision: `mdt-observatory-vnet--r20260917133707-028a7d`.
One active revision and replica; managed-identity private Blob persistence.
No additional real-model meeting was started for this UI release, so the
presenter's current room was not replaced by an acceptance fixture.
Screenshots and preservation evidence remain in Git-ignored `artifacts`.

## Full colorectal dossier release - 2026-09-17

The current application uses the complete supplied `case.md` clinical record.
These checks verify software behavior and source fidelity, not clinical safety,
medical correctness or regulatory readiness.

| Gate | Evidence |
|---|---|
| Source fidelity | All 22 structured sections, nine baseline/response lesions, three alternatives and eight consultation contributions retained; original source SHA checked and source file unchanged |
| Packaged data | `src/mdt/dossiers/crc_case.json` included in the built wheel and checked against the runtime dossier |
| Python | Ruff and strict mypy across 11 modules pass; 162 tests pass with all five browser tests enabled, 92% coverage |
| Browser | Complete workflow, full dossier, all seven layouts, light/dark themes, mobile, clinical activity and visible errors; three additional regressions verify explicit mode selection survives late snapshots and reconnects |
| Frontend | 72 unit tests and TypeScript/Vite production build pass |
| Evidence | Five separately verified source records; original CAIRO5 abstract-only, four full-text records; publication/access dates and applicability limits remain explicit |
| Historical records | Earlier-case mutations rejected without rewriting old snapshots; new-case proposal, export and restart retain the complete dossier |
| Real-model UI | All seven workspaces inspected during actual CRC model activity without page errors or technical-provider text; nine lesions, three alternatives and eight contributions present |
| Real-model workflow locally | `fa34b63c-bf11-4512-a2d4-3663ec98d772` captured with seven valid positions, 287 events and explicit human steering/concurrence in 499.2 seconds |
| Real-model workflow in Azure | `df3f94ff-e0cf-408e-aa5e-54b600f8b4a2` captured with seven valid positions and 289 events in 489.2 seconds; managed identity, full case and human gates preserved |
| Cloud telemetry | Matching `CaseClosed` log at 2026-09-17T12:06:49.667607Z, plus model, role, tool and persistence spans |
| Cloud browser | Both authenticated acceptance tests pass against the final image (104.36 seconds), including selected rehearsal mode, full workflow, dossier and specialty themes |
| Release persistence | Both the preceding lung decision and complete CRC live decision remained byte-identical across the final drain/replacement; latest CRC selection preserved |
| Final rehearsal | `7f22b8d5-28c1-401a-acce-6460aa026b35` captured on the final image: seven roles, 304 events, exact whole-case equality and complete export |
| Release | Final image healthy with one active revision/replica, unchanged private Blob policies and all three scoped identity roles |

All new clinical presentation removes the repetitive legacy data label. The
demonstration/not-for-clinical-use notice remains; internal evidence-schema flags
and historical audit records retain compatibility.

Preceding colorectal dossier release image:

```text
acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:0ba97fe380625977a2c6944635320036a97d80708b0d1e42d284896d815248b4
```

Revision: `mdt-observatory-vnet--r20260917122210-92169a`.
The complete live CRC export retained SHA256
`7f2105468bbcd1ec7a30c8b085bffe80b0d10a80bc2561e5e4610f7ea5bbaf91`
across the final replica replacement. Source fidelity and preservation proofs,
live/rehearsal exports and browser screenshots are retained under ignored
`artifacts/crc-*` files.

## Previous Tailwind release - 2026-09-16

These earlier checks validate the preceding software demonstration,
not clinical safety, medical correctness or regulatory readiness.

| Gate | Evidence |
|---|---|
| Python quality | Ruff and strict mypy pass across all 10 application modules |
| Python acceptance | 116 tests pass, including two real-browser tests, concurrent reviews, provider budgets, Blob storage, stale writes and outage recovery; 91% coverage |
| Frontend | Tailwind 4.3.3, 55 unit tests and TypeScript/Vite production build pass |
| Specialty UI | All seven distinct compositions verified in both themes, including actual case-field bindings, mobile navigation/overflow, persisted/system/URL theme preferences and keyboard switching |
| Clinical activity | Provider metadata and internal event/tool names absent from visible and hidden UI content; clinical findings remain, and failures explicitly state that no new conclusion was recorded |
| Local running service | Complete rehearsal captured as `bd983f62-c6a1-4bb4-adb9-1fc2bb03469b`, seven roles, 216 events |
| Real Azure model locally | Full meeting `38ae90ff-61e4-426b-afec-73e97d81090f` captured, seven roles, 229 events, 492.7 seconds |
| Concurrent Azure reviews locally | Meeting `c7cf1307-b246-41d0-a858-bd2fcdc381d9` captured, seven roles, 226 events, 484.1 seconds, zero rate-limit events; three specialties executed tools before the first position was published |
| Local update persistence | Existing in-discussion meeting `628ad3ae-675a-48a5-90c5-00e84c031d08` restored byte-for-byte after restarting the updated runtime |
| Public dependencies | Frozen Python/npm locks; Python artifact hashes verified against public PyPI; ACR remote builds succeed |
| Private infrastructure | Customer VNet, approved Blob private endpoint and scoped managed-identity roles deployed; public storage and Shared Key remain disabled |
| Azure application | TLS, health, readiness, protected API, presenter login and complete real-browser walkthrough pass |
| Tailwind cloud release | Both authenticated browser tests pass against the new image (79.13 seconds), including all specialty layouts/themes and the complete workflow |
| Cloud update persistence | Existing decision `4f675568-da0a-4d2e-ae31-ff18af310432` and latest-meeting selection preserved byte-for-byte across the image release |
| Real Azure model in cloud | Meeting `4f675568-da0a-4d2e-ae31-ff18af310432` captured with seven roles and 228 events, using managed identity and real model calls without fallback |
| Concurrent Azure reviews in cloud | New-release meeting `4354f818-464c-4106-8951-42062e7f962c` captured with seven roles, 228 events, 484.7 seconds and zero rate-limit events; three specialties performed tool work before the first published position |
| Clinical UI during real inference | All seven deployed workspaces inspected during actual model activity; no raw provider metadata or page errors, while audit exports retain provenance |
| Cloud restart persistence | Original replica fully removed; exactly one healthy replacement restored the latest meeting and byte-identical complete decision export |
| Telemetry | Deployed model, role, tool and persistence spans, real deployment/request/token metadata, `mdt.events` metrics and the cloud meeting's `CaseClosed` log queried in Application Insights |
| Migration cleanup | Unused original app, environment and two old identity role assignments removed; environment absence verified after asynchronous deletion |

Deployed demo:
<https://mdt-observatory-vnet.delightfulfield-8de6d3f0.westeurope.azurecontainerapps.io>.
Presenter access is required. The locally generated token is stored in the
Git-ignored, current-user-restricted `.azure\presenter-token.txt`.

The preceding Tailwind release image was:

```text
acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:4b3271795f4dee592c0c7fb1b06a1070cd0bb8faa2f159d8bddc630d66004204
```

## Reproduce

```powershell
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen mypy
Set-Location frontend
npm ci
npm test
npm run build
Set-Location ..
uv run --frozen playwright install chromium
$env:MDT_BROWSER_TESTS = "1"
uv run --frozen pytest --cov=mdt
```

The real model smoke uses `scripts\smoke.py --mode azure` against a running
configured API. Rehearsal is the predictable 60-90 second presenter path; this
small shared model deployment requires paced requests and took about eight
minutes for the complete live-model scenario.

Generated decision exports and desktop/mobile screenshots are retained in ignored
`artifacts\`. Deployment history, including the storage-policy finding and its
private-network resolution, is recorded in `.azure\deployment-plan.md`.
The Tailwind release's final live meeting and interleaving evidence are in
`artifacts\tailwind-cloud-azure-decision.json` and
`artifacts\tailwind-cloud-live-proof.json`. Application Insights recorded its
matching `CaseClosed` event at 2026-09-16T19:43:32Z.

## Cloud durability proof

The completed cloud meeting was exported before restarting its active revision.
Verification waited until the original replica was absent and exactly one ready
replacement remained, rather than accepting a health response during overlap.
The replacement returned the same latest meeting ID and `DECISION_CAPTURED`
phase; the full export, including positions, evidence, memory, concurrence and
event history, had the same SHA256:

```text
0D11FAB8E6305854E51DF929A2950B6679EC0BA838030EFCC75B5ACB60AC08AE
```

`artifacts\cloud-before-restart.json` and
`artifacts\cloud-restart-proof.json` retain the snapshot, hash, replica identities
and verification timestamp (2026-09-16T15:59:17Z).
Application Insights separately recorded the matching `CaseClosed` event at
2026-09-16T15:54:33Z under service name `mdt-observatory`.
