# Evaluation strategy

This repository evaluates **software and interaction behavior**, not clinical
validity. Passing these gates does not qualify the system to diagnose or treat.

## Deterministic acceptance suite

Workflow tests exercise seven-role activation, cited positions, two initial
frictions, targeted reassessment, the human imaging gate, residual uncertainty,
versioned proposals, objections, all-role concurrence and immutable closure.
Failure tests cover unavailable agents, explicit retries, interrupted process
recovery, concurrent commands, stale votes, bounded subscriber queues and memory
forgetting across meetings.

API tests check input validation, same-origin commands, signed presenter cookies,
expiration/tamper, access boundaries, non-fallback model configuration and export.
Agent tests check role/tool separation, evidence validity and live runtime limits.

Case-fidelity tests compare the packaged colorectal dossier against the supplied
source, accounting only for documented presentation/provenance normalization.
All source fields, measurement pairs, units and dates must survive into meeting
snapshots and exports. Check all nine liver lesions, the three management
alternatives, eight consult contributions, treatment cycles/doses, molecular and
laboratory data. Trial summaries with unresolved citations cannot be promoted to
verified medical sources.

Workflow invariants retain the nine-site imaging review gate, evidence-setting
limits and all human approvals. A stable 5 mm nodule is not established benign,
detectable ctDNA is not an automatic surgical veto, and the source's preferred
sequence is not automatically authorized. Old-case snapshots must remain
unchanged and cannot be reassessed by a different case runtime.

## Browser gate

The browser walkthrough must use the real backend (not API mocks), navigate
central, radiology, research/protocol and wall workspaces, inspect provenance,
steer a specialist and reach a captured decision. Check desktop and mobile
overflow, uncaught JavaScript errors and reconnect behavior.

## Live model gate

`uv run --frozen python scripts\smoke.py --mode azure` runs the same scenario through
Azure-hosted specialist calls. It requires seven valid positions, the initial
friction pair, human imaging steering, targeted follow-up and final concurrence.
The export records model/tool provenance and human contributions.

Live output is variable. Failures are blocking, visible and must not be concealed
by a rehearsal fallback. Review changes to prompts, schemas, tools or model
deployment against the same semantic invariants before demonstrating them.

## Cloud gate

Run the smoke suite against the deployed HTTPS endpoint with presenter access.
For the real-browser gate, set `MDT_BROWSER_TESTS=1`, `MDT_BROWSER_URL` to that
endpoint and `MDT_PRESENTER_TOKEN`, then run `tests/test_browser.py`. This uses
the deployed backend and changes the shared demo room; run outside presentations.
Verify database recovery after a replica restart, health/readiness probes,
image revision identity and Application Insights workflow spans/counters.
Keep exports and screenshots in ignored `artifacts/`; summarize observed results
in the deployment plan without secrets.
