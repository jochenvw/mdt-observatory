import { useMemo } from 'react';
import qrcode from 'qrcode-generator';
import { ArrowRight, Check, CircleDot, LayoutGrid, LockKeyhole, LoaderCircle, MonitorPlay, QrCode, Repeat2, UserRoundCheck } from 'lucide-react';
import { concurrenceActor, first } from './helpers';
import { PHASE_MEANING } from './presentation';
import { ROLES } from './types';
import type { Meeting, Role } from './types';
import { Badge, ROLE_META } from './ui';
import { ROLE_LAYOUTS } from './roleLayouts';

export const EVENT_NAME = 'Health Rewired Munich 2026';

/** The five moments of a tumour board, in the words a clinician would use. */
export const MEETING_STAGES = [
  { name: 'The chair opens a case', phases: ['IDLE', 'CASE_LOADING'], detail: 'The presenter on the big screen chooses a fictional patient. Every specialty screen fills automatically; nobody needs to reload.' },
  { name: 'Each assistant prepares on its own', phases: ['INITIAL_ANALYSIS', 'POSITION_COLLECTION'], detail: 'Seven AI assistants read the same record independently. Each one writes down what it considered, why, and what it concluded — step by step, on its specialty screen.' },
  { name: 'Disagreements go back to the table', phases: ['FRICTION_ANALYSIS', 'TARGETED_DISCUSSION', 'POSITION_UPDATE'], detail: 'The chair compares the positions. Only the questions where specialties genuinely disagree are sent back for a focused round, and positions may change.' },
  { name: 'A plan is proposed', phases: ['PLAN_PROPOSAL'], detail: 'The agreed positions are combined into one proposal, with the conditions that must hold before it is acted on.' },
  { name: 'People confirm or object', phases: ['CONCURRENCE', 'DECISION_CAPTURED'], detail: 'Each specialist confirms or objects for their own specialty. An objection sends the plan back for discussion. The AI never decides.' },
] as const;

export function stageIndex(phase: string): number {
  return MEETING_STAGES.findIndex(stage => (stage.phases as readonly string[]).includes(phase));
}

export function joinUrl(): string {
  return `${window.location.origin}/`;
}

/** Plain-language orientation for clinicians who have not seen reasoning agents at work. */
export function DemoExplainer({ compact = false }: { compact?: boolean }) {
  return <section data-testid="demo-explainer" aria-labelledby="explainer-title" className="card p-5 sm:p-7">
    <p className="eyebrow mb-2">WHAT YOU ARE ABOUT TO SEE</p>
    <h2 id="explainer-title" className="text-xl sm:text-2xl">A tumour board, prepared by AI assistants and decided by people</h2>
    <p className="mt-3 max-w-3xl text-sm leading-7 text-cp-text-muted">This is a simulated multidisciplinary team meeting. The patient is fictional and every record is synthetic. Each specialty at the table has an <strong className="text-cp-text">AI assistant</strong> — software that reads the case, looks up evidence and writes down its reasoning, the way a colleague would prepare for the board. You play the specialist: you watch your assistant think, answer when it asks you something, and have the final word for your specialty.</p>
    <ol className={`mt-6 grid list-none gap-3 ${compact ? 'md:grid-cols-5' : 'md:grid-cols-2 xl:grid-cols-5'}`}>
      {MEETING_STAGES.map((stage, index) => <li key={stage.name} className="rounded-xl border border-cp-border bg-cp-bg-elevated p-4">
        <span className="font-mono text-[11px] text-cp-accent">{String(index + 1).padStart(2, '0')}</span>
        <h3 className="mt-2 text-sm">{stage.name}</h3>
        {!compact && <p className="mt-2 text-xs leading-6 text-cp-text-muted">{stage.detail}</p>}
      </li>)}
    </ol>
    <div className="mt-6 grid gap-3 border-t border-cp-border pt-5 text-[13px] leading-6 md:grid-cols-3 [&>div]:flex [&>div]:gap-3 [&_svg]:mt-0.5 [&_svg]:shrink-0 [&_svg]:text-cp-accent">
      <div><CircleDot size={17} /><p><strong>Watch the reasoning.</strong> <span className="text-cp-text-muted">Each step reads “considered … because … concluded …”. Nothing is hidden and every source can be opened.</span></p></div>
      <div><UserRoundCheck size={17} /><p><strong>Answer when asked.</strong> <span className="text-cp-text-muted">If the meeting needs something only you can give, your screen turns amber and shows exactly where to type.</span></p></div>
      <div><Check size={17} /><p><strong>You decide.</strong> <span className="text-cp-text-muted">At the end you confirm or object for your specialty. The assistant proposes; it does not decide.</span></p></div>
    </div>
  </section>;
}

