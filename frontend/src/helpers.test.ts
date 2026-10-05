import { describe, expect, it } from 'vitest';
import { acceptSnapshot, activitySummary, concurrenceActor, errorMessage, first, humanConcurred, imagingSeries, label, safeUrl, text, time } from './helpers';
import type { Meeting, Position } from './types';

function meeting(id = 'case-1', eventId = 1): Meeting {
  return {
    id, phase: 'CONCURRENCE', mode: 'rehearsal', case: {}, roles: {}, evidence: [],
    frictions: [], memories: [], plan: { version: 2, direction: 'INVESTIGATE_FURTHER', title: 'Plan', decision: 'Investigate further.', summary: 'Review', actions: [], conditions: [], resolved_requirements: [], evidence_ids: [], created_at: '2026-09-16' },
    concurrences: {}, objections: [],
    events: [{ id: eventId, meeting_id: id, type: 'PlanProposed', role: null, payload: {}, timestamp: '2026-09-16' }],
    round: 2, busy: false, error: null, created_at: '2026-09-16', closed_at: null,
  };
}

describe('safe source links', () => {
  it.each(['javascript:alert(1)', 'data:text/html,danger', 'http://example.com', '//example.com', '/relative', 'https://user:secret@example.com', 'not a link'])('rejects %s', value => {
    expect(safeUrl(value)).toBeNull();
  });
  it('permits credential-free HTTPS', () => {
    expect(safeUrl('https://example.com/paper?q=test')).toBe('https://example.com/paper?q=test');
  });
});
describe('arbitrary contract context', () => {
  it('preserves clinical biomarker acronyms in nested field labels', () => {
    expect(label('PD-L1 TPS')).toBe('PD-L1 TPS');
    expect(label('pd_l1_tps')).toBe('PD-L1 TPS');
    expect(label('EGFR')).toBe('EGFR');
    expect(label('alk')).toBe('ALK');
    expect(text({ 'PD-L1 TPS': '60%', EGFR: 'no sensitizing variant', ALK: 'negative' })).toBe('PD-L1 TPS: 60% · EGFR: no sensitizing variant · ALK: negative');
  });
  it('labels keys and renders nested data without losing false or zero', () => {
    expect(label('performance_status')).toBe('Performance Status');
    expect(label('currentScan')).toBe('Current Scan');
    expect(label('PUBLIC_ABSTRACT_ONLY')).toBe('Public Abstract Only');
    expect(text({ previous_treatment: ['A', 'B'], progression: false, count: 0 })).toBe('Previous Treatment: A · B · Progression: No · Count: 0');
    expect(first({ empty: '', zero: 0 }, ['empty', 'zero'], 'missing')).toBe('0');
    expect(text(null)).toBe('Not provided');
  });
  it('handles activity objects and validation errors', () => {
    expect(activitySummary({ type: 'ToolResult', summary: 'Compared imaging', tool: 'compare_imaging' })).toBe('Compared imaging');
    expect(activitySummary({ tool: 'compare_imaging' })).toBe('Compare current and prior lesion measurements, growth and measurement limitations.');
    expect(errorMessage({ detail: [{ msg: 'Required', loc: ['body', 'role'] }] }, 422)).toContain('Required');
    expect(errorMessage(null, 500)).toContain('500');
    expect(time('unavailable')).toBe('unavailable');
  });
});
describe('live snapshot ordering', () => {
  it('rejects a stale mutation response after a newer SSE update', () => {
    const current = meeting('case-1', 8);
    expect(acceptSnapshot(current, meeting('case-1', 7))).toBe(current);
  });
  it('accepts a new meeting, equal-event updates and initial snapshots', () => {
    const next = meeting('case-2', 1);
    expect(acceptSnapshot(meeting('case-1', 8), next)).toBe(next);
    expect(acceptSnapshot(null, next)).toBe(next);
    expect(acceptSnapshot(meeting('case-2', 1), next)).toBe(next);
  });
});
describe('human concurrence is version-specific', () => {
  it('never counts agent support as human concurrence', () => {
    const value = meeting();
    value.concurrences.radiology = { role: 'radiology', actor: 'agent', plan_version: 2, comment: '', timestamp: '2026-09-16' };
    expect(humanConcurred(value, 'radiology')).toBe(false);
    value.concurrences.radiology.actor = 'human';
    expect(humanConcurred(value, 'radiology')).toBe(true);
    value.concurrences.radiology.plan_version = 1;
    expect(humanConcurred(value, 'radiology')).toBe(false);
    value.plan = null;
    expect(humanConcurred(value, 'radiology')).toBe(false);
  });
  describe('case imaging measurements', () => {
    it('uses actual valid measurements in chronological order without mutating input', () => {
      const imaging = [
        { label: 'Current', diameter_mm: 23, weeks_ago: 0 },
        { label: 'Baseline', diameter_mm: 14, weeks_ago: 26 },
        { label: 'Previous', diameter_mm: 17, weeks_ago: 11 },
        { label: 'Invalid', diameter_mm: -1, weeks_ago: 5 },
      ];
      expect(imagingSeries({ imaging }).map(item => item.diameter_mm)).toEqual([14, 17, 23]);
      expect(imagingSeries({ measurements: imaging }).map(item => item.diameter_mm)).toEqual([14, 17, 23]);
      expect(imaging[0].label).toBe('Current');
    });
    describe('policy-authorized agent concurrence', () => {
      function withPathology(autonomy: Position['autonomy']): Meeting {
        const value = meeting();
        const trace = { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' };
        value.roles.pathology = {
          role: 'pathology', label: 'Pathology', status: 'PUBLISHED', context: {}, trace,
          activity: [], guidance: [], revision: 1, error: null,
          position: {
            role: 'pathology', case_id: value.id, position: 'Confirmed tissue findings', confidence: .8,
            autonomy, claims: [], uncertainties: [], recommendation: 'Conditional plan',
            questions_for_mdt: [], human_intervention: false, provenance: [], stance: 'SUPPORT',
            friction_keys: [], trace,
          },
        };
        value.concurrences.pathology = {
          role: 'pathology', actor: 'agent', plan_version: 2, comment: 'Demo policy', timestamp: '2026-09-16',
        };
        return value;
      }
      it('counts current-version AUTO approval as agent concurrence, never human', () => {
        const value = withPathology('AUTO');
        expect(concurrenceActor(value, 'pathology')).toBe('agent');
        expect(humanConcurred(value, 'pathology')).toBe(false);
      });
      it.each(['REVIEW', 'ESCALATE'] as const)('does not authorize agent approval for %s', autonomy => {
        const value = withPathology(autonomy);
        expect(concurrenceActor(value, 'pathology')).toBeNull();
        expect(humanConcurred(value, 'pathology')).toBe(false);
      });
      it('requires the current plan version even for AUTO', () => {
        const value = withPathology('AUTO');
        value.plan!.version = 3;
        expect(concurrenceActor(value, 'pathology')).toBeNull();
      });
      it('keeps explicit human approval distinguishable from AUTO policy', () => {
        const value = withPathology('AUTO');
        value.concurrences.pathology!.actor = 'human';
        expect(concurrenceActor(value, 'pathology')).toBe('human');
        expect(humanConcurred(value, 'pathology')).toBe(true);
      });
    });
    it('never invents measurements from absent or malformed data', () => {
      expect(imagingSeries({})).toEqual([]);
      expect(imagingSeries({ imaging: [null, {}, { label: 'Missing timing', diameter_mm: 23 }, { label: 'Invalid', diameter_mm: Infinity, weeks_ago: 0 }] })).toEqual([]);
    });
  });
});
