import { ArrowRight, Eraser, Play } from 'lucide-react';
import type { CaseSummary, Meeting, Mode } from './types';
import { Badge } from './ui';
import { statusLabel } from './presentation';

interface Props {
  cases: CaseSummary[];
  selected: string;
  select: (id: string) => void;
  meeting: Meeting | null;
  loading: boolean;
  canStart: boolean;
  mode: Mode;
  start: () => void;
  resume: () => void;
  clearRoom: () => void;
  pending: boolean;
}

export function CaseSelection({ cases, selected, select, meeting, loading, canStart, mode, start, resume, clearRoom, pending }: Props) {
  return <section data-testid="case-selection" className="mx-auto max-w-5xl space-y-6 py-4">
    <header><p className="font-mono text-xs tracking-widest text-cp-accent">MDT CASE CATALOG</p><h1 className="mt-3 text-3xl">Select a case for multidisciplinary review</h1><p className="mt-3 text-sm leading-7 text-cp-text-muted">Review a case summary, then open its seven specialty workspaces. Starting a new meeting preserves the previous meeting's audit.</p></header>
    {meeting && <section aria-label="Current meeting" data-testid="room-control" className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-cp-accent bg-cp-accent-soft p-5"><div><h2 className="text-lg">Return to the current meeting</h2><p className="mt-2 text-sm">{statusLabel(meeting.phase)} · {meeting.mode === 'azure' ? 'Live AI review' : 'Scripted demonstration'}</p><p className="mt-1 font-mono text-xs text-cp-text-muted">{String(meeting.case.pseudonym ?? meeting.case.id ?? meeting.id)}</p><p className="mt-3 max-w-xl text-sm leading-6 text-cp-text-muted">Clearing the room empties every open specialty screen back to standby. The meeting is kept and stays readable and exportable from its record.</p></div><div className="flex flex-wrap items-center gap-3"><button data-testid="resume-meeting" className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-cp-accent bg-cp-surface px-4 py-2 text-sm text-cp-accent" onClick={resume}>Resume meeting <ArrowRight size={16} /></button><button data-testid="clear-room" className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-cp-border bg-cp-surface px-4 py-2 text-sm" disabled={pending || meeting.busy} onClick={clearRoom}><Eraser size={16} />Clear the room</button></div></section>}
    <fieldset className="space-y-4"><legend className="mb-3 text-sm font-semibold">Available cases</legend>
      {cases.map(item => <label key={item.id} className={`block cursor-pointer rounded-2xl border bg-cp-surface p-5 sm:p-6 ${selected === item.id ? 'border-cp-accent ring-1 ring-cp-accent' : 'border-cp-border'}`}>
        <div className="flex items-start gap-3"><input type="radio" name="selected-case" value={item.id} checked={selected === item.id} onChange={() => select(item.id)} className="mt-1 size-4 shrink-0 accent-cp-accent" /><div className="min-w-0"><span className="text-lg font-semibold">{item.title}</span><p className="mt-2 text-xs text-cp-text-muted">{item.patient_label} · {item.stage}</p><p className="mt-4 text-sm leading-7">{item.question}</p><div className="mt-4 flex flex-wrap gap-2"><Badge tone="success">Dossier available</Badge><Badge>Seven specialty workspaces</Badge><Badge>Human review required</Badge></div></div></div>
      </label>)}
      {!cases.length && <p role="status" className="rounded-xl border border-cp-border p-5 text-sm">{loading ? 'Loading available cases...' : 'No case catalog is available. Reconnect to refresh it before starting a meeting.'}</p>}
    </fieldset>
    <div className="flex flex-wrap items-center gap-4"><button data-testid="start-case" disabled={!canStart} onClick={start} className="inline-flex min-h-12 items-center gap-2 rounded-xl border border-cp-accent bg-cp-accent px-5 py-3 text-sm font-semibold text-cp-accent-fg"><Play size={17} />Start case</button><p className="text-sm text-cp-text-muted">{mode === 'azure' ? 'Live AI review' : 'Scripted demonstration'} · {meeting?.busy ? 'Wait for the active round before starting another meeting.' : 'The selected dossier is copied into the new meeting.'}</p></div>
  </section>;
}
