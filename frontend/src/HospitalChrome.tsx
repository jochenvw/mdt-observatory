import { useEffect, useState } from 'react';
import { ArrowUpRight, CalendarClock, CircleHelp, ClipboardCheck, Languages, MonitorSmartphone, Stethoscope, UserRound } from 'lucide-react';
import { first } from './helpers';
import { ROLE_META } from './ui';
import { LANGUAGE_NAME } from './Outcome';
import { ROLES } from './types';
import type { Meeting, Role, Workspace } from './types';

// A fictional hospital so the demonstration reads as running inside a clinical information system.
export const HOSPITAL = {
  name: 'Westerpark University Medical Centre',
  department: 'Oncology Centre · Tumour board',
  room: 'MDT room 2.14',
};

const WORKSTATION: Record<Exclude<Workspace, Role>, string> = {
  join: 'Participant check-in',
  cases: 'Tumour board coordinator',
  central: 'MDT room display',
  chair: 'MDT chair',
  outcome: 'MDT chair · outcome',
  wall: 'MDT room display',
};

export function workstationLabel(workspace: Workspace): string {
  return ROLES.includes(workspace as Role) ? `${ROLE_META[workspace as Role].person} workstation` : WORKSTATION[workspace as Exclude<Workspace, Role>];
}

function useClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

/** Workstation and time in the hospital header, so each screen reads as a named clinical workstation. */
export function Workstation({ workspace }: { workspace: Workspace }) {
  const now = useClock();
  return <span data-testid="workstation" className="workstation flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
    <span className="flex items-center gap-1.5"><MonitorSmartphone size={13} className="text-cp-chrome-muted" /><span className="hidden text-cp-chrome-muted lg:inline">{HOSPITAL.room} ·</span><strong className="font-semibold">{workstationLabel(workspace)}</strong></span>
    <span className="hidden items-center gap-1.5 text-cp-chrome-muted sm:flex"><CalendarClock size={13} />{now.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })} · {now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
  </span>;
}

function sexAndAge(meeting: Meeting): string {
  const label = first(meeting.case, ['patient']).toLowerCase();
  const sex = /\b(woman|female)\b/.test(label) ? 'F' : /\b(man|male)\b/.test(label) ? 'M' : '';
  const age = first(meeting.case, ['age', 'age_years']);
  return [sex, age && `${age} y`].filter(Boolean).join(' · ');
}

/** EHR-style patient banner: who is on the table, in every workspace, from the case record only. */
export function PatientBanner({ meeting, showCase }: { meeting: Meeting; showCase: () => void }) {
  const data = meeting.case;
  const pseudonym = first(data, ['pseudonym', 'patient_id', 'id', 'case_id'], 'Case activating');
  const reference = first(data, ['id', 'case_id']);
  const diagnosis = first(data, ['diagnosis', 'disease']);
  const stage = first(data, ['stage', 'disease_stage']).split(';')[0];
  const performance = first(data, ['performance_status']).split(';')[0];
  const language = first(data, ['preferred_language'], 'en');
  const fields = [
    { label: 'Case ref', value: reference, compact: true },
    { label: 'Diagnosis', value: diagnosis, wide: true },
    { label: 'Stage', value: stage },
    { label: 'Performance', value: performance },
  ].filter(item => item.value);
  return <section data-testid="patient-banner" aria-label="Patient on the table" className="patient-banner flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-cp-border bg-cp-banner px-3 py-2 sm:px-6">
    <button className="flex items-center gap-3 border-0! bg-[inherit]! p-0 text-left" onClick={showCase} aria-label={`Open case record for ${pseudonym}`}>
      <span aria-hidden="true" className="flex size-9 items-center justify-center rounded-full bg-cp-chrome text-cp-chrome-fg"><UserRound size={19} /></span>
      <span><strong className="block text-base leading-tight">{pseudonym}</strong><small className="text-[11px] text-cp-text-muted">{sexAndAge(meeting) || 'Patient'} · fictional record</small></span>
    </button>
    {fields.map(item => <div key={item.label} className={`min-w-0 ${item.wide ? 'flex-[1_1_18rem]' : ''} ${item.compact ? 'max-sm:hidden' : ''}`}><span className="block text-[9px] font-semibold uppercase tracking-widest text-cp-text-soft">{item.label}</span><strong className={`block text-xs font-semibold ${item.wide ? 'line-clamp-1' : ''}`} title={item.value}>{item.value}</strong></div>)}
    <div data-testid="patient-language" className="flex items-center gap-2 rounded-md border border-cp-border bg-cp-surface px-2.5 py-1"><Languages size={15} className="text-cp-accent" /><span><span className="block text-[9px] font-semibold uppercase tracking-widest text-cp-text-soft">Speaks</span><strong className="block text-xs">{LANGUAGE_NAME[language] ?? language.toUpperCase()}</strong></span></div>
  </section>;
}

