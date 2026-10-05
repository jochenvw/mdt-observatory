import { useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Check, CheckCheck, FileText, Flag, Heart, LoaderCircle, Printer, RefreshCw, ShieldCheck, TriangleAlert } from 'lucide-react';
import { time } from './helpers';
import { clinicalActivity, documentError, DOCUMENT_NAME, outcomeText, statusLabel } from './presentation';
import { AUDIENCES, ROLES } from './types';
import type { Audience, Communication, Meeting, MeetingEvent, Role } from './types';
import { Badge, BulletList, Empty, ROLE_META } from './ui';

type Mutate = (action: string, body: unknown) => Promise<boolean>;

/** Native names for the languages the patient-summary skill has calibrated checks for. */
export const LANGUAGE_NAME: Record<string, string> = { en: 'English', de: 'Deutsch', it: 'Italiano', nl: 'Nederlands' };
const LANGUAGE_ENGLISH: Record<string, string> = { en: 'English', de: 'German', it: 'Italian', nl: 'Dutch' };
/** Fixed labels inside the patient's document, shown in the patient's own language. */
const PATIENT_LABELS: Record<string, { glossary: string; questions: string; draft: string; approved: string }> = {
  en: { glossary: 'Words explained', questions: 'Questions you may want to ask', draft: 'Draft · not yet approved by your care team', approved: 'Checked and approved by your care team' },
  de: { glossary: 'Begriffe erklärt', questions: 'Fragen, die Sie stellen können', draft: 'Entwurf · noch nicht von Ihrem Behandlungsteam freigegeben', approved: 'Von Ihrem Behandlungsteam geprüft und freigegeben' },
  it: { glossary: 'Parole spiegate', questions: 'Domande che potrebbe voler fare', draft: 'Bozza · non ancora approvata dal suo team di cura', approved: 'Controllato e approvato dal suo team di cura' },
  nl: { glossary: 'Woorden uitgelegd', questions: 'Vragen die u kunt stellen', draft: 'Concept · nog niet goedgekeurd door uw behandelteam', approved: 'Gecontroleerd en goedgekeurd door uw behandelteam' },
};
const AUDIENCE_TITLE: Record<Audience, string> = { patient: 'Patient summary', clinician: 'Letter to accountable medical doctor' };
const AUDIENCE_PURPOSE: Record<Audience, string> = {
  patient: 'Plain-language explanation of the outcome, written gently in the patient’s own language.',
  clinician: 'Clinician-to-clinician outcome letter in English, using standard medical terminology.',
};
const STATUS_TONE: Record<string, string> = { DRAFTING: 'accent', DRAFT: 'warning', CHANGES_REQUESTED: 'warning', APPROVED: 'success', FAILED: 'danger' };
const STATUS_TEXT: Record<string, string> = { DRAFTING: 'Drafting…', DRAFT: 'Awaiting clinician review', CHANGES_REQUESTED: 'Changes requested', APPROVED: 'Approved', FAILED: 'Could not be drafted' };

export function languageLabel(code: string): string {
  const native = LANGUAGE_NAME[code];
  if (!native) return code.toUpperCase();
  return code === 'en' ? native : `${native} (${LANGUAGE_ENGLISH[code]})`;
}
export function documentStatus(item: Communication | undefined): string {
  return item ? STATUS_TEXT[item.status] ?? statusLabel(item.status) : 'Not started';
}
function documentEvents(meeting: Meeting, audience: Audience, revision?: number): MeetingEvent[] {
  return meeting.events.filter(event => {
    if (!event.type.startsWith('Communication')) return false;
    const payload = event.payload;
    const mine = payload.audience === audience || (Array.isArray(payload.audiences) && payload.audiences.includes(audience));
    return mine && (revision === undefined || payload.revision === undefined || payload.revision === revision);
  });
}
function signOff(meeting: Meeting) {
  const version = meeting.plan?.version;
  const current = ROLES.filter(role => meeting.concurrences[role]?.plan_version === version);
  return {
    total: current.length,
    human: current.filter(role => meeting.concurrences[role]?.actor === 'human'),
    agent: current.filter(role => meeting.concurrences[role]?.actor === 'agent'),
  };
}

