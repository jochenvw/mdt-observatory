import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RoleStandby } from './App';
import { CaseSelection } from './CaseSelection';
import { ROLE_LAYOUTS } from './roleLayouts';
import { acceptSnapshot } from './helpers';
import { ROLES } from './types';
import type { Meeting } from './types';

function meetingOf(id: string, lastEventId: number): Meeting {
  return {
    id, phase: 'INITIAL_ANALYSIS', mode: 'rehearsal', case: { id: `${id}-case` },
    roles: {}, evidence: [], frictions: [], memories: [], plan: null, concurrences: {},
    objections: [], events: [{ id: lastEventId, meeting_id: id, timestamp: '2026-09-17T10:00:00', type: 'PhaseChanged', role: null, payload: {} }],
    round: 1, busy: false, error: null, created_at: '2026-09-17', closed_at: null,
  } as unknown as Meeting;
}

describe('a specialty screen opened before any case is activated', () => {
  it('stands by with its own specialty identity and no patient content', () => {
    for (const role of ROLES) {
      const markup = renderToStaticMarkup(<RoleStandby role={role} mode="rehearsal" />);
      expect(markup).toContain(`data-testid="standby-${role}"`);
      expect(markup).toContain(ROLE_LAYOUTS[role].title);
      expect(markup).toContain('Waiting for the chair to open a case');
      expect(markup).toContain('No patient record is loaded');
      expect(markup).toContain('data-testid="demo-explainer"');
      for (const focus of ROLE_LAYOUTS[role].focus) expect(markup).toContain(focus);
    }
  });

  it('keeps each specialty visually distinct while it waits', () => {
    const shells = ROLES.map(role => renderToStaticMarkup(<RoleStandby role={role} mode="rehearsal" />).slice(0, 400));
    expect(new Set(shells).size).toBe(ROLES.length);
  });

  it('states which meeting mode the room is running', () => {
    expect(renderToStaticMarkup(<RoleStandby role="radiology" mode="azure" />)).toContain('NO ACTIVE CASE');
  });
});

describe('the orchestrator case-selection screen', () => {
  function selection(meeting: Meeting | null, pending = false) {
    return renderToStaticMarkup(<CaseSelection cases={[]} selected="" select={() => {}} meeting={meeting} loading={false} canStart={false} mode="rehearsal" start={() => {}} resume={() => {}} clearRoom={() => {}} pending={pending} />);
  }

  it('offers a room reset whenever a case is loaded, and explains what it does', () => {
    const markup = selection(meetingOf('meeting-a', 1));
    expect(markup).toContain('data-testid="clear-room"');
    expect(markup).toContain('Clear the room');
    expect(markup).toContain('empties every open specialty screen back to standby');
    expect(markup).toContain('stays readable and exportable');
  });

  it('offers no room reset when the room is already on standby', () => {
    expect(selection(null)).not.toContain('data-testid="clear-room"');
  });

  it('refuses to reset the room while a round is still running', () => {
    const busy = meetingOf('meeting-a', 1);
    busy.busy = true;
    expect(selection(busy)).toMatch(/data-testid="clear-room"[^>]*disabled/);
    expect(selection(meetingOf('meeting-a', 1), true)).toMatch(/data-testid="clear-room"[^>]*disabled/);
  });
});

describe('a screen receiving room updates', () => {
  it('replaces the whole screen when the orchestrator opens a different case', () => {
    const previous = meetingOf('meeting-a', 400);
    const next = meetingOf('meeting-b', 1);
    expect(acceptSnapshot(previous, next).id).toBe('meeting-b');
  });

  it('ignores an out-of-order update for the case already on screen', () => {
    const current = meetingOf('meeting-a', 400);
    expect(acceptSnapshot(current, meetingOf('meeting-a', 399))).toBe(current);
  });

  it('accepts newer activity for the case already on screen', () => {
    const current = meetingOf('meeting-a', 400);
    expect(acceptSnapshot(current, meetingOf('meeting-a', 401)).events.at(-1)?.id).toBe(401);
  });
});
