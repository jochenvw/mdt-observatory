import type { Data, Meeting, Role } from './types';
import { clinicalActivity, clinicalError, clinicalText } from './presentation';

export function label(value: string): string {
  const biomarkers: Record<string, string> = { pdl1tps: 'PD-L1 TPS', pdl1: 'PD-L1', egfr: 'EGFR', alk: 'ALK' };
  const biomarker = biomarkers[value.replace(/[^a-z0-9]/gi, '').toLowerCase()];
  if (biomarker) return biomarker;
  return value.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}
export function text(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not provided';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.map(text).join(' · ');
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${label(key)}: ${text(item)}`).join(' · ');
  return String(value);
}
export function first(data: Data, keys: string[], fallback = ''): string {
  for (const key of keys) if (data[key] !== undefined && data[key] !== null && data[key] !== '') return text(data[key]);
  return fallback;
}
export function safeUrl(raw: string): string | null {
  try {
    const url = new URL(raw);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
export function time(raw: string): string {
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}
export function humanConcurred(meeting: Meeting, role: Role): boolean {
  const concurrence = meeting.concurrences[role];
  return Boolean(meeting.plan && concurrence?.actor === 'human' && concurrence.plan_version === meeting.plan.version);
}
export function concurrenceActor(meeting: Meeting, role: Role): 'human' | 'agent' | null {
  const concurrence = meeting.concurrences[role];
  if (!meeting.plan || !concurrence || concurrence.plan_version !== meeting.plan.version) return null;
  if (concurrence.actor === 'human') return 'human';
  return meeting.roles[role]?.position?.autonomy === 'AUTO' ? 'agent' : null;
}
export function roleAttention(meeting: Meeting, role: Role): { title: string; detail: string; tone: string; running: boolean } {
  const state = meeting.roles[role];
  const cue = (title: string, detail: string, tone = '', running = false) => ({ title, detail, tone, running });
  if (state?.error || /ERROR|FAIL/i.test(state?.status ?? '')) return cue('Review failed', clinicalText(state?.error ?? '', clinicalError(state?.error)), 'danger');
  if (meeting.phase === 'DECISION_CAPTURED') return cue('Meeting finished', 'The decision and retained conditions are recorded. This meeting is read-only.', 'success');
  if (meeting.busy && /ANALYZ|SEARCH|CHECK|REASSESS|RUNNING|WORKING/i.test(state?.status ?? '')) return cue('Review running', 'The specialist is reviewing the case. Findings below update as review steps finish.', 'accent', true);
  const prior = meeting.concurrences[role];
  if (meeting.plan && prior && prior.plan_version !== meeting.plan.version) return cue('Plan changed - review again', `Previous concurrence does not cover proposal version ${meeting.plan.version}.`, 'warning');
  if (meeting.phase === 'CONCURRENCE' && meeting.plan) {
    const actor = concurrenceActor(meeting, role);
    if (actor === 'human') return cue('Human review recorded', `You concurred with proposal version ${meeting.plan.version}. An objection still reopens discussion.`, 'success');
    if (actor === 'agent') return cue('Agent support recorded', 'Demonstration policy allows this contribution. It is not human sign-off; you may still review or object.');
    return cue('Your review is needed', `Read proposal version ${meeting.plan.version} and its conditions, then concur or record an objection.`, 'warning');
  }
  const questions = meeting.frictions.filter(item => !item.resolved && item.roles.includes(role));
  if (questions.length) return cue('Question needs attention', `${questions.length} unresolved question${questions.length === 1 ? ' involves' : 's involve'} this specialty. Add guidance or ask the chair for focused review.`, 'warning');
  if (meeting.busy) return cue('Waiting for the team', 'Other specialists are still reviewing. A published position is not a final MDT decision.');
  if (state?.position) return cue(state.revision > 1 ? 'Assessment updated' : 'Review finished', `Specialist position revision ${state.revision} is available. It is not a final MDT decision.`, state.revision > 1 ? 'accent' : 'success');
  return cue('Review not started', 'The specialist assessment will appear when the case review begins.');
}
export function acceptSnapshot(current: Meeting | null, next: Meeting): Meeting {
  if (!current || current.id !== next.id) return next;
  const latest = current.events.at(-1)?.id ?? -1;
  const incoming = next.events.at(-1)?.id ?? -1;
  return incoming < latest ? current : next;
}
export function activitySummary(item: Data, role?: Role): string {
  return clinicalActivity(item, role).summary;
}
export interface ImagingMeasurement { label: string; diameter_mm: number; weeks_ago: number }
export function imagingSeries(context: Data): ImagingMeasurement[] {
  const measurements = Array.isArray(context.measurements) ? context.measurements : context.imaging;
  if (!Array.isArray(measurements)) return [];
  return measurements.filter((item: unknown): item is ImagingMeasurement => {
    if (!item || typeof item !== 'object') return false;
    return 'label' in item && typeof item.label === 'string'
      && 'diameter_mm' in item && typeof item.diameter_mm === 'number' && Number.isFinite(item.diameter_mm) && item.diameter_mm > 0
      && 'weeks_ago' in item && typeof item.weeks_ago === 'number' && Number.isFinite(item.weeks_ago) && item.weeks_ago >= 0;
  }).sort((a, b) => b.weeks_ago - a.weeks_ago);
}
export function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) return text(payload.detail);
  return `Request failed (${status}). Please try again.`;
}
