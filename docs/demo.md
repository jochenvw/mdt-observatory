# Presenter walkthrough

Use **Scripted demonstration** (`rehearsal`) for a predictable 60-90 second presentation.
**Live AI review** (`azure`) demonstrates
real model tool calling, but latency and quota can exceed the scripted timing.
The mode badge remains visible throughout.

Choose light or dark with the theme control; the choice survives reload.
The screens look like a module in a (fictional) hospital system: the header names
the MDT room and which workstation each screen represents, and the patient banner
keeps the patient, diagnosis, stage and spoken language (German, Italian or English)
visible on every screen, so the audience always knows whose case is on the table.
Switch between specialties to show genuinely different working surfaces: radiology
comparison, oncology toxicity/options, surgical readiness, pathology findings,
research applicability, protocol conditions and patient priorities. Activity
describes clinical review tasks, not model calls or infrastructure operations.

Each specialty is recognizable from its first screen:

| Role | Visual identity |
|---|---|
| Radiology | High-contrast reading-room header, scan-blue navigation and image-led comparison |
| Oncology | Rose-tinted treatment board with full-width response and toxicity content |
| Surgery | Green planning canvas, anatomical clearance maps and procedural-sequence review |
| Pathology | Ruled, monospace report header with specimen-specific field grids |
| Research | Editorial evidence desk with a three-column study comparison |
| Protocol | Amber pathway canvas and numbered review stages |
| Patient perspective | Centered, spacious goals-focused layout with a circular heart emblem |

Start from **Case selection**, choose the available dossier and execution mode,
then **Start case**. **Resume meeting** returns to the current room without
replacing it. Three independently configured dossiers are available:

| Case | Discussion focus |
|---|---|
| CRC-2026-001 | Original BRAF-mutant case; nine liver sites after four cycles of targeted induction |
| CRC-2026-002 | RAS/BRAF-wild-type sigmoid cancer; eleven baseline liver sites, disappearing lesions, detectable ctDNA and neuropathy after eight cycles |
| PDAC-2026-003 | Pancreatic surgery; anatomical operability versus cardiac, renal, frailty and patient-priority constraints |

`case_2.md` supplied the latter two separate patient narratives. Each selection
uses its own full record, specialist contexts, evidence and review conditions.
Starting another case replaces the active room, not historical saved records.
The walkthrough below describes the original case.

Switching roles returns to a live desk: role identity and attention state above,
newest-first review activity and human controls in the center, and a terse case
snapshot on the right. **View case record** opens the complete dossier.
**Read full assessment and uncertainties** exposes the public assessment;
**Read proposal, conditions and evidence** opens the full proposal before review.
Detailed specialty source workspaces and saved preferences expand on demand.
During concurrence, the review form leads; guidance remains expandable below it.

Public updates ease in over 900 ms, unless reduced motion is selected. This does
not slow the actual meeting or delay errors and requests for human input.
Attention labels distinguish running, finished, updated and input-needed states.
Agent support is never presented as human sign-off. Role colors indicate
specialty identity, not approval.

If a live review takes too long, **Review taking longer** announces one bounded
retry. A persistent failure remains visible and requires retry or chair
intervention; it is not a clinical conclusion and never switches to rehearsal.
Operational errors do not appear as the next clinical question.

| Time | Presenter action | What the audience sees |
|---|---|---|
| 0:00 | Choose the dossier and mode in Case selection; Start case | Patient context activates across seven workspaces |
| 0:05 | Stay on central or switch to wall | Separate specialist activities, tools and positions |
| 0:15 | Inspect the friction cards | Complete liver-site clearance versus biological disease control |
| 0:20 | Open Radiology, then expand the clinical workspace | Live assessment first; all nine liver sites, measurements, vessel relationships and indeterminate 5 mm lung nodule remain inspectable |
| 0:25 | Inspect the memory nudge; explicitly use or ignore it | A preference is visible, not silently applied |
| 0:30 | Steer: "Review all nine liver sites, vessel margins and the indeterminate lung nodule before clearance planning." | Human guidance, reassessment, revised position with remaining conditions |
| 0:40 | Return to chair; request targeted follow-up | Only relevant roles investigate remaining questions |
| 0:50 | Inspect Research / Protocol and click a claim | Source, region, access, applicability and limitations |
| 1:00 | Compare three management options and the conditional proposal | Local treatment now, further systemic therapy, or deferred local treatment; no automatic surgery decision |
| 1:02 | Scroll to Similar cases; remove a criterion, then apply the pending molecular result | The matched cohort, denominators and warnings recalculate; what comparable boards recorded stays separate from what those patients experienced |
| 1:05 | Concur from the roles awaiting human review | Version-bound human sign-offs arrive centrally |
| 1:15 | Open the captured decision and export | Complete provenance, evidence and human contributions |
| 1:20 | Click **Open outcome &amp; letters** on the consensus banner | "Consensus reached", the numbered plan forward, retained conditions and who signed off (clinician versus demonstration policy) |
| 1:25 | Open the patient summary, then the colleague letter | A gentle plain-language summary in the patient's language with a glossary; an English clinician-to-clinician letter with tables |
| 1:30 | Enter a reviewer name; Approve, or Request changes with a comment | Named, version-bound approval; a change request redrafts the document and revokes earlier approval |