export function RoleCaseSummary({ meeting, showCase }: { meeting: Meeting; showCase: () => void }) {
  const data = meeting.case;
  const suppliedText = (keys: string[]): string => {
    for (const key of keys) {
      const value = data[key];
      if (typeof value === 'string' && value.trim()) return value;
      if (typeof value === 'number' && Number.isFinite(value)) return String(value);
    }
    return '';
  };
  const name = suppliedText(['pseudonym', 'patient_name', 'patient_id', 'id', 'case_id']) || 'Patient details in complete record';
  const patient = suppliedText(['patient']);
  const age = suppliedText(['age', 'age_years']);
  const diagnosis = suppliedText(['diagnosis', 'disease', 'summary']);
  const stage = suppliedText(['stage', 'disease_stage']);
  const performance = suppliedText(['performance_status']);
  const treatment = suppliedText(['treatment', 'treatment_history']);
  const previousTreatment = suppliedText(['previous_treatment']);
  const history = suppliedText(['history', 'important_history']);
  const question = suppliedText(['question', 'clinical_question', 'case_question', 'current_clinical_question'])
    || 'The shared decision question has not been recorded.';
  const patientSummary = [
    patient && patient !== name ? patient : '',
    age && !patient.includes(age) ? `${age}${/^\d+$/.test(age) ? ' years' : ''}` : '',
  ].filter(Boolean).join(' · ') || 'Open the complete record for supplied patient details.';
  const situation = [diagnosis, stage, performance].filter(Boolean).join(' · ')
    || 'The current clinical situation has not been summarized.';
  const completed = [...new Set([treatment, previousTreatment].filter(Boolean))].join(' · ') || history
    || 'No prior work or treatment has been summarized.';
  const items = [
    { label: 'Patient', value: patientSummary, icon: UserRound },
    { label: 'Current situation', value: situation, icon: Stethoscope },
    { label: 'What has been done', value: completed, icon: ClipboardCheck },
    { label: 'Question to resolve', value: question, icon: CircleHelp, emphasis: true },
  ];
  return <section data-testid="role-case-summary" aria-label="Case briefing for this specialty" className="mb-4 overflow-hidden rounded-2xl border border-cp-border bg-cp-surface">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-cp-border px-4 py-3 sm:px-5">
      <div><p className="eyebrow text-[var(--cp-role,var(--cp-accent))]!">CASE BRIEFING</p><h2 className="mt-1 text-base">{name}</h2></div>
      <button data-testid="view-role-case-record" className="text-button" onClick={showCase}>View case record <ArrowUpRight size={14} /></button>
    </header>
    <div aria-label="Case briefing sections" className="grid auto-cols-[minmax(16rem,85vw)] grid-flow-col overflow-x-auto md:auto-cols-auto md:grid-flow-row md:grid-cols-2 md:overflow-visible xl:grid-cols-4">
      {items.map(({ label, value, icon: Icon, emphasis }) => <article key={label} className={`min-w-0 border-l border-t border-cp-border p-4 first:border-l-0 ${emphasis ? 'bg-[color-mix(in_srgb,var(--cp-role,var(--cp-accent))_8%,var(--cp-surface))]' : ''}`}>
        <div className="mb-2 flex items-center gap-2 text-[var(--cp-role,var(--cp-accent))]"><Icon size={16} /><h3 className="font-mono text-[10px] uppercase tracking-widest">{label}</h3></div>
        <p className={`line-clamp-4 break-words text-[13px] leading-6 md:line-clamp-none ${emphasis ? 'font-medium text-cp-text' : 'text-cp-text-muted'}`}>{value}</p>
      </article>)}
    </div>
  </section>;
}