/** Shown on the chair and central screens once the team has recorded its decision. */
export function OutcomeBanner({ meeting, open }: { meeting: Meeting; open: () => void }) {
  if (meeting.phase !== 'DECISION_CAPTURED' || !meeting.plan) return null;
  const signed = signOff(meeting);
  return <section data-testid="outcome-banner" aria-label="Consensus reached" className="mb-5 flex flex-wrap items-center gap-5 rounded-2xl border-2 border-cp-success bg-cp-surface p-5 sm:p-6">
    <span className="flex size-14 shrink-0 items-center justify-center rounded-full border border-cp-success text-cp-success"><CheckCheck size={30} /></span>
    <div className="min-w-0 flex-1">
      <p className="eyebrow">MDT OUTCOME · PLAN VERSION {meeting.plan.version}</p>
      <h2 className="mt-1 text-2xl">Consensus reached. The plan forward is on record.</h2>
      <p className="mt-1 text-sm leading-7 text-cp-text-muted">{signed.total} of 7 specialties recorded · {signed.human.length} clinician concurrence{signed.human.length === 1 ? '' : 's'}{signed.agent.length ? `, ${signed.agent.length} automatic under demonstration policy (not human sign-off)` : ''}. Next: review the patient summary and the letter to the accountable medical doctor.</p>
      <div className="mt-3 flex flex-wrap gap-2">{AUDIENCES.map(audience => { const item = meeting.communications?.[audience]; return <Badge key={audience} tone={item ? STATUS_TONE[item.status] : ''} pulse={item?.status === 'DRAFTING'}>{DOCUMENT_NAME[audience]}: {documentStatus(item)}</Badge>; })}</div>
    </div>
    <button data-testid="open-outcome" className="button primary large" onClick={open}>Open outcome &amp; letters <ArrowRight size={16} /></button>
  </section>;
}