/** QR modules are drawn black on white in both themes so phone cameras can read them. */
export function JoinQr({ url, className = '' }: { url: string; className?: string }) {
  const { size, path } = useMemo(() => {
    const code = qrcode(0, 'M');
    code.addData(url);
    code.make();
    const count = code.getModuleCount();
    let d = '';
    for (let row = 0; row < count; row += 1) for (let col = 0; col < count; col += 1) if (code.isDark(row, col)) d += `M${col + 4} ${row + 4}h1v1h-1z`;
    return { size: count + 8, path: d };
  }, [url]);
  return <svg data-testid="join-qr" role="img" aria-label={`QR code to join the meeting at ${url}`} viewBox={`0 0 ${size} ${size}`} shapeRendering="crispEdges" className={`rounded-lg ${className}`}><rect width={size} height={size} fill="#fff" /><path d={path} fill="#000" /></svg>;
}

/** Shown on the big screen so everyone in the room, or on the call, can join from a laptop or phone. */
export function JoinCard({ url, open }: { url: string; open?: () => void }) {
  return <section data-testid="join-card" aria-label="Join this meeting" className="mb-5 flex flex-wrap items-center gap-5 rounded-2xl border border-cp-border bg-cp-surface p-4 sm:p-5">
    <JoinQr url={url} className="size-28 shrink-0" />
    <div className="min-w-0 flex-1">
      <p className="eyebrow mb-1"><QrCode size={13} className="mr-1 inline" />JOIN THIS MEETING · {EVENT_NAME.toUpperCase()}</p>
      <p className="text-sm leading-6 text-cp-text-muted">Scan or open the address on your laptop, pick your specialty and follow along. No key needed.</p>
      <p data-testid="join-url" className="mt-2 break-all font-mono text-base font-semibold text-cp-text">{url}</p>
    </div>
    {open && <button className="text-button" onClick={open}>Show full join screen <ArrowRight size={14} /></button>}
  </section>;
}

export function Join({ meeting, presenter, choose, openPresenter, openCases, url }: {
  meeting: Meeting | null; presenter: boolean; choose: (role: Role) => void; openPresenter: () => void; openCases: () => void; url: string;
}) {
  const diagnosis = meeting ? first(meeting.case, ['diagnosis', 'disease', 'summary'], 'a case') : '';
  return <div data-testid="join-screen" className="pt-2">
    <section className="grid items-start gap-8 border-b border-cp-border pb-8 pt-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <Badge tone="accent"><span className="status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success" />{EVENT_NAME.toUpperCase()} · LIVE DEMONSTRATION</Badge>
        <h1 className="mt-5 text-4xl font-medium leading-tight tracking-tight sm:text-5xl">Join the tumour board.<br /><span className="text-cp-accent">Pick the specialty you will play.</span></h1>
        <p className="mt-5 max-w-2xl text-sm leading-7 text-cp-text-muted">You are joining a simulated multidisciplinary team meeting, in the room or remotely — it works the same. The chair runs the meeting from the big screen. Your screen shows your specialty: its AI assistant's reasoning, the questions it needs you to answer, and the plan you are asked to confirm.</p>
        <p data-testid="room-status" role="status" className="mt-5 inline-flex flex-wrap items-center gap-2 rounded-xl border border-cp-border bg-cp-bg-elevated px-3 py-2 text-[13px]">
          {meeting ? <><span className="status-dot inline-block size-2 rounded-full bg-cp-success motion-safe:animate-pulse" /><strong>A case is in progress.</strong><span className="text-cp-text-muted">You will join it live: {diagnosis}.</span></>
            : <><LoaderCircle size={14} className="text-cp-text-muted motion-safe:animate-spin" /><strong>The room is on standby.</strong><span className="text-cp-text-muted">Pick a role now; your screen fills when the chair opens a case.</span></>}
        </p>
      </div>
      {presenter ? <aside aria-label="Share this meeting" className="card flex flex-col items-center gap-4 p-5 text-center">
        <p className="eyebrow">PUT THIS ON THE BIG SCREEN</p>
        <JoinQr url={url} className="w-full max-w-64" />
        <p data-testid="join-url" className="break-all font-mono text-lg font-semibold">{url}</p>
        <p className="text-xs leading-6 text-cp-text-muted">Participants scan or type the address, pick a specialty and wait. They need no key.</p>
        <button data-testid="open-case-selection" className="button primary" onClick={openCases}><LayoutGrid size={16} />Go to case selection<ArrowRight size={16} /></button>
      </aside> : <aside aria-label="Demo team" className="card p-5 text-sm leading-6">
        <p className="eyebrow mb-2"><MonitorPlay size={13} className="mr-1 inline" />RUNNING THE DEMO?</p>
        <p className="text-cp-text-muted">The chair's screen — choosing cases and running the rounds — is for the demo team on the big screen and needs the presenter key.</p>
        <button data-testid="presenter-entry" className="button secondary mt-4" onClick={openPresenter}><LockKeyhole size={15} />Open the chair's screen</button>
      </aside>}
    </section>
    <section aria-labelledby="choose-role" className="py-8">
      <p className="eyebrow mb-2">STEP 1 OF 2</p>
      <h2 id="choose-role" className="mb-5 text-2xl">Choose your role at the table</h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {ROLES.map(role => { const meta = ROLE_META[role]; const Icon = meta.icon; return <button key={role} data-testid={`join-${role}`} className={`${ROLE_LAYOUTS[role].shell} group flex min-h-32 flex-col items-start gap-2 rounded-2xl border border-cp-border bg-cp-surface p-5 text-left hover:border-[var(--cp-role)] focus-visible:border-[var(--cp-role)]`} onClick={() => choose(role)}>
          <span className="flex w-full items-center justify-between text-[var(--cp-role)]"><Icon size={24} /><ArrowRight size={16} className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" /></span>
          <strong className="text-base">{meta.person}</strong>
          <span className="text-xs leading-5 text-cp-text-muted">{meta.description}</span>
        </button>; })}
      </div>
      <p className="mt-4 text-xs leading-6 text-cp-text-muted">Several people may pick the same role; you will all see the same specialty screen. You can change role at any time.</p>
    </section>
    <p className="eyebrow mb-3">STEP 2 OF 2 · WHILE YOU WAIT</p>
    <DemoExplainer />
  </div>;
}

