import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DocumentScreen, Outcome, OutcomeBanner, documentStatus, languageLabel } from './Outcome';
import { clinicalActivity, documentError } from './presentation';
import { ROLES } from './types';
import type { Audience, Communication, Meeting } from './types';

const noop = async () => true;

function doc(audience: Audience, overrides: Partial<Communication> = {}): Communication {
  return {
    audience, plan_version: 1, revision: 1, status: 'DRAFT', generated_by: 'azure', author_role: 'chair',
    language: audience === 'patient' ? 'de' : 'en', title: audience === 'patient' ? 'Ihr Behandlungsplan' : 'MDT outcome letter',
    sections: [{ id: 'plan', heading: audience === 'patient' ? 'Was jetzt passiert' : 'Plan', paragraphs: ['Erster Schritt.'], bullets: [], columns: audience === 'clinician' ? ['Item', 'Detail'] : [], rows: audience === 'clinician' ? [['CEA', '12 µg/L'], ['8', 'PROTOCOL_NOT_PUBLIC: verify local pathway']] : [], source_refs: ['plan.actions[0]'] }],
    glossary: audience === 'patient' ? [{ term: 'MDT', meaning: 'Ein Treffen von Fachleuten.' }] : [],
    questions_to_ask: audience === 'patient' ? ['Wann ist der nächste Termin?'] : [],
    citations: [], reviews: [], requested_changes: [],
    checks: { word_count: 500, word_target: [450, 900], sentence_count: 40, average_sentence_words: 12, longest_sentence_words: 22, reading_ease: 64, reading_formula: 'Amstad', grade_level: null, reading_target: '≥ 60', language: 'de', detected_language: 'de', unexplained_terms: [], uncovered_refs: [], unsupported_numbers: [], unresolved_citations: [], unknown_refs: [] },
    approved_by: null, approved_role: null, approved_at: null, approved_revision: null, error: null,
    created_at: '2026-09-16T10:00:00Z', updated_at: '2026-09-16T10:00:00Z',
    ...overrides,
  };
}

function decided(communications: Meeting['communications'] = { patient: doc('patient'), clinician: doc('clinician') }): Meeting {
  return {
    id: 'outcome-test', phase: 'DECISION_CAPTURED', mode: 'rehearsal', case: {}, roles: {},
    evidence: [], frictions: [], memories: [], objections: [], events: [], round: 2, busy: false, error: null,
    plan: { version: 1, title: 'Liver-first conversion plan', summary: 'Agreed with conditions.', actions: ['Repeat MRI after cycle 6', 'Re-present at MDT'], conditions: ['Remnant volume to be confirmed'], evidence_ids: [], created_at: '2026-09-16T10:00:00Z' },
    concurrences: Object.fromEntries(ROLES.map((role, index) => [role, { role, plan_version: 1, actor: index === 0 ? 'human' : 'agent', comment: '', timestamp: '2026-09-16T10:00:00Z' }])),
    communications, created_at: '2026-09-16T09:00:00Z', closed_at: '2026-09-16T10:00:00Z',
  };
}

function screen(meeting: Meeting, audience: Audience, reviewer = '') {
  return renderToStaticMarkup(<DocumentScreen meeting={meeting} audience={audience} item={meeting.communications?.[audience]} back={() => {}} pending={false} mutate={noop} reviewer={reviewer} setReviewer={() => {}} reviewRole="" setReviewRole={() => {}} />);
}

