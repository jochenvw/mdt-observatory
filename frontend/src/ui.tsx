import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { Activity, ArrowUpRight, BookOpen, Check, ChevronRight, CircleDot, Heart, Microscope, ScanLine, Scissors, ShieldCheck, X } from 'lucide-react';
import { label, safeUrl, text } from './helpers';
import type { Data, Evidence, Meeting, Role } from './types';
import { clinicalCaseKind } from './caseProfiles';
import { clinicalActivity, clinicalData, clinicalItems, clinicalText, recordText, statusLabel } from './presentation';

export const ROLE_META = {
  radiology: { label: 'Radiology', person: 'Radiologist', short: 'RA', icon: ScanLine, description: 'Imaging & interval change', title: 'Imaging review and interval change assessment', prompt: 'Give growth kinetics more weight; distinguish growth from confirmed progression.' },
  oncology: { label: 'Oncology', person: 'Medical oncologist', short: 'ON', icon: Activity, description: 'Treatment & tolerability', title: 'Treatment strategy and tolerability review', prompt: 'Reassess the recommendation in light of previous toxicity and performance status.' },
  surgery: { label: 'Surgery', person: 'Surgeon', short: 'SU', icon: Scissors, description: 'Resectability & procedural risk', title: 'Resectability and procedural risk assessment', prompt: 'Clarify what must be confirmed before offering a local procedure.' },
  pathology: { label: 'Pathology', person: 'Pathologist', short: 'PA', icon: Microscope, description: 'Tissue & molecular findings', title: 'Tissue and molecular findings review', prompt: 'Distinguish confirmed tissue findings from assumptions that require a new biopsy.' },
  research: { label: 'Research', person: 'Evidence specialist', short: 'RE', icon: BookOpen, description: 'Evidence & patient applicability', title: 'Evidence review and patient applicability assessment', prompt: 'Prioritize European evidence and make population mismatch and access limits explicit.' },
  protocol: { label: 'Protocol', person: 'Guideline specialist', short: 'PR', icon: ShieldCheck, description: 'Dutch & European pathways', title: 'Guideline and care-pathway review', prompt: 'Check Dutch guidance first and flag protocol details that are not publicly accessible.' },
  patient: { label: 'Patient perspective', person: 'Patient advocate', short: 'PT', icon: Heart, description: 'Preferences & lived context', title: 'Patient goals and preferences review', prompt: 'Check that the plan reflects the patient’s stated priorities without inferring preferences.' },
} satisfies Record<Role, { label: string; person: string; short: string; icon: typeof Activity; description: string; title: string; prompt: string }>;

export function roleMetaFor(role: Role, meeting: Meeting | null) {
  const meta = ROLE_META[role];
  if (!meeting || !clinicalCaseKind(meeting.case)) return meta;
  const fallback = clinicalCaseKind(meeting.case) === 'pancreatic_perioperative' && role === 'surgery' ? 'Surgical / perioperative review' : meta.label;
  return { ...meta, label: recordText(meeting.roles[role]?.label || fallback) };
}