/** Tells a participant where they are and lets them go back to pick another role. */
export function ParticipantBar({ role, change }: { role: Role; change: () => void }) {
  const meta = ROLE_META[role];
  const Icon = meta.icon;
  return <div data-testid="participant-bar" className={`${ROLE_LAYOUTS[role].shell} flex flex-wrap items-center gap-3 text-xs`}>
    <span className="inline-flex items-center gap-2 rounded-full border border-[var(--cp-role)] px-3 py-1.5 font-semibold text-[var(--cp-role)]"><Icon size={14} />You are the {meta.person.toLowerCase()}</span>
    <button data-testid="change-role" className="text-button" onClick={change}><Repeat2 size={14} />Change role</button>
  </div>;
}

/** Where the meeting is, in plain words, on every specialty screen. */
export function MeetingStage({ meeting }: { meeting: Meeting }) {
  const active = meeting.phase === 'DECISION_CAPTURED' ? MEETING_STAGES.length : stageIndex(meeting.phase);
  const published = ROLES.filter(item => meeting.roles[item]?.position).length;
  const open = meeting.frictions.filter(item => !item.resolved).length;
  const confirmed = ROLES.filter(item => concurrenceActor(meeting, item)).length;
  const shown = Math.min(active, MEETING_STAGES.length - 1);
  const summary = shown < 0 ? `Round ${meeting.round} · Review needs attention` : `Round ${meeting.round} · Stage ${shown + 1} of ${MEETING_STAGES.length}: ${MEETING_STAGES[shown].name}`;
  return <section data-testid="meeting-stage" data-phase={meeting.phase} aria-label="Where the meeting is" className="mb-3 rounded-2xl border border-cp-border bg-cp-bg-elevated px-4 py-2 sm:py-3">
    <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-1">
      <p className="eyebrow max-sm:hidden">WHERE THE MEETING IS · ROUND {meeting.round}</p>
      <p className="min-w-0 flex-1 truncate text-[13px] font-semibold sm:hidden" title={summary}>{summary}</p>
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-cp-text-muted max-sm:hidden [&_dd]:inline [&_dd]:font-semibold [&_dd]:text-cp-text [&_dt]:inline">
        <div><dt>Positions published </dt><dd>{published}/7</dd></div>
        <div><dt>Open disagreements </dt><dd>{open}</dd></div>
        <div><dt>Specialties confirmed </dt><dd>{meeting.plan ? `${confirmed}/7` : 'after the plan'}</dd></div>
      </dl>
      {meeting.busy && <span className="inline-flex items-center gap-2 text-xs text-cp-text-muted"><LoaderCircle size={13} className="motion-safe:animate-spin" /><span className="max-sm:sr-only">Assistants are reasoning now</span></span>}
    </div>
    <ol className="mt-2 grid list-none grid-cols-5 gap-1.5 max-sm:hidden" aria-label="Meeting stages">
      {MEETING_STAGES.map((stage, index) => <li key={stage.name} aria-current={index === active ? 'step' : undefined} className={`border-t-4 pt-1.5 text-[11px] leading-4 ${index === active ? 'border-cp-accent font-semibold text-cp-text' : index < active ? 'border-cp-success text-cp-text-muted' : 'border-cp-border text-cp-text-soft'}`}>
        <span>{stage.name}</span>
      </li>)}
    </ol>
    {PHASE_MEANING[meeting.phase] && <p data-testid="stage-meaning" className="mt-1.5 text-[13px] leading-6 max-sm:hidden">{meeting.phase === 'DECISION_CAPTURED' ? 'The decision is recorded. The chair will open the next case.' : PHASE_MEANING[meeting.phase]}</p>}
  </section>;
}
