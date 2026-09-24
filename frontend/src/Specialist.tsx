import { useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowRight, ArrowUpRight, Brain, Check, ChevronDown, Clock3, Eye, Fingerprint, Focus, Heart, History, Layers, MessageSquareText, MoveUpRight, ScanLine, Send, ShieldCheck, Sparkles } from 'lucide-react';
import { first, imagingSeries, label, needsHumanReply, roleAttention, text, time } from './helpers';
import type { ImagingMeasurement } from './helpers';
import { Badge, BulletList, DataFields, Empty, EvidenceTable, Modal, roleMetaFor, SectionHeading, Status } from './ui';
import type { EvidenceSelection } from './ui';
import type { Data, Meeting, Memory, Role, RoleState } from './types';
import { clinicalActivity, clinicalData, clinicalItems, clinicalText } from './presentation';
import { ROLE_LAYOUTS } from './roleLayouts';
import { CaseClinical, ConversionClinical, isConversionCase } from './CaseDossier';
import { clinicalProfile, DEFAULT_RADIOLOGY_REPLY } from './caseProfiles';

interface Props {
  role: Role;
  meeting: Meeting;
  pending: boolean;
  guidance: string;
  setGuidance: (value: string) => void;
  steer: () => Promise<void>;
  mutate: (action: string, body: unknown) => Promise<boolean>;
  inspect: (selection: EvidenceSelection) => void;
  review?: ReactNode;
}

