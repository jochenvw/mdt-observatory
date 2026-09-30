import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EVENT_NAME, Join, JoinCard, MeetingStage, stageIndex } from './Join';
import { PHASES, ROLES } from './types';
import type { Meeting } from './types';

function meeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: 'meeting-a', phase: 'INITIAL_ANALYSIS', mode: 'azure', case: { id: 'case-a', diagnosis: 'Metastatic colorectal cancer' },
    roles: {}, evidence: [], frictions: [], memories: [], plan: null, concurrences: {}, objections: [], events: [],
    round: 1, busy: true, error: null, created_at: '2026-09-17', closed_at: null, ...overrides,
  } as unknown as Meeting;
}
const noop = () => {};

describe('the participant join screen', () => {
  it('lets a participant pick any of the seven roles without a key', () => {
    const markup = renderToStaticMarkup(<Join meeting={null} presenter={false} url="https://mdt.example/" choose={noop} openPresenter={noop} openCases={noop} />);
    for (const role of ROLES) expect(markup).toContain(`data-testid="join-${role}"`);
    expect(markup).toContain(EVENT_NAME.toUpperCase());
    expect(markup).toContain('The room is on standby');
    expect(markup).toContain('data-testid="demo-explainer"');
    expect(markup).toContain('The AI never decides');
    // The chair's controls are offered only behind the presenter key.
    expect(markup).toContain('data-testid="presenter-entry"');
    expect(markup).not.toContain('data-testid="join-qr"');
    expect(markup).not.toContain('data-testid="open-case-selection"');
  });

  it('tells a late joiner that a case is already running', () => {
    const markup = renderToStaticMarkup(<Join meeting={meeting()} presenter={false} url="https://mdt.example/" choose={noop} openPresenter={noop} openCases={noop} />);
    expect(markup).toContain('A case is in progress');
    expect(markup).toContain('Metastatic colorectal cancer');
  });

  it('gives the big screen a scannable address and the way into case selection', () => {
    const markup = renderToStaticMarkup(<Join meeting={null} presenter url="https://mdt.example/" choose={noop} openPresenter={noop} openCases={noop} />);
    expect(markup).toContain('data-testid="join-qr"');
    expect(markup).toContain('https://mdt.example/');
    expect(markup).toContain('data-testid="open-case-selection"');
    expect(markup).not.toContain('data-testid="presenter-entry"');
    expect(renderToStaticMarkup(<JoinCard url="https://mdt.example/" />)).toContain('No key needed');
  });
});

describe('the meeting stage on a specialty screen', () => {
  it('maps every workflow phase onto one of the five plain-language stages', () => {
    for (const phase of PHASES) expect(stageIndex(phase)).toBeGreaterThanOrEqual(0);
    expect(stageIndex('INITIAL_ANALYSIS')).toBe(1);
    expect(stageIndex('TARGETED_DISCUSSION')).toBe(2);
    expect(stageIndex('CONCURRENCE')).toBe(4);
  });

  it('says what is happening now and that the assistants are reasoning', () => {
    const markup = renderToStaticMarkup(<MeetingStage meeting={meeting()} />);
    expect(markup).toContain('ROUND 1');
    expect(markup).toContain('Assistants are reasoning now');
    expect(markup).toContain('Each specialty is reviewing the same record independently');
    expect(markup).toMatch(/aria-current="step"[^>]*>[^<]*<span[^>]*>Each assistant prepares on its own/);
  });

  it('never presents a recorded decision as still open', () => {
    const markup = renderToStaticMarkup(<MeetingStage meeting={meeting({ phase: 'DECISION_CAPTURED', busy: false })} />);
    expect(markup).toContain('The decision is recorded');
    expect(markup).not.toContain('aria-current="step"');
  });

  it('keeps rendering when a review fails', () => {
    const markup = renderToStaticMarkup(<MeetingStage meeting={meeting({ phase: 'ERROR', busy: false })} />);
    expect(markup).toContain('Review needs attention');
    expect(markup).not.toContain('aria-current="step"');
  });
});
