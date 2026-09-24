import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PatientBanner, Workstation, workstationLabel } from './HospitalChrome';
import { ROLES } from './types';
import type { Meeting } from './types';

function meeting(caseData: Meeting['case']): Meeting {
  return {
    id: 'hospital-test', phase: 'INITIAL_ANALYSIS', mode: 'rehearsal', case: caseData, roles: {},
    evidence: [], frictions: [], memories: [], objections: [], events: [], round: 1, busy: false, error: null,
    plan: null, concurrences: {}, created_at: '2026-09-16T10:00:00Z', closed_at: null,
  } as unknown as Meeting;
}

describe('hospital chrome', () => {
  it('labels every workspace as a hospital workstation', () => {
    for (const role of ROLES) expect(workstationLabel(role)).toMatch(/workstation$/);
    expect(workstationLabel('chair')).toBe('MDT chair');
    const markup = renderToStaticMarkup(<Workstation workspace="radiology" />);
    expect(markup).toContain('data-testid="workstation"');
    expect(markup).toContain('MDT room');
    expect(markup).toContain('Radiologist workstation');
  });

  it('shows the patient on the table from the case record, including the spoken language', () => {
    const markup = renderToStaticMarkup(<PatientBanner showCase={() => {}} meeting={meeting({
      id: 'CASE-MDT-PDAC-PERIOP-2026-003', pseudonym: 'PDAC-2026-003', patient: 'PDAC case · 72-year-old woman', age: 72,
      diagnosis: 'Pancreatic head adenocarcinoma', stage: 'ypT2; borderline', performance_status: 'ECOG 1; CFS 4', preferred_language: 'it',
    })} />);
    expect(markup).toContain('PDAC-2026-003');
    expect(markup).toContain('F · 72 y');
    expect(markup).toContain('ECOG 1');
    expect(markup).not.toContain('CFS 4');
    expect(markup).toContain('Italiano');
    expect(markup).toContain('fictional record');
  });

  it('never invents demographics that the case record does not contain', () => {
    const markup = renderToStaticMarkup(<PatientBanner showCase={() => {}} meeting={meeting({ id: 'CASE-X', pseudonym: 'CRC-2026-002', patient: 'CRC case · 58-year-old man', age: 58 })} />);
    expect(markup).toContain('M · 58 y');
    expect(markup).not.toMatch(/Diagnosis|Stage|Performance/);
    expect(markup).toContain('English');
  });
});
