import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ConsensusPanel } from './App';
import { ROLES } from './types';
import type { Meeting, Role, RoleState } from './types';

function roleState(role: Role, stance: string, revision: number): RoleState {
  return {
    role, label: role, status: 'READY', context: {},
    trace: { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' },
    position: {
      position: `${role} position`, recommendation: 'Recorded recommendation', stance,
      autonomy: 'ASSIST', human_intervention: false, claims: [], provenance: [], questions_for_mdt: [],
    },
    activity: [], guidance: [], revision, error: null,
  } as unknown as RoleState;
}
function meetingWith(overrides: Partial<Meeting> = {}): Meeting {
  const roles: Meeting['roles'] = {};
  ROLES.forEach((role, index) => { roles[role] = roleState(role, index === 6 ? 'UNCERTAIN' : index < 4 ? 'SUPPORT' : 'CONDITIONAL', index < 2 ? 2 : 1); });
  return {
    id: 'consensus-test', phase: 'POSITION_UPDATE', mode: 'rehearsal', case: {}, roles,
    evidence: [], frictions: [{ id: 'f1', question: 'Open question', roles: ['radiology'], resolved: false } as never,
      { id: 'f2', question: 'Settled question', roles: ['surgery'], resolved: true } as never],
    memories: [], plan: null, concurrences: {}, objections: [], events: [],
    round: 2, busy: false, error: null, created_at: '2026-09-17', closed_at: null,
    ...overrides,
  } as Meeting;
}

describe('consensus panel', () => {
  it('shows how many specialties align, how many revised, and which questions remain', () => {
    const markup = renderToStaticMarkup(<ConsensusPanel meeting={meetingWith()} openRole={() => {}} />);
    expect(markup).toContain('data-testid="consensus-panel"');
    expect(markup).toContain('1 question still separate');
    expect(markup).toContain('1 of 2 questions resolved');
    expect(markup).toMatch(/data-testid="consensus-support">6</);
    expect(markup).toMatch(/data-testid="consensus-revised">2</);
    expect(markup).toContain('Revised after discussion');
    for (const role of ROLES) expect(markup).toContain(`data-testid="consensus-${role}"`);
  });

  it('marks agent auto-concurrence as not human sign-off', () => {
    const meeting = meetingWith({
      phase: 'CONCURRENCE',
      plan: { version: 1, summary: 'Proposed plan', conditions: [], claims: [] } as never,
      concurrences: { radiology: { actor: 'human', plan_version: 1, comment: '' }, surgery: { actor: 'agent', plan_version: 1, comment: '' } } as never,
    });
    meeting.roles.surgery!.position!.autonomy = 'AUTO';
    const markup = renderToStaticMarkup(<ConsensusPanel meeting={meeting} openRole={() => {}} />);
    expect(markup).toContain('Clinician concurrence recorded');
    expect(markup).toContain('not human sign-off');
    expect(markup).toMatch(/data-testid="consensus-signed">2</);
  });

  it('does not claim a decision before one is captured', () => {
    const markup = renderToStaticMarkup(<ConsensusPanel meeting={meetingWith()} openRole={() => {}} />);
    expect(markup).not.toContain('Decision recorded');
    const closed = renderToStaticMarkup(<ConsensusPanel meeting={meetingWith({ phase: 'DECISION_CAPTURED', frictions: [] })} openRole={() => {}} />);
    expect(closed).toContain('Decision recorded');
    expect(closed).toContain('The team reached a recorded decision');
  });
});
