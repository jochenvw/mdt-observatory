import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Specialist } from './Specialist';
import { ROLE_LAYOUTS } from './roleLayouts';
import { clinicalError, presentMeeting, recordText } from './presentation';
import { ROLES } from './types';
import type { Evidence, Meeting, Role } from './types';

const headings: Record<Role, string> = {
  radiology: 'Longitudinal imaging review',
  oncology: 'Toxicity and tolerability',
  surgery: 'Anatomical resectability',
  pathology: 'Molecular findings',
  research: 'Appraisal lens',
  protocol: 'Conditions before application',
  patient: 'Support and shared decision-making',
};
function caseFor(role: Role): Meeting {
  return {
    id: 'layout-test', phase: 'INITIAL_ANALYSIS', mode: 'rehearsal', case: {},
    roles: { [role]: {
      role, label: role, status: 'ANALYZING',
      context: { question: 'What remains uncertain?', measurements: [{ label: 'Current study', diameter_mm: 23, weeks_ago: 0 }], treatment: 'Recorded prior treatment', toxicity: 'Recorded adverse effect', molecular: 'Recorded marker', stated_preferences: ['Preserve independence'] },
      trace: { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' },
      position: null, activity: [], guidance: [], revision: 0, error: null,
    } },
    evidence: [], frictions: [], memories: [], plan: null, concurrences: {}, objections: [], events: [],
    round: 1, busy: false, error: null, created_at: '2026-09-16', closed_at: null,
  };
}
function renderScenario(role: Role, context: Record<string, unknown>, configure?: (meeting: Meeting) => void) {
  const raw = caseFor(role);
  const state = raw.roles[role];
  if (!state) throw new Error('Specialty fixture is required');
  state.context = context;
  configure?.(raw);
  const original = JSON.stringify(raw);
  const presented = presentMeeting(raw);
  if (!presented) throw new Error('Presented meeting is required');
  const markup = renderToStaticMarkup(<Specialist role={role} meeting={presented} pending={false} guidance="" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
  expect(JSON.stringify(raw)).toBe(original);
  return markup;
}
function clinicalBlock(markup: string, title: string) {
  const article = [...markup.matchAll(/<article\b[^>]*>[\s\S]*?<\/article>/g)].find(match => match[0].includes(`<h3>${title}</h3>`))?.[0];
  expect(article, `Visible clinical panel: ${title}`).toBeDefined();
  return article ?? '';
}

describe('scenario-shaped clinical data bindings', () => {
  it('binds case treatment history and contrasts both oncology toxicity records above the treatment board', () => {
    const context = {
      biomarkers: { 'PD-L1 TPS': '60%', EGFR: 'no sensitizing variant', ALK: 'negative' },
      performance_status: 'ECOG 1',
      referral_summary: 'No significant prior systemic treatment toxicity.',
      archived_toxicity_note: 'Synthetic signed discharge summary: grade 3 immune-mediated pneumonitis during pembrolizumab for melanoma; hospitalization and systemic steroids required.',
      question: 'Can high PD-L1 override trial mismatch and prior toxicity?',
    };
    const previousTreatment = 'Pembrolizumab for prior melanoma; not treatment for this lung lesion';
    const treatment = 'Lung lesion untreated; prior melanoma immunotherapy stopped for severe toxicity';
    const markup = renderScenario('oncology', context, meeting => {
      meeting.case = { previous_treatment: previousTreatment, treatment, history: ['Prior melanoma treated with immunotherapy.'] };
    });
    const prior = clinicalBlock(markup, 'Treatment already received');
    expect(prior).toContain(previousTreatment);
    expect(prior).toContain(treatment);
    expect(prior).toContain('Prior melanoma treated with immunotherapy.');
    expect(prior).not.toContain('Not specified');
    const conflict = clinicalBlock(markup, 'Reconcile the toxicity history');
    expect(conflict).toContain(context.referral_summary);
    expect(conflict).toContain(recordText(context.archived_toxicity_note));
    expect(markup.indexOf('Reconcile the toxicity history')).toBeLessThan(markup.indexOf('Treatment already received'));
    const options = clinicalBlock(markup, 'Options requiring discussion');
    expect(options).toContain('PD-L1 TPS');
    expect(options).toContain('EGFR');
    expect(options).toContain('ALK');
    expect(options).not.toMatch(/Pd L1 Tps|Egfr|Alk/);
  });
  it('places surgical reserve and the work-up question inside confirmation and fitness panels', () => {
    const context = {
      anatomy: 'Peripheral RUL lesion; inferior margin uncertain; nodal disease unproven.',
      reserve: 'Synthetic FEV1 78%, DLCO 61% predicted; postoperative values pending.',
      risk: 'Prior immune pneumonitis and scarring require anaesthetic/respiratory assessment.',
      question: 'Consider a local-treatment work-up, not automatic surgery or immunotherapy.',
    };
    const markup = renderScenario('surgery', context);
    const confirmation = clinicalBlock(markup, '02 / Confirmation needed');
    expect(confirmation).toContain(recordText(context.reserve));
    expect(confirmation).toContain(context.question);
    expect(confirmation).not.toContain('Not specified');
    const fitness = clinicalBlock(markup, 'Patient fitness and risk');
    expect(fitness).toContain(recordText(context.reserve));
    expect(fitness).toContain(context.risk);
  });
  it('fills pathway stages with supplied Dutch/EU evidence, access limits and current review conditions', () => {
    const context = {
      jurisdiction: 'Netherlands / European Union',
      question: 'Separate guidelines, EMA authorisation, trial eligibility and local policy.',
      trial: 'CheckMate 816 / NCT02998528; CTIS is the preferred registry entry point.',
      institutional_protocol: 'PROTOCOL_NOT_PUBLIC: the fictional hospital pathway is not supplied. Do not infer approval.',
    };
    const evidence: Evidence[] = [
      {
        id: 'NL-NSCLC', title: 'Niet kleincellig longcarcinoom - Dutch guideline overview',
        url: 'https://richtlijnendatabase.nl/', date: '2025-09-18', authority: 'Richtlijnendatabase / NVALT',
        region: 'NL', kind: 'GUIDELINE', access: 'PUBLIC_FULL_TEXT', patient_match: 'PARTIAL',
        passage: 'Curated paraphrase: this modular Dutch NSCLC guideline covers diagnostics, treatment, communication, follow-up and organisation of care. The overview is not a verified patient-specific treatment recommendation.',
        limitations: ['Only the overview was curated, not every treatment module.', 'Module-level recommendations, local adoption and reimbursement must be checked.'],
        scrutiny: {}, synthetic: false, retrieval: 'CURATED',
      },
      {
        id: 'EU-EMA-OPDIVO', title: 'Opdivo (nivolumab) - EMA European public assessment report',
        url: 'https://www.ema.europa.eu/en/medicines/human/EPAR/opdivo', date: '2026-09-16', authority: 'European Medicines Agency',
        region: 'EU', kind: 'REGULATORY', access: 'PUBLIC_FULL_TEXT', patient_match: 'PARTIAL',
        passage: 'Curated paraphrase: the EMA overview describes neoadjuvant nivolumab plus platinum chemotherapy in resectable NSCLC producing PD-L1 and at high risk of recurrence. An authorisation is not proof of benefit or safety for this patient.',
        limitations: ['EU authorisation does not establish Dutch reimbursement or hospital approval.'],
        scrutiny: {}, synthetic: false, retrieval: 'CURATED',
      },
    ];
    const condition = 'Full current product information and toxicity management need clinician review.';
    const markup = renderScenario('protocol', context, meeting => {
      const state = meeting.roles.protocol;
      if (!state) throw new Error('Protocol fixture is required');
      state.trace.observations = [context.institutional_protocol];
      state.trace.uncertainties = [context.institutional_protocol];
      state.activity = [{ type: 'ObservationAdded', summary: context.institutional_protocol }];
      state.position = {
        role: 'protocol', case_id: meeting.id, position: 'Review applicability', confidence: 0,
        autonomy: 'REVIEW', claims: [], uncertainties: [context.institutional_protocol],
        recommendation: 'Review access limitations', questions_for_mdt: [context.question],
        human_intervention: true, provenance: [], stance: 'CONDITIONAL', friction_keys: [], trace: state.trace,
      };
      meeting.evidence = evidence;
      meeting.plan = { version: 1, direction: 'INVESTIGATE_FURTHER', title: 'Review', decision: 'Investigate further.', summary: 'Conditional review', actions: [], conditions: [condition], resolved_requirements: [], evidence_ids: evidence.map(source => source.id), created_at: '2026-09-16' };
    });
    const nl = markup.split('data-testid="protocol-step-NL"')[1]?.split('data-testid="protocol-step-EU"')[0];
    const eu = markup.split('data-testid="protocol-step-EU"')[1]?.split('data-testid="protocol-step-ACCESS"')[0];
    const access = markup.split('data-testid="protocol-step-ACCESS"')[1]?.split('data-testid="protocol-step-IF"')[0];
    const conditions = markup.split('data-testid="protocol-step-IF"')[1]?.split('Complete protocol record')[0];
    expect(nl).toContain(evidence[0].passage);
    expect(nl).toContain(evidence[0].limitations[1]);
    expect(eu).toContain(evidence[1].passage);
    expect(eu).toContain(evidence[1].limitations[0]);
    expect(access).toContain(context.trial);
    expect(access).toContain('Local pathway unavailable');
    expect(conditions).toContain(context.question);
    expect(conditions).toContain(condition);
    expect(conditions).toContain('Do not infer approval.');
    expect(markup).not.toContain('PROTOCOL_NOT_PUBLIC');
    expect(markup).not.toContain('Not specified');
  });
  it('uses actual priorities and the clinical question for an unquantified patient-burden discussion', () => {
    const context = {
      stated_priorities: ['Synthetic preference: preserve independent daily activity.', 'Synthetic preference: avoid another severe breathing complication.'],
      support: 'Lives alone; daughter can accompany appointments by prior arrangement.',
      question: 'Explain uncertain benefit and pulmonary risk plainly; invite preference.',
    };
    const markup = renderScenario('patient', context);
    const burden = clinicalBlock(markup, 'Treatment burden');
    expect(burden).toContain('Treatment burden has not been quantified');
    expect(burden).toContain(recordText(context.stated_priorities[0]));
    expect(burden).toContain(recordText(context.stated_priorities[1]));
    expect(burden).toContain(context.question);
    expect(burden).not.toContain('Not specified');
    expect(clinicalBlock(markup, 'Support and shared decision-making')).toContain(context.support);
  });
});
describe('specialty-specific clinical compositions', () => {
  it('promotes a legacy timeout in next_action to a visible review failure without rewriting the audit', () => {
    const raw = caseFor('oncology');
    const state = raw.roles.oncology!;
    const error = 'Specialist analysis failed: APITimeoutError; no rehearsal fallback.';
    state.trace.next_action = error;
    state.activity = [{ type: 'UncertaintyRaised', summary: error, error: true }];
    const safe = presentMeeting(raw)!;
    expect(safe.roles.oncology?.trace.next_action).toBe('');
    expect(safe.roles.oncology?.error).toBe(clinicalError(error));
    const markup = renderToStaticMarkup(<Specialist role="oncology" meeting={safe} pending={false} guidance="" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
    expect(markup).toContain('role="alert"');
    expect(markup).toContain('did not respond in time');
    expect(markup).not.toMatch(/APITimeoutError|no rehearsal fallback|NEXT CLINICAL QUESTION/);
    expect(raw.roles.oncology?.trace.next_action).toBe(error);
  });
  it('renders the shared capacity-error category without reclassifying it as a plan conflict', () => {
    const raw = caseFor('radiology');
    const role = raw.roles.radiology;
    if (!role) throw new Error('Radiology fixture is required');
    const rawError = 'Specialist analysis failed: RateLimitError; request_id=req_failed_review';
    role.error = rawError;
    role.status = 'ERROR';
    const presented = presentMeeting(raw);
    if (!presented) throw new Error('Presented meeting is required');
    const markup = renderToStaticMarkup(<Specialist role="radiology" meeting={presented} pending={false} guidance="" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
    expect(markup).toContain('role="alert"');
    expect(markup).toContain(clinicalError(rawError));
    expect(markup).toContain('No new conclusion has been recorded');
    expect(markup).not.toMatch(/plan has changed|RateLimitError|request_id|req_failed_review/);
    expect(raw.roles.radiology?.error).toBe(rawError);
  });
  it('assigns seven distinct layouts and theme-token-only color treatments', () => {
    expect(new Set(ROLES.map(role => ROLE_LAYOUTS[role].identity)).size).toBe(7);
    expect(new Set(ROLES.map(role => ROLE_LAYOUTS[role].header)).size).toBe(7);
    expect(new Set(ROLES.map(role => ROLE_LAYOUTS[role].canvas)).size).toBe(7);
    expect(new Set(ROLES.map(role => ROLE_LAYOUTS[role].title)).size).toBe(7);
    for (const layout of Object.values(ROLE_LAYOUTS)) {
      expect(layout.grid).toContain('grid');
      expect(layout.shell).toContain('var(--cp-');
      expect(layout.header).not.toMatch(/#[0-9a-f]|rgb\(|hsl\(/i);
      expect(layout.focus).toHaveLength(3);
    }
  });
  it.each(ROLES)('renders the %s clinical composition and preserves steering controls', role => {
    const markup = renderToStaticMarkup(<Specialist role={role} meeting={caseFor(role)} pending={false} guidance="" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
    expect(markup).toContain(`data-testid="role-layout-${role}"`);
    expect(markup).toContain(`data-testid="workspace-${role}"`);
    expect(markup).toContain(`data-testid="role-identity-${role}"`);
    expect(markup).toContain(ROLE_LAYOUTS[role].title);
    expect(markup).toContain('aria-label="Specialty focus"');
    for (const focus of ROLE_LAYOUTS[role].focus) expect(markup).toContain(focus);
    expect(markup).toContain(`data-layout="${ROLE_LAYOUTS[role].identity}"`);
    expect(markup).toContain(`data-testid="clinical-${role}"`);
    expect(markup).toContain(headings[role]);
    expect(markup).toContain('data-testid="guidance-input"');
    expect(markup).toContain('data-testid="send-guidance"');
    expect(markup).toContain('How the agent moved from question to conclusion');
    for (const step of ['Trying to answer', 'Considered', 'This showed', 'But this remains uncertain', 'So the current conclusion is', 'Next']) expect(markup).toContain(step);
    expect(markup.indexOf('data-testid="activity-desk"')).toBeLessThan(markup.indexOf(`data-testid="clinical-${role}"`));
    expect(markup).toContain('Saved review preferences');
    expect(markup).toContain('No saved review preferences for this specialty.');
    expect(markup).not.toContain('calibrated clinical confidence');
  });
});
describe('agent question to the specialist', () => {
  it('asks the human in the first person and offers a reported-finding reply', () => {
    const friction = { id: 'imaging', question: 'Can targeted human review map all 11 original sites?', roles: ['radiology' as Role], missing: ['Reconcile all 11 baseline sites.', 'PROTOCOL_NOT_PUBLIC: confirm the local pathway.'], blocking: true, resolved: false, resolution: null };
    const setup = (meeting: Meeting) => { meeting.phase = 'TARGETED_DISCUSSION'; meeting.case = { id: 'CASE-MDT-CRC-WT-2026-002' }; meeting.frictions = [friction]; meeting.roles.radiology!.status = 'DONE'; };
    const asking = renderScenario('radiology', {}, setup);
    expect(asking).toContain('data-testid="agent-question"');
    expect(asking).toContain('I cannot settle this from the record alone');
    expect(asking).toContain('Can targeted human review map all 11 original sites?');
    expect(asking).toContain('What I need you to check (2)');
    expect(asking).not.toContain('PROTOCOL_NOT_PUBLIC');
    expect(asking).toContain('data-testid="human-action-required"');
    expect(asking).toContain('The MDT is waiting for the radiologist');
    expect(asking).toContain('The next MDT step hinges on');
    expect(asking).toContain('Enter what you reviewed and found');
    expect(asking).toContain('data-testid="go-to-human-reply"');
    expect(asking).toContain('Radiologist input required');
    expect(asking).toContain('Send reply');
    expect(asking).toContain('placeholder="I reviewed the baseline and current MRI');
    const stillOpen = renderScenario('radiology', {}, meeting => { setup(meeting); meeting.roles.radiology!.guidance = ['Go ahead']; });
    expect(stillOpen).toContain('Your last reply did not say what you reviewed');
    expect(stillOpen).toContain('the dependency remains open');
    const quiet = renderScenario('radiology', {}, meeting => { meeting.phase = 'TARGETED_DISCUSSION'; });
    expect(quiet).not.toContain('agent-question');
    expect(quiet).not.toContain('human-action-required');
    expect(quiet).toContain('Instruct your agent');
  });
});
