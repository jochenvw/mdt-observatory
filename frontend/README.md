# MDT / Observatory frontend

React 19, TypeScript and Vite. All workflow data comes from the shared FastAPI
meeting contract. There are no frontend-generated cases, positions, tool results,
concurrences or timed state transitions.

```powershell
cd C:\_CODE\mbt_vision\frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:8000`. `npm run build` type-checks and
creates `frontend\dist` for the parent FastAPI static host. `npm test` runs the
contract-adjacent helper tests. Production must serve `/api` before the SPA
fallback, and proxy SSE without response buffering.

With Python Playwright and Chromium available, `python tests\browser_smoke.py`
checks the built app against isolated API fixtures, without starting a server.
It covers all seven workspaces at 375px and desktop widths, live draft retention,
mutation errors, memory, evidence, targeted follow-up, concurrence and export.
Screenshots are written to the ignored `tests\artifacts` directory.

## Presenter flow

1. Select **Deterministic rehearsal**, then **Start case**. The central screen
   shows the case, seven live specialists, the state machine and emerging friction.
2. Open **Radiology**. Compare the explicitly synthetic SVG illustration and
   inspect the actual backend-provided measurements below it. Use/ignore a memory,
   send suggested growth-kinetics guidance, and observe the reassessment.
3. Return to **Central MDT** or **Chair** and request a targeted follow-up once
   agent work has finished. Open a claim to inspect source access and limitations.
4. Review the proposed plan and concur as the relevant human specialists.
   Comments are optional for concurrence, required for objections. Objections
   return control to backend orchestration. Export the full captured meeting.

Aim for 60–90 seconds in rehearsal; actual progress depends on backend execution
and explicit presenter actions. The in-app presenter guide documents the sequence.
**Live Azure model + curated tools** accurately labels Azure mode; neither mode
claims live web retrieval or calibrated clinical confidence.

### Full workspace walkthrough

The short demonstration emphasizes Radiology and Chair. For a complete tour,
use the same case and open each workspace; do not start a separate patient per role.

| Workspace | What to demonstrate |
| --- | --- |
| Central MDT | Case question, specialist publication, exact phase, and the friction that replaces a generic discussion. |
| Chair | Delegation monitor, failed-agent retry, and one targeted round rather than rerunning every role. |
| Radiology | Synthetic illustration versus actual 14/17/23 mm case measurements, comparison caveats, growth-kinetics steering, and visible memory use/ignore/inspect/forget. |
| Oncology | Prior melanoma treatment and severe toxicity versus the untreated lung lesion; inspect tolerability and the conditional systemic-treatment position. |
| Surgery | Anatomical feasibility, fitness, tissue confirmation and MDT recommendation as distinct review gates—not automatically completed checks. |
| Pathology | Specimen/histology/molecular context and what remains unconfirmed about the new finding. |
| Research | Europe-first sources, patient match, exact supporting passage, study limitations and abstract/full-text access. |
| Protocol | Dutch/European guidance, regulatory context and precise protocol availability; do not equate an unavailable institutional pathway with a missing public trial protocol. |
| Patient perspective | Stated priorities, actual support needs, and why no demographic preference is inferred. |
| Wall | All seven independent positions, current assessments, uncertainties and latest activities side by side. |

Return to Central MDT for the conditional plan. Select each human role, concur
against the displayed plan version, or object with a reason. A revised plan
requires fresh version-specific review. Export the final record before starting
another demonstration.

**Replay an existing meeting:** the persistent toolbar always exposes **Start new
case** and **Mode for next case** when a meeting is loaded, including after a browser
refresh of a closed meeting. Both are disabled while work is busy. Starting another
meeting calls `POST /api/meetings`; it does not delete the previous meeting's audit.
The next-case mode initializes once from the loaded meeting when no choice has
been made. An explicit selection, including one made while the initial meeting
is loading, survives later snapshots, SSE updates and reconnects. The current
meeting's mode badge is separate; starting a case submits the selected mode.

After a production build, run the isolated mode-race browser regressions from
the repository root with:

```powershell
$env:MDT_BROWSER_TESTS = "1"
uv run --frozen pytest tests\test_browser_mode_selection.py -q
```

The root pytest gate discovers these tests; without `MDT_BROWSER_TESTS=1`,
they are skipped like the other opt-in browser acceptance tests.
They exercise delayed snapshots, reconnects and the actual outgoing start payload
without contacting the application backend or an AI service.

### Stable browser selectors

Use Playwright `get_by_test_id(...)` / `getByTestId(...)`. Accessible names remain
available alongside these IDs.

| Test ID | Surface |
| --- | --- |
| `start-case` | Initial activation, or persistent toolbar **Start new case** when any meeting is loaded. |
| `mode-select` | Execution mode initially; next-case mode when a meeting is loaded. Disabled while busy. |
| `view-central`, `view-chair`, `view-wall` | Main navigation. |
| `view-radiology`, `view-oncology`, `view-surgery`, `view-pathology`, `view-research`, `view-protocol`, `view-patient` | Specialist navigation. |
| `guidance-input`, `send-guidance` | Current specialist's steering form. |
| `followup` | Targeted follow-up button in the friction panel, shown when questions are open. |
| `phase` | State-machine section; inspect `data-phase` for the exact enum, e.g. `CONCURRENCE`. |
| `review-role` | Central/chair/wall human-role selector. |
| `concur-{role}`, `object-{role}` | Vote buttons for the currently selected human role, using exact contract role strings. Select `review-role` first when iterating all seven. A successful concurrence removes that role's concurrence button and shows a recorded-status label. |
| `open-evidence` | Central evidence-library button. |
| `source-drawer` | Open evidence dialog, accessible name “Follow the evidence”. |

At mobile widths, open the button named **Toggle workspace navigation** before
using navigation selectors. Published positions visibly include **Position published**.

## Integration behavior

- Named SSE `state` events contain the full `Meeting`. EventSource reconnects to
  the same stream; snapshots with older event IDs cannot overwrite newer state.
- Accepted meeting mutations trigger a GET snapshot refresh in addition to SSE.
  If refresh fails, the accepted response is retained and the failure is surfaced.
- Both concurrence and objection payloads include the displayed `plan_version`.
  Human support for an older version is never shown as approval of a newer plan.
- Concurrence progress distinguishes human approval from current-version agent
  approval authorized by `AUTO` demo policy. `REVIEW`/`ESCALATE` agent support does
  not count as policy concurrence or human sign-off.
- Guidance and review drafts are independent of meeting snapshots. SSE updates
  do not replace the application or steal focus.
- 401 responses open presenter authentication via `POST /api/auth`. Secrets are
  not persisted; the server controls the HTTP-only cookie.
- All mutation errors are visible alerts. Buttons prevent concurrent presenter
  mutations and respect backend `busy`/closed state.
- Arbitrary case and role-context objects are rendered recursively with labels.
  Role-specific layouts do not assume one fixed patient schema.
- Radiology recognizes `context.measurements` (or `context.imaging`) records with `label`, `diameter_mm` and
  `weeks_ago`, rendering their actual chronological measurements alongside the
  illustrative SVG. Missing measurements are never filled in from the artwork.
- Evidence links require credential-free HTTPS and open with
  `rel="noopener noreferrer"`. All display content is React-escaped.
- The pre-app Clawpilot theme script honors `?scoutTheme=light|dark`, otherwise
  the system preference. The toolbar can toggle theme. Color tokens are exclusively
  Clawpilot variables; Segoe UI and reduced-motion support are included.
