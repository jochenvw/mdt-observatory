import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ResearchOperationsPanel } from './ResearchPanel';
import { researchOperations } from './researchOperations';
import { clinicalActivity, presentMeeting } from './presentation';
import type { Evidence, Meeting, MeetingEvent } from './types';

function found(id: string, overrides: Partial<Evidence> = {}): Evidence {
  return {
    id, title: `Hepatectomy for BRAF prediction model study ${id}`, url: `https://pubmed.ncbi.nlm.nih.gov/${id.replace(/\D/g, '')}/`,
    date: '2020-05-01', authority: 'Demo Journal', region: 'INTERNATIONAL', kind: 'LITERATURE', access: 'PUBLIC_ABSTRACT_ONLY',
    patient_match: 'NOT_ASSESSED', passage: 'Abstract text about synthetic lethality.', limitations: ['Patient-to-study applicability has not been assessed.'],
    scrutiny: {}, synthetic: false, retrieval: 'RECORDED', retrieved_at: '2026-09-24T10:00:00Z', retrieved_via: 'Europe PMC',
    source_tier: 'INTL', query: 'BRAF colorectal liver metastases', identifiers: { pmid: id.replace(/\D/g, '') }, ...overrides,
  };
}
let nextId = 1;
function event(type: string, payload: MeetingEvent['payload']): MeetingEvent {
  return { id: nextId++, meeting_id: 'm', type, role: 'research', payload, timestamp: '2026-09-24T10:00:00Z' };
}
const curated: Evidence = { ...found('CRC-CAIRO5'), retrieval: 'CURATED', source_tier: undefined, retrieved_at: undefined, retrieved_via: undefined, patient_match: 'HIGH', title: 'CAIRO5' };
function meeting(events: MeetingEvent[], evidence: Evidence[] = []): Meeting {
  return {
    id: 'm', phase: 'TARGETED_DISCUSSION', mode: 'rehearsal', case: {}, evidence: [curated, ...evidence], frictions: [], memories: [], plan: null,
    concurrences: {}, objections: [], events, round: 1, busy: false, error: null, created_at: '', closed_at: null,
    roles: { research: { role: 'research', label: 'Research', status: 'READY', context: {}, activity: [], guidance: [], revision: 1, error: null,
      trace: { assessment: '', hypothesis: '', observations: [], uncertainties: [], evidence_checking: [], next_action: '' },
      position: { position: 'p', recommendation: 'r', stance: 'SUPPORT', autonomy: 'REVIEW', human_intervention: false, questions_for_mdt: [], uncertainties: [],
        claims: [{ claim: 'c', evidence_ids: ['REC-PMID-30000001'] }], provenance: ['CRC-CAIRO5', 'REC-PMID-30000001'], trace: { assessment: '', hypothesis: '', observations: [], uncertainties: [], evidence_checking: [], next_action: '' } } as never } },
  } as Meeting;
}
const guidelineSearch = [
  event('ToolStarted', { tool: 'search_dutch_guidelines', retrieval: 'RECORDED', sources: ['richtlijnendatabase'], query: 'levermetastasen', summary: 'Replaying a recorded search: Searching Richtlijnendatabase for “levermetastasen”' }),
  event('ToolCompleted', { tool: 'search_dutch_guidelines', retrieval: 'RECORDED', status: 'completed', query: 'levermetastasen', summary: 'Richtlijnendatabase: 3 of 12 shown', result_count: 3, already_curated: [],
    checks: [{ source: 'richtlijnendatabase', label: 'Richtlijnendatabase', tier: 'NL', status: 'completed', total: 12, returned: 3, message: '' }] }),
];
const failedSearch = [
  event('ToolStarted', { tool: 'search_clinical_trials', retrieval: 'RECORDED', sources: ['ctis', 'clinicaltrials_gov'], query: 'BRAF V600E colorectal', summary: 'x' }),
  event('ToolCompleted', { tool: 'search_clinical_trials', retrieval: 'RECORDED', status: 'completed', query: 'BRAF V600E colorectal', summary: 'EU CTIS: unavailable; ClinicalTrials.gov: 2 of 40 shown', result_count: 2, already_curated: ['CRC-CAIRO5'],
    checks: [
      { source: 'ctis', label: 'EU Clinical Trials register (CTIS)', tier: 'EU', status: 'unavailable', total: 0, returned: 0, message: 'EU Clinical Trials register (CTIS) is temporarily unavailable (status 503).' },
      { source: 'clinicaltrials_gov', label: 'ClinicalTrials.gov', tier: 'US', status: 'completed', total: 40, returned: 2, message: '' },
    ] }),
];