Alternate ending: object to a proposal with a substantive concern. The chair
reopens discussion. Request targeted follow-up, inspect the updated proposal,
and give fresh human concurrence. Previous votes do not silently transfer.

## Closing: outcome and letters

When the decision is captured, both outcome documents start drafting on their
own; the banner on the central and chair screens shows their status. Drafting
takes about 30–90 seconds per document and always uses the configured language
model, including in the scripted demonstration. Nothing is scripted: if the
model is unavailable, the document card says so, and **Regenerate draft** tries
again. Starting another case waits until drafting finishes.

- **Patient summary.** Written in the patient's recorded preferred language:
  English for CRC-2026-001, German for CRC-2026-002 and Italian for
  PDAC-2026-003. It explains gently, defines terms in a glossary and lists
  questions to ask.
- **Colleague letter.** British English with standard terminology: diagnosis,
  treatment to date, discussion, outcome, conditions, actions and owners, and
  what the patient has been told.
- **Automatic checks.** Readability (per-language formula), length, sentence
  length and grounding against the record are advisory. They never approve a
  document; only a named clinician does, and approval binds to the plan version
  and revision.

Point out that the documents cite only the recorded meeting and never add a date,
dose or recommendation the MDT did not record.

## Language to use

"Seven agents work through seven professional lenses. The chair coordinates
unresolved questions. Humans intervene where judgment changes the outcome."

Do not claim that illustrative confidence is medical probability, the curated
searches are live research, the unavailable protocol was read, or the system
is clinically validated. This is an interaction-model demonstrator.

For Similar cases, say what the cohort is: "Among the comparable historical cases
in this synthetic cohort, this many boards recorded additional diagnostics first."
Do not say that an approach worked better, was preferred or is recommended, and
do not connect a recorded decision to a recorded outcome as cause and effect.
Quote a finding into the discussion only with its denominator and cohort
definition; the board still decides.

## Case fidelity checkpoints

Open the complete case record to inspect presentation, medications, laboratory
results, pathology, molecular variants, pharmacogenomics, imaging acquisition,
all treatment doses and cycles, response assessments and alternative diagnoses.
Use the timeline and CEA/ctDNA trends rather than presenting only a current snapshot.

Keep these uncertainties visible: nine original sites must remain targetable;
the baseline 23% future liver remnant is not the same as the predicted >65%
parenchymal-sparing remnant; PET cannot reliably characterize the stable 5 mm
lung nodule; persistent ctDNA does not automatically prohibit surgery; systemic
trial efficacy does not prove benefit of the proposed conversion sequence.
Hepatobiliary, colorectal, interventional-radiology and radiation-oncology
contributions appear within the surgical review, not as invented extra sign-offs.

The source's liver-first preference is a conditional discussion position.
Present the counterarguments and patient goals (long-term control, independence,
avoiding permanent stoma) before requesting human concurrence.

## Additional case walkthroughs

For **CRC-2026-002**, inspect the response timeline and caregiver priorities.
Eleven baseline sites are reported, but the source's conceptual illustration is
not a complete measured lesion map. Six clear residual lesions, three disappeared
sites and two scars must not be conflated with the additional uncertain 7 mm
focus. Persistent ctDNA is not a surgical veto; grade 2 neuropathy affects the
trade-off between more systemic treatment and conditional local therapy.
Radiology guidance can be: "Review liver mapping, vascular margins and all
baseline sites." Request the targeted round and compare all six supplied
strategies before reviewing the conditional proposal.

For **PDAC-2026-003**, compare technically plausible resection with perioperative
reserve and cognition/independence goals. The source's CKD stage label and eGFR
are inconsistent; risk scores and model probabilities are supplied illustrations,
not independently calculated or validated predictions. No model chooses pressure
targets, medication withholding, treatment or ICU placement. Radiology guidance
can be: "Review pancreatic imaging, vascular anatomy and the limitations of
cardiac imaging." The targeted round retains cardiac stability, local protocols,
alert ownership, patient discussion and postoperative monitoring as conditions.
The staged hypotension example is hypothetical, not an observed clinical event.