export function Outcome({ meeting, pending, mutate }: { meeting: Meeting; pending: boolean; mutate: Mutate }) {
  const [open, setOpen] = useState<Audience | null>(null);
  const [reviewer, setReviewer] = useState('');
  const [reviewRole, setReviewRole] = useState<Role | ''>('');
  const plan = meeting.plan;
  if (meeting.phase !== 'DECISION_CAPTURED' || !plan) {
    return <section data-testid="outcome-pending" className="panel"><p className="eyebrow">MDT OUTCOME</p><h1 className="mt-2">The outcome is not recorded yet</h1><p className="mt-3 max-w-3xl text-base leading-8 text-cp-text-muted">Once every specialty has recorded its review of the proposal, this screen shows the agreed plan, patient summary and letter to the accountable medical doctor. Current stage: {statusLabel(meeting.phase)}.</p></section>;
  }
  const item = open ? meeting.communications?.[open] : undefined;
  if (open) {
    return <DocumentScreen key={open} meeting={meeting} audience={open} item={item} back={() => setOpen(null)} pending={pending} mutate={mutate} reviewer={reviewer} setReviewer={setReviewer} reviewRole={reviewRole} setReviewRole={setReviewRole} />;
  }
  const signed = signOff(meeting);
  return <div data-testid="outcome-overview" className="space-y-5">
    <section className="overflow-hidden rounded-2xl border-2 border-cp-success bg-cp-surface">
      <div className="flex flex-wrap items-center gap-5 border-b border-cp-border bg-cp-bg-elevated p-6 sm:p-8">
        <span className="flex size-16 shrink-0 items-center justify-center rounded-full border border-cp-success text-cp-success"><CheckCheck size={36} /></span>
        <div className="min-w-[min(100%,30rem)] flex-1"><p className="eyebrow">MDT OUTCOME · PLAN VERSION {plan.version} · RECORDED {time(meeting.closed_at ?? plan.created_at)}</p><h1 className="mt-2 text-4xl">Consensus reached</h1><p className="mt-2 text-lg leading-8">{plan.title}</p></div>
        <div className="flex flex-col items-end gap-3"><Badge tone="success"><ShieldCheck size={13} />{signed.total} of 7 recorded</Badge><div data-testid="outcome-quick-documents" className="flex flex-wrap justify-end gap-2">{AUDIENCES.map(audience => { const doc = meeting.communications?.[audience]; return <button key={audience} className="button secondary" disabled={!doc} onClick={() => setOpen(audience)}>{audience === 'patient' ? <Heart size={15} /> : <FileText size={15} />}{DOCUMENT_NAME[audience]}{doc && audience === 'patient' ? ` · ${LANGUAGE_NAME[doc.language] ?? doc.language.toUpperCase()}` : ''} · {documentStatus(doc)}</button>; })}</div></div>
      </div>
      <div className="grid gap-8 p-6 sm:p-8 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,1fr)]">
        <div>
          <Badge tone={plan.direction === 'PROCEED_TREATMENT' ? 'success' : 'warning'}>{plan.direction === 'PROCEED_TREATMENT' ? 'Proceed with treatment' : 'More investigation is required'}</Badge>
          <h2 className="mt-4 text-2xl">{plan.decision || plan.title}</h2>
          <p className="mt-3 max-w-4xl text-base leading-8 text-cp-text-muted">{plan.summary}</p>
          {plan.resolved_requirements.length > 0 && <div className="mt-5 rounded-xl border border-cp-success bg-cp-bg-elevated p-5"><h2 className="text-lg">Completed requirements</h2><BulletList items={plan.resolved_requirements.map(item => item.finding)} /></div>}
          <h2 className="mt-6 text-2xl">The plan forward</h2>
          <ol data-testid="outcome-actions" className="mt-4 list-none space-y-4">{plan.actions.map((action, index) => <li key={index} className="flex gap-4"><span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-cp-accent font-mono text-sm text-cp-accent-fg">{index + 1}</span><p className="text-base leading-8">{outcomeText(action)}</p></li>)}</ol>
        </div>
        <div className="space-y-5">
          {plan.conditions.length > 0 && <div className="rounded-r-xl border-l-4 border-cp-warning bg-cp-bg-elevated px-5 py-4"><h2 className="text-lg">Conditions &amp; retained uncertainty</h2><p className="mt-1 text-xs text-cp-text-muted">These travel with the plan; they are not resolved by agreement.</p><BulletList items={plan.conditions} /></div>}
          <div className="rounded-xl border border-cp-border p-5"><h2 className="text-lg">Sign-off</h2><ul className="mt-3 space-y-2 text-sm">{ROLES.map(role => { const concur = meeting.concurrences[role]; return <li key={role} className="flex items-center justify-between gap-3 border-b border-cp-border pb-2 last:border-0"><span>{ROLE_META[role].label}</span><span className="inline-flex items-center gap-1 text-xs text-cp-text-muted">{concur?.actor === 'human' ? <><Check size={14} className="text-cp-success" />Clinician concurred</> : concur?.actor === 'agent' ? 'Automatic (demo policy)' : 'Not recorded'}</span></li>; })}</ul></div>
        </div>
      </div>
    </section>
    <section aria-label="Communicating the outcome">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">COMMUNICATING THE OUTCOME</p><h2 className="mt-1 text-2xl">Letters drafted from the recorded outcome</h2></div><p className="max-w-xl text-xs leading-6 text-cp-text-muted">Each document is drafted by a language model applying a writing skill to this record only. Neither is shared until a named clinician approves it.</p></div>
      <div className="grid gap-5 lg:grid-cols-2">{AUDIENCES.map(audience => <DocumentCard key={audience} meeting={meeting} audience={audience} open={() => setOpen(audience)} />)}</div>
    </section>
  </div>;
}

function DocumentCard({ meeting, audience, open }: { meeting: Meeting; audience: Audience; open: () => void }) {
  const item = meeting.communications?.[audience];
  const Icon = audience === 'patient' ? Heart : FileText;
  const activity = item ? documentEvents(meeting, audience, item.revision).slice(-3).reverse() : [];
  return <article data-testid={`document-card-${audience}`} className="card flex flex-col gap-4 p-6">
    <div className="flex items-start gap-4"><span className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-cp-highlight bg-cp-accent-soft text-cp-accent"><Icon size={24} /></span><div className="min-w-0 flex-1"><h3 className="text-xl">{AUDIENCE_TITLE[audience]}</h3><p className="mt-1 text-sm leading-6 text-cp-text-muted">{AUDIENCE_PURPOSE[audience]}</p></div></div>
    <div className="flex flex-wrap gap-2"><Badge tone={item ? STATUS_TONE[item.status] : ''} pulse={item?.status === 'DRAFTING'}>{documentStatus(item)}</Badge>{item && <Badge tone="accent">Language: {languageLabel(item.language)}</Badge>}{item && item.revision > 1 && <Badge>Revision {item.revision}</Badge>}</div>
    {item?.status === 'APPROVED' && <p className="text-sm leading-6"><Check size={15} className="mr-1 inline text-cp-success" />Approved by <strong>{item.approved_by}</strong>{item.approved_role ? ` (${ROLE_META[item.approved_role].person})` : ''} · {time(item.approved_at ?? item.updated_at)}</p>}
    {item?.status === 'FAILED' && <p role="alert" className="flex gap-2 rounded-xl border border-cp-danger p-3 text-sm leading-6 text-cp-danger"><TriangleAlert size={17} className="mt-1" />{documentError(item.error)}</p>}
    {item?.status === 'DRAFTING' && <ActivityList events={activity} />}
    {!item && <p className="text-sm text-cp-text-muted">Drafting starts automatically when the decision is captured.</p>}
    <button data-testid={`open-document-${audience}`} className="button secondary mt-auto self-start" onClick={open} disabled={!item}>{item?.status === 'DRAFT' ? 'Read and review' : item?.status === 'FAILED' ? 'Open and regenerate' : 'Open document'} <ArrowRight size={15} /></button>
  </article>;
}

function ActivityList({ events }: { events: MeetingEvent[] }) {
  if (!events.length) return <p className="flex items-center gap-2 text-sm text-cp-text-muted"><LoaderCircle size={15} className="motion-safe:animate-spin" />Preparing the draft…</p>;
  return <ol aria-live="polite" className="activity-stream space-y-2 border-l-2 border-cp-highlight pl-4">{events.map(event => { const entry = clinicalActivity({ ...event.payload, type: event.type }); return <li key={event.id} className="clinical-update text-sm leading-6"><time className="mr-2 font-mono text-[11px] text-cp-text-soft">{time(event.timestamp)}</time><span className={entry.failure ? 'text-cp-danger' : ''}>{entry.summary}</span></li>; })}</ol>;
}

interface DocumentProps {
  meeting: Meeting; audience: Audience; item: Communication | undefined; back: () => void; pending: boolean; mutate: Mutate;
  reviewer: string; setReviewer: (value: string) => void; reviewRole: Role | ''; setReviewRole: (value: Role | '') => void;
}
export function DocumentScreen({ meeting, audience, item, back, pending, mutate, reviewer, setReviewer, reviewRole, setReviewRole }: DocumentProps) {
  return <div data-testid={`document-${audience}`} className="space-y-4">
    <div className="no-print flex flex-wrap items-center justify-between gap-3"><button data-testid="outcome-back" className="button secondary" onClick={back}><ArrowLeft size={15} />Back to the outcome</button>{item && item.status !== 'DRAFTING' && item.status !== 'FAILED' && <button className="button secondary" onClick={() => window.print()}><Printer size={15} />Print</button>}</div>
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="min-w-0">{!item ? <Empty>This document has not been started.</Empty> : item.status === 'DRAFTING' ? <section className="panel"><h1 className="text-2xl">{AUDIENCE_TITLE[audience]}</h1><p className="mt-2 text-sm text-cp-text-muted">Drafting revision {item.revision} in {languageLabel(item.language)}.</p><div className="mt-5"><ActivityList events={documentEvents(meeting, audience, item.revision).slice(-8).reverse()} /></div></section> : item.status === 'FAILED' ? <section role="alert" className="panel border-cp-danger!"><h1 className="flex items-center gap-2 text-2xl text-cp-danger"><TriangleAlert size={24} />{AUDIENCE_TITLE[audience]} could not be drafted</h1><p className="mt-3 text-base leading-8">{documentError(item.error)}</p></section> : audience === 'patient' ? <PatientDocument item={item} /> : <LetterDocument item={item} />}</div>
      <ReviewPanel meeting={meeting} audience={audience} item={item} pending={pending} mutate={mutate} reviewer={reviewer} setReviewer={setReviewer} reviewRole={reviewRole} setReviewRole={setReviewRole} />
    </div>
  </div>;
}

function DocumentStamp({ item, text }: { item: Communication; text: { draft: string; approved: string } }) {
  const approved = item.status === 'APPROVED';
  return <p className={`mb-6 inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${approved ? 'border-cp-success' : 'border-cp-warning'}`}>{approved ? <Check size={15} className="text-cp-success" /> : <Flag size={15} className="text-cp-warning" />}{approved ? text.approved : text.draft}</p>;
}

function PatientDocument({ item }: { item: Communication }) {
  const text = PATIENT_LABELS[item.language] ?? PATIENT_LABELS.en;
  return <article data-testid="patient-document" lang={item.language} className="printable-document card mx-auto max-w-4xl p-7 sm:p-12">
    <DocumentStamp item={item} text={text} />
    <h1 className="text-4xl leading-tight">{item.title}</h1>
    {item.sections.map(section => <section key={section.id} className="mt-9"><h2 className="text-2xl text-cp-accent">{section.heading}</h2>{section.paragraphs.map((paragraph, index) => <p key={index} className="mt-4 text-lg leading-9">{paragraph}</p>)}{section.bullets.length > 0 && <ul className="mt-4 list-disc space-y-2 pl-6 text-lg leading-9">{section.bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}</ul>}</section>)}
    {item.questions_to_ask.length > 0 && <section className="mt-10 rounded-2xl bg-cp-accent-soft p-6"><h2 className="text-2xl">{text.questions}</h2><ul className="mt-4 list-disc space-y-3 pl-6 text-lg leading-8">{item.questions_to_ask.map((question, index) => <li key={index}>{question}</li>)}</ul></section>}
    {item.glossary.length > 0 && <section className="mt-10"><h2 className="text-2xl">{text.glossary}</h2><dl className="mt-4 grid gap-4 sm:grid-cols-2">{item.glossary.map(entry => <div key={entry.term} className="rounded-xl border border-cp-border p-4"><dt className="text-lg font-semibold"><dfn className="not-italic">{entry.term}</dfn></dt><dd className="mt-1 text-base leading-7">{entry.meaning}</dd></div>)}</dl></section>}
  </article>;
}

function LetterDocument({ item }: { item: Communication }) {
  return <article data-testid="letter-document" lang="en-GB" className="printable-document card mx-auto max-w-4xl p-7 sm:p-12">
    <DocumentStamp item={item} text={{ draft: 'Draft · not valid until signed off by a named clinician', approved: `Signed off by ${item.approved_by ?? 'a named clinician'}` }} />
    <h1 className="text-3xl">{outcomeText(item.title)}</h1>
    {item.sections.map(section => <section key={section.id} className="mt-8"><h2 className="border-b border-cp-border pb-2 text-lg uppercase tracking-wide text-cp-text-muted">{section.heading}</h2>{section.paragraphs.map((paragraph, index) => <p key={index} className="mt-3 text-base leading-8">{outcomeText(paragraph)}</p>)}{section.bullets.length > 0 && <ul className="mt-3 list-disc space-y-2 pl-6 text-base leading-8">{section.bullets.map((bullet, index) => <li key={index}>{outcomeText(bullet)}</li>)}</ul>}{section.rows.length > 0 && <div className="mt-3 overflow-x-auto"><table className="text-sm!"><thead><tr>{section.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{section.rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex} className="text-sm">{outcomeText(cell)}</td>)}</tr>)}</tbody></table></div>}</section>)}
  </article>;
}

