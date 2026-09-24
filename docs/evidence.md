# MDT case evidence and specialist runtime

**Fictional demonstration — not for clinical use.** The supplied `case.md` explicitly
describes invented identifiers, dates, laboratories, images and genomic findings.
Academic profiles and personal framing attribution have been removed from repository
source documents at the user's request; clinical content is retained and source
hashes have been updated. `CASE-MDT-CRC-BRAF-2026-001` remains available;
previous saved decisions and exports are not rewritten.

## Full-fidelity case package

`src\mdt\dossiers\crc_case.json` contains all 22 sections of the source YAML and the full
MDT-relevant narrative, including three management alternatives, eight specialty
contributions, the preferred conditional strategy, decision pathway and clinician brief.
`CASE["dossier"]` exposes the entire nested structure, not a shortened summary.
`CASE["management_alternatives"]` exposes the three source alternatives with `name`, `sequence`,
`advantages`, `disadvantages` and `evidence` fields; none marks an actor-selected treatment.
This is the single option key in both the API and packaged JSON; no `management_options`
alias or duplicate list is added.
`importlib.resources` loads the JSON from the installed package without a runtime YAML
dependency. Conversion used the existing PyYAML parser; source-fidelity tests parse the
original YAML and compare every nested value.

Documented normalization is limited to the original demonstration-label adjective
becoming “case,” the original identifier prefix becoming `CASE-`, and the source
demonstration boolean becoming `demo`. The exact source SHA-256 is recorded in the
package. Narrative citation tokens become explicit **source-supplied, unverified
reference** labels; those tokens are not usable publication citations.

Academic profiles are excluded from the clinical package and removed from the
source documents. No real clinician identity endorses the source's preferences
or generated positions.

## Additional case packages

`case_2.md` contains two separate patient narratives, packaged as
`crc_wt_case.json` and `pancreatic_case.json`. Each retains its own structured
record, clinical narrative, source tables, alternatives, consultation perspectives
and source SHA-256. Seven case-bound contexts and runtime definitions drive both
rehearsal and live review; they are not aliases of the original colorectal case.

The wild-type colorectal case retains eleven reported baseline sites and the
incomplete, conceptual five-row lesion illustration without inventing remaining
measurements. Disappeared deposits are not declared eradicated. The additional
7 mm focus remains indeterminate. The pancreatic case retains the source's renal
staging discrepancy, supplied/unvalidated risk scores, hypothetical physiology
reveal and unknown postoperative outcomes. Neither risk predictions nor
source-preferred strategies authorise treatment, ICU placement or medication
withholding. Additional perioperative consultations are consolidated into the
existing seven scopes, not fabricated independent approvals.

The additional evidence resource contains the following independently inspected
**public abstracts**, reviewed on 2026-09-17. Full article/protocol access is not
claimed. URLs, identifiers, population, results and limitations remain inspectable.
Original-case evidence objects are unchanged; the shared CAIRO5 publication has
a separate case-specific projection for the left-sided wild-type comparison.

