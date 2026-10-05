# Presenter walkthrough

## Room setup: Health Rewired Munich 2026

The demonstration simulates a real MDT meeting. Participants can be in the room
or remote; either works.

1. **Share the URL.** Open the site, unlock with the presenter key
   (**Open the chair's screen**) and put the **Join screen** on the big
   display. It shows the URL and a QR code. Participants need no key.
2. **Everyone picks a role.** Each clinician picks a specialty on their laptop or
   phone and sees "Waiting for the chair to open a case", plus a short explainer:
   each specialty has an AI assistant that reads the record, reasons in the open,
   disagrees and waits for a human.
3. **The chair (voorzitter) decides the case.** The demo team opens **Case
   selection**, picks the case the chair named and starts it. Every participant
   screen fills with the case briefing.
4. **Watch the reasoning.** The **meeting stage** strip above each workspace tells
   the audience which of five stages the meeting is in, which round is running
   and what that means. Each assistant's reasoning path shows what it considered,
   what it found and why it concluded. The radiology screen turns amber when the
   MDT is waiting for the radiologist.
5. **Consensus.** Participants concur or object for their own specialty. Only a
   human sign-off counts; the assistants never decide.
6. **Next case.** The demo team clears the room or starts the next case, and every
   screen repopulates.

Case selection, follow-up rounds, retry, cohort edits, letters, export and
clearing the room are presenter-only. Share the URL only with the audience: in
live AI mode every participant instruction uses the shared model quota.

## Running the walkthrough
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

Switching roles returns to a live desk: a case briefing at the top states the
patient, current situation, work already completed and question to resolve.
The agent review then narrates its public decision path as question considered,
information checked, finding, retained uncertainty, current conclusion and next
action. Role identity, attention state, newest-first activity and human controls
remain in the center. **View case record** opens the complete dossier.
**Full assessment** exposes the expanded public assessment;
**Read proposal, conditions and evidence** opens the full proposal before review.
Detailed specialty source workspaces and saved preferences expand on demand.
During concurrence, the review form leads; guidance remains expandable below it.

**When the human must intervene.** A question the agent cannot settle from the
record, such as the imaging question on the radiology workspace, shows **MDT
waiting for human input** in the attention state and a prominent **Human finding
required · MDT blocked** handoff. It names the specialist the meeting is waiting
for, the question and checks the next step hinges on, and the sequence that the
finding unlocks. **Enter the finding** moves focus to the highlighted response
box labelled **Enter what you reviewed and found**. The human specialist reports
the reviewed source and finding; **Use example reply** fills in a demonstration report. General approval
("go ahead") names nothing reviewed, so the question stays open and the panel
says why and remains visibly blocked. After a valid reply the workspace shows **Question answered** and the
next step: the chair runs the focused follow-up round, then proposes a plan.
Specialties whose question closes in that follow-up round show **Waiting for the
chair** instead of asking for input.

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
| 0:30 | Answer the radiology agent's question (**Use example reply** or: "I reviewed all nine liver sites, the vessel margins and the lung nodule…") | The agent asked; the human reports the review; reassessment and revised position with remaining conditions |
| 0:40 | Return to chair; request targeted follow-up | Only relevant roles investigate remaining questions |
| 0:50 | Open Research; point at **Research operations**, then inspect Research / Protocol and click a claim | Which Dutch, EU, international, US and preprint sources were searched, the queries, what was found and what the position cites; source, region, access, applicability and limitations |
| 1:00 | Compare three management options and the conditional proposal | Local treatment now, further systemic therapy, or deferred local treatment; no automatic surgery decision |
| 1:02 | Scroll to Similar cases; remove a criterion, then apply the pending molecular result | The matched cohort, denominators and warnings recalculate; what comparable boards recorded stays separate from what those patients experienced |
| 1:05 | Concur from the roles awaiting human review | Version-bound human sign-offs arrive centrally |
| 1:15 | Open the captured decision and export | Complete provenance, evidence and human contributions |
| 1:20 | Click **Open outcome &amp; letters** on the consensus banner | "Consensus reached", the numbered plan forward, retained conditions and who signed off (clinician versus demonstration policy) |
| 1:25 | Open the patient summary, then the letter to the accountable medical doctor | A gentle plain-language summary in the patient's language with a glossary; an English clinician-to-clinician letter with tables |
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
evidence was searched live, the unavailable protocol was read, or the system
is clinically validated. This is an interaction-model demonstrator.

**Public searches.** In rehearsal the Research screen shows **Recorded replay**:
real search responses captured on 2026-09-24, replayed without network access.
Say "these are real searches recorded earlier", not "it is searching now". In live
mode the badge reads **Live public search** and results depend on the sources
responding. Either way, found papers are leads that are *not appraised for this
patient*; a failed source is shown as unavailable, never hidden. Only clinical
concepts are sent to public sources, never names, dates or case identifiers.

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
Radiology's reply can be **Use example reply**: a reported review of all 11
original sites, the 7 mm IVa focus, the vessels and the remnant. Request the
targeted round and compare all six supplied
strategies before reviewing the conditional proposal.

For **PDAC-2026-003**, compare technically plausible resection with perioperative
reserve and cognition/independence goals. The source's CKD stage label and eGFR
are inconsistent; risk scores and model probabilities are supplied illustrations,
not independently calculated or validated predictions. No model chooses pressure
targets, medication withholding, treatment or ICU placement. Radiology's reply
can be **Use example reply**: a reported review of the SMV/portal interface,
with aortic stenosis and cardiac reserve still pending. The targeted round retains cardiac stability, local protocols,
alert ownership, patient discussion and postoperative monitoring as conditions.
The staged hypotension example is hypothetical, not an observed clinical event.