describe('research operations', () => {
  it('derives sources, searches and findings from the recorded meeting only', () => {
    const ops = researchOperations(meeting([...guidelineSearch, ...failedSearch], [found('REC-PMID-30000001'), found('REC-NCT-1', { kind: 'TRIAL_REGISTRATION', source_tier: 'US', identifiers: { nct: 'NCT00000001' } })]));
    expect(ops.retrieval).toBe('RECORDED');
    expect(ops.capturedAt).toBe('2026-09-24');
    expect(ops.runs.map(run => run.status)).toEqual(['completed', 'completed']);
    const state = Object.fromEntries(ops.sources.map(source => [source.key, source.state]));
    expect(state).toMatchObject({ richtlijnendatabase: 'completed', ctis: 'unavailable', clinicaltrials_gov: 'completed', pubmed: 'not_searched' });
    expect(ops.found.map(group => group.tier)).toEqual(['INTL', 'US']);
    expect(ops.found.flatMap(group => group.items).some(item => item.retrieval === 'CURATED')).toBe(false);
    expect(ops.cited.has('REC-PMID-30000001')).toBe(true);
  });

  it('shows a running search until it completes', () => {
    const ops = researchOperations(meeting([guidelineSearch[0]]));
    expect(ops.runs[0].status).toBe('running');
    expect(ops.sources.find(source => source.key === 'richtlijnendatabase')?.state).toBe('searching');
  });

  it('renders the replay label, every source, the queries, failures and cited records', () => {
    const markup = renderToStaticMarkup(<ResearchOperationsPanel meeting={meeting([...guidelineSearch, ...failedSearch], [found('REC-PMID-30000001')])} inspect={() => {}} />);
    expect(markup).toContain('data-testid="research-operations"');
    expect(markup).toContain('Recorded replay · captured 2026-09-24');
    expect(markup).toContain('Nothing is searched live');
    for (const source of ['Richtlijnendatabase', 'EU CTIS', 'Europe PMC', 'PubMed', 'ClinicalTrials.gov', 'Preprints']) expect(markup).toContain(source);
    expect(markup).toContain('“levermetastasen”');
    expect(markup).toContain('3 of 12 shown');
    expect(markup).toContain('temporarily unavailable (status 503)');
    expect(markup).toContain('1 already in the curated set');
    expect(markup).toContain('Cited in position');
    expect(markup).toContain('Not appraised for this patient');
    expect(markup).toContain('PMID 30000001');
  });

  it('is honest when nothing was searched', () => {
    const markup = renderToStaticMarkup(<ResearchOperationsPanel meeting={meeting([])} inspect={() => {}} />);
    expect(markup).toContain('No public search has been run');
    expect(markup).not.toContain('Recorded replay');
    expect(markup).not.toContain('Live public search');
  });

  it('labels live searches as live', () => {
    const live = guidelineSearch.map(item => ({ ...item, payload: { ...item.payload, retrieval: 'LIVE' } }));
    const markup = renderToStaticMarkup(<ResearchOperationsPanel meeting={meeting(live, [found('LIVE-PMID-30000001', { retrieval: 'LIVE' })])} inspect={() => {}} />);
    expect(markup).toContain('Live public search');
    expect(markup).not.toContain('Recorded replay');
  });
});

describe('search narration', () => {
  it('narrates searches, findings and unavailable sources in clinician words', () => {
    const started = clinicalActivity({ ...guidelineSearch[0].payload, type: 'ToolStarted' }, 'research');
    expect(started.title).toBe('Replaying a recorded public search');
    expect(started.summary).toContain('Richtlijnendatabase for “levermetastasen”');
    const partly = clinicalActivity({ ...failedSearch[1].payload, type: 'ToolCompleted' }, 'research');
    expect(partly).toMatchObject({ title: 'Search partly unavailable', failure: true });
    const paper = clinicalActivity({ type: 'EvidenceFound', retrieval: 'LIVE', kind: 'TRIAL_REGISTRATION', retrieved_via: 'ClinicalTrials.gov', summary: 'A trial' }, 'research');
    expect(paper.title).toBe('Trial found · ClinicalTrials.gov');
    expect(paper.summary).toContain('not yet appraised');
    const unavailable = clinicalActivity({ type: 'UncertaintyRaised', tool: 'search_europepmc', summary: 'Live search of Europe PMC was unavailable: Europe PMC could not be searched (status 404).' }, 'research');
    expect(unavailable.failure).toBe(true);
    expect(unavailable.summary).toContain('Europe PMC could not be searched');
  });

  it('keeps searched titles verbatim while curated text is still cleaned', () => {
    const presented = presentMeeting(meeting([], [found('REC-PMID-30000001')]))!;
    const searched = presented.evidence.find(item => item.id === 'REC-PMID-30000001')!;
    expect(searched.title).toContain('prediction model');
    expect(searched.passage).toContain('synthetic lethality');
  });
});
