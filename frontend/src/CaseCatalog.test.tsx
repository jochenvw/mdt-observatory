import { readFileSync } from 'node:fs';
import { Children, isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { request } from './api';
import { CaseSelection } from './CaseSelection';
import { CaseClinical, CaseTimeline, CompleteCaseRecord, isConversionCase, ManagementOptions, RecordValue } from './CaseDossier';
import { clinicalCaseKind, clinicalProfile } from './caseProfiles';
import { presentMeeting } from './presentation';
import { Specialist } from './Specialist';
import { ROLES } from './types';
import type { CaseSummary, Data, Meeting, Role } from './types';

const cases: CaseSummary[] = [
  { id: 'CASE-MDT-CRC-BRAF-2026-001', title: 'Colorectal BRAF conversion review', patient_label: 'Original demonstration case', stage: 'Stage IV', question: 'Review local clearance.' },
  { id: 'CASE-MDT-CRC-WT-2026-002', title: 'Colorectal conversion response', patient_label: '58-year-old man', stage: 'Stage IV', question: 'Review disappearing liver lesions and treatment burden.' },
  { id: 'CASE-MDT-PDAC-PERIOP-2026-003', title: 'Pancreatic perioperative review', patient_label: '72-year-old woman', stage: 'Stage IIB', question: 'Separate technical feasibility from physiological approval.' },
];
function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  return Children.toArray(node).flatMap(child => isValidElement<Record<string, unknown>>(child) ? [child, ...elements(child.props.children as ReactNode)] : []);
}
afterEach(() => vi.unstubAllGlobals());

describe('case catalog selection', () => {
  it.each(cases)('selects and posts the explicit ID for $title', async item => {
    let selected = cases[0].id;
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'new-meeting' })));
    vi.stubGlobal('fetch', fetch);
    const props = {
      cases, selected, select: (id: string) => { selected = id; },
      meeting: null, loading: false, canStart: true, mode: 'rehearsal' as const,
      start: () => request('/meetings', { mode: 'rehearsal', case_id: selected }), resume: () => {},
      clearRoom: () => {}, pending: false,
    };
    const radio = elements(CaseSelection(props)).find(element => element.type === 'input' && element.props.value === item.id);
    expect(radio).toBeDefined();
    (radio!.props.onChange as () => void)();
    const selectedTree = CaseSelection({ ...props, selected });
    const markup = renderToStaticMarkup(selectedTree);
    expect(markup.match(/type="radio"/g)).toHaveLength(3);
    for (const choice of cases) expect(markup).toContain(choice.title);
    expect(markup).toContain('Select a case for multidisciplinary review');
    expect(markup).not.toMatch(/Bring the team together|No other case is currently available/);
    const checked = elements(selectedTree).filter(element => element.type === 'input' && element.props.checked);
    expect(checked.map(element => element.props.value)).toEqual([item.id]);
    const start = elements(selectedTree).find(element => element.props['data-testid'] === 'start-case')!;
    await (start.props.onClick as () => Promise<unknown>)();
    expect(fetch).toHaveBeenCalledWith('/api/meetings', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ mode: 'rehearsal', case_id: item.id }),
    }));
  });
  it('keeps catalog absence visible and disables start while loading', () => {
    const markup = renderToStaticMarkup(<CaseSelection cases={[]} selected="" select={() => {}} meeting={null} loading canStart={false} mode="rehearsal" start={() => {}} resume={() => {}} clearRoom={() => {}} pending={false} />);
    expect(markup).toContain('Loading available cases');
    expect(markup).toContain('disabled=""');
  });
});