function CheckRow({ label, value, ok, detail }: { label: string; value: ReactNode; ok: boolean; detail?: string }) {
  return <div className="flex items-start justify-between gap-3 border-b border-cp-border py-2 text-sm last:border-0"><span>{label}{detail && <small className="block text-[11px] text-cp-text-soft">{detail}</small>}</span><span className={`inline-flex items-center gap-1 text-right font-medium ${ok ? '' : 'text-cp-warning'}`}>{ok ? <Check size={14} className="text-cp-success" /> : <TriangleAlert size={14} />}{value}</span></div>;
}

function Checks({ item }: { item: Communication }) {
  const checks = item.checks;
  if (!checks) return null;
  const patient = item.audience === 'patient';
  const [low, high] = checks.word_target;
  const issues = [
    ...checks.unexplained_terms.map(term => `Unexplained term: ${term}`),
    ...checks.unsupported_numbers.map(number => `Number not found in the record: ${number}`),
    ...(checks.uncovered_refs.length ? [`${checks.uncovered_refs.length} plan item(s) not referenced`] : []),
    ...(checks.unknown_refs.length ? [`${checks.unknown_refs.length} reference(s) not in the record`] : []),
    ...(checks.unresolved_citations.length ? [`${checks.unresolved_citations.length} citation(s) not cited by the plan`] : []),
  ];
  return <section data-testid="document-checks" className="border-t border-cp-border pt-4"><h3>Automatic checks</h3><p className="mb-2 mt-1 text-xs leading-5 text-cp-text-muted">Advisory signals for the reviewer. They never approve a document.</p>
    {patient && <CheckRow label={checks.reading_formula} detail={`Target: ${checks.reading_target}`} value={checks.reading_ease} ok={checks.reading_ease >= 60} />}
    {patient && <CheckRow label="Written in" value={checks.detected_language ? languageLabel(checks.detected_language) : 'Not determined'} ok={!checks.detected_language || checks.detected_language === item.language} />}
    <CheckRow label="Length" detail={`Target ${low}–${high} words`} value={`${checks.word_count} words`} ok={checks.word_count >= low && checks.word_count <= high} />
    <CheckRow label="Longest sentence" value={`${checks.longest_sentence_words} words`} ok={!patient || checks.longest_sentence_words <= 30} />
    <CheckRow label="Grounding issues" value={issues.length || 'None'} ok={!issues.length} />
    {issues.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-cp-text-muted">{issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
  </section>;
}

function ReviewPanel({ meeting, audience, item, pending, mutate, reviewer, setReviewer, reviewRole, setReviewRole }: Omit<DocumentProps, 'back'>) {
  const [comment, setComment] = useState('');
  const plan = meeting.plan;
  const name = reviewer.trim();
  const ready = Boolean(item && plan && name && !pending);
  const body = (extra: Record<string, unknown> = {}) => ({ reviewer: name, role: reviewRole || null, ...(item && plan ? { plan_version: plan.version, revision: item.revision } : {}), ...extra });
  const send = async (action: 'approve' | 'request-changes' | 'regenerate', extra: Record<string, unknown> = {}) => {
    const payload = action === 'regenerate' ? { reviewer: name, role: reviewRole || null } : body(extra);
    if (await mutate(`communications/${audience}/${action}`, payload)) setComment('');
  };
  const canApprove = ready && item?.status === 'DRAFT';
  const canChange = ready && (item?.status === 'DRAFT' || item?.status === 'APPROVED') && Boolean(comment.trim());
  const canRegenerate = ready && (item?.status === 'FAILED' || item?.status === 'CHANGES_REQUESTED');
  return <aside data-testid="review-panel" aria-label="Clinician review" className="card space-y-4 p-5 xl:sticky xl:top-4 no-print">
    <div><p className="eyebrow">CLINICIAN REVIEW</p><h2 className="mt-1 text-xl">{DOCUMENT_NAME[audience]}</h2>{item && <div className="mt-2 flex flex-wrap gap-2"><Badge tone={STATUS_TONE[item.status]} pulse={item.status === 'DRAFTING'}>{documentStatus(item)}</Badge><Badge>Revision {item.revision}</Badge><Badge>Plan v{item.plan_version}</Badge><Badge tone="accent">{languageLabel(item.language)}</Badge></div>}{item?.status === 'APPROVED' && <p data-testid="approval-record" className="mt-3 flex items-center gap-2 rounded-lg border border-cp-success px-3 py-2 text-sm"><Check size={15} className="shrink-0 text-cp-success" /><span>Approved by <strong>{item.approved_by}</strong> · revision {item.approved_revision ?? item.revision} · {time(item.approved_at ?? item.updated_at)}</span></p>}</div>
    <p className="text-xs leading-6 text-cp-text-muted">Drafted by a language model from the recorded outcome of this {meeting.mode === 'azure' ? 'live' : 'demonstration'} meeting. It may contain errors. A named clinician must read and approve it before it is shared.</p>
    {item && <Checks item={item} />}
    <form className="space-y-3 border-t border-cp-border pt-4" onSubmit={event => { event.preventDefault(); if (canApprove) void send('approve', { comment: comment.trim() }); }}>
      <div><label htmlFor="reviewer-name">Reviewing clinician (name)</label><input data-testid="reviewer-name" id="reviewer-name" value={reviewer} maxLength={80} onChange={event => setReviewer(event.target.value)} placeholder="e.g. Dr J. de Vries" autoComplete="off" /></div>
      <div><label htmlFor="reviewer-role">Specialty <span className="text-cp-text-muted">(optional)</span></label><select id="reviewer-role" className="w-full" value={reviewRole} onChange={event => setReviewRole(event.target.value as Role | '')}><option value="">Not stated</option>{ROLES.map(role => <option key={role} value={role}>{ROLE_META[role].person}</option>)}</select></div>
      <div><label htmlFor="document-comment">Comment <span className="text-cp-text-muted">(required to request changes)</span></label><textarea data-testid="document-comment" id="document-comment" rows={3} maxLength={2000} value={comment} onChange={event => setComment(event.target.value)} placeholder="What should change in the next draft?" /></div>
      <div className="flex flex-wrap gap-2">
        <button data-testid="approve-document" type="submit" className="button primary flex-1" disabled={!canApprove}><Check size={15} />Approve</button>
        <button data-testid="request-changes" type="button" className="button secondary flex-1" disabled={!canChange} onClick={() => void send('request-changes', { comment: comment.trim() })}><Flag size={15} />Request changes</button>
      </div>
      {(item?.status === 'FAILED' || item?.status === 'CHANGES_REQUESTED') && <button data-testid="regenerate-document" type="button" className="button secondary w-full" disabled={!canRegenerate} onClick={() => void send('regenerate')}><RefreshCw size={15} />Regenerate draft</button>}
      {!name && <p className="text-xs text-cp-text-muted">Enter your name to approve or request changes.</p>}
    </form>
    {item && item.reviews.length > 0 && <details className="border-t border-cp-border pt-3"><summary>Review history ({item.reviews.length})</summary><ol className="space-y-2 text-xs leading-5">{item.reviews.slice().reverse().map((review, index) => <li key={index}><strong>{review.reviewer}</strong> · {review.action === 'approve' ? 'approved' : review.action === 'request_changes' ? 'requested changes' : 'regenerated'} revision {review.revision} · {time(review.timestamp)}{review.comment && <p className="text-cp-text-muted">{review.comment}</p>}</li>)}</ol></details>}
  </aside>;
}