export function Specialist({ role, meeting, pending, guidance, setGuidance, steer, mutate, inspect, review }: Props) {
  const meta = roleMetaFor(role, meeting);
  const profile = clinicalProfile(meeting.case, role);
  const layout = profile ? { ...ROLE_LAYOUTS[role], title: profile.title, focus: profile.focus } : ROLE_LAYOUTS[role];
  const state = meeting.roles[role];
  const Icon = meta.icon;
  const context = clinicalData(state?.context ?? {});
  const conversionCase = isConversionCase(meeting.case);
  const suggestedGuidance = profile?.guidance ?? (conversionCase ? {
    radiology: 'Review all nine liver sites, vessel margins and the indeterminate lung nodule before clearance planning.',
    oncology: 'Compare four cycles with a longer biological test, including persistent ctDNA, toxicity and perioperative interruption.',
    surgery: 'Confirm all nine baseline sites are clearable, the remnant and vessel constraints, and liver-first versus synchronous colectomy.',
    pathology: 'Review BRAF V600E, pMMR/MSS and variant-level findings; distinguish tissue from plasma evidence and biopsy limitations.',
    research: 'Separate BREAKWATER, CAIRO5 and PROVENC3 populations and endpoints. Make unverified claims and source access explicit.',
    protocol: 'Compare the three current alternatives and outstanding conditions without inferring a validated perioperative pathway.',
    patient: 'Balance a credible curative-intent opportunity with independence, permanent-stoma concerns, treatment burden and support.',
  }[role] : meta.prompt);
  const [memory, setMemory] = useState<Memory | null>(null);
  const [showAssessment, setShowAssessment] = useState(false);
  const attention = roleAttention(meeting, role);
  const events = meeting.events.filter(event => event.role === role || ['PlanProposed', 'PlanUpdated', 'DecisionCaptured', 'CaseClosed'].includes(event.type));
  const activity = events.length ? events.map(event => ({ ...event.payload, id: event.id, type: event.type, timestamp: event.timestamp })) : state?.activity ?? [];
  const blocked = pending || meeting.busy || meeting.phase === 'DECISION_CAPTURED';
  const questions = meeting.phase === 'DECISION_CAPTURED' ? [] : meeting.frictions.filter(item => !item.resolved && item.roles.includes(role) && needsHumanReply(item, role));
  const asking = questions.length > 0;
  const stillOpen = asking && (state?.guidance.length ?? 0) > 0;
  const exampleReply = profile?.reply ?? (conversionCase && role === 'radiology' ? DEFAULT_RADIOLOGY_REPLY : suggestedGuidance);
  const example = asking ? exampleReply : suggestedGuidance;
  const memories = meeting.memories.filter(item => item.role === role);
  const liveMemory = memory ? meeting.memories.find(item => item.id === memory.id) : null;
  return <section data-testid={`workspace-${role}`} data-role={role} data-layout={layout.identity} aria-label={`${meta.label} specialist workspace`} className={layout.shell}>
    <div data-testid={`role-layout-${role}`} data-layout={layout.identity}>
    <header data-testid={`role-identity-${role}`} className={`workspace-heading mb-4 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-3 p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] ${layout.header}`}>
      <div aria-hidden="true" className="role-emblem flex size-16 shrink-0 flex-col items-center justify-center gap-1 rounded-xl border border-[var(--cp-role)] text-[var(--cp-role)]"><Icon size={28} /><span className="font-mono text-[10px] tracking-widest">{meta.short}</span></div>
      <div className="role-heading-copy min-w-0"><p className="role-eyebrow font-mono text-[10px] tracking-widest text-cp-text-muted">{meta.person} / SPECIALIST WORKSPACE</p><h1 className="role-title mt-2 text-2xl sm:text-3xl">{layout.title}</h1><p className="role-subtitle mt-2 text-sm leading-6 text-cp-text-muted">{profile ? meta.label : meta.title}</p></div>
      <div className="role-state col-span-2 sm:col-span-1"><Status value={state?.status ?? 'IDLE'} /></div>
      <ol aria-label="Specialty focus" className="role-focus col-span-2 flex flex-wrap gap-3 border-t border-cp-border pt-3 text-[10px] sm:col-span-3">{layout.focus.map((focus, index) => <li key={focus} className="flex items-center gap-2"><span aria-hidden="true" className="font-mono text-[10px]">{String(index + 1).padStart(2, '0')}</span>{focus}</li>)}</ol>
    </header>
    <div data-testid="role-attention" role={attention.tone === 'danger' ? 'alert' : 'status'} className={`mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border-l-4 bg-cp-surface px-4 py-3 ${attention.tone === 'danger' ? 'border-cp-danger' : attention.tone === 'warning' ? 'border-cp-warning' : attention.tone === 'success' ? 'border-cp-success' : 'border-[var(--cp-role)]'}`}><Badge tone={attention.tone} pulse={attention.running}>{attention.title}</Badge><p className="text-xs leading-6">{attention.detail}</p></div>
    <div data-testid="activity-desk" className="grid items-start gap-4 md:grid-cols-[minmax(0,1fr)_minmax(260px,0.9fr)]">
      <section className="min-w-0 card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="text-base">Review activity</h2><Badge>Newest first</Badge></div>
        <ReasoningSteps state={state} open={() => setShowAssessment(true)} />
        <ActivityStream role={role} activity={activity} />
        <button onClick={() => inspect({ ids: [] })} className="mt-3 inline-flex min-h-9 items-center gap-2 text-xs font-semibold text-cp-accent">Open evidence library <ArrowUpRight size={14} /></button>
      </section>
      <div className="min-w-0 space-y-4">
        {review}
        <details open={!review} className="min-w-0 card p-4 steering-panel">
          <summary className="text-sm font-semibold"><MessageSquareText size={18} />{asking ? 'Your agent is asking you' : 'Instruct your agent'}</summary>
          {asking ? <div data-testid="agent-question" role="status" className="my-3 rounded-xl border-l-4 border-cp-warning bg-cp-bg-elevated p-3 text-xs leading-6">
            <p><strong>{stillOpen ? 'Your last reply did not say what you reviewed, so I have kept this open: ' : 'I cannot settle this from the record alone: '}</strong>{clinicalText(questions[0].question)}</p>
            <div className="mt-1 text-cp-text-muted">{questions[0].missing.length > 0 && <><details className="inline [&[open]]:block"><summary className="inline cursor-pointer font-semibold text-cp-accent">What I need you to check ({questions[0].missing.length})</summary><ul className="my-2 list-disc space-y-1 pl-4 text-cp-text">{questions[0].missing.map(item => <li key={item}>{clinicalText(item)}</li>)}</ul></details></>}Tell me what you reviewed and found; “go ahead” is not enough.{questions.length > 1 ? ` ${questions.length - 1} more question${questions.length > 2 ? 's' : ''} follow.` : ''}</div>
          </div> : <p className="my-3 text-xs leading-6 text-cp-text-muted">You are the specialist. Tell your agent what to review, or challenge its assessment.</p>}
          <form onSubmit={event => { event.preventDefault(); void steer(); }}>
            <label className="sr-only" htmlFor={`guidance-${role}`}>{asking ? 'Reply' : 'Instruction'} to the {meta.label} agent</label>
            <textarea data-testid="guidance-input" id={`guidance-${role}`} value={guidance} onChange={event => setGuidance(event.target.value)} placeholder={example} rows={3} maxLength={2000} />
            <div className="form-footer mt-3 flex flex-wrap items-center justify-between gap-3"><button type="button" className="text-button" onClick={() => setGuidance(example)} disabled={blocked}>{asking ? 'Use example reply' : 'Use suggested instruction'}</button><button data-testid="send-guidance" className="button primary" type="submit" disabled={blocked || !guidance.trim()}><Send size={15} />{asking ? 'Send reply' : 'Send instruction'}</button></div>
          </form>
          {(state?.guidance.length ?? 0) > 0 && <div className="guidance-receipt mt-4 flex items-start gap-3 border-t border-cp-border pt-4 [&>svg]:text-cp-success [&_strong]:text-xs [&_p]:my-1 [&_p]:text-xs [&_p]:leading-7 [&_small]:text-[10px] [&_small]:text-cp-text-muted"><Check size={15} /><div><strong>Your last message</strong><p>{state?.guidance.at(-1)}</p><small>{/REASSESS|ANALYZ|WORKING/i.test(state?.status ?? '') ? 'Agent reassessing…' : `Current position revision ${state?.revision ?? 0} · see activity for reassessment outcome`}</small></div></div>}
        </details>
        <details className="min-w-0 card p-4"><summary className="text-sm font-semibold"><Brain size={18} />Saved review preferences</summary>
          {memories.length ? <div className="memory-list space-y-3">{memories.map(item => <article className={`memory-card rounded-xl border border-cp-border bg-cp-bg-elevated p-4 [&>p]:my-3 [&>p]:text-xs [&>p]:leading-7 ${item.status === 'FORGOTTEN' ? 'forgotten [&>p]:italic [&>p]:text-cp-text-muted' : ''}`} key={item.id}>
            <div className="row flex items-center gap-2 between justify-between wrap flex-wrap"><Badge>{label(item.category)}</Badge><Status value={item.status} /></div>
            <p>{item.status === 'FORGOTTEN' ? 'This memory has been forgotten.' : item.text}</p>
            <div className="memory-actions flex flex-wrap gap-2 [&>button]:rounded-lg [&>button]:border [&>button]:border-cp-border [&>button]:bg-cp-surface [&>button]:px-3 [&>button]:py-2 [&>button]:text-xs [&>button:first-child]:text-cp-accent [&>button:last-child]:ml-auto"><button onClick={() => void mutate('memory', { memory_id: item.id, action: 'use' })} disabled={blocked || item.status === 'FORGOTTEN' || item.status === 'USED'}>Use</button><button onClick={() => void mutate('memory', { memory_id: item.id, action: 'ignore' })} disabled={blocked || item.status === 'FORGOTTEN' || item.status === 'IGNORED'}>Ignore</button><button onClick={() => setMemory(item)}>Inspect</button><button onClick={() => void mutate('memory', { memory_id: item.id, action: 'forget' })} disabled={blocked || item.status === 'FORGOTTEN'}>Forget</button></div>
          </article>)}</div> : <Empty>No saved review preferences for this specialty.</Empty>}
        </details>
      </div>
    </div>
    <details className="my-5 card p-4"><summary className="text-sm font-semibold">Open {meta.label.toLowerCase()} clinical workspace and source records <ChevronDown size={14} /></summary>
      <div className="mt-4 space-y-5">
        {profile ? <CaseClinical role={role} meeting={meeting} inspect={inspect} /> : conversionCase ? <ConversionClinical role={role} meeting={meeting} inspect={inspect} /> : <>
          {role === 'radiology' && <Radiology context={context} />}
          {role === 'oncology' && <Oncology context={context} meeting={meeting} />}
          {role === 'surgery' && <Surgery context={context} />}
          {role === 'pathology' && <Pathology context={context} />}
          {role === 'research' && <Research context={context} meeting={meeting} inspect={inspect} />}
          {role === 'protocol' && <Protocol context={context} meeting={meeting} inspect={inspect} />}
          {role === 'patient' && <Patient context={context} />}
        </>}
        {(profile || conversionCase || role !== 'research' && role !== 'protocol') && state?.position && <section className="panel p-5!"><SectionHeading eyebrow="CLAIM → SOURCE" title="What supports this position" /><ClaimList state={state} inspect={inspect} /></section>}
      </div>
    {state?.position && <section className="panel specialist-position my-5 [&>h3]:my-3 [&>h3]:text-xl [&>p]:text-sm [&>p]:leading-7 [&>p]:text-cp-text-muted [&>details]:mt-4"><SectionHeading eyebrow={`SHARED WITH MDT · REVISION ${state.revision}`} title="Published specialist position" aside={<Badge tone="accent">{state.position.autonomy}</Badge>} /><Badge tone="success">Position published</Badge><h3>{state.position.position}</h3><p>{state.position.recommendation}</p><div className="position-meta mt-5 flex flex-wrap items-center gap-3 border-t border-cp-border pt-4 [&>.muted]:text-xs"><Badge>{label(state.position.stance)}</Badge><Badge>{state.position.human_intervention ? 'Human-steered' : 'Agent contribution'}</Badge><span className="muted text-sm leading-7 text-cp-text-muted">Clinical judgment and the conditions of the recommendation remain essential.</span></div>{state.position.questions_for_mdt.length > 0 && <><h4>Questions for the MDT</h4><BulletList items={state.position.questions_for_mdt} /></>}<details><summary>Position provenance <ChevronDown size={14} /></summary><BulletList items={state.position.provenance} /></details></section>}
    </details>
    {showAssessment && <Modal title={`${meta.label} assessment and uncertainties`} close={() => setShowAssessment(false)} wide><Assessment state={state} /></Modal>}
    {liveMemory && <Modal title="Memory provenance" close={() => setMemory(null)}><Badge tone="warning">Nudge, not evidence or clinical policy</Badge><h3>{liveMemory.status === 'FORGOTTEN' ? 'Memory forgotten' : liveMemory.text}</h3><DataFields data={{ category: liveMemory.category, role: liveMemory.role, clinician: liveMemory.clinician_id, source: liveMemory.source, date: liveMemory.date, status: liveMemory.status }} /><p className="muted text-sm leading-7 text-cp-text-muted">Preferences and experiential nudges do not become medical facts. Explicit use, ignore and forget actions are recorded by the meeting service.</p></Modal>}
    </div>
  </section>;
}