function meetingFor(data: Data, role: Role): Meeting {
  return {
    id: 'case-catalog-test', phase: 'INITIAL_ANALYSIS', mode: 'rehearsal', case: data,
    roles: { [role]: {
      role, label: role === 'surgery' && clinicalCaseKind(data) === 'pancreatic_perioperative' ? 'Surgical / perioperative review' : role,
      status: 'ANALYZING', context: {
        workspace: `Supplied ${role} workspace`, question: data.question,
        detailed_findings: { nested: ['Complete role-specific source detail', { unresolved: 'Assessment remains conditional' }] },
        risk_review: 'Illustrative unvalidated risk model; not physiological approval or an automated ICU choice.',
        source_metadata: { access: 'Supplied source record; not independently validated' },
        provider: 'hidden-provider', request_id: 'hidden-request', token_usage: 12345,
      },
      trace: { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' },
      position: null, activity: [], guidance: [], revision: 0, error: null,
    } },
    evidence: [], frictions: [], memories: [], plan: null, concurrences: {}, objections: [], events: [],
    round: 1, busy: false, error: null, created_at: '2026-09-17', closed_at: null,
  };
}
const newCases = [
  { id: cases[1].id, kind: 'crc_conversion_response', diagnosis: 'Sigmoid colorectal cancer', question: cases[1].question },
  { id: cases[2].id, kind: 'pancreatic_perioperative', diagnosis: 'Pancreatic head adenocarcinoma', question: cases[2].question },
];

describe.each(newCases)('$kind specialty sources', data => {
  it.each(ROLES)('uses complete %s role context, distinct guidance and unchanged activity controls', role => {
    const raw = meetingFor(data, role);
    const before = JSON.stringify(raw);
    const meeting = presentMeeting(raw)!;
    const markup = renderToStaticMarkup(<Specialist role={role} meeting={meeting} pending={false} guidance="Unsent clinician draft" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
    const profile = clinicalProfile(data, role)!;
    expect(markup).toContain(profile.title.replaceAll('&', '&amp;'));
    expect(markup).toContain('Complete role-specific source detail');
    expect(markup).toContain('Assessment remains conditional');
    expect(markup).toContain('Illustrative unvalidated risk model');
    expect(markup).toContain('not independently validated');
    expect(markup).toContain('data-testid="guidance-input"');
    expect(markup).toContain('Unsent clinician draft');
    expect(markup).toContain('Saved review preferences');
    expect(markup).toContain('data-testid="complete-case-record"');
    expect(markup.indexOf('data-testid="activity-desk"')).toBeLessThan(markup.indexOf(`data-testid="clinical-${role}"`));
    expect(markup).not.toMatch(/hidden-provider|hidden-request|12345|encorafenib|cetuximab|BREAKWATER|PROVENC3|nine baseline|nine liver|four-cycle|11\.8|0\.42|216 →/i);
    expect(markup).not.toContain('liver-segment-map');
    expect(markup).not.toContain('illustrative-scan');
    if (data.kind === 'pancreatic_perioperative') expect(markup).not.toMatch(/colorectal|colectomy|BRAF|liver remnant/i);
    expect(JSON.stringify(raw)).toBe(before);
  });
  it('does not choose the original renderer just because the new dossier has baseline liver MRI', () => {
    const similarShape = { ...data, dossier: { imaging: { baseline_liver_MRI: { metastatic_lesions: [] } } } };
    expect(isConversionCase(similarShape)).toBe(false);
    expect(clinicalCaseKind({ ...similarShape, kind: undefined })).toBe(data.kind);
    const markup = renderToStaticMarkup(<CaseTimeline data={similarShape} />);
    expect(markup).not.toMatch(/BRAF|MAY–SEPTEMBER|Biochemical and molecular response/);
  });
  it('does not infer specialty findings when role context is absent', () => {
    const meeting = meetingFor(data, 'radiology');
    meeting.roles.radiology!.context = {};
    const markup = renderToStaticMarkup(<CaseClinical role="radiology" meeting={meeting} inspect={() => {}} />);
    expect(markup).toContain('Detailed source context for this specialty has not been supplied');
    expect(markup).not.toContain('<svg');
  });
});

describe.each(['crc_wt_case.json', 'pancreatic_case.json'])('packaged %s full record', file => {
  it.each(ROLES)('retains the complete packaged %s context and keeps clinical projections ahead of expandable source narratives', role => {
    const envelope = JSON.parse(readFileSync(new URL(`../../src/mdt/dossiers/${file}`, import.meta.url), 'utf8')) as { case: Data; role_contexts: Record<Role, Data> };
    const raw = meetingFor(envelope.case, role);
    raw.roles[role]!.context = envelope.role_contexts[role];
    const meeting = presentMeeting(raw)!;
    const markup = renderToStaticMarkup(<CaseClinical role={role} meeting={meeting} inspect={() => {}} />);
    for (const [key, value] of Object.entries(envelope.role_contexts[role])) {
      if (key === 'workspace' || key === 'question') continue;
      expect(markup).toContain(`data-testid="clinical-source-${role}-${key}"`);
      expect(markup).toContain(renderToStaticMarkup(<RecordValue value={value} />).replaceAll('PROTOCOL_NOT_PUBLIC', 'Local pathway unavailable'));
    }
    expect(markup).not.toMatch(/liver-segment-map|liver-lesion-table|BRAF V600E plasma VAF|NINE BASELINE SITES/);
    expect(markup.indexOf(`data-testid="clinical-source-${role}-caveats"`)).toBeLessThan(markup.indexOf(`data-testid="clinical-source-${role}-source_sections"`));
    expect(markup).toContain(`<details data-testid="clinical-source-${role}-source_sections"`);
  });
  it('preserves every nested dossier section, narrative and management alternative without inventing charts', () => {
    const envelope = JSON.parse(readFileSync(new URL(`../../src/mdt/dossiers/${file}`, import.meta.url), 'utf8')) as { case: Data };
    const pack = envelope.case;
    const original = JSON.stringify(pack);
    const presented = presentMeeting(meetingFor(pack, 'research'))!;
    const markup = renderToStaticMarkup(<CompleteCaseRecord data={presented.case} />);
    for (const [key, value] of Object.entries(pack.dossier as Data)) {
      expect(markup).toContain(`data-testid="record-section-${key}"`);
      expect(markup).toContain(renderToStaticMarkup(<RecordValue value={value} />));
    }
    for (const key of ['narrative', 'source_sections', 'management_alternatives', 'specialty_contributions']) {
      if (pack[key] !== undefined) expect(markup).toContain(renderToStaticMarkup(<RecordValue value={pack[key]} />));
    }
    const alternatives = renderToStaticMarkup(<ManagementOptions data={presented.case} />);
    expect(alternatives).toContain('Management alternatives for discussion');
    expect(alternatives).not.toContain('Local clearance, more biological testing, or disease control?');
    expect(markup).not.toContain('<svg');
    expect(JSON.stringify(pack)).toBe(original);
  });
});
