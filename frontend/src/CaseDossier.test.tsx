import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CaseTimeline, CompleteCaseRecord, ConversionClinical, isConversionCase, ManagementOptions, recordLabel, RecordValue } from './CaseDossier';
import { presentMeeting, recordText } from './presentation';
import { Specialist } from './Specialist';
import { ROLES } from './types';
import type { Data, Meeting, Role } from './types';

const casePack = JSON.parse(readFileSync(new URL('../../src/mdt/dossiers/crc_case.json', import.meta.url), 'utf8'));
const dossier = casePack.dossier;
function meetingFor(role: Role): Meeting {
  return {
    id: 'case-ui-test', phase: 'INITIAL_ANALYSIS', mode: 'rehearsal',
    case: { ...casePack, id: dossier.case.case_id },
    roles: { [role]: {
      role, label: role, status: 'ANALYZING', context: {},
      trace: { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' },
      position: null, activity: [], guidance: [], revision: 0, error: null,
    } },
    evidence: [], frictions: [], memories: [], plan: null, concurrences: {}, objections: [], events: [],
    round: 1, busy: false, error: null, created_at: '2026-09-16', closed_at: null,
  };
}
function markupFor(role: Role) {
  const meeting = presentMeeting(meetingFor(role))!;
  return renderToStaticMarkup(<ConversionClinical role={role} meeting={meeting} inspect={() => {}} />);
}
const renderedValue = (value: unknown) => renderToStaticMarkup(<RecordValue value={value} />);

describe('complete packaged CRC case presentation', () => {
  it('keeps the full structured dossier in accessible sections, without mutating the source or dropping scanner models', () => {
    const original = JSON.stringify(casePack);
    const markup = renderToStaticMarkup(<CompleteCaseRecord data={casePack} />);
    expect(Object.keys(dossier).length).toBeGreaterThan(20);
    for (const [section, value] of Object.entries(dossier)) {
      expect(markup).toContain(`data-testid="record-section-${section}"`);
      expect(markup).toContain(renderedValue(value));
    }
    expect(markup).toContain('<summary>Baseline Laboratory Results</summary>');
    expect(markup).toContain('MAGNETOM Vida');
    expect(markup).toContain('SOMATOM Force');
    expect(markup).toContain('Study instance UID');
    expect(markup).toContain('Case overview and source narrative');
    expect(markup).not.toMatch(/synthetic|syntetic|SYN-|<pre|turn\d+(?:search|view)/i);
    expect(JSON.stringify(casePack)).toBe(original);
  });
  it('retains clinical acronyms, assay units and hierarchy', () => {
    expect(recordLabel('CEA_ug_L')).toBe('CEA (µg/L)');
    expect(recordLabel('ANC_x10e9_L')).toBe('ANC (×10⁹/L)');
    expect(recordLabel('magnesium_mmol_L')).toBe('Magnesium (mmol/L)');
    expect(recordLabel('BRAF_V600E_VAF_percent')).toBe('BRAF V600E VAF (%)');
    expect(recordLabel('weight_kg_at_diagnosis')).toBe('Weight at diagnosis (kg)');
    expect(renderedValue(dossier.baseline_laboratory_results)).toContain('<dt');
    expect(renderedValue(dossier.baseline_laboratory_results)).toContain('Hematology');
    expect(renderedValue(dossier.molecular_profile)).toContain('c.1799T&gt;A');
  });
  it('creates a report field grid for each supplied specimen without assuming additional biopsies', () => {
    const markup = markupFor('pathology').split('Complete source clinical dossier')[0];
    const specimens = Object.entries(dossier.pathology);
    expect(markup.match(/data-testid="pathology-specimen-/g)).toHaveLength(specimens.length);
    for (const [specimen, value] of specimens) {
      expect(markup).toContain(`data-testid="pathology-specimen-${specimen}"`);
      expect(markup).toContain(recordLabel(specimen));
      expect(markup).toContain(renderedValue(value));
    }
  });
  it('shows every May–September date and preserves the two different post-cycle-4 marker dates', () => {
    const markup = renderToStaticMarkup(<CaseTimeline data={casePack} />);
    expect(markup).toContain('2026-05-04');
    for (const event of dossier.diagnostic_timeline) expect(markup).toContain(`dateTime="${event.date}"`);
    expect(markup).toContain('216 → 82 → 31.6');
    expect(markup).toContain('11.8 → 0.42');
    expect(markup).toContain('2026-06-23');
    expect(markup).toContain('2026-09-01');
    expect(markup).toContain('2026-09-09');
    expect(markup).toContain('Both source dates are retained, not reconciled');
    expect(markup).toContain('Persistent detectable ctDNA');
  });
  it('uses all nine source MRI lesion dimensions and never reuses lung-growth artwork for CRC', () => {
    const markup = markupFor('radiology');
    const table = markup.split('data-testid="liver-lesion-table"')[1]?.split('</table>')[0];
    expect(table).toBeDefined();
    expect(table?.match(/scope="row"/g)).toHaveLength(9);
    for (const lesion of dossier.imaging.baseline_liver_MRI.metastatic_lesions) {
      expect(table).toContain(`>S${lesion.segment}</th>`);
      expect(table).toContain(lesion.size_mm);
      expect(table).toContain((dossier.response_assessment.liver_MRI.measurements as Data)[`S${lesion.segment}_mm`]);
    }
    expect(markup).toContain('illustrative liver segment map');
    expect(markup).toContain('NOT CLINICAL IMAGING');
    expect(markup).toContain('3 mm from IVC');
    expect(markup).toContain('2 mm from the middle hepatic vein');
    expect(markup).toContain('PET cannot reliably classify');
    expect(markup).not.toMatch(/axial chest|14\/17\/23|growth kinetics/i);
  });
  it('renders all three alternatives with their actual sequence, advantages, disadvantages and evidence caveats', () => {
    const markup = renderToStaticMarkup(<ManagementOptions data={casePack} />);
    expect(casePack.management_alternatives).toHaveLength(3);
    for (const [index, alternative] of casePack.management_alternatives.entries()) {
      expect(markup).toContain(`data-testid="management-option-${index + 1}"`);
      for (const value of Object.values(alternative)) expect(markup).toContain(renderedValue(value));
    }
    expect(markup).toContain('HUMAN DECISION REQUIRED');
    expect(markup).toContain('not independently verified');
    expect(markup).not.toMatch(/href=|https?:|turn\d/);
  });
  it('uses management_alternatives as the only case field while retaining the management-options selector', () => {
    expect(casePack).not.toHaveProperty('management_options');
    const markup = renderToStaticMarkup(<ManagementOptions data={{ management_options: casePack.management_alternatives }} />);
    expect(markup).toContain('data-testid="management-options"');
    expect(markup).not.toContain('data-testid="management-option-1"');
    expect(markup).toContain('management alternatives have not been supplied');
  });
  it('grounds all seven specialty presentations in the full source narrative, not a shortened lung fixture', () => {
    const source = readFileSync(new URL('../../case.md', import.meta.url), 'utf8');
    const expected: Partial<Record<Role, string[]>> = {
      oncology: ['300 mg PO once daily', '500 mg/m2 IV every 14 days', '85 mg/m2 IV every 14 days', '2026-08-17', 'CTCAE grade 2'],
      surgery: ['Hepatobiliary surgery', 'Colorectal surgery', 'Interventional radiology', 'Radiation oncology', 'liver-first; delayed right hemicolectomy', '>65'],
      pathology: ['c.1799T>A', 'p.Val600Glu', '41.2', '28.7', '18.4', 'MLH1', 'UGT1A1', '*1/*28'],
      research: ['BREAKWATER', 'CAIRO5', 'PROVENC3'],
      patient: ['preserve independence and avoid permanent stoma', 'lives with partner; two adult children', 'Palliative/supportive care'],
    };
    for (const [role, terms] of Object.entries(expected)) {
      const markup = markupFor(role as Role).split('Complete source clinical dossier')[0];
      for (const term of terms) {
        expect(source, `Source contains ${term}`).toContain(term);
        const escaped = term.replaceAll('&', '&amp;').replaceAll('>', '&gt;').replaceAll('<', '&lt;');
        expect(markup, `${role} clinical panel contains ${term}`).toContain(escaped);
      }
    }
    expect(markupFor('surgery')).toContain('no site-specific treatment to S5, S2 or S4b');
    expect(markupFor('research')).toContain('not the same setting as conversion-stage IV disease');
    expect(markupFor('protocol')).toContain('not verified guidelines');
    expect(markupFor('protocol')).toContain('data-testid="management-option-3"');
  });
  it.each(ROLES)('retains the %s workspace contract, complete record access and human controls', role => {
    const raw = meetingFor(role);
    const original = JSON.stringify(raw);
    const meeting = presentMeeting(raw)!;
    const markup = renderToStaticMarkup(<Specialist role={role} meeting={meeting} pending={false} guidance="" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
    expect(markup).toContain(`data-testid="workspace-${role}"`);
    expect(markup).toContain(`data-testid="clinical-${role}"`);
    expect(markup).toContain('data-testid="complete-case-record"');
    expect(markup).toContain('data-testid="guidance-input"');
    expect(markup).toContain('data-testid="send-guidance"');
    if (role === 'radiology') expect(markup).toContain('placeholder="Review all nine liver sites, vessel margins and the indeterminate lung nodule before clearance planning."');
    expect(markup).toContain('Saved review preferences');
    expect(markup).not.toMatch(/synthetic|syntetic|SYN-/i);
    expect(JSON.stringify(raw)).toBe(original);
  });
  it('does not inject CRC measurements or options into persisted older meetings', () => {
    const raw = meetingFor('radiology');
    raw.case = { id: 'CASE-NSCLC-OLD', diagnosis: 'NSCLC', history: 'Prior melanoma' };
    raw.roles.radiology!.context = { measurements: [{ label: 'Current', diameter_mm: 23, weeks_ago: 0 }] };
    expect(isConversionCase(raw.case)).toBe(false);
    expect(renderToStaticMarkup(<CaseTimeline data={raw.case} />)).toBe('');
    const markup = renderToStaticMarkup(<Specialist role="radiology" meeting={raw} pending={false} guidance="" setGuidance={() => {}} steer={async () => {}} mutate={async () => true} inspect={() => {}} />);
    expect(markup).toContain('Longitudinal imaging review');
    expect(markup).not.toMatch(/BRAF|liver-segment-map|mFOLFOX6|CAIRO5/);
    expect(recordText('SYN-NSCLC-OLD')).toBe('CASE-NSCLC-OLD');
  });
});