function ReasoningSteps({ state, open }: { state?: RoleState; open: () => void }) {
  const trace = state?.trace;
  const observations = clinicalItems(trace?.observations ?? []);
  const steps: { label: string; body: string[]; tone?: string }[] = [
    { label: 'Question being answered', body: [clinicalText(trace?.hypothesis ?? '', 'The specialist is establishing the clinical question for this case.')] },
    { label: 'What was checked', body: (trace?.evidence_checking ?? []).length ? trace!.evidence_checking : ['Source records for this specialty are being retrieved.'] },
    { label: 'What was found', body: observations.length ? observations : ['Findings will appear as the review progresses.'] },
    { label: 'What remains uncertain', body: (trace?.uncertainties ?? []).length ? trace!.uncertainties : ['No uncertainty has been recorded yet.'], tone: 'warning' },
    { label: 'Position taken', body: [clinicalText(trace?.assessment ?? '', 'Waiting for specialist review.')] },
    { label: 'Next clinical question', body: [clinicalText(trace?.next_action ?? '', 'Continue reviewing the unresolved clinical questions.')] },
  ];
  return <div data-testid="reasoning-steps" className="mb-4 rounded-xl border border-cp-border bg-cp-bg-elevated p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><p className="font-mono text-[10px] tracking-wide text-cp-text-soft">HOW THIS SPECIALTY REACHED ITS POSITION / REVISION {state?.revision ?? 0}</p><button onClick={open} className="inline-flex min-h-8 items-center gap-1.5 text-[11px] font-semibold text-cp-accent">Full assessment <ArrowUpRight size={13} /></button></div>
    <ol className="list-none space-y-3">{steps.map((step, index) => <li key={step.label} className={`grid grid-cols-[22px_minmax(0,1fr)] gap-3 border-l-2 pl-3 ${step.tone === 'warning' ? 'border-cp-warning' : 'border-[var(--cp-role)]'}`}>
      <span aria-hidden="true" className="font-mono text-[11px] text-cp-text-soft">{String(index + 1).padStart(2, '0')}</span>
      <div><p className="text-[11px] font-semibold uppercase tracking-wide text-cp-text-muted">{step.label}</p>{step.body.slice(0, 3).map((line, lineIndex) => <p key={lineIndex} className="mt-1 text-[13px] leading-6">{line}</p>)}</div>
    </li>)}</ol>
  </div>;
}
function Assessment({ state }: { state?: RoleState }) {
  const trace = state?.trace;
  return <section className="panel assessment"><SectionHeading eyebrow="SPECIALIST ASSESSMENT · BASIS FOR REVIEW" title="Specialist assessment" aside={<Sparkles size={20} />} />
    {state?.error && <div role="alert" className="alert">{state.error}</div>}
    <div className="assessment-current rounded-r-xl border-l-2 border-[var(--cp-role,var(--cp-accent))] bg-cp-bg-elevated p-4 [&_h3]:mt-2 [&_h3]:font-medium [&_h3]:leading-7"><span className="eyebrow">CURRENT ASSESSMENT</span><h3>{clinicalText(trace?.assessment ?? '', 'Waiting for specialist review.')}</h3></div>
    {trace?.hypothesis && <div className="hypothesis mt-5 flex items-start gap-3 [&>svg]:mt-1 [&>svg]:text-cp-accent [&_h4]:mt-0 [&_p]:text-xs [&_p]:leading-7 [&_p]:text-cp-text-muted"><Focus size={18} /><div><h4>Working hypothesis</h4><p>{clinicalText(trace.hypothesis)}</p></div></div>}
    {clinicalItems(trace?.observations ?? []).length > 0 && <><h4>Clinical observations</h4><BulletList items={clinicalItems(trace!.observations)} checked /></>}
    {(trace?.uncertainties.length ?? 0) > 0 && <div className="uncertainty mt-4 rounded-r-lg border-l-2 border-cp-warning bg-cp-bg-elevated px-4 pb-3 pt-1"><h4>What remains uncertain</h4><BulletList items={trace!.uncertainties} /></div>}
    {(trace?.evidence_checking.length ?? 0) > 0 && <><h4>Evidence being checked</h4><BulletList items={trace!.evidence_checking} /></>}
    {trace?.next_action && <div className="next-action mt-5 flex gap-3 rounded-xl bg-cp-surface-soft p-4 [&>svg]:mt-1 [&>svg]:text-cp-accent [&_p]:mt-1 [&_p]:text-xs [&_p]:leading-7"><ArrowRight size={17} /><div><span className="eyebrow">NEXT CLINICAL QUESTION</span><p>{clinicalText(trace.next_action, 'Continue reviewing the unresolved clinical questions.')}</p></div></div>}
  </section>;
}
export function ActivityStream({ activity, role }: { activity: Data[]; role?: Role }) {
  return activity.length ? <ol className="activity-stream max-h-96 list-none overflow-y-auto [&>li]:grid [&>li]:grid-cols-[18px_minmax(0,1fr)] [&>li]:gap-3 [&>li]:border-b [&>li]:border-cp-border [&>li]:py-3 [&_time]:font-mono [&_time]:text-[9px] [&_time]:text-cp-text-soft [&_p]:mt-2 [&_p]:text-xs [&_p]:leading-7" aria-label="Recent clinical review activity">{activity.slice(-7).reverse().map((item, index) => {
    const entry = clinicalActivity(item, role);
    return <li data-activity-id={typeof item.id === 'number' ? item.id : undefined} className={entry.failure ? '' : 'clinical-update'} key={String(item.id ?? `${text(item.timestamp)}-${text(item.type)}-${text(item.summary)}-${index}`)}><span className={`activity-node mt-1 flex size-4 items-center justify-center rounded-full border border-cp-border text-cp-success ${entry.failure ? 'border-cp-danger! text-cp-danger!' : ''}`}><Check size={11} /></span><div><div className="row flex items-center gap-2 between justify-between"><span className="eyebrow">{entry.title}</span><time>{item.timestamp ? time(String(item.timestamp)) : ''}</time></div><p>{entry.summary}</p></div></li>;
  })}</ol> : <Empty>Clinical observations, evidence reviews and specialist positions will appear here.</Empty>;
}
function ClaimList({ state, inspect }: { state: RoleState; inspect: (selection: EvidenceSelection) => void }) {
  return <div className="claim-list space-y-2 [&>button]:flex [&>button]:w-full [&>button]:items-start [&>button]:gap-3 [&>button]:rounded-xl [&>button]:border [&>button]:border-cp-border [&>button]:bg-cp-bg-elevated [&>button]:p-4 [&>button]:text-left [&>button]:text-xs [&>button]:leading-7 [&_small]:mt-1 [&_small]:block [&_small]:text-[10px] [&_small]:text-cp-accent [&>button>span:nth-child(2)]:flex-1 [&_svg]:text-cp-accent">{state.position?.claims.map((claim, index) => <button key={index} onClick={() => inspect({ ids: claim.evidence_ids, claim: claim.claim })}><span className="claim-index font-mono text-[10px] text-cp-text-soft">{String(index + 1).padStart(2, '0')}</span><span>{claim.claim}<small>{claim.evidence_ids.length} linked source{claim.evidence_ids.length === 1 ? '' : 's'}</small></span><ArrowUpRight size={18} /></button>)}</div>;
}