| Evidence | Source and interpretation limit |
|---|---|
| `CRC-CAIRO5` | [2023 original abstract](https://pubmed.ncbi.nlm.nih.gov/37329889/): left-sided RAS/BRAF-wild-type bevacizumab/panitumumab arms; no optimal surgical timing established |
| `CRC-CAIRO3` | [2015 maintenance trial](https://pubmed.ncbi.nlm.nih.gov/25862517/): maintenance/reintroduction after CAPOX-bevacizumab disease control, not conversion-surgery selection |
| `CRC-PLCRC` | [2016 cohort infrastructure](https://pubmed.ncbi.nlm.nih.gov/27560599/): longitudinal clinical, patient-reported and biomaterial research; not treatment-benefit evidence or verified current enrollment |
| `PERIOP-PRETREAT` | [2025 randomized trial](https://pubmed.ncbi.nlm.nih.gov/41076587/): stopped for futility; risk-stratified pressure management did not establish improved six-month disability or secondary clinical outcomes |
| `PERIOP-PONV-RISK` | [2014 cluster-randomized trial](https://pubmed.ncbi.nlm.nih.gov/24105403/): risk display changed prescribing but did not establish improved nausea/vomiting outcomes |
| `PERIOP-PONV-ACTION` | [2015 prospective before-after study](https://pubmed.ncbi.nlm.nih.gov/25274048/): actionable support was associated with improved outcomes; not a randomized head-to-head comparison with risk display |

The added colorectal case also uses the separately reviewed CAIRO5 long-term and
PROVENC3 records below, retaining their setting limitations. It does not receive
BRAF-targeted BREAKWATER or Dutch BRAF-specific treatment advice. The pancreatic
case receives no colorectal study records. Source narrative assertions remain
source-supplied even when a related publication has been independently reviewed.

## Original BRAF case fidelity

All nine baseline MRI sites are mapped to response measurements: S8, S4a, S7, S6,
S5, S3, S2, S1 and S4b. Baseline CT counted eight while MRI counted nine; both are
retained. The proposed source procedure explicitly assigns S8/S4a/S7 resections
and selected S6/S3/S1 ablations, but does not assign a treatment to S5/S2/S4b.
Mapping these sites is **not** inventing a safe treatment or declaring clearance.
The baseline major-resection FLR of 23% and predicted >65% remnant with a feasible
parenchymal-sparing approach are different strategies, not interchangeable measurements.

Source ambiguity is preserved: `tumor_markers.after_cycle_4.date` is 2026-09-01,
while `response_assessment.biomarkers.date` is 2026-09-09 for the same reported
CEA/CA19-9 values. No missing dates, doses, treatment allocations or consistency
corrections are invented.

## Evidence access and limits

Curated role tools are local and labelled `CURATED`, never simulated
network searches. Source inspection and deterministic calculations are real. Independent
research review on **2026-09-17** retrieved the sources below; curated tools do not repeat
that retrieval or claim a live search. Case links use `case://` as local identifiers.
The legacy evidence boolean is retained in the schema for saved-export compatibility;
clinical panels should identify records by `CASE_RECORD` and show the demo banner.

| Evidence ID | Access | Supported interpretation |
| --- | --- | --- |
| `CASE-CRC-{ROLE}` | `PUBLIC_FULL_TEXT` case record | Supplied fictional observations within that specialty. Not external medical evidence. |
| `CRC-BREAKWATER` | [`PUBLIC_FULL_TEXT`](https://pmc.ncbi.nlm.nih.gov/articles/PMC12197837/) | Previously untreated BRAF V600E metastatic systemic PFS/OS benefit; Pfizer funded. Not liver-only, a conversion-metastasectomy randomization or perioperative-duration study. DOI `10.1056/NEJMoa2501912`; online 2025-05-30. |
| `CRC-CAIRO5` | [`PUBLIC_ABSTRACT_ONLY`](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:37329889%20AND%20SRC:MED&format=json&resultType=core) | Original 2023 induction report, abstract verified via Europe PMC. Initially unresectable liver-only disease; right-sided/RAS/BRAF stratification does not establish a BRAF-only effect. Different induction from this case. DOI `10.1016/S1470-2045(23)00219-X`. |
| `CRC-CAIRO5-LONGTERM` | [`PUBLIC_FULL_TEXT`](https://pmc.ncbi.nlm.nih.gov/articles/PMC11583021/) | Separate long-term report: no demonstrated OS advantage for triplet versus doublet induction, with an underpowered survival comparison. Not a randomized surgery-versus-no-surgery inference. DOI `10.1001/jamaoncol.2024.5174`; online 2024-11-21, January 2025 issue. |
| `CRC-PROVENC3` | [`PUBLIC_FULL_TEXT`](https://pmc.ncbi.nlm.nih.gov/articles/PMC12785881/) | Postoperative ctDNA prognosis in 209 resected stage III patients receiving adjuvant chemotherapy; not a stage IV surgical veto. DOI `10.1093/bjs/znaf281`. PMC date 2026-01-09 and PubMed date 2025-12-24 are both retained. |
| `CRC-NVMO-BOM` | [`PUBLIC_FULL_TEXT`](https://medischeoncologie.nl/artikelen/2026/juli/2026-6/encorafenib-cetuximab-en-chemotherapie-bij-gemetastaseerd-braf-v600e-gemuteerd-colorectaalcarcinoom) | Positive Dutch PASKWIL 2023 palliative systemic-treatment advice, not a conversion pathway or local approval. July 2026 advice; e-publication 2026-07-11, print 2026-08-12. |

The case narrative preserves author-supplied numerical study summaries and unverified
reference labels for fidelity; the separate evidence objects carry independently reviewed
sources and access metadata. This does not retroactively verify every sentence in the
source narrative. No hazard ratio, efficacy estimate, DOI, publication URL, regulatory
approval or guideline recommendation is fabricated. Evidence dates are the **2026-09-17
independent review/access date**; case-record dates remain the simulation date.
Missing quantitative scrutiny is explicitly marked not extracted, not filled in from
assumptions. Access to an article does not claim every full protocol, supplement or
amendment was reviewed. Dutch BOM guidance is distinguished from international studies,
regulatory authorization, reimbursement and local approval.
The [official NVMO listing](https://www.nvmo.org/bom/encorafenib-cetuximab-en-chemotherapie-bij-gemetastaseerd-braf-v600e-gemuteerd-colorectaalcarcinoom/)
is recorded separately from the full advice page. Nonuniform post-progression
BRAF-directed therapy in the control arm remains an explicit interpretation caveat.

`PROTOCOL_NOT_PUBLIC` describes the unavailable local perioperative pathway. Trial
publication, full protocol/amendments, regulatory indication, reimbursement and local
approval remain distinct. Protocol access is a retained condition on a proposed review,
not permission to start treatment.

## Public literature and trial search

On top of the curated set, the **research role only** can search six public sources
(`src/mdt/literature.py`). Other roles are never offered these tools.

| Tier | Source | Host | Tool |
| --- | --- | --- | --- |
| NL | Richtlijnendatabase | `richtlijnendatabase.nl` | `search_dutch_guidelines` |
| EU | EU Clinical Trials register (CTIS) | `euclinicaltrials.eu` | `search_clinical_trials` |
| INTL | Europe PMC | `www.ebi.ac.uk` | `search_europepmc`, `fetch_abstract` |
| INTL | PubMed (NCBI E-utilities) | `eutils.ncbi.nlm.nih.gov` | `search_pubmed` |
| US | ClinicalTrials.gov | `clinicaltrials.gov` | `search_clinical_trials` |
| PREPRINT | Preprints via Europe PMC | `www.ebi.ac.uk` | `search_preprints` |

- **Retrieval labels.** `LIVE` (Azure mode, searched during the meeting) or `RECORDED`
  (rehearsal: real responses captured by `scripts/record_searches.py` on 2026-09-24 and
  replayed from `src/mdt/dossiers/recorded_searches.json`; the network is never used).
  IDs are prefixed `LIVE-`/`REC-`. Curated records keep `CURATED` and serialise unchanged.
- **Honesty.** Searched records carry `patient_match: NOT_ASSESSED`, all scrutiny fields
  "not extracted", and limitations naming the retrieval, US context or preprint status.
  Registry and guideline hits are `METADATA_ONLY`; abstracts are `PUBLIC_ABSTRACT_ONLY`.
  Duplicates of curated records (by PMID, PMCID, DOI, NCT or EU CT number) are not added.
  Finding papers never settles the patient-applicability friction.
- **Privacy.** Queries are clinical concepts only; any query containing case identifiers,
  dates, ages, record numbers or e-mail addresses is refused before a request is sent.
  Only HTTPS requests to the five allowlisted hosts are possible; responses are capped
  at 2 MB with one retry on 429/5xx.
- **Budget.** At most six searches per analysis (further calls are refused, not fatal).
  Search rounds earn at most two extra model steps and a bounded token allowance; the
  curated-tool budget stays hard.
- **Grounding.** A position may cite only records returned in that analysis; citing an
  unreturned PMID, NCT or EU CT number fails validation.
- **Failures.** An unavailable source becomes a visible uncertainty in the position and
  on the Research screen; it never becomes a silent gap.
- **Research screen.** The *Research operations* panel shows every source (searched,
  unavailable or not searched), each query and its counts, and the papers, trials and
  guidelines found, grouped Dutch → European → international → US → preprints, with
  "Cited in position" markers and links to the public record.

## Original case: seven roles, eight specialty contributions

The existing seven runtime roles are unchanged. Surgery includes HPB and colorectal
perspectives plus interventional-radiology and radiation-oncology consultation.
These are not extra human votes. Patient perspective includes source supportive-care
contributions and documented goals, without inventing preference or consent.
Each role sees its own relevant detailed dossier sections and allowlisted evidence;
the complete dossier remains available to the application.

Core tool names remain `compare_imaging`, `reconcile_toxicity`, `assess_operability`,
`inspect_pathology`, `inspect_curated_study`, `check_curated_protocol` and
`inspect_stated_priorities`. Oncology, surgery, research and protocol additionally
have their own `assess_{role}_applicability` tool.

## Original case friction and human review

Radiology initially retains `imaging` / `ESCALATE`. The tool maps all nine sites and
computes a descriptive MRI longest-diameter sum of 223 → 124 mm (−44.4%).
This is **not a formal RECIST target set or segmented volumetry**; CT partial response
is reported by the source. Follow-up needs human review guidance about mapping,
clearance, vessels, liver, lung or chest. Generic thanks, publish instructions,
unrelated growth guidance, and instructions to ignore review do not clear the blocker.
Considering guidance moves the discussion to conditional review; it does not certify
clearance or claim a new scan was performed.

Oncology, surgery, research and protocol initially retain `applicability`. Each must
execute its own follow-up applicability tool before its blocking question clears.
This compares BREAKWATER, CAIRO5 and PROVENC3 with conditional limits, not newfound
trial eligibility. Runtime safety gates retain these uncertainties even if a live
model omits them:

- All nine baseline sites need expert clearance review, including unassigned S5/S2/S4b.
- S1 remains 3 mm from the IVC and S4a 2 mm from the MHV; margin, heat-sink, access
  and venous drainage concerns persist.
- >65% remnant is a prediction conditional on feasible parenchymal-sparing clearance.
- The stable 5 mm lung nodule is indeterminate and below reliable PET resolution;
  repeat thin-section CT/human review is not automatically a benign finding.
- BRAF ctDNA VAF remains detectable at 0.42%; stage III prognosis supplies no hard veto.
- Perioperative interruption/restart, oxaliplatin toxicity, colorectal sequencing and
  limited perioperative evidence after BRAF/EGFR induction need human review.

All three strategies remain options: local clearance review now, further systemic
therapy then reassessment, or systemic disease control with selective consolidation.
The source-preferred liver-first proposal is conditional and not an automatic choice.
Pathology's rehearsal `AUTO` only publishes supplied tissue facts; it is not treatment
approval. Confidence numbers are demonstration scores, not calibrated probabilities.

## Runtime and provider boundaries

`analyze(role, *, case_id, mode, guidance, phase, emit, settings=None) -> Position`
remains independent from the chair's rounds, state machine, persistence and concurrence.
Modes are explicitly `rehearsal` or `azure`; phases are `initial` or `followup`.
Unaccepted memories are not silently injected as policy.

Azure uses `AsyncOpenAI` Responses function calling followed by strict
`responses.parse(text_format=Position)`, with `reasoning={"effort": "low"}` and
`store=False`. Model-selected tools must be allowlisted and executed before publication.
Case/role binding, returned evidence IDs, provenance, unknown URLs/identifiers, strict
schema, refusal/truncation and budgets are validated. Failures remain visible with no
rehearsal fallback. Grounding validates identifiers, not every sentence's entailment;
clinical source scrutiny still requires humans.

The first model request contains a compact clinical summary, source file/hash/simulation
date, the preserved biomarker-date ambiguity, and the role's workspace/question. Its
first tool returns every field in the complete role-relevant context. Subsequent tools
reference that first output and send only derived context additions. Evidence already
returned is referenced by ID rather than copied repeatedly; the first full source record
remains in the isolated conversation and audit tool results retain complete evidence.
The entire case, all eight consultations and all options
are not injected into every role. No source data is truncated: the full dossier remains
in the application record. All seven initial and follow-up model paths exercise the
actual reserve-budget guard in mocked Responses tests. Live prompts request one to
three concise claims within the unchanged 2,000-output-token schema budget.

Default concurrency stays **three** role loops and shared request spacing stays
**20 seconds**, configurable through `MDT_AZURE_MAX_CONCURRENT_ROLES` (1–7) and
`MDT_AZURE_REQUEST_INTERVAL_SECONDS` (0–60). Queue time is bounded separately.
No deployment, quota or pacing change accompanies this case migration.

Existing limits remain four logical model calls, five tools, 2,000 output tokens per
call, 48,000 observed total tokens, 300 seconds active time and 600 seconds queue
time. Conservative input reservation remains in place. Requests allow 90 seconds
of read inactivity, 10 seconds for connection/pool acquisition and 30 seconds
for writes. One timeout/connection retry waits two seconds plus shared pacing;
it remains within the active-role deadline and never replays completed local
tools. Unknown usage from a timed-out remote request is not reported as measured
usage; the provider may still charge for that inference.
SDK retries remain disabled; the bounded two-retry 429 loop honors server cooldowns
up to 60 seconds, shares pacing and fails explicitly on malformed/excessive delays.
Clients and credentials close through the existing exit stack.

Activity presents clinician-readable assessment summaries, not hidden reasoning.
Telemetry and audit exports retain bounded deployment/request/response/token metadata,
not credentials, prompts, patient passages or guidance. Existing historic live-verification
artifacts describe the previous case, not proof of live execution for this CRC package.
The migration's offline tests exercise all seven roles and the real Responses SDK
over mocked HTTP, including grounding, tool-loop, rate-limit and safety boundaries.
