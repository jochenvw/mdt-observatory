import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, request, requestEmpty } from './api';
import { acceptSnapshot } from './helpers';
import type { CaseSummary, Config, Meeting, Mode, VoiceContributionAccepted, VoiceContributionInput } from './types';
import { clinicalError } from './presentation';

export function useMeeting() {
  const [config, setConfig] = useState<Config | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [connection, setConnection] = useState<'connecting' | 'online' | 'reconnecting' | 'offline'>('connecting');
  const [generation, setGeneration] = useState(0);
  const operation = useRef(false);

  const report = useCallback((cause: unknown) => {
    if (cause instanceof ApiError && cause.status === 401) setNeedsAuth(true);
    setError(clinicalError(cause, cause instanceof ApiError ? cause.status : undefined));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      try {
        const settings = await request<Config>('/config', undefined, controller.signal);
        setConfig(settings);
        const [current, available] = await Promise.all([
          request<Meeting | null>('/meeting', undefined, controller.signal),
          request<CaseSummary[]>('/cases', undefined, controller.signal),
        ]);
        if (!controller.signal.aborted) {
          setCases(available);
          setMeeting(previous => current ? acceptSnapshot(previous, current) : null);
          setConnection('online');
        }
      } catch (cause) {
        if (!controller.signal.aborted) { report(cause); setConnection('offline'); }
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, [generation, report]);

  const meetingId = meeting?.id;
  // One room channel per screen, live from load: a screen opened before any case
  // is activated, and a screen still showing the previous case, both follow the
  // orchestrator without a manual reload.
  useEffect(() => {
    if (needsAuth) return;
    let active = true;
    const stream = new EventSource('/api/room/stream', { withCredentials: true });
    setConnection('connecting');
    stream.onopen = () => { if (active) setConnection('online'); };
    stream.addEventListener('room', event => {
      if (!active) return;
      try {
        const room = JSON.parse((event as MessageEvent<string>).data) as { meeting: Meeting | null };
        if (!('meeting' in room)) throw new Error('Invalid room update received. Reconnect to recover.');
        const snapshot = room.meeting;
        if (snapshot && (!Array.isArray(snapshot.events) || !snapshot.roles)) throw new Error('Invalid meeting update received. Reconnect to recover.');
        setMeeting(current => snapshot ? acceptSnapshot(current, snapshot) : null);
        setConnection('online');
      } catch (cause) { report(cause); }
    });
    stream.onerror = () => {
      if (!active) return;
      setConnection('reconnecting');
      // EventSource hides HTTP status. A snapshot request makes authentication failures actionable.
      void request<Meeting | null>('/meeting').then(snapshot => {
        if (active) setMeeting(current => snapshot ? acceptSnapshot(current, snapshot) : null);
      }).catch(cause => {
        if (active && cause instanceof ApiError) report(cause);
      });
    };
    return () => { active = false; stream.close(); };
  }, [needsAuth, generation, report]);

  async function run(action: () => Promise<void>): Promise<boolean> {
    if (operation.current) return false;
    operation.current = true;
    setPending(true);
    setError(null);
    try { await action(); return true; }
    catch (cause) { report(cause); return false; }
    finally { operation.current = false; setPending(false); }
  }

  const mutate = (action: string, body: unknown) => run(async () => {
    if (!meetingId) throw new Error('Start a case before performing this action.');
    const path = `/meetings/${encodeURIComponent(meetingId)}`;
    const next = await request<Meeting>(`${path}/${action}`, body);
    setMeeting(current => current?.id === meetingId ? acceptSnapshot(current, next) : current);
    try {
      const latest = await request<Meeting>(path);
      setMeeting(current => current?.id === meetingId ? acceptSnapshot(current, latest) : current);
    } catch (cause) {
      report(cause instanceof ApiError ? cause : new Error(`Action accepted, but refreshing the meeting failed: ${cause instanceof Error ? cause.message : 'unknown connection error'}`));
    }
  });
  const start = (mode: Mode, caseId: string) => run(async () => {
    setMeeting(await request<Meeting>('/meetings', { mode, case_id: caseId }));
  });
  const clearRoom = () => run(async () => {
    await requestEmpty('/room/clear', {});
    setMeeting(null);
  });
  const submitVoiceContribution = (body: VoiceContributionInput) => run(async () => {
    if (!meetingId) throw new Error('Start a case before joining the discussion.');
    const accepted = await request<VoiceContributionAccepted>(
      `/meetings/${encodeURIComponent(meetingId)}/voice/contributions`,
      body,
    );
    setMeeting(current => current?.id === meetingId ? acceptSnapshot(current, accepted.meeting) : current);
  });
  const authenticate = (token: string) => run(async () => {
    await requestEmpty('/auth', { token });
    setNeedsAuth(false);
    setGeneration(value => value + 1);
  });
  const download = () => run(async () => {
    if (!meetingId) throw new Error('No meeting to export.');
    const response = await fetch(`/api/meetings/${encodeURIComponent(meetingId)}/export`, { credentials: 'same-origin' });
    if (!response.ok) throw new ApiError(`Export failed (${response.status}).`, response.status);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = `mdt-${meetingId.replace(/[^a-zA-Z0-9_-]/g, '')}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  return {
    config, cases, meeting, loading, pending, error, needsAuth, connection,
    mutate, start, authenticate, download, clearRoom, submitVoiceContribution,
    clearError: () => setError(null),
    dismissAuth: () => setNeedsAuth(false),
    reconnect: () => { setError(null); setGeneration(value => value + 1); },
  };
}