function Radiology({ context }: { context: Data }) {
  const [overlay, setOverlay] = useState(true);
  const [view, setView] = useState<'compare' | 'current'>('compare');
  const measurements = Object.entries(context).filter(([key, value]) => /mm|weeks|growth|volume|interval|diameter/i.test(key) && (typeof value === 'string' || typeof value === 'number')).slice(0, 4);
  const series = imagingSeries(context);
  return <>
    <section data-testid="clinical-radiology" className="panel imaging-panel border-t-4! border-t-cp-link!"><SectionHeading eyebrow="RADIOLOGY / LONGITUDINAL REVIEW" title="Longitudinal imaging review" aside={<ScanLine size={21} />} />
      <div className="imaging-toolbar mb-4 flex flex-wrap items-center justify-between gap-3"><div className="segmented inline-flex rounded-lg border border-cp-border bg-cp-surface-soft p-1 [&>button]:flex [&>button]:items-center [&>button]:gap-2 [&>button]:rounded-md [&>button]:border-0 [&>button]:px-3 [&>button]:py-2 [&>button]:text-xs [&>button[aria-pressed=true]]:bg-cp-surface [&>button[aria-pressed=true]]:text-cp-accent"><button aria-pressed={view === 'compare'} onClick={() => setView('compare')}><Layers size={14} />Compare</button><button aria-pressed={view === 'current'} onClick={() => setView('current')}>Current</button></div><button className="text-button" aria-pressed={overlay} onClick={() => setOverlay(value => !value)}><Eye size={15} />Overlay {overlay ? 'on' : 'off'}</button></div>
      <div className={`scan-pair grid grid-cols-2 gap-3 ${view === 'current' ? 'single mx-auto max-w-xl grid-cols-1!' : ''}`}>{view === 'compare' && <IllustrativeScan previous overlay={overlay} measurement={series.at(-2)} />}<IllustrativeScan overlay={overlay} measurement={series.at(-1)} /></div>
      <div className="illustration-notice mt-3 flex items-center justify-center gap-2 text-center font-mono text-[8px] text-cp-link"><Fingerprint size={15} /><span>ILLUSTRATIVE SVG · NOT A PATIENT SCAN · NOT TO SCALE</span></div>
      {series.length > 0 && <div className="lesion-history mt-5 border-t border-cp-border pt-4 [&>ol]:my-4 [&>ol]:flex [&>ol]:flex-wrap [&>ol]:gap-y-4 [&_li]:relative [&_li]:flex [&_li]:min-w-20 [&_li]:flex-1 [&_li]:flex-col [&_li]:border-t [&_li]:border-cp-border-strong [&_li]:pr-3 [&_li]:pt-4 [&_strong]:my-1 [&_strong]:text-3xl [&_strong]:font-medium [&_strong]:text-cp-link [&_small]:text-sm [&_li>span:last-child]:text-[10px] [&_li>span:last-child]:text-cp-text-soft [&>.muted]:text-xs"><p className="eyebrow">RECORDED LESION DIAMETER / CASE RECORD</p><ol>{series.map((measurement, index) => <li key={`${measurement.label}-${measurement.weeks_ago}-${index}`}><span className="measurement-node absolute -top-1 left-0 size-2 rounded-full bg-cp-link" /><span className="eyebrow">{measurement.label}</span><strong>{measurement.diameter_mm}<small> mm</small></strong><span>{measurement.weeks_ago === 0 ? 'Current study' : `${measurement.weeks_ago} weeks ago`}</span></li>)}</ol><p className="muted text-sm leading-7 text-cp-text-muted">Observed diameter change is not, by itself, confirmed progression or a treatment recommendation.</p></div>}
      {measurements.length > 0 && <dl className="measurement-strip mt-4 flex flex-wrap gap-5 border-t border-cp-border pt-4 [&>div]:min-w-20 [&>div]:flex-1 [&_dt]:font-mono [&_dt]:text-[9px] [&_dt]:text-cp-text-soft [&_dd]:mt-1 [&_dd]:text-3xl [&_dd]:text-cp-link">{measurements.map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{text(value)}</dd></div>)}</dl>}
      <div className="imaging-caption mt-4 flex items-start gap-3 border-t border-cp-border pt-4 [&>svg]:text-cp-link [&_p]:text-xs [&_p]:leading-7 [&_p]:text-cp-text-muted"><MoveUpRight size={20} /><p>Illustrative localization only. Clinical measurements and interpretations below come from the case record, never from this illustration.</p></div>
    </section>
    <ClinicalRecord context={context} title="Imaging reports, measured change and comparison caveats" />
  </>;
}
function IllustrativeScan({ previous = false, overlay, measurement }: { previous?: boolean; overlay: boolean; measurement?: ImagingMeasurement }) {
  return <figure className="scan overflow-hidden rounded-xl border border-cp-border bg-cp-surface-soft [&>svg]:block [&>svg]:h-auto [&>svg]:w-full [&_figcaption]:flex [&_figcaption]:flex-wrap [&_figcaption]:items-center [&_figcaption]:justify-between [&_figcaption]:gap-1 [&_figcaption]:p-3 [&_figcaption]:text-[9px] [&_figcaption]:text-cp-text-muted"><div className="scan-label flex flex-wrap justify-between gap-2 px-3 pt-3 font-mono text-[7px] tracking-wide text-cp-text-soft [&>span:first-child]:text-cp-link"><span>{previous ? 'PRIOR / COMPARISON' : 'CURRENT / FOCUS'}</span><span>AXIAL SCHEMATIC</span></div><svg viewBox="0 0 360 300" role="img" aria-label={`${previous ? 'Prior' : 'Current'} illustrative axial chest schematic with lesion; not a real scan or actual measurement`}>
    <defs><pattern id={`grid-${previous}`} width="20" height="20" patternUnits="userSpaceOnUse"><path d="M 20 0 L 0 0 0 20" className="scan-grid" /></pattern></defs>
    <rect width="360" height="300" fill={`url(#grid-${previous})`} />
    <path className="body-outer" d="M180 38C98 31 34 87 36 156c2 75 55 112 144 112s142-37 144-112C326 87 262 31 180 38Z" />
    <path className="body-inner" d="M180 49C107 42 50 88 49 153c-1 64 48 100 131 100s132-36 131-100c-1-65-58-111-131-104Z" />
    <path className="lung" d="M143 67C108 54 71 85 63 121c-14 64 20 109 64 107 25-1 22-29 22-56 0-24 20-42 17-61-2-17-10-34-23-44Z" />
    <path className="lung" d="M217 67c35-13 72 18 80 54 14 64-20 109-64 107-25-1-22-29-22-56 0-24-20-42-17-61 2-17 10-34 23-44Z" />
    <path className="organ" d="M171 140c-16 6-23 34-16 55 9 26 37 37 54 17 15-18 7-44-8-60-11-13-20-17-30-12Z" />
    <circle className="bone" cx="180" cy="233" r="17" /><circle className="organ" cx="180" cy="233" r="8" />
    <path className="vessel" d="M133 106l-15 37-23 14m23-14 9 38m-9-38-29-18m45 8 4 48m91-75 15 37 23 14m-23-14-9 38m9-38 29-18m-45 8-4 48" />
    <path className="bone rib" d="M67 89l14 8m-28 27 15 4m-15 42 15-3m3 43 14-8m25 34 8-15m175-132-14 8m28 27-15 4m15 42-15-3m-3 43-14-8m-25 34-8-15" />
    <ellipse className="lesion" cx="101" cy="168" rx={previous ? 10 : 15} ry={previous ? 8 : 12} />
    {overlay && <g className="annotation"><rect x={previous ? 82 : 77} y={previous ? 150 : 145} width={previous ? 38 : 48} height={previous ? 36 : 46} rx="3" /><path d={`M${previous ? 120 : 125} 168H151L167 128H244`} /><circle cx="101" cy="168" r="2" /><text x="171" y="120">TARGET REGION</text><path d="M91 190h20m-20-4v8m20-8v8" /></g>}
    <text x="17" y="156" className="orientation">R</text><text x="334" y="156" className="orientation">L</text><text x="176" y="26" className="orientation">A</text><text x="176" y="287" className="orientation">P</text>
  </svg><figcaption>{measurement ? `${measurement.label} · ${measurement.diameter_mm} mm` : previous ? 'Reference geometry' : 'Illustrative interval change'}<Badge>{measurement ? `${measurement.weeks_ago}w ago` : previous ? 'T − 1' : 'T 0'}</Badge></figcaption></figure>;
}
function Oncology({ context, meeting }: { context: Data; meeting: Meeting }) {
  const clinicalContext = { ...meeting.case, ...context };
  const hasToxicityRecords = Boolean(context.referral_summary && context.archived_toxicity_note);
  return <section data-testid="clinical-oncology" className="space-y-5">
    <div className="rounded-2xl border border-cp-accent bg-cp-accent-soft p-6"><p className="eyebrow">SYSTEMIC TREATMENT CONFERENCE</p><h2 className="mt-2 text-2xl">Benefit must meet tolerability.</h2><p className="mt-3 max-w-3xl text-sm text-cp-text-muted">{clinicalText(first(context, ['question']), 'Which treatment options remain appropriate given the recorded diagnosis and treatment burden?')}</p></div>
    {hasToxicityRecords && <article data-testid="oncology-toxicity-conflict" className="rounded-xl border border-cp-border border-l-4 border-l-cp-danger bg-cp-accent-soft p-5">
      <h3>Reconcile the toxicity history</h3><p className="mt-2 text-sm text-cp-text-muted">Compare the referral statement with the archived toxicity record before judging treatment safety.</p>
      <div className="mt-4 grid gap-5 md:grid-cols-2"><DataFields data={{ referral_summary: context.referral_summary }} /><DataFields data={{ archived_toxicity_note: context.archived_toxicity_note }} /></div>
    </article>}
    <div className="grid gap-4 lg:grid-cols-3">
      <ClinicalBlock title="Treatment already received" subtitle="Prior indication and response" icon={<History size={23} />} context={clinicalContext} keys={/previous|prior|history|treatment|therap/} className="border-t-4 border-t-cp-accent" />
      <ClinicalBlock title="Toxicity and tolerability" subtitle="Adverse effects and tolerability" icon={<Heart size={23} />} context={context} keys={/toxicity|adverse|toler|safety|contraind|risk/} className="bg-cp-accent-soft! border-cp-accent!" />
      <ClinicalBlock title="Options requiring discussion" subtitle="Disease, biomarkers and fitness" icon={<ArrowRight size={23} />} context={clinicalContext} keys={/option|consider|recommend|biomarker|performance|ecog|diagnos|stage|fitness/} className="border-t-4 border-t-cp-border-strong" />
    </div>
    <ClinicalRecord context={context} title="Complete oncology record" />
  </section>;
}
function Surgery({ context }: { context: Data }) {
  return <section data-testid="clinical-surgery" className="overflow-hidden card">
    <div className="flex flex-wrap items-center justify-between gap-4 border-b-4 border-cp-success p-6"><div><p className="eyebrow">OPERABILITY REVIEW</p><h2 className="mt-2">Feasible does not yet mean suitable.</h2></div><Badge>Review gates, not completed checks</Badge></div>
    <div className="grid lg:grid-cols-[1.2fr_1fr]">
      <div className="space-y-4 border-cp-border p-5 lg:border-r"><ClinicalBlock title="01 / Anatomical resectability" subtitle="Local extent and procedural constraints" context={context} keys={/anatom|lesion|operab|resect|surg|location/} className="border-l-4 border-l-cp-success" /><ClinicalBlock title="02 / Confirmation needed" subtitle="What must be known before a procedure?" context={context} keys={/confirm|tissue|biopsy|missing|uncertain|condition|question|reserve/} /></div>
      <div className="bg-cp-bg-elevated p-5"><ClinicalBlock title="Patient fitness and risk" subtitle="Physiology, prior treatment and preferences" context={context} keys={/fitness|risk|function|pulmon|cardiac|ecog|perform|contraind|prefer|reserve/} className="border-t-4 border-t-cp-success" /><p className="mt-5 text-xs leading-7 text-cp-text-muted">No procedural recommendation is inferred from the presence of data. The specialist assessment records the clinical judgment and conditions.</p></div>
    </div><div className="border-t border-cp-border p-5"><ClinicalRecord context={context} title="Complete surgical review" /></div>
  </section>;
}
function Pathology({ context }: { context: Data }) {
  return <section data-testid="clinical-pathology" className="overflow-hidden rounded-2xl border border-cp-border-strong bg-cp-surface">
    <div className="flex items-center gap-4 bg-cp-text p-6 text-cp-bg"><Fingerprint size={34} /><div><p className="font-mono text-[10px] tracking-widest">DIAGNOSTIC DOSSIER</p><h2 className="mt-1">Tissue before assumption.</h2></div></div>
    <div className="space-y-5 p-5">
      <ClinicalBlock title="Specimen and histology" subtitle="Provenance of the diagnosis" context={context} keys={/specimen|histolog|tissue|patholog|diagnos|biopsy/} icon={<Layers size={22} />} className="rounded-none! border-x-0! border-t-0!" />
      <div className="border-l-4 border-cp-accent bg-cp-accent-soft p-5"><h3>Molecular findings</h3><p className="mt-1 text-xs text-cp-text-muted">Reported biomarkers, not assumed eligibility</p><ContextFacts context={context} keys={/molecular|biomarker|mutation|marker|egfr|alk|pdl|kras/} /></div>
      <ClinicalBlock title="Diagnostic limitations" subtitle="What the existing tissue cannot establish" context={context} keys={/limit|uncertain|confirm|caveat|missing|condition/} />
      <p className="border-t border-cp-border pt-4 text-xs leading-7 text-cp-text-muted">An earlier specimen does not automatically establish the origin or behaviour of a new lesion.</p><ClinicalRecord context={context} title="Complete pathology record" />
    </div>
  </section>;
}
function Research({ context, meeting, inspect }: { context: Data; meeting: Meeting; inspect: (selection: EvidenceSelection) => void }) {
  return <section data-testid="clinical-research" className="overflow-hidden rounded-2xl border border-cp-link bg-cp-surface">
    <div className="flex flex-wrap items-end justify-between gap-5 border-b border-cp-link bg-cp-surface-soft p-6"><div><p className="eyebrow">EVIDENCE COMPARISON / EUROPE FIRST</p><h2 className="mt-2 text-2xl">The result is only useful if it fits.</h2></div><div className="flex gap-5">{[['Sources', meeting.evidence.length], ['Applicability cautions', meeting.evidence.filter(item => item.patient_match !== 'HIGH').length]].map(([title, count]) => <div key={title}><strong className="text-3xl font-medium text-cp-link">{count}</strong><p className="text-xs text-cp-text-muted">{title}</p></div>)}</div></div>
    <div className="grid xl:grid-cols-[250px_minmax(0,1fr)]"><aside className="border-cp-border bg-cp-bg-elevated p-5 xl:border-r"><h3>Appraisal lens</h3><div className="mt-4 space-y-4">{['Netherlands first', 'European applicability', 'Population and endpoints', 'Access and limitations'].map((item, index) => <div className="flex gap-3 text-xs" key={item}><span className="font-mono text-cp-link">0{index + 1}</span>{item}</div>)}</div><div className="mt-6"><ClinicalRecord context={context} title="Research brief" /></div></aside><div className="min-w-0 p-5"><EvidenceTable evidence={meeting.evidence} inspect={inspect} /></div></div>
    {meeting.roles.research?.position && <div className="border-t border-cp-border p-5"><SectionHeading title="Claims and patient applicability" /><ClaimList state={meeting.roles.research} inspect={inspect} /></div>}
  </section>;
}
function Protocol({ context, meeting, inspect }: { context: Data; meeting: Meeting; inspect: (selection: EvidenceSelection) => void }) {
  const sources = meeting.evidence.filter(source => /guideline|protocol|regulat|ctis|ema|richtlijn/i.test(`${source.kind} ${source.title} ${source.authority}`));
  const position = meeting.roles.protocol?.position;
  const conditions: Data = {
    ...context,
    ...(position?.uncertainties.length ? { specialist_uncertainties: position.uncertainties } : {}),
    ...(position?.questions_for_mdt.length ? { questions_for_mdt: position.questions_for_mdt } : {}),
    ...(meeting.plan?.conditions.length ? { plan_conditions: meeting.plan.conditions } : {}),
  };
  return <section data-testid="clinical-protocol" className="rounded-2xl border border-cp-border bg-cp-bg-elevated p-5 sm:p-6">
    <SectionHeading eyebrow="CONDITIONAL CARE PATHWAY" title="Conditions and limitations" aside={<ShieldCheck size={25} />} />
    <ol className="ml-4 border-l-2 border-cp-warning">
      {[
        { title: 'Dutch guidance', tag: 'NL', keys: /dutch|national|richtlijn|jurisdiction/, sourceId: 'NL-NSCLC' },
        { title: 'European and regulatory context', tag: 'EU', keys: /europ|esmo|ema|regulat|jurisdiction/, sourceId: 'EU-EMA-OPDIVO' },
        { title: 'Protocol access', tag: 'ACCESS', keys: /protocol|ctis|access|institution|trial/ },
        { title: 'Conditions before application', tag: 'IF', keys: /condition|applicab|limit|deviat|uncertain|missing|question/ },
      ].map(step => {
        const source = meeting.evidence.find(item => item.id === step.sourceId);
        const fields = Object.fromEntries(Object.entries(step.tag === 'IF' ? conditions : context).filter(([key]) => step.keys.test(key)));
        return <li key={step.tag} data-testid={`protocol-step-${step.tag}`} className="relative pb-6 pl-7 last:pb-0"><span className="absolute -left-2 top-5 size-3.5 rounded-full border-2 border-cp-warning bg-cp-surface" /><div className="rounded-xl border border-cp-border bg-cp-surface p-4"><div className="flex items-center justify-between gap-3"><h3>{step.title}</h3><Badge tone="warning">{step.tag}</Badge></div>
          {Object.keys(fields).length > 0 ? <DataFields data={fields} /> : !source && !step.sourceId && <p className="mt-4 text-xs text-cp-text-muted">No specialty review detail has been supplied for this stage yet.</p>}
          {source ? <div className="mt-4 border-t border-cp-border pt-4"><h4>{source.title}</h4><Badge>{label(source.access)}</Badge><p className="mt-3 text-sm leading-7">{clinicalText(source.passage)}</p><BulletList items={source.limitations} /><button className="mt-3 inline-flex items-center gap-2 rounded-lg border border-cp-border bg-cp-surface px-3 py-2 text-xs" onClick={() => inspect({ ids: [source.id] })}>Inspect {source.title}<ArrowUpRight size={14} /></button></div> : step.sourceId && <p className="mt-4 text-xs text-cp-text-muted">The relevant guidance source has not yet been supplied to this meeting. No patient-specific applicability is established.</p>}
        </div></li>;
      })}
    </ol><p className="mt-6 border-l-4 border-cp-warning p-4 text-xs leading-7">Unavailable institutional guidance must not be confused with an unavailable public trial protocol. Only recorded access information is shown.</p>
    <div className="mt-6"><EvidenceTable evidence={sources} inspect={inspect} /></div><ClinicalRecord context={context} title="Complete protocol record" />
  </section>;
}
function Patient({ context }: { context: Data }) {
  const hasBurden = Object.keys(context).some(key => /burden|toxicity|daily|quality|adverse|treatment/.test(key));
  return <section data-testid="clinical-patient" className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
    <div className="rounded-2xl border border-cp-accent bg-cp-accent-soft p-7 sm:p-9"><Heart className="mb-6 text-cp-accent" size={34} /><p className="eyebrow">STATED PRIORITIES, NOT ASSUMED PREFERENCES</p><h2 className="mt-3 max-w-xl text-3xl font-medium leading-tight">Patient priorities in the plan.</h2><div className="mt-6 border-l-2 border-cp-accent pl-5"><ContextFacts context={context} keys={/prefer|priorit|goal|value|wish|concern|statement/} /></div><p className="mt-6 text-xs leading-7 text-cp-text-muted">Only preferences in the case record are displayed. Demographics do not establish what this patient wants.</p></div>
    <div className="space-y-5"><article data-testid="patient-burden-discussion" className="rounded-xl border border-cp-border bg-cp-bg-elevated p-5"><h3>Treatment burden</h3><p className="mt-2 text-xs leading-7 text-cp-text-muted">{hasBurden ? 'Recorded daily-life demands and adverse effects for discussion.' : 'Treatment burden has not been quantified in the supplied record. Discuss potential burden against the stated priorities; do not assume a preference.'}</p><ContextFacts context={context} keys={hasBurden ? /burden|toxicity|daily|quality|adverse|treatment/ : /question|stated_priorities|prefer|priorit|goal/} /></article><ClinicalBlock title="Support and shared decision-making" subtitle="Support, consent and unanswered questions" context={context} keys={/support|living|lives|family|carer|consent|decision|question/} icon={<MessageSquareText size={23} />} /></div>
    <div className="flex items-start gap-3 rounded-xl border border-cp-border bg-cp-surface p-5 text-sm lg:col-span-2"><Clock3 className="text-cp-accent" size={20} /><p>Human concurrence does not replace a patient conversation or informed consent. Review the clinical proposal together with its expected burden.</p></div><div className="lg:col-span-2"><ClinicalRecord context={context} title="Complete patient-perspective record" /></div>
  </section>;
}

function ContextFacts({ context, keys }: { context: Data; keys: RegExp }) {
  const fields = Object.fromEntries(Object.entries(context).filter(([key]) => keys.test(key)));
  return Object.keys(fields).length ? <DataFields data={fields} /> : <p className="mt-4 text-xs leading-7 text-cp-text-muted">Not specified in the available case record. Confirm with the team before drawing a conclusion.</p>;
}
function ClinicalBlock({ context, keys, title, subtitle, icon, className = '' }: { context: Data; keys: RegExp; title: string; subtitle: string; icon?: React.ReactNode; className?: string }) {
  return <article className={`rounded-xl border border-cp-border bg-cp-surface p-5 ${className}`}><div className="flex items-start gap-3">{icon && <span className="text-[var(--cp-role)]">{icon}</span>}<div><h3>{title}</h3><p className="mt-1 text-xs text-cp-text-muted">{subtitle}</p></div></div><ContextFacts context={context} keys={keys} /></article>;
}
function ClinicalRecord({ context, title }: { context: Data; title: string }) {
  return <details className="rounded-xl border border-cp-border bg-cp-surface p-4"><summary className="text-sm font-medium">{title}<ChevronDown size={14} /></summary><DataFields data={context} /></details>;
}
