import { describe, expect, it } from 'vitest';
import { clinicalActivity, clinicalData, clinicalError, clinicalItems, clinicalText, isTechnical, recordData, ROLE_FOCUS, statusLabel } from './presentation';

describe('clinical activity presentation', () => {
  it('normalizes legacy display copy and identifiers without rewriting records or losing source acquisition data', () => {
    const raw = {
      case_id: 'SYN-OLD-001',
      dossier: { synthetic: true, imaging: { technique: { model: 'MAGNETOM Vida', slice_thickness_mm: 3 } }, assay: 'Syntetic assay' },
      provider: 'Do not display',
    };
    const original = JSON.stringify(raw);
    const presented = clinicalData(raw);
    expect(presented.case_id).toBe('CASE-OLD-001');
    expect(presented.dossier).toEqual({ demonstration: true, imaging: { technique: { model: 'MAGNETOM Vida', slice_thickness_mm: 3 } }, assay: 'demonstration assay' });
    expect(presented).not.toHaveProperty('provider');
    expect(JSON.stringify(presented)).not.toMatch(/synthetic|syntetic|SYN-/i);
    expect(recordData({ synthetic_assay: 'SYN-PATH' })).toEqual({ demonstration_assay: 'CASE-PATH' });
    expect(clinicalError('Synthetic case tissue review failed.')).not.toMatch(/synthetic/i);
    expect(JSON.stringify(raw)).toBe(original);
  });
  it('translates the local-pathway tag in context, observations, uncertainty and activity without losing the caveat', () => {
    const raw = 'PROTOCOL_NOT_PUBLIC: the fictional hospital pathway is not supplied. Do not infer approval.';
    const expected = 'Local pathway unavailable: the fictional hospital pathway is not supplied. Do not infer approval.';
    expect(clinicalText('PROTOCOL_NOT_PUBLIC')).toBe('Local pathway unavailable');
    expect(clinicalText(raw)).toBe(expected);
    expect(clinicalItems([raw])).toEqual([expected]);
    expect(clinicalData({ institutional_protocol: raw })).toEqual({ institutional_protocol: expected });
    expect(clinicalActivity({ type: 'ObservationAdded', summary: raw }, 'protocol').summary).toBe(expected);
    expect(clinicalActivity({ type: 'UncertaintyRaised', summary: raw }, 'protocol').summary).toBe(expected);
  });
  it('preserves actual clinical observations without inventing results', () => {
    expect(clinicalActivity({ type: 'ObservationAdded', summary: 'The inferior margin remains ambiguous.' }, 'radiology')).toEqual({
      title: 'Clinical observation', summary: 'The inferior margin remains ambiguous.', failure: false,
    });
  });
  it('translates tool identifiers into the clinical task being reviewed', () => {
    const entry = clinicalActivity({ type: 'ToolStarted', tool: 'compare_imaging', summary: 'tool compare_imaging request_id=req_12' }, 'radiology');
    expect(entry.summary).toContain('Compare current and prior lesion measurements');
    expect(entry.summary).not.toMatch(/request_id|compare_imaging|req_12/);
    expect(clinicalActivity({ type: 'ToolCompleted', tool: 'get_pathology_context', summary: 'Inspected role-scoped context' }, 'pathology').summary).toContain('tissue provenance');
  });
  it('replaces actual provider-call proof with role-specific review context', () => {
    const entry = clinicalActivity({ type: 'ObservationAdded', deployment: 'private-deployment', model_request_id: 'req_1', token_usage: { total_tokens: 888 }, summary: 'ACTUAL AZURE CALL req_1 888 tokens' }, 'pathology');
    expect(entry.title).toBe('Specialist assessment');
    expect(entry.summary).toBe(ROLE_FOCUS.pathology);
    expect(JSON.stringify(entry)).not.toMatch(/AZURE|req_1|888|deployment|tokens/);
  });
  it('does not echo unknown events or arbitrary JSON', () => {
    const entry = clinicalActivity({ type: 'ProviderTransportCacheReady', summary: '{"request_id":"req_1"}', endpoint: 'secret' });
    expect(entry.title).toBe('Team update');
    expect(entry.summary).not.toContain('req_1');
    expect(clinicalActivity({ type: 'FutureUnrecognizedEvent', summary: 'Internal opaque detail' })).toEqual({
      title: 'Team update', summary: 'A team update was recorded. No additional clinical detail was provided.', failure: false,
    });
  });
  it('surfaces failed reviews with actionable wording, not provider errors', () => {
    const entry = clinicalActivity({ type: 'RoleFailed', error: 'OpenAI RateLimitError request_id=req_2 HTTP 429 quota exhausted', status_code: 429 }, 'research');
    expect(entry.failure).toBe(true);
    expect(entry.summary).toContain('No new conclusion has been recorded');
    expect(entry.summary).not.toMatch(/OpenAI|HTTP|429|req_2|quota/);
    expect(clinicalError('Traceback Azure exception')).toContain('could not be completed');
    expect(clinicalError('opaque', 409)).toContain('plan has changed');
    expect(clinicalError('opaque', 422)).toContain('required review information');
    expect(clinicalError('Unexpected EOF')).not.toContain('EOF');
    expect(clinicalError('Tissue sample is unavailable for this review.')).toBe('Tissue sample is unavailable for this review.');
  });
  it('preserves the start-new-case recovery action for rejected historical-case mutations', () => {
    const message = 'This meeting belongs to a different case. Start a new case to use the current dossier.';
    const presented = clinicalError(message, 409);
    expect(presented).toContain('Start a new case');
    expect(presented).toContain('existing record remains available for review and export');
    expect(presented).not.toMatch(/plan has changed|provider|retry/i);
    expect(clinicalError(message)).toBe(presented);
    expect(clinicalError('The team is busy.', 409)).toContain('plan has changed');
  });
  it('keeps clinical uncertainty, tissue names and biomarker facts intact', () => {
    expect(clinicalText('NSCLC')).toBe('NSCLC');
    expect(clinicalText('EGFR negative; tissue confirmation remains necessary.')).toContain('EGFR negative');
    expect(clinicalItems(['Inferior inflammatory margin remains uncertain.', 'ACTUAL AZURE CALL model=x request_id=req_1', 'OpenAI timeout error'])).toEqual([
      'Inferior inflammatory margin remains uncertain.',
      clinicalError('OpenAI timeout error'),
    ]);
  });
  it('removes transport-only fields from presentation copies, never the source object', () => {
    const raw = { diagnosis: 'NSCLC', model_request_id: 'req_4', token_usage: { total_tokens: 987 }, nested: { marker: 'ALK', deployment: 'private' } };
    expect(clinicalData(raw)).toEqual({ diagnosis: 'NSCLC', nested: { marker: 'ALK' } });
    expect(raw.model_request_id).toBe('req_4');
    expect(raw.token_usage.total_tokens).toBe(987);
  });
  it('uses explicit process labels and a safe unknown-status fallback', () => {
    expect(statusLabel('TARGETED_DISCUSSION')).toBe('Focused clinical discussion');
    expect(statusLabel('AZURE_REQUEST_FAILED')).toBe('Review needs attention');
  });
  it.each(['APITimeoutError', 'APIConnectionError', 'APIStatusError', 'HTTPStatusError', 'TimeoutError'])('recognizes acronym-led %s without hiding the failure', name => {
    const raw = `Specialist analysis failed: ${name}; no rehearsal fallback.`;
    expect(isTechnical(raw)).toBe(true);
    const safe = clinicalError(raw);
    expect(safe).not.toMatch(/API|HTTP|Error|fallback/);
    expect(clinicalText(raw, 'Waiting for review.')).toBe(safe);
    expect(clinicalItems([raw])).toEqual([safe]);
    expect(clinicalData({ next_action: raw }).next_action).toBe(safe);
    expect(clinicalActivity({ type: 'UncertaintyRaised', summary: raw, error: true })).toMatchObject({
      failure: true, summary: safe,
    });
    expect(clinicalError(safe)).toBe(safe);
  });
  it('keeps timeout, capacity and generic failures distinct when presented repeatedly', () => {
    expect(clinicalError('APITimeoutError')).toContain('did not respond in time');
    const capacity = clinicalError('RateLimitError', 429);
    expect(clinicalError(capacity)).toBe(capacity);
    expect(clinicalError('AgentRuntimeError: analysis failed. Check model configuration, permissions, quota and server diagnostics, then retry.')).not.toContain('service is busy');
    expect(clinicalActivity({
      type: 'ReviewRetryScheduled', error_type: 'APITimeoutError',
      summary: 'Another review attempt is scheduled. No new conclusion has been recorded.',
    })).toMatchObject({ title: 'Review taking longer', failure: true });
  });

  it('narrates process events in clinical language instead of generic filler', () => {
    const generic = 'A team update was recorded. No additional clinical detail was provided.';
    const cases: Record<string, unknown>[] = [
      { type: 'PhaseChanged', phase: 'TARGETED_DISCUSSION' },
      { type: 'HumanGuidanceReceived', summary: 'Confirm the resection margin assumption.' },
      { type: 'EvidenceRequested', roles: ['radiology', 'surgery'] },
      { type: 'MemoryAction', memory_id: 'm1', action: 'use' },
      { type: 'ConcurrenceInvalidated' },
      { type: 'AnalysisRetried' },
      { type: 'AnalysisInterrupted' },
      { type: 'RoleAnalysisStarted', round: 2 },
      { type: 'PositionUpdated', revision: 3 },
      { type: 'ConcurrenceGiven', actor: 'human' },
    ];
    for (const payload of cases) {
      const entry = clinicalActivity(payload, 'radiology');
      expect(entry.title, String(payload.type)).not.toBe('Team update');
      expect(entry.summary, String(payload.type)).not.toBe(generic);
      expect(isTechnical(entry.summary), String(payload.type)).toBe(false);
    }
  });

  it('names the meeting stage a phase change moves into', () => {
    const entry = clinicalActivity({ type: 'PhaseChanged', phase: 'CONCURRENCE' });
    expect(entry.summary.toLowerCase()).toContain('review');
  });

  it('reports clearing the room as closing the meeting, not as losing the record', () => {
    const entry = clinicalActivity({ type: 'RoomCleared', summary: 'The meeting was closed on the shared screens. The record stays available for review and export.' });
    expect(entry.title.toLowerCase()).toContain('closed');
    expect(entry.summary).toContain('review and export');
    expect(isTechnical(entry.summary)).toBe(false);
  });
});
