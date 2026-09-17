# MDT Observatory deployment plan

Status: Deployed - room synchronisation release live

Released 2026-09-17 (22:41 +02:00): image
`sha256:378d7ffa39766c1c5d443b95964b46c44ffd8bcbf7a57e87e384541fb6c607d8`,
revision `mdt-observatory-vnet--r20260917204147-7df16e`, 100% traffic, single active
replica, `RunningAtMaxScale`, prior revisions drained. Built from the committed and
pushed source at `42059c4` (clean working tree, tag `release-room-sync`,
https://github.com/jochenvw/mdt-observatory), so the running container is provably
the published commit. TLS/health/readiness/private-Blob verified by the release
script; live smoke test confirmed the frontend returns 200 while `/api/meeting`,
`/api/room/stream` and `/api/cases` all return 401 without the presenter cookie and
200 with it, listing all three cases. Live RBAC re-confirmed: AcrPull, Storage Blob
Data Contributor on the `mdt-state` container only, Cognitive Services OpenAI User.

Previously released 2026-09-17: image `sha256:043d7cdba49f1f12c0303f0cdd22aa5d4edc05a25815b3bbd223ee9796695f57`,
revision `mdt-observatory-vnet--r20260917174949-3656fc`, 100% traffic, single active
replica, prior revisions drained, TLS/health/readiness/private-Blob verified. Live
RBAC re-confirmed: AcrPull at the registry, Storage Blob Data Contributor scoped to
the `mdt-state` container only, and Cognitive Services OpenAI User on the existing
model account. Live acceptance of the new room channel: `GET /api/room/stream`,
`GET /api/meeting` and `POST /api/room/clear` all return 401 without the presenter
cookie; authenticated, clearing returned `{"cleared": true}`, `GET /api/meeting`
then reported `null` (standby) and the cleared meeting record remained readable at
`GET /api/meetings/{id}` (200). A deliberate `az containerapp revision restart` then
confirmed the reset is durable: the room still reported `null` after the restart
instead of resurrecting the closed case. The live room was left on standby.

Superseded during this release: `sha256:f3b51cb6…` (revision `…r20260917171524-10546a`)
and `sha256:684176de…` (revision `…r20260917173323-c950b5`); the latter exposed the
non-durable reset that this release fixes.

Released 2026-09-17: image `sha256:66821dd96a6e4318f3e51248ab739355199bc6f176937b20b05bbff49d9dce7e`,
revision `mdt-observatory-vnet--r20260917164101-10952a`, 100% traffic, single active
replica, prior revisions drained, TLS/health/readiness/private-Blob verified. Live
RBAC re-confirmed: AcrPull, Storage Blob Data Contributor on `mdt-state` only, and
Cognitive Services OpenAI User on the existing model account.

Previously released 2026-09-17: image `sha256:99f639e1bd3f01866c1fde0d21acd3a45d02607ccc5b71f1136127c2a6ed4fd1`,
revision `mdt-observatory-vnet--r20260917155254-b1c68c`, single active replica,
legacy app drained, TLS/health/readiness verified.

## Objective and success conditions

Implement vision.txt as an agentic oncology MDT demonstrator using fictional data.
Completion requires a tested local browser experience, independently scoped
specialist agents, structured evidence and friction, human steering and sign-off,
persistent decision provenance, Azure deployment, and verified instrumentation.

Completed CRC release: replace the initial lung case with the complete supplied `case.md`
colorectal-conversion dossier (`case.txt` is absent). Preserve all source fields,
dates, uncertainty, three management alternatives and eight consult contributions.
Surface the record throughout the seven existing specialty workspaces and export;
remove repetitive fictional-data labels while retaining the demonstration safety
notice. Historical meetings remain unchanged and review/export-only.

Current release: package both distinct case narratives from `case_2.md`, remove
personal academic framing from repository sources, and expose three selectable
cases. Bind role data, tools, prompts, evidence, friction, proposals and memories
to the chosen case without global switching. Preserve source ambiguity, current
room/export bytes, timeout recovery, human review and private storage gates.
No quota, dependency, RBAC or network changes are required.

Follow-up release: rewrite frontend-only section headers and role taglines that
read as marketing copy (e.g. "THE CHAIR FINDS THE FRICTION, NOT THE ANSWER",
"The meeting, unfolding") into plain, clinical-software-grade labels, consistent
with hospital software conventions. No backend, evidence, contract, infra or
RBAC changes; TSX/test-only diff.

Demonstration comprehension release: make the reasoning and the route to
consensus followable on a projected screen by clinicians without AI background.
Narrate meeting-stage, clinician-guidance, evidence-request, retry, interruption,
memory and concurrence-invalidation events in clinical language instead of the
generic team-update fallback; show each specialty's reasoning as an expanded
numbered sequence (question, what was checked, what was found, what remains
uncertain, position, next question); add a consensus panel reporting alignment,
positions revised after focused discussion and recorded reviews; differentiate
workspace-wall cards by specialty responsibility, own finding and distinct
uncertainty; raise the activity-log and phase-rail type scale and state the
plain-language meaning of the current stage. One backend string in
`src/mdt/agents.py` loses a tool-implementation reference. No contract, schema,
infra, quota, RBAC or network changes. The generic unknown-event fallback,
failure visibility, rehearsal/live labeling and human review gates are preserved.

Room synchronisation release: run the demonstration across several screens at once.
Every screen subscribes to the room rather than to one meeting, so a specialty screen
opened before any case exists is already attached, shows a specialty-branded standby
view stating that no patient record is loaded, and populates when the orchestrator
starts a case. Starting a different case replaces every screen from scratch. The
orchestrator gains a "Return room to standby" control that wipes every screen back to
standby without deleting the meeting, which stays readable and exportable; it is
refused while a round is running. The same reset is offered on the case-selection
screen beside the current meeting, so the room can be emptied from where the next
case is chosen. No infra, quota, dependency, RBAC or network changes.
Persistence, export bytes, presenter authentication, failure visibility,
rehearsal/live labeling and human review gates are preserved.

Status note: validated 2026-09-17 by azure-validate; Section 7 proof recorded above.

All validation checks pass for the build stage:
- [x] Bicep compilation and authenticated approved subscription.
- [x] Baseline ARM validation, what-if without deletions, eight inherited policies inspected.
- [x] Static least-privilege role assignments and one-writer/private-storage gates.
- [x] Ruff, mypy, 220 Python tests including seven browser cases, 121 frontend tests/build.
- [x] Installed wheel includes three dossiers and the additional evidence resource.
- [x] Repository-owned name scan, including ignored artifacts, passes.
- [x] Exact-image revalidation at 2026-09-17 17:14 +02:00; no deletions.
- [x] Fresh idle-room snapshot and read-only deployed acceptance; export byte-identical.
- [x] Header/tagline copy pass: 121 frontend tests, production build, Ruff/mypy/pytest re-run clean.
- [x] Demonstration comprehension pass: Ruff, mypy, 220 Python tests including seven browser cases, 133 frontend tests, production build, screenshot review at 1920x1080.
- [x] Room synchronisation pass: Ruff, mypy, 226 Python tests including eight browser cases (one driving seven simultaneous browser contexts), 136 frontend tests, production build.

## Section 7: Validation Proof - room synchronisation release

Commands completed on 2026-09-17 (19:00-19:20 +02:00):

| Command | Result |
|---|---|
| `uv run --frozen ruff check .` | All checks passed |
| `uv run --frozen mypy` | Success: no issues found in 12 source files |
| `MDT_BROWSER_TESTS=1 uv run --frozen pytest -q` | 226 passed, 2 warnings |
| `npx tsc -b` | No diagnostics |
| `npm test -- --run` | 10 test files, 136 tests passed |
| `npm run build` | Built clean |
| `az bicep build --file infra/main.bicep` | Compiled clean, no errors or warnings |
| `az account show` | Authenticated to approved subscription `e3825c9a-4bce-43e1-899e-1610156c9383`, Enabled |
| Static role review of `infra/modules/*.bicep` | Exactly three assignments: AcrPull `7f951dda`, Storage Blob Data Contributor `ba92f5b4` scoped to the `mdt-state` container, Cognitive Services OpenAI User `5e0bd9bd`. No Owner or Contributor. |

New regression coverage:
- `tests/test_api.py` adds five room tests: a screen attached before any case exists
  receives the activation, clearing returns every screen to standby while the meeting
  record stays reviewable and exportable, clearing is refused (409) during an active
  round and rejected without presenter authentication, a cleared room stays cleared
  across a server restart (with the reset recorded on the meeting's own audit trail),
  and an uncleared room still resumes on the participants' screens after a restart.
- `tests/test_browser.py` adds `test_participant_screens_follow_the_orchestrator_across_cases`,
  which opens seven independent browser contexts (one orchestrator, six specialties),
  asserts every specialty screen starts on its own standby view with no patient record,
  that all six populate with the orchestrator's case and each shows its own distinct
  reasoning, that "Return room to standby" wipes all six with no residue of the case,
  and that a second, different case repopulates all six from scratch, then clears the
  room again from the case-selection screen and confirms all six return to standby
  with no residue while the second meeting stays exportable.
- `frontend/src/standby.test.tsx` asserts the standby view renders each specialty's own
  identity and responsibilities with no patient content, that the seven standby screens
  remain visually distinct, that a room update for a different meeting replaces the
  screen while a stale update for the current meeting is ignored, and that the
  case-selection reset appears only when a case is loaded, explains that it empties
  every screen while keeping the record, and is disabled during an active round.

Infrastructure is unchanged from the validated baseline: no edits to `infra/`,
`azure.yaml`, `Dockerfile`, `pyproject.toml` or `uv.lock`. The prior subscription-scope
ARM validation, ResourceIdOnly what-if with no deletions and eight inspected policy
assignments therefore remain in force. No quota, dependency, RBAC or network changes.

Backend changes are additive to the HTTP surface: `GET /api/room/stream` and
`POST /api/room/clear`, both behind the same presenter-cookie gate as every other
patient-data route, and `GET /api/meeting` now reports the active room rather than
the last meeting. Clearing does not delete: persistence, export bytes, conditional
ETag writes, the one-writer gate and the single active revision/replica gate are
untouched. Returning the room to standby is an explicit orchestrator action rather
than an automatic consequence of consensus, so a captured decision stays on screen
for discussion until the room is cleared. Clearing is now durable: the meeting model
gains `cleared`, the reset is written through the existing persistence path as a
`RoomCleared` audit event, and the engine restores the standby state on startup, so a
revision restart cannot resurrect a closed case onto the participants' screens. The
additive `cleared` field is the only schema change; exports of meetings recorded
before this release are unaffected.

## Section 7: Validation Proof - demonstration comprehension release

Commands completed on 2026-09-17 (18:15-18:45 +02:00):

| Command | Result |
|---|---|
| `uv run --frozen ruff check .` | All checks passed |
| `uv run --frozen mypy` | Success: no issues found in 12 source files |
| `MDT_BROWSER_TESTS=1 uv run --frozen pytest -q` | 220 passed, 2 warnings |
| `npx tsc -b` | No diagnostics |
| `npm test -- --run` | 9 test files, 133 tests passed |
| `npm run build` | Built in 2.21s; 386.66 kB JS / 63.88 kB CSS |
| `uv build --wheel --quiet` | Wheel contains all four clinical/evidence JSON resources |
| `az bicep build --file infra/main.bicep` | Compiled clean, no errors or warnings |
| `az account show` | Authenticated to approved subscription `e3825c9a-4bce-43e1-899e-1610156c9383` |

New regression coverage: `frontend/src/consensus.test.tsx` asserts the alignment,
revision and recorded-review counts, that agent auto-concurrence is labelled as not
human sign-off, and that no decision is claimed before one is captured.
`frontend/src/presentation.test.ts` asserts the ten process event types no longer
fall through to the generic team-update filler, that none leak technical wording,
and that the unknown-event fallback is still preserved.

Infrastructure is unchanged from the validated baseline: no edits to `infra/`,
`azure.yaml`, `Dockerfile`, `pyproject.toml` or `uv.lock`. The prior subscription-scope
ARM validation, ResourceIdOnly what-if with no deletions, and eight inspected policy
assignments therefore remain in force. Static role verification re-confirmed AcrPull
at the registry, Blob Data Contributor at the container and OpenAI User at the model
account. Private Blob networking, disabled shared keys and anonymous access,
conditional ETag writes and the single active revision/replica gate are untouched.

The single backend change is one clinician-facing string in `src/mdt/agents.py`;
no contract, schema, evidence, tool-scope or persistence behaviour changes.

## Section 7: Validation Proof - three-case release

Commands completed on 2026-09-17:
`uv run --frozen ruff check .`, `uv run --frozen mypy`,
`MDT_BROWSER_TESTS=1 uv run --frozen pytest`, `npm test -- --run`,
`npm run build`, and `uv build --wheel --quiet`.
All passed: 220 Python tests, 121 frontend tests and the production build.
The wheel contains all four clinical/evidence JSON resources.

The session `validate-activity.ps1` completed Bicep compilation, subscription-scope
ARM validation and ResourceIdOnly what-if with no deletions against the baseline
image. Eight policy assignments were inspected. Static role verification confirms
AcrPull at the registry, Blob Data Contributor at the container, and OpenAI User
at the existing model account. Private Blob networking, disabled shared keys and
anonymous access, conditional ETags and one replica are unchanged.

The current cloud room is idle in TARGETED_DISCUSSION with 274 events; its raw
export is preserved in the private session folder, outside the repository.
Historical generated artifacts containing old source attribution were moved out
of the repository without modifying their audit contents. Source documents and
current packaged records are de-identified; clinical source fidelity passes.

Exact-image Bicep/ARM validation and what-if passed at 2026-09-17 17:14 +02:00,
with eight inherited policy assignments inspected and no deletions. Live RBAC
confirms the three expected scoped roles for the unchanged app identity.

### Follow-up: clinical-header copy pass

`az bicep build --file infra\main.bicep` compiled cleanly with no diff to
infrastructure (this release is frontend copy/test only). Re-ran
`uv run --frozen ruff check .` (pass) and `uv run --frozen pytest -q`
(213 passed, 7 skipped — browser tests skipped, no backend behavior touched)
to confirm the backend is unaffected. `npm test -- --run` (121 passed) and
`npm run build` (clean production build) verify the rewritten headers/taglines
render correctly and no test still asserts the old marketing-style copy. No
RBAC, network, storage or evidence-contract change; same image build/release
recipe as prior releases.

Validated image:
`acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:37eb593b248118957c21657c5f53b8ef80a617c807a8ab87d52c69610eb28083`

Released revision `mdt-observatory-vnet--r20260917151534-a56132` is healthy with
exactly one active revision/replica and the expected immutable image. Post-release
RBAC confirms the unchanged app identity and its three scoped data-plane roles.
The authenticated catalog exposes all three cases. Deployed assets passed
seven-role, light/dark, mobile, record and resume checks. Both added cases were
also rendered through browser-only local fixtures, not replacement cloud meetings.
The existing room `4bc0d93e-9e37-471c-b139-3ccb09aeacc7` remains idle in
TARGETED_DISCUSSION with 274 events and a byte-identical export.

Endpoint:
https://mdt-observatory-vnet.delightfulfield-8de6d3f0.westeurope.azurecontainerapps.io

Previous timeout release: fix acronym-led exception leakage, keep operational errors out
of the next clinical question, and add one bounded timeout/connection retry with
a 90-second read-inactivity limit. Preserve existing role deadlines, shared
pacing, separate 429 cooldown/retry budget, failed-review gates, live labeling
and the current room. No case, quota, dependency or infrastructure changes.

Previous release: activity-first specialty, central and chair desks, prominent
role/state cues, gentle public-update animation, terse right-side case context,
and an authenticated case-selection/resume screen. The API accepts an explicit
configured case ID and rejects unknown IDs without replacing the current room.
Preserve full dossier access, review failures, light/dark themes, execution-mode
selection and version-bound human controls. No case content, runtime, dependency
or infrastructure changes are required.

The completed intermediate image `677be0a5ceb20fd7914c643e9d8f2f7284afc9a59ea9faebad6a9402fe50f54c`
predates this scope and must not be deployed. Build a fresh validated image.

### Prior intermediate specialty identity validation (superseded scope)

- Frontend: 73 tests and production TypeScript/Vite build pass.
- Backend: Ruff, strict mypy and 157 non-browser tests pass; 92% coverage.
- Initial browser acceptance: both workflow and specialty checks pass. All seven
  role canvases and identity treatments differ in computed styling, with clinical
  content starting above y=820 at 1440x900; role titles remain visible on mobile.
  Surgical assessment/clinical columns are reversed relative to the image-led
  workspaces; navigation resets scroll and preserves accessible role selection.
- Final full-suite run: 162 tests pass with all five browser tests enabled,
  including first-viewport geometry, seven distinct computed role surfaces,
  mobile identity, mode selection, clinical error visibility and full workflow.
  Ruff, mypy and the final 73-test frontend build pass.
- Azure account and subscription are correct. Bicep compilation, baseline ARM
  validation and what-if pass with no deletions. Static roles retain registry
  AcrPull, container-scoped Blob Data Contributor and model-account OpenAI User;
  private storage and one-replica limits are unchanged. Live AcrPull is confirmed.
- The presenter's current room is a live case in TARGETED_DISCUSSION, not a test
  fixture. Only release while it is idle, snapshot immediately before release,
  and verify byte-identical restoration before read-only UI checks.
- ACR build is approved. Exact-image ARM validation and what-if remain required
  before the drain-aware release.
- Release must preserve the current shared room; cloud visual acceptance will
  be read-only rather than starting or replacing the presenter's meeting.

## Checkpoints

1. Read the complete vision; define architecture and executable acceptance criteria.
2. Implement a Python/uv event-driven backend and curated synthetic scenarios.
3. Implement central, chair, specialist and wall workspaces with live updates.
4. Integrate Azure-hosted model tool calling and OpenTelemetry without silent fallbacks.
5. Run unit, integration, evaluation and browser tests; resolve failures.
6. Validate infrastructure, deploy to Azure, and verify health, demo and telemetry.
7. Document operation, limitations, evidence sources and the demo walkthrough.

## Initial architecture

Python 3.12+, uv locked dependencies, FastAPI, Pydantic structured contracts,
SQLite transactional state/event records, SSE snapshots and React/TypeScript/Vite.
Seven independent role runtimes with allowlisted tools, structured outputs and
Azure OpenAI tool calling; a deterministic rehearsal runtime is explicitly labeled.
The chair is an application state machine, not an omniscient clinical agent.
One synthetic lung oncology case demonstrates conflicting imaging interpretation,
population mismatch, unavailable protocol, human review and conditional consensus.

Recipe: standalone Bicep + Azure CLI staged remote build. `azure.yaml` remains
an optional service descriptor; releases use the drain-aware deployment script,
not `azd deploy`. The local Docker daemon is unavailable, so local `azd package`
is not the packaging path. ACR performs the actual container build.
One VNet-integrated Azure Container App replica with managed-identity Blob
persistence over a private endpoint (SQLite remains the local backend),
ACR remote image builds (local Docker engine is unavailable), managed identity,
existing Azure AI model resource, Log Analytics and Application Insights.
No EHR integration, real clinician impersonation or real-patient treatment guidance.
One shared demonstration room; presenter secret protects cloud data access and mutations.
Azure resources isolated in a new demo resource group. Model access is scoped
to the existing Foundry account, without changing its deployments.

## Azure context

Subscription: MCAPS-Hybrid-REQ-60585-2023-jowylick
(e3825c9a-4bce-43e1-899e-1610156c9383), enabled and authenticated.
Application region: westeurope (authenticated azd default, verified capacity).
Model account region: swedencentral. GlobalStandard inference does not guarantee
regional data residency.
Existing model account: nl-stu-jvw-ai-saoyr2, nl-stu-jvw-foundry-rg.
Verified deployment: nl-stu-jvw-gpt-6-astra, model gpt-6-astra,
GlobalStandard capacity 10. Live requests are serialized and paced for this quota.
Use dedicated demo resources only; do not modify unrelated existing resources.
The user explicitly authorized autonomous implementation and Azure deployment.
These are non-destructive implementation defaults under that authorization.

## Acceptance gates

- Seven roles receive case activation without refresh, with different contexts/tools.
- Positions cite only known evidence, with access, geography and scrutiny metadata.
- Imaging and evidence-applicability friction cannot be cleared by a timer alone.
- Human steering creates a revised position and invalidates previous concurrence.
- REVIEW/ESCALATE positions require explicit human concurrence; objections reopen.
- Case closure requires all roles, no blocking friction and version-bound concurrence.
- Decision export includes positions, evidence, dissent, guidance and event history.
- Memory use/ignore/forget is explicit and role/clinician scoped.
- Reconnect, restart, concurrent commands and model/tool errors are tested.
- Browser walkthrough includes central, radiology, evidence, memory and final decision.
- Live model mode invokes Azure, executes allowlisted tools, validates structured
  outputs and fails visibly without silently switching to rehearsal.
- Deployed health, complete meeting and Application Insights traces are verified.

## Validation evidence

The following entries are chronological checkpoints. Earlier failures and pending
checks are superseded by the later verified results; see docs/verification.md
for the final acceptance matrix.

- Local orchestration/API checkpoint: 16 tests passed, including stale plan
  rejection, objection reopening, failure recovery and persistent memory forgetting.
- Parent-owned backend files pass Ruff and strict mypy.
- Running local rehearsal completed through DECISION_CAPTURED with seven roles
  and 216 persisted events; export: artifacts/local-rehearsal-decision.json.
- Live Azure smoke exposed a specialist runtime import failure. This is a
  blocking integration defect under active repair; no rehearsal fallback occurred.
- Frontend browser and Azure deployment checks are not yet complete.
- Integrated Python suite: 65 passed, 1 opt-in browser test skipped, 91% coverage.
  Strict mypy passes across all nine application modules.
- Frontend production TypeScript/Vite build passes. Real browser renders the
  central/chair screens; repeat-case controls and test selector integration
  remain under validation. Browser gate is not claimed complete.
- Bicep compiles without warnings; deployment PowerShell syntax and nine mocked
  CLI safety scenarios pass. No resources have been provisioned yet.
- Existing model token acquisition and public-network prerequisites pass.
- Locked Python wheel mirror is anonymously reachable from the development
  host. Public PyPI re-locking hit pythonhosted TLS failures; ACR build must
  prove artifact retrieval before deployment is considered verified.

## 7. Validation proof

### Timeout recovery validation - 2026-09-17

- Audit diagnosis: oncology emitted APITimeoutError at 12:36:12 UTC and
  successfully published after an explicit retry at 12:49:54 UTC. The current
  room is healthy, not blocked by that historical error.
- `uv run --frozen ruff check .` and `uv run --frozen mypy`: pass.
- Full `MDT_BROWSER_TESTS=1 uv run --frozen pytest --tb=short`: 179 pass.
- Frontend: 83 tests and TypeScript/Vite production build pass.
- Real SDK over mocked HTTP verifies dispatched timeout values, single
  timeout/connection retry, exhaustion, both tool and position stages, no local
  tool replay, no rehearsal fallback, non-retryable service errors, shared
  pacing, separate finite 429 budgets, cancellation and client cleanup.
- Workflow invariant: failed review blocks synthesis, keeps the clinical
  question intact and retains the exact failure in audit/activity.
- Browser reproduces the reported legacy next_action value: visible timeout
  alert, no raw exception/fallback text, and no next-clinical-question block.
- Bicep compilation, ARM validation and what-if passed at 15:59 CEST against
  the deployed baseline, with no deletions. Static/live scoped identity roles
  remain correct; infrastructure and inherited policies are unchanged.
- Fresh immutable image and exact-image preflight are required before release.
  Preserve the current idle room and use read-only cloud acceptance.

### Timeout recovery release proof - 2026-09-17

- Built and deployed `acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:1be329961488d0196d3a9cccab52101dd412c01d8f83f979e4546bffd901d528`.
- Exact-image Bicep/ARM validation and what-if succeeded at 16:05 CEST with
  no deletions. Private Blob infrastructure checks passed.
- Revision `mdt-observatory-vnet--r20260917140552-8829a1` is healthy with one
  active replica and unchanged least-privilege managed-identity roles.
- Read-only cloud checks passed for seven roles, both themes, mobile and the
  exact legacy timeout presentation. No technical exception appears as a
  clinical question; the failure remains an explicit alert.
- Live room `4bc0d93e-9e37-471c-b139-3ccb09aeacc7` remained selected and
  byte-identical at 274 events. No clinical actions, model acceptance meetings,
  quota changes or policy changes were made.

### Live activity desks and case selection - 2026-09-17, 15:29 CEST

- `uv run --frozen ruff check .` and `uv run --frozen mypy`: pass.
- `MDT_BROWSER_TESTS=1 uv run --frozen pytest --tb=short`: 164 pass.
- `npm --prefix frontend test -- --run`: 76 pass.
- `npm --prefix frontend run build`: TypeScript and production build pass.
- Final source-panel spacing changes were followed by all 76 frontend tests,
  production build and all five browser tests, passing again.
- Browser assertions cover seven distinct role headers/canvases in both themes,
  activity beginning above y=530 at 1440x900, first-screen guidance and review
  controls, the right case rail, full source access, mobile overflow, reduced
  motion and 900 ms animation. Incoming newest-first updates preserve existing
  entry nodes, clinician drafts and scroll position.
- Case catalog authentication, explicit selected-ID fidelity, unknown-ID
  no-mutation, active-round replacement prevention, resume and the three
  execution-mode race regressions pass.
- Bicep compilation, subscription ARM validation and ResourceIdOnly what-if
  succeeded at 15:24 CEST against the deployed baseline image. No deletions;
  inherited policy assignments remain unchanged.
- Static and live role review confirm registry AcrPull, container-scoped Blob
  Data Contributor and model-account OpenAI User. Private networking, managed
  identity and one-active-replica deployment gates remain unchanged.
- Recipe: existing staged PowerShell plus standalone Bicep. Reuse the approved
  subscription, resource group and West Europe environment; no azd bootstrap.
- Build a fresh image, validate its exact digest, then preserve the idle current
  room across the drain-aware release. Cloud browser acceptance is read-only.

### Live activity release proof - 2026-09-17

- Fresh image: `acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:c6b57bcdccceb97172eb650c3744d04831a5bcde08b723e17b4736898d5425ef`.
- Exact-image Bicep/ARM validation and what-if succeeded at 15:36 CEST, without
  deletions. Existing private Blob infrastructure checks passed.
- Drain-aware release created `mdt-observatory-vnet--r20260917133707-028a7d`;
  TLS, readiness, protected API, frontend and one active replica verified.
- Read-only cloud browser acceptance passed for all seven roles, both themes,
  mobile, case selection/resume and complete-record/assessment drawers.
- Current live room `4bc0d93e-9e37-471c-b139-3ccb09aeacc7` remained selected and
  byte-identical: TARGETED_DISCUSSION, 274 events. No clinical commands or new
  model acceptance meetings were issued.
- Live roles remain registry AcrPull, container-scoped Blob Data Contributor
  and model-account OpenAI User. No quota or policy changes.

Infrastructure bootstrap and application build validation checks pass. Bootstrap
is complete. The corrected application is approved for `-Stage Build`; release
still requires validating the resulting immutable image reference and completing
the full local live-model meeting.

- Bicep compilation: `az bicep build --file infra/main.bicep --stdout` passed.
- ARM validation: `az deployment sub validate`, bootstrap=true, westeurope,
  explicitly nonsecret validation token, passed without changes.
- What-if: `az deployment sub what-if --result-format ResourceIdOnly` succeeded.
  Ten creates in the isolated demo group; no deletions or existing model changes.
  Two role assignment IDs cannot be computed until the new identity exists;
  these are documented what-if limitations, not unsupported resource types.
- Authentication: Azure CLI token acquisition succeeded.
- Capacity: Microsoft.App ManagedEnvironmentCount 0/50 in westeurope.
- Policies: assigned policies inspected; bootstrap ARM validation reported no
  policy denial. Existing model content-filter policy is not changed.
- Static roles: AcrPull (7f951dda-4ed3-4680-a7ca-43fe172d538d) scoped only to
  demo ACR; Cognitive Services OpenAI User
  (5e0bd9bd-7b93-4f28-af87-19fc36ad61bd) scoped only to the existing model account.
  Principal is the demo Container App's system-assigned managed identity.
- Live runtime: individual radiology and research Responses API calls succeeded.
  The full seven-role run exposed HTTP 429 capacity pressure; bounded
  queuing/backoff is being added before the live acceptance gate is retried.
- Browser: real backend case activation, wall/radiology, human steering,
  targeted follow-up and evidence dialog pass. Vote payload version and
  repeat-case controls are being corrected before the final browser gate.
- Dependency portability: all 84 Python package records and 1,179 artifact URLs
  normalized to public PyPI after every SHA256 was checked against version-specific
  PyPI metadata. `uv sync --frozen` and 18 workflow/API/telemetry tests pass.
  Frontend lock similarly uses public npm with integrity hashes preserved.
- Bootstrap preflight defect fixed: local `az extension show` must not receive
  `--subscription`. The corrected bootstrap execution is now in progress.
- Bootstrap completed successfully. Private placeholder confirmed: external
  ingress false, no application secrets or mounts, provisioning Succeeded.
- Live RBAC verified for principal d6c914a6-54b0-4115-959b-6c2ad2e5db36:
  AcrPull on demo ACR and Cognitive Services OpenAI User on the existing account.
- Final local software gates: 85 Python tests passed at 92% coverage;
  Ruff and strict mypy pass; 19 frontend unit tests pass. The real-backend
  Playwright test passes through decision capture, reload, repeat-case and mobile.
- Seven live specialist analyses passed with zero 429s using serialized,
  20-second paced requests (288.3 seconds; 24,363 tokens). Full meeting live smoke
  is now running against the local app, including steering/follow-up/sign-off.
- Application Insights SDK configuration and an actual local trace/log flush
  succeeded; Azure ingestion accepted every submitted item (HTTP 200).
- Final combined local gate: 86 Python tests pass (including real-browser demo)
  with 92% coverage, 24 frontend tests pass, strict mypy and Ruff pass, production
  frontend build passes. Mixed human/AUTO concurrence display is now consistent.
- Full live Azure meeting passed: 38ae90ff-61e4-426b-afec-73e97d81090f,
  DECISION_CAPTURED, seven roles, 229 events, 492.7 seconds. Human steering,
  targeted evidence follow-up and all required concurrence completed without
  fallback. Export: artifacts/local-azure-decision.json.
- Application Insights query confirmed the local validation dependency span
  and log under service name mdt-observatory.
- Actual ACR remote Docker build succeeded using public dependency artifacts.
  Immutable image:
  acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:1d8c569cd23f29d6fb5db7f41283ae17887c08f39411e2dfc37e9720c36e641c
- Release ARM validation and what-if succeeded with bootstrap=false and that
  exact image. Preview contains no deletions; scoped RBAC assignments were
  already verified live. Application release is now authorized through the
  drain-aware script; cloud functional and persistence verification follows.
- Actual release exposed a runtime infrastructure defect: Azure Files mount
  failed with CIFS error 13 before Python started. Storage public network access
  was Disabled without a private network path. This is being corrected in IaC;
  anonymous blob access remains prohibited and the share contains synthetic data.
- A second rollout issue was observed: Single revision mode reactivated the
  previous healthy bootstrap despite explicit drain. Bootstrap has no data mount,
  so no SQLite writer overlap occurred. Rollout control is being corrected to
  prevent that behavior for future application revisions.
- Cloud endpoint/browser acceptance failed on the unavailable revision. Neither
  cloud functionality nor cloud persistence is claimed verified yet.
- Governance root cause confirmed: inherited MCAPS modify policies disable
  public storage networking and REST Shared Key authentication. No waiver,
  exclusion tag or policy exemption is authorized or deployed.
- Revised architecture keeps those controls: customer VNet, Blob private
  endpoint/private DNS, managed identity and Storage Blob Data Contributor.
  A new VNet-integrated app/environment avoids destructive replacement.
- Blob persistence implements the existing contract with conditional ETag
  snapshots, scoped memory and explicit storage-failure pause/recovery.
  Its full rehearsal workflow and stale-write/restart/memory/error tests pass.
- The old failed application was switched to Multiple revision mode and both
  known revisions deactivated; active revision listing is empty. No storage
  network restrictions were changed.
- Private-Blob migration artifacts are ready: new app mdt-observatory-vnet,
  environment cae-mdt-observatory-vnet, customer VNet/subnets, Blob private
  endpoint and DNS, container-scoped data role, and no file mounts/storage keys.
  The unapproved exemption artifact and runbook path were removed.
- Updated application gate: 99 Python tests pass including full browser, Blob
  workflow, stale-write prevention and outage recovery; strict mypy/Ruff pass.
  The refreshed public lock has 85 packages and 1,181 verified artifact hashes.
- Private-network bootstrap ARM validation and what-if succeeded. Preview
  creates the new VNet-integrated app/environment, VNet, private endpoint/DNS and
  Blob container; legacy resources are ignored, not deleted. Existing storage
  remains private and Shared Key disabled. No policy exemption is present.
- Private bootstrap deployed successfully. Blob private endpoint is Approved;
  account public access remains Disabled, Shared Key false, anonymous access false.
  New principal e54f8696-7815-4132-87e3-13dfcccbf7e6 has verified container-scoped
  Blob Data Contributor, registry-scoped AcrPull and model-account OpenAI User.
- Final revised local gates: 100 Python tests including browser pass (91%
  coverage), 24 frontend tests, Ruff and strict mypy pass.
- Fresh public-dependency ACR image built successfully:
  acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:edfecf0f5912bc8010d270e334fc19736e98336ca45490153464a5a73d611bb6
- Private application release ARM validation and what-if succeeded with the
  exact image; preview reports zero deletions. Cloud release is authorized.
- Private application deployed and verified at:
  https://mdt-observatory-vnet.delightfulfield-8de6d3f0.westeurope.azurecontainerapps.io
  TLS, health, readiness, frontend, protected API, private Blob metadata, no
  mounts and one active replica pass the release verifier.
- Complete real-browser cloud walkthrough passed (52.96 seconds), including
  decision capture, source inspection, human steering, reload, repeat case and
  mobile. Separate real presenter-token browser login also passed.
- Deployed `mdt.persistence.save` and tool spans are queryable in Application
  Insights. The full managed-identity live-model cloud meeting is running.
- Verified inactive legacy app/environment and their two task-created scoped
  identity roles are being retired; the new app and Blob data are untouched.
- Full managed-identity cloud live-model meeting passed:
  4f675568-da0a-4d2e-ae31-ff18af310432, DECISION_CAPTURED, seven roles, 228 events.
  Human steering, targeted follow-up and version-bound concurrence completed
  without rehearsal fallback. Export: artifacts/cloud-azure-decision.json.
- Actual cloud revision restart verified at 2026-09-16T15:59:17Z. The original
  replica was completely absent and exactly one healthy replacement remained
  before comparing the latest meeting and complete decision export. State was
  byte-identical, SHA256:
  0D11FAB8E6305854E51DF929A2950B6679EC0BA838030EFCC75B5ACB60AC08AE.
  Proof: artifacts/cloud-restart-proof.json.
- Application Insights queries verified deployed model, role, tool and private
  persistence spans; real model deployment, Azure request IDs and token usage;
  mdt.events metrics; and the exact cloud meeting's CaseClosed log at
  2026-09-16T15:54:33Z.
- Local service remains ready at http://127.0.0.1:8000. The unused original app
  and both old identity role assignments are removed. Its unused environment
  is ScheduledForDelete; no current app, Blob data or policy control was removed.
- Legacy retirement completed: the old environment is confirmed absent from
  Azure's resource listing. The delete command returned before resource removal,
  so verification explicitly waited for actual absence. All application,
  documentation and cleanup acceptance work is complete.

## UI refinement: Tailwind, specialty workspaces and clinical activity

User-requested follow-up: migrate the interface to Tailwind, add a persistent
light/dark switch, make specialty layouts and color treatments clearly distinct,
and present review activity in language useful to medical professionals.
Technical model provenance remains in saved audit records and telemetry.

Live specialist concurrency is now configurable from 1-7, default 3. Shared
request spacing defaults to 20 seconds and remains subject to bounded provider
cooldowns. The deployment script and Bicep carry both settings explicitly.
The shared Foundry allocation was inspected, not modified: 10 RPM / 10,000 TPM;
regional capacity usage 10 of 1,000. Increasing its allocation is a separate
operator decision, not a prerequisite for the UI release.

Acceptance for this refinement requires frontend unit/build gates, backend
concurrency/pacing regressions, all seven role workspaces in both themes,
mobile/clinical-copy browser checks, a real concurrent-role meeting, and a
drain-aware cloud release with authenticated browser verification.

Validation checklist for the existing standalone-Bicep release:
- Bicep compilation and updated parameter/safety regression tests.
- Subscription template validation and what-if with the exact release image.
- Existing subscription authentication and unchanged storage-policy controls.
- Static role verification: container-scoped Blob Data Contributor,
  registry-scoped AcrPull and model-account-scoped OpenAI User remain unchanged.
- Frontend build/unit and backend/browser gates before release.

### UI refinement validation proof

- Tailwind 4.3.3 frontend production build and 55 unit tests pass.
- Ruff, strict mypy and all 116 Python tests pass, including both complete browser
  acceptance tests; coverage remains 91%.
- Browser acceptance covers all seven distinct workspaces in both themes,
  visible real-scenario field bindings, mobile navigation/overflow, persisted and
  system preferences, URL overrides, keyboard theme switching, clinical error
  language and absence of provider metadata even from hidden UI content.
- Full live three-role-concurrency meeting
  c7cf1307-b246-41d0-a858-bd2fcdc381d9 captured: seven roles, 226 events,
  484.1 seconds, zero rate-limit events. Three specialties executed tools before
  the first position was published.
- Bicep compilation, parameter/default/bounds tests and all existing infrastructure
  safety scripts pass. Subscription ARM validation with the current immutable
  baseline image and new 3/20 scheduling parameters returned Succeeded.
- ResourceIdOnly what-if reports no deletions. Three deferred scoped role
  assignments remain the known what-if limitation; static roles/scopes are
  unchanged. Subscription authentication and both existing demo rooms were checked.
- The next step is the non-disruptive ACR image build, followed by ARM validation
  and what-if using its exact digest before the drain-aware release.
- ACR remote build succeeded with the public dependency locks. Exact image:
  acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:4b3271795f4dee592c0c7fb1b06a1070cd0bb8faa2f159d8bddc630d66004204.
  ARM validation returned Succeeded and exact-image what-if contains no deletions.
- The updated local service is ready on port 8000 and restored its existing
  in-discussion meeting byte-for-byte. The cloud room is idle and its completed
  decision was exported before release for a post-release equality check.
- Tailwind image released successfully. TLS, readiness, authentication, private
  Blob controls and one active replica pass. Live role settings are 3/20 and
  all three existing least-privilege role assignments remain intact.
- The previous cloud decision and latest-meeting selection survived release
  byte-for-byte. Theme bootstrap is served correctly from /assets/theme.js.
- Both authenticated cloud browser tests pass (79.13 seconds), including the
  complete workflow and all seven specialty views in light/dark modes.
- Final managed-identity live cloud meeting
  4354f818-464c-4106-8951-42062e7f962c reached DECISION_CAPTURED: seven roles,
  228 events, 484.7 seconds, zero rate-limit events. Radiology, oncology and
  surgery executed tools before the first position was published.
- Read-only browser inspection during that real cloud run verified all seven
  workspaces show clinical activity without provider metadata or page errors.
  Application Insights contains the exact meeting's CaseClosed log at
  2026-09-16T19:43:32Z plus model, role, tool and persistence spans.
- Documentation is updated. Foundry allocation remains unchanged; the proposed
  higher-capacity configuration is documented as an operator tuning decision.
  All requested refinement work is complete.

## Full colorectal dossier release

The existing Bicep topology, private storage policies, role scopes and 3/20 runtime
scheduling remain unchanged. This is an application-only replacement using the
same drain-aware immutable-image release path. No shared Foundry quota changes.

Validation checklist (all gates complete):
- Source fidelity, complete packaged dossier and runtime/evidence/tool-loop tests.
- Workflow, export, restart and historical-case isolation invariants.
- Ruff, strict mypy, full Python suite and frontend unit/production build.
- Local browser acceptance for the full dossier, seven layouts and both themes.
- Real-model complete colorectal workflow with explicit review and concurrence.
- Bicep compilation, authentication, policy and static role verification.
- Subscription ARM validation and what-if using the exact ACR image digest.
- Post-release data preservation, readiness, private controls and one active replica.
- Authenticated cloud browser and managed-identity live colorectal verification.

### Colorectal validation proof

- Workflow/API integration: 23 tests passed after aligning the canonical
  `management_alternatives` field; Blob and observability integration also passed.
- Initial full CRC backend gate: Ruff and strict mypy across 11 modules passed;
  143 tests passed, two browser tests remained opt-in, coverage 92%. Evidence
  access metadata was subsequently refined and requires the final combined gate.
- `az bicep build --file infra/main.bicep --stdout` passed. Azure account is
  enabled in the expected subscription. `az deployment sub validate` with the
  current immutable baseline image and 3/20 parameters returned Succeeded;
  ResourceIdOnly what-if returned Succeeded with no deletions. The existing
  three deferred identity-role references remain the known what-if limitation.
- Static role scopes/definitions remain correct: registry AcrPull, container
  Blob Data Contributor and model-account OpenAI User. Live storage still has
  public networking Disabled, Shared Key false, anonymous access false and
  default firewall Deny; no policy exceptions were introduced.
- The existing idle cloud decision `4354f818-464c-4106-8951-42062e7f962c` was
  preserved in `artifacts/crc-cloud-before-release.json` before release.
- Final local gate: Ruff and strict mypy pass; 157 Python tests plus both browser
  acceptance tests pass (159 total). Coverage is 92%; 72 frontend unit tests and
  TypeScript/Vite production build pass. Original source SHA and wheel resource
  equality are covered; all 22 source sections and 9/3/8 derived counts persist.
- Live CRC meeting `fa34b63c-bf11-4512-a2d4-3663ec98d772` reached
  DECISION_CAPTURED with seven roles, 287 events and explicit steering/concurrence
  in 499.2 seconds. The full dossier, three alternatives and eight consultations
  survived capture. All seven workspaces were inspected during actual inference
  without page errors or provider metadata.
- Non-disruptive ACR build is now approved under azure-deploy. Validate and
  preview its exact digest before the drain-aware Release stage. Cloud acceptance
  and preservation checks remain mandatory after release.
- ACR build succeeded. Exact image
  `acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:588efd593a1790c6e5341ee7ae04314577a20215f89f880cd29b29df028cc694`
  passed subscription ARM validation (Succeeded) and exact-image what-if
  (Succeeded, no deletions). Existing managed-identity AcrPull was verified before
  build. Release is approved with unchanged concurrency 3 and pacing 20 seconds.
- Release succeeded as `mdt-observatory-vnet--r20260917115031-14c2f6`.
  Readiness, private Blob controls, one healthy replica and all three scoped
  identity roles pass. The preceding cloud decision remains byte-identical.
- Cloud browser acceptance exposed a mode-selection defect: after choosing
  rehearsal on the historical live meeting, the new case actually started in
  Azure mode. The observed timeout was a genuine live review, not a storage,
  model or infrastructure failure. The real run is being completed with explicit
  human gates; the UI synchronization fix and a selected-mode regression are
  required before final release acceptance. No timeout threshold was relaxed.
- Selector root cause fixed: active-meeting synchronization overwrote the next
  case's explicit mode. Initialization now occurs once and explicit selection
  wins over late snapshots, SSE updates and reconnects. All 159 existing tests
  (including both browser tests) pass, plus three browser regressions that were
  reproduced against the old build and assert outgoing mode payloads in both
  directions. The new regressions are discovered by root pytest and use the
  existing browser opt-in flag. Ruff, mypy and 72 frontend tests/build pass.
- Bicep compilation and ARM baseline validation were rerun successfully after the
  selector correction. Infrastructure, scoped roles and policies are unchanged.
  The corrected image is approved for non-disruptive ACR build; its exact digest
  must pass ARM validation/what-if before a second drain-aware release.
- Managed-identity CRC meeting `df3f94ff-e0cf-408e-aa5e-54b600f8b4a2` completed:
  seven roles, 289 events, 489.2 seconds. Its matching CaseClosed log was found
  in Application Insights at 2026-09-17T12:06:49.667607Z. Preserve that complete
  CRC export as well as the earlier lung decision during the final UI release.
- Final complete suite: 162 tests pass with all five browser tests enabled,
  92% coverage. Both local and cloud captured decisions match the entire packaged
  CASE exactly, not just selected counts or summary fields.
- Corrected image
  `acrmdtgy76frdpub6io.azurecr.io/mdt-observatory@sha256:0ba97fe380625977a2c6944635320036a97d80708b0d1e42d284896d815248b4`
  built successfully, passed exact-image ARM validation and what-if (Succeeded;
  no deletions), and is approved for the final drain-aware release.
- Final corrected release succeeded as
  `mdt-observatory-vnet--r20260917122210-92169a`: one healthy active replica,
  exact image `0ba97fe380625977a2c6944635320036a97d80708b0d1e42d284896d815248b4`,
  private Blob controls and all three least-privilege roles intact.
- Both previous lung and live CRC exports survived the final replica replacement
  byte-for-byte; the complete current case equals the packaged CASE. CRC export
  SHA256: `7f2105468bbcd1ec7a30c8b085bffe80b0d10a80bc2561e5e4610f7ea5bbaf91`.
- Both authenticated browser tests pass on the final image (104.36 seconds),
  including selected-mode preservation, full workflow, all dossier values, seven
  specialty layouts, both themes, mobile and clinical-only activity/errors.
- Final rehearsal `7f22b8d5-28c1-401a-acce-6460aa026b35` reached
  DECISION_CAPTURED with seven roles and 304 events. The final shared room now
  presents the colorectal dossier rather than the historical lung case.
  Exact whole-case fidelity was asserted before steering and again through
  captured export. No model-quota change was required or applied.
- Final documentation and task tracking complete. Demo URL:
  https://mdt-observatory-vnet.delightfulfield-8de6d3f0.westeurope.azurecontainerapps.io