export function Badge({ children, tone = '', pulse = false }: { children: ReactNode; tone?: string; pulse?: boolean }) {
  const tones: Record<string, string> = {
    accent: 'border-cp-highlight! bg-cp-accent-soft! text-cp-accent!',
    success: 'border-cp-success! bg-cp-surface! text-cp-text!',
    warning: 'border-cp-warning! bg-cp-bg-elevated! text-cp-text!',
    danger: 'border-cp-danger! bg-cp-surface! text-cp-danger!',
  };
  return <span className={`badge inline-flex max-w-full items-center gap-1.5 rounded-md border border-cp-border bg-cp-surface-soft px-2 py-1 text-[10px] font-medium leading-snug text-cp-text-muted ${tones[tone] ?? ''}`}>{pulse && <span className="status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success pulse motion-safe:animate-pulse" />}{children}</span>;
}
export function Status({ value }: { value: string }) {
  const working = /ANALYZ|SEARCH|CHECK|REASSESS|RUNNING|WORKING|LOADING|START/i.test(value);
  const tone = /ERROR|FAIL|ESCALATE/i.test(value) ? 'danger' : /READY|PUBLISHED|COMPLETE|SUPPORT|CONCUR|CAPTURED/i.test(value) ? 'success' : /REVIEW|CONDITIONAL|UNCERTAIN/i.test(value) ? 'warning' : working ? 'accent' : '';
  return <Badge tone={tone} pulse={working}>{statusLabel(value)}</Badge>;
}
export function SectionHeading({ eyebrow, title, aside }: { eyebrow?: string; title: string; aside?: ReactNode }) {
  return <div className="section-heading mb-5 flex items-center justify-between gap-4 [&_.eyebrow]:mb-1 [&>svg]:text-[var(--cp-role,var(--cp-accent))]"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>{aside}</div>;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty flex items-center gap-3 py-5 text-sm leading-7 text-cp-text-soft [&_svg]:text-cp-border-strong"><CircleDot size={20} /><p>{children}</p></div>;
}
export function DataValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return value.length ? <ul className="data-list list-disc space-y-3 pl-5">{value.map((item, index) => <li key={index}><DataValue value={item} /></li>)}</ul> : <span className="muted text-sm leading-7 text-cp-text-muted">None recorded</span>;
  if (value !== null && typeof value === 'object') return <DataFields data={value as Data} compact />;
  return <span>{typeof value === 'string' ? clinicalText(value) : text(value)}</span>;
}
export function DataFields({ data, compact = false }: { data: Data; compact?: boolean }) {
  return <dl className={`data-fields mt-3 [&>div]:min-w-0 [&>div]:border-b [&>div]:border-cp-border [&>div]:py-3 [&>div:last-child]:border-0 [&_dt]:mb-1 [&_dt]:text-[10px] [&_dt]:font-medium [&_dt]:uppercase [&_dt]:tracking-wide [&_dt]:text-cp-text-soft [&_dd]:break-words [&_dd]:text-sm [&_dd]:leading-7 ${compact ? 'compact mt-0! [&>div]:grid [&>div]:grid-cols-[minmax(80px,0.7fr)_minmax(0,1.4fr)] [&>div]:gap-3 [&_dt]:normal-case! [&_dd]:text-xs!' : ''}`}>{Object.entries(clinicalData(data)).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd><DataValue value={value} /></dd></div>)}</dl>;
}
export function BulletList({ items, checked = false }: { items: string[]; checked?: boolean }) {
  return <ul className={`bullet-list my-2 flex list-none flex-col gap-2 [&>li]:flex [&>li]:items-start [&>li]:gap-2 [&>li]:text-xs [&>li]:leading-7 [&_svg]:mt-1.5 [&_svg]:text-cp-accent ${checked ? 'checked [&_svg]:text-cp-success!' : ''}`}>{clinicalItems(items).map((item, index) => <li key={index}>{checked ? <Check size={15} /> : <ChevronRight size={15} />}<span>{item}</span></li>)}</ul>;
}
export function Modal({ title, children, close, wide = false, testId }: { title: string; children: ReactNode; close: () => void; wide?: boolean; testId?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => { dialog?.close(); previous?.focus(); };
  }, []);
  return <dialog data-testid={testId} ref={ref} className={`drawer fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-dvh w-full max-w-[560px] overflow-y-auto border-0 border-l border-cp-border bg-cp-surface p-0 text-cp-text shadow-[var(--cp-shadow)] backdrop:bg-cp-overlay ${wide ? 'wide max-w-[720px]!' : ''}`} aria-label={title} onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="drawer-content min-h-full p-5 sm:p-7 [&>p]:my-4 [&>p]:leading-8 [&>h3]:my-5 [&>form]:mt-5"><div className="drawer-heading mb-6 flex items-center justify-between gap-4 border-b border-cp-border pb-5 [&_h2]:mt-1 [&_h2]:text-2xl"><div><p className="eyebrow">INSPECTABLE BY DESIGN</p><h2>{title}</h2></div><button className="icon-button" onClick={close} aria-label="Close panel"><X size={20} /></button></div>{children}</div>
  </dialog>;
}
export interface EvidenceSelection { ids: string[]; claim?: string }
export function EvidenceDrawer({ selection, evidence, close }: { selection: EvidenceSelection; evidence: Evidence[]; close: () => void }) {
  const sources = selection.ids.length ? selection.ids.map(id => evidence.find(item => item.id === id)) : evidence;
  return <Modal testId="source-drawer" title="Follow the evidence" close={close} wide>
    <div className="provenance-chain mb-5 flex items-center gap-2 text-[10px] uppercase tracking-wider text-cp-accent"><span>Claim</span><ChevronRight size={14} /><span>Evidence</span><ChevronRight size={14} /><span>Source & scrutiny</span></div>
    {selection.claim && <blockquote className="selected-claim text-lg! font-medium">{selection.claim}</blockquote>}
    {sources.length === 0 && <Empty>No evidence has been retrieved yet.</Empty>}
    {sources.map((source, index) => source ? <EvidenceDetail key={source.id} source={source} /> : <div className="alert" key={selection.ids[index]}>Source {recordText(selection.ids[index])} is not available in this snapshot. This claim cannot yet be verified.</div>)}
  </Modal>;
}
function EvidenceDetail({ source }: { source: Evidence }) {
  const url = safeUrl(source.url);
  return <article className="evidence-detail border-t border-cp-border py-6 [&>h3]:my-4 [&>h3]:text-xl [&>.muted]:text-xs [&>.button]:mt-4">
    <div className="row flex items-center gap-2 wrap flex-wrap"><Badge tone="accent">{source.region === 'US' ? 'US context · not EU standard' : source.region}</Badge><Badge>{label(source.kind)}</Badge><Badge tone={source.patient_match === 'HIGH' ? 'success' : 'warning'}>{label(source.patient_match)} patient match</Badge></div>
    <h3>{source.title}</h3><p className="muted text-sm leading-7 text-cp-text-muted">{source.authority} · {source.date} · {recordText(source.id)}</p>
    <div className="access-box my-4 flex items-start gap-3 rounded-xl border border-cp-border bg-cp-bg-elevated p-4 [&>svg]:text-cp-accent [&_strong]:text-xs [&_p]:mt-2 [&_p]:text-xs [&_p]:leading-7 [&_p]:text-cp-text-muted"><ShieldCheck size={19} /><div><strong>{label(source.access)}</strong><p>{source.access === 'PUBLIC_ABSTRACT_ONLY' ? 'Abstract only. Full text has not been retrieved.' : source.access === 'NOT_ACCESSIBLE' ? 'Source is not accessible. Do not interpret as verified full text.' : source.access === 'LICENSED_INTERNAL' ? 'Licensed/internal source; not publicly accessible.' : 'Public full-text access classification supplied by the evidence service.'}</p></div></div>
    <div className="row flex items-center gap-2 wrap flex-wrap"><Badge>{source.retrieval === 'CURATED' ? 'Curated evidence' : 'Recorded evidence source'}</Badge>{source.synthetic && <Badge tone="warning">Case record source</Badge>}</div>
    <h4>Supporting passage / data</h4><blockquote>{source.passage || 'No supporting passage was supplied.'}</blockquote>
    {Object.keys(source.scrutiny).length > 0 && <><h4>Critical appraisal</h4><DataFields data={source.scrutiny} compact /></>}
    {source.limitations.length > 0 && <><h4>Limitations & applicability</h4><BulletList items={source.limitations} /></>}
    {url ? <a className="button secondary" href={url} target="_blank" rel="noopener noreferrer">Open original source <ArrowUpRight size={16} /></a> : <p className="muted text-sm leading-7 text-cp-text-muted">No safe HTTPS source link available.</p>}
  </article>;
}
export function EvidenceTable({ evidence, inspect }: { evidence: Evidence[]; inspect: (selection: EvidenceSelection) => void }) {
  return evidence.length ? <div className="table-scroll relative max-w-full overflow-x-auto"><table><caption className="sr-only">Evidence sources, geographical context, access and patient applicability</caption><thead><tr><th>Source / study</th><th>Context</th><th>Access</th><th>Patient fit</th><th><span className="sr-only">Inspect</span></th></tr></thead><tbody>{evidence.map(source => <tr key={source.id}><td><strong>{source.title}</strong><small>{source.authority} · {source.date}</small></td><td><Badge>{source.region}</Badge></td><td>{label(source.access)}</td><td><Badge tone={source.patient_match === 'HIGH' ? 'success' : 'warning'}>{label(source.patient_match)}</Badge></td><td><button className="icon-button" aria-label={`Inspect ${source.title}`} onClick={() => inspect({ ids: [source.id] })}><ArrowUpRight size={18} /></button></td></tr>)}</tbody></table></div> : <Empty>Sources will appear as specialist agents retrieve and scrutinize evidence.</Empty>;
}
export function eventSummary(payload: Data, type: string, role?: Role): string {
  return clinicalActivity({ ...payload, type }, role).summary;
}