describe('outcome screen', () => {
  it('announces consensus only once the decision is captured', () => {
    const meeting = decided();
    const banner = renderToStaticMarkup(<OutcomeBanner meeting={meeting} open={() => {}} />);
    expect(banner).toContain('Consensus reached');
    expect(banner).toContain('1 clinician concurrence');
    expect(banner).toContain('6 automatic under demonstration policy (not human sign-off)');
    expect(renderToStaticMarkup(<OutcomeBanner meeting={{ ...meeting, phase: 'CONCURRENCE' }} open={() => {}} />)).toBe('');
    const pending = renderToStaticMarkup(<Outcome meeting={{ ...meeting, phase: 'CONCURRENCE' }} pending={false} mutate={noop} />);
    expect(pending).toContain('data-testid="outcome-pending"');
  });

  it('shows the plan forward, conditions and both documents with status and language', () => {
    const markup = renderToStaticMarkup(<Outcome meeting={decided()} pending={false} mutate={noop} />);
    expect(markup).toContain('The plan forward');
    expect(markup).toContain('Repeat MRI after cycle 6');
    expect(markup).toContain('Remnant volume to be confirmed');
    expect(markup).toContain('data-testid="document-card-patient"');
    expect(markup).toContain('data-testid="document-card-clinician"');
    expect(markup).toContain('Language: Deutsch (German)');
    expect(markup).toContain('Awaiting clinician review');
    expect(markup).toContain('data-testid="outcome-quick-documents"');
    expect(markup).toContain('Patient summary · Deutsch · Awaiting clinician review');
  });

  it('keeps a failed draft visible and never substitutes scripted text', () => {
    const meeting = decided({ patient: doc('patient', { status: 'FAILED', error: 'Azure OpenAI is not configured on this server.', sections: [] }) });
    const markup = renderToStaticMarkup(<Outcome meeting={meeting} pending={false} mutate={noop} />);
    expect(markup).toContain('Could not be drafted');
    expect(markup).toContain('no scripted text was substituted');
    expect(markup).not.toMatch(/Azure|AZURE_OPENAI/);
    expect(screen(meeting, 'patient', 'Dr A')).toContain('data-testid="regenerate-document"');
  });

  it('renders the patient summary in the patient language with translated labels', () => {
    const markup = screen(decided(), 'patient');
    expect(markup).toContain('lang="de"');
    expect(markup).toContain('Begriffe erklärt');
    expect(markup).toContain('Fragen, die Sie stellen können');
    expect(markup).toContain('<dfn');
    expect(markup).toContain('Entwurf');
    const italian = screen(decided({ patient: doc('patient', { language: 'it' }) }), 'patient');
    expect(italian).toContain('lang="it"');
    expect(italian).toContain('Parole spiegate');
  });

  it('renders the colleague letter in English with its tables', () => {
    const markup = screen(decided(), 'clinician');
    expect(markup).toContain('data-testid="letter-document"');
    expect(markup).toContain('lang="en-GB"');
    expect(markup).toContain('<table');
    expect(markup).toContain('not valid until signed off by a named clinician');
    expect(markup).toContain('Local pathway unavailable: verify local pathway');
    expect(markup).not.toContain('PROTOCOL_NOT_PUBLIC');
  });

  it('requires a named reviewer before approval', () => {
    expect(screen(decided(), 'patient')).toMatch(/data-testid="approve-document"[^>]*disabled/);
    expect(screen(decided(), 'patient', 'Dr J. de Vries')).not.toMatch(/data-testid="approve-document"[^>]*disabled/);
    expect(screen(decided(), 'patient', 'Dr J. de Vries')).toMatch(/data-testid="request-changes"[^>]*disabled/);
  });

  it('shows who approved the document', () => {
    const approved = decided({ patient: doc('patient', { status: 'APPROVED', approved_by: 'Dr J. de Vries', approved_revision: 1, approved_at: '2026-09-16T10:05:00Z' }) });
    const markup = renderToStaticMarkup(<Outcome meeting={approved} pending={false} mutate={noop} />);
    expect(markup).toContain('Approved by <strong>Dr J. de Vries</strong>');
    expect(screen(approved, 'patient')).toContain('Von Ihrem Behandlungsteam geprüft und freigegeben');
    expect(screen(approved, 'patient')).toContain('data-testid="approval-record"');
  });

  it('labels languages and statuses for clinicians', () => {
    expect(languageLabel('en')).toBe('English');
    expect(languageLabel('it')).toBe('Italiano (Italian)');
    expect(languageLabel('fr')).toBe('FR');
    expect(documentStatus(undefined)).toBe('Not started');
    expect(documentStatus(doc('patient', { status: 'DRAFTING' }))).toBe('Drafting…');
  });
});

describe('outcome document activity', () => {
  it('narrates drafting events readably', () => {
    expect(clinicalActivity({ type: 'CommunicationDraftingStarted', audiences: ['patient', 'clinician'] }).title).toBe('Outcome documents: drafting');
    expect(clinicalActivity({ type: 'CommunicationActivity', audience: 'patient', activity: 'ReviewRetryScheduled' }).title).toBe('Patient summary: waiting');
    expect(clinicalActivity({ type: 'CommunicationDrafted', audience: 'clinician', revision: 2 }).title).toBe('Colleague letter ready for review · revision 2');
    const approved = clinicalActivity({ type: 'CommunicationApproved', audience: 'patient', reviewer: 'Dr A' });
    expect(approved.title).toBe('Patient summary approved');
    expect(approved.summary).toContain('Dr A');
    const failed = clinicalActivity({ type: 'CommunicationFailed', audience: 'patient', summary: 'AZURE_OPENAI_ENDPOINT deployment quota exceeded (429)' });
    expect(failed.failure).toBe(true);
    expect(failed.summary).not.toMatch(/AZURE|deployment|429/);
  });

  it('explains document failures without provider details', () => {
    expect(documentError('Server restarted while drafting')).toContain('restarted');
    expect(documentError('Request timed out')).toContain('did not finish in time');
    expect(documentError('HTTP 401 Unauthorized')).toContain('refused access');
    expect(documentError('')).toContain('No scripted text was substituted');
    expect(documentError('https://nl-example.openai.azure.com/openai/deployments/x failed')).not.toMatch(/openai|azure/i);
  });
});
