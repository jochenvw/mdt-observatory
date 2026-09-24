import { useEffect, useState } from 'react';
import { CalendarClock, Languages, MonitorSmartphone, UserRound } from 'lucide-react';
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
