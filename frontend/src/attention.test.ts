import { describe, expect, it } from 'vitest';
import { roleAttention } from './helpers';
import type { Meeting } from './types';

function meeting(): Meeting {
  return {
    id: 'attention', phase: 'CONCURRENCE', mode: 'rehearsal', case: {}, roles: {},
    evidence: [], frictions: [], memories: [], concurrences: {}, objections: [], events: [],
    round: 1, busy: false, error: null, created_at: '', closed_at: null,
    plan: { version: 2, title: 'Conditional proposal', summary: '', actions: [], conditions: [], evidence_ids: [], created_at: '' },
  };
}

describe('clinical attention cues', () => {
  it('requests human review and does not mistake agent support for human sign-off', () => {
    const state = meeting();
    expect(roleAttention(state, 'radiology').title).toBe('Your review is needed');
    state.concurrences.radiology = { role: 'radiology', plan_version: 2, actor: 'agent', comment: '', timestamp: '' };
    expect(roleAttention(state, 'radiology').title).toBe('Your review is needed');
    state.concurrences.radiology.actor = 'human';
    expect(roleAttention(state, 'radiology').title).toBe('Human review recorded');
    state.concurrences.radiology.plan_version = 1;
    expect(roleAttention(state, 'radiology').title).toBe('Plan changed - review again');
    expect(roleAttention(state, 'radiology').detail).toContain('version 2');
  });
  it('does not resolve open questions merely because a round has stopped', () => {
    const state = meeting();
    state.phase = 'TARGETED_DISCUSSION';
    state.frictions = [{ id: 'imaging', question: 'Review all sites', roles: ['radiology'], missing: [], blocking: true, resolved: false, resolution: null }];
    expect(roleAttention(state, 'radiology').title).toBe('Your input is needed');
    state.roles.radiology = {
      role: 'radiology', label: 'Radiology', status: 'DONE', context: {}, position: null,
      trace: { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' },
      activity: [], guidance: ['Go ahead'], revision: 2, error: null,
    };
    expect(roleAttention(state, 'radiology')).toMatchObject({ title: 'Question still open', tone: 'warning' });
    state.frictions.push({ id: 'applicability', question: 'Is the evidence applicable?', roles: ['research'], missing: [], blocking: true, resolved: false, resolution: null });
    expect(roleAttention(state, 'research').title).toBe('Waiting for the chair');
    expect(state.frictions[0].resolved).toBe(false);
    expect(roleAttention(state, 'surgery').title).toBe('Review not started');
    const answered = { ...state, frictions: [{ ...state.frictions[0], resolved: true }, state.frictions[1]] };
    expect(roleAttention(answered, 'radiology').title).toBe('Question answered');
    state.phase = 'DECISION_CAPTURED';
    expect(roleAttention(state, 'radiology').detail).toContain('read-only');
  });
  it('makes failed and running specialist reviews explicit', () => {
    const state = meeting();
    state.roles.radiology = {
      role: 'radiology', label: 'Radiology', status: 'ANALYZING', context: {}, position: null,
      trace: { assessment: '', observations: [], hypothesis: '', uncertainties: [], evidence_checking: [], next_action: '' },
      activity: [], guidance: [], revision: 0, error: null,
    };
    state.busy = true;
    expect(roleAttention(state, 'radiology')).toMatchObject({ title: 'Review running', running: true });
    state.roles.radiology.error = 'RateLimitError request_id=internal';
    expect(roleAttention(state, 'radiology')).toMatchObject({ title: 'Review failed', running: false, tone: 'danger' });
    expect(roleAttention(state, 'radiology').detail).not.toMatch(/RateLimitError|request_id/);
  });
});
