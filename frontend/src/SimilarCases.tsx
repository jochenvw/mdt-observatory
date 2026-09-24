import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { AlertTriangle, Info, Quote, RefreshCw, Users } from 'lucide-react';
import { Badge, Empty, SectionHeading } from './ui';
import type { Cohort, ComparableCase, CriterionReport, DecisionSummary, SiteVariation } from './cohort';
import { barWidth, criterionState, degraded, fetchCohort, interval, share, spread } from './cohort';

interface Props {
  caseId: string;
  quote?: (reference: string, criteria: string[] | null, resolved: string[]) => void;
  pending?: boolean;
}

// Similar cases is read-only clinical context. Nothing here changes the meeting
// unless a clinician explicitly quotes a finding into the discussion.
export function SimilarCases({ caseId, quote, pending = false }: Props) {
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [criteria, setCriteria] = useState<string[] | null>(null);
  const [resolved, setResolved] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openCase, setOpenCase] = useState<string | null>(null);

  useEffect(() => { setCriteria(null); setResolved([]); setCohort(null); }, [caseId]);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    return fetchCohort(caseId, criteria, resolved, true, signal)
      .then(result => { if (!signal?.aborted) { setCohort(result); setError(null); } })
      .catch(cause => { if (!signal?.aborted) setError(cause instanceof Error ? cause.message : 'The historical cohort could not be loaded.'); })
      .finally(() => { if (!signal?.aborted) setLoading(false); });
  }, [caseId, criteria, resolved]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  function toggle(report: CriterionReport) {
    const active = cohort ? cohort.definition.criteria : [];
    setCriteria(report.enabled ? active.filter(key => key !== report.key) : [...active, report.key]);
  }
  // A result arriving recalculates immediately; an explicitly chosen criteria set
  // gains the characteristic that was previously unusable.
  function arrive(report: CriterionReport) {
    setResolved(current => current.includes(report.key) ? current : [...current, report.key]);
    setCriteria(current => current === null || current.includes(report.key) ? current : [...current, report.key]);
  }

  if (error) return <section data-testid="similar-cases"><SectionHeading eyebrow="SIMILAR CASES" title="Comparable historical cases" /><div className="alert">{error}</div></section>;
  if (!cohort) return <section data-testid="similar-cases"><SectionHeading eyebrow="SIMILAR CASES" title="Comparable historical cases" /><Empty>Matching the current case against the governed historical cohort…</Empty></section>;
  return <CohortView cohort={cohort} loading={loading} resolved={resolved} toggle={toggle} arrive={arrive} quote={quote} pending={pending} openCase={openCase} setOpenCase={setOpenCase} />;
}

interface ViewProps {
  cohort: Cohort;
  loading?: boolean;
  resolved: string[];
  toggle: (report: CriterionReport) => void;
  arrive: (report: CriterionReport) => void;
  quote?: (reference: string, criteria: string[] | null, resolved: string[]) => void;
  pending?: boolean;
  openCase?: string | null;
  setOpenCase?: (update: (current: string | null) => string | null) => void;
}

export function CohortView({ cohort, loading = false, resolved, toggle, arrive, quote, pending = false, openCase = null, setOpenCase = () => {} }: ViewProps) {
  const missing = degraded(cohort);
  return <section data-testid="similar-cases" className="mb-5">
    <SectionHeading eyebrow="SIMILAR CASES" title="What comparable boards recorded" aside={<div className="row flex flex-wrap items-center gap-2"><Badge tone="warning">{cohort.label}</Badge>{cohort.synthetic && <Badge>Synthetic demonstration cohort</Badge>}</div>} />
    <p className="mb-4 max-w-3xl text-sm leading-7 text-cp-text-muted">Historical decisions and outcomes do not determine what is right for this patient. Nothing here is ranked, preferred or recommended, and outcomes are observational.</p>

    <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4 [&>div]:rounded-xl [&>div]:border [&>div]:border-cp-border [&>div]:bg-cp-surface [&>div]:p-4 [&_dt]:text-[10px] [&_dt]:uppercase [&_dt]:tracking-wide [&_dt]:text-cp-text-soft [&_dd]:mt-1 [&_dd]:text-sm [&_dd]:leading-7">
      <div><dt>Matching cases</dt><dd data-testid="cohort-matched"><strong className="text-xl">{cohort.matched}</strong> of {cohort.governed_total} governed records ({cohort.match_percentage}%)</dd></div>
      <div><dt>Active criteria</dt><dd>{cohort.definition.criteria.length} applied · {cohort.exact_matches} exact, {cohort.near_matches} near matches</dd></div>
      <div><dt>Data sources</dt><dd>{cohort.hospitals} hospitals · {cohort.countries.join(', ')}</dd></div>
      <div><dt>Coverage</dt><dd>{cohort.date_range} · cohort refreshed {cohort.refreshed}</dd></div>
    </div>

    {missing.length > 0 && <div data-testid="cohort-degraded" className="alert mb-5"><strong>Matching is degraded.</strong><ul className="mt-2 list-disc space-y-2 pl-5 text-xs leading-7">{missing.map(note => <li key={note}>{note}</li>)}</ul></div>}
    {cohort.suppressed && <div data-testid="cohort-suppressed" className="alert mb-5"><AlertTriangle size={16} /> Fewer than {cohort.definition.minimum_subgroup} comparable cases remain. Results are suppressed to prevent identification and over-reading of a very small group.</div>}

    <details className="mb-5 rounded-xl border border-cp-border bg-cp-surface p-4" data-testid="cohort-criteria">
      <summary>Why these cases? Matching criteria and their effect</summary>
      <p className="my-3 text-xs leading-7 text-cp-text-muted">{cohort.why_these_cases}</p>
      <div className="table-scroll relative max-w-full overflow-x-auto"><table><caption className="sr-only">Matching criteria, patient values, tolerance and effect on the cohort</caption>
        <thead><tr><th>Criterion</th><th>Value in this case</th><th>Rule and tolerance</th><th>Effect</th><th><span className="sr-only">Apply</span></th></tr></thead>
        <tbody>{cohort.criteria.map(report => <tr key={report.key}>
          <td><strong>{report.label}</strong><small>{criterionState(report)}</small></td>
          <td>{report.patient_value}{report.reason && <small>{report.reason}</small>}</td>
          <td>{report.rule.toLowerCase()} · {report.tolerance}</td>
          <td>{report.enabled ? `${report.exact} exact, ${report.near} near · removes ${report.removed} · ${report.not_recorded_in_cohort} not recorded historically` : 'Not applied to this cohort'}</td>
          <td>{report.status === 'AVAILABLE'
            ? <button className="text-button" disabled={loading} onClick={() => toggle(report)}>{report.enabled ? 'Remove' : 'Add'}</button>
            : report.awaiting ? <button className="text-button" disabled={loading || resolved.includes(report.key)} onClick={() => arrive(report)}><RefreshCw size={13} />{resolved.includes(report.key) ? 'Result applied' : 'Result arrived'}</button> : <span className="muted text-xs text-cp-text-soft">Unavailable</span>}</td>
        </tr>)}</tbody></table></div>
      {cohort.unavailable_in_cohort.length > 0 && <p className="mt-3 text-xs leading-7 text-cp-text-muted">Not recorded in the historical cohort: {cohort.unavailable_in_cohort.join(', ')}.</p>}
      {cohort.ignored_criteria.length > 0 && <p className="mt-1 text-xs leading-7 text-cp-text-muted">Available but not applied: {cohort.ignored_criteria.join(', ')}.</p>}
    </details>

    <div className="grid items-start gap-4 lg:grid-cols-2">
      <Panel title="Decisions recorded by comparable boards" testId="cohort-decisions">
        {cohort.decisions.length === 0 ? <Empty>No decisions can be shown for this cohort.</Empty> : cohort.decisions.map(item => <Bar key={item.category} item={item} quote={quote && (() => quote(`decision:${item.category}`, cohort.definition.criteria, resolved))} pending={pending} />)}
      </Panel>
      <Panel title="Recorded outcomes (observational)" testId="cohort-outcomes">
        {cohort.outcomes.length === 0 ? <Empty>No outcomes can be shown for this cohort.</Empty> : <>
          <ul className="flex list-none flex-col gap-3">{cohort.outcomes.map(item => <li key={item.measure} className="border-b border-cp-border pb-3 last:border-0">
            <div className="flex items-start justify-between gap-3"><strong className="text-xs">{item.label}</strong>{quote && <button className="text-button" disabled={pending} onClick={() => quote(`outcome:${item.measure}`, cohort.definition.criteria, resolved)} aria-label={`Quote ${item.label} in the discussion`}><Quote size={13} />Quote</button>}</div>
            <p className="mt-1 text-xs leading-7 text-cp-text-muted">{share(item.numerator, item.denominator)} · {interval(item.interval_low, item.interval_high)} · {item.missing} missing or unevaluable{item.followup_days_median === null ? '' : ` · median follow-up ${item.followup_days_median} days`}</p>
          </li>)}</ul>
          <ul className="mt-3 flex list-none flex-col gap-2 text-xs leading-7 text-cp-text-muted">{cohort.intervals.map(item => <li key={item.measure}><strong>{item.label}:</strong> {spread(item)} · recorded for {item.recorded} of {item.denominator} cases{item.note ? ` · ${item.note}` : ''}</li>)}</ul>
        </>}
      </Panel>
    </div>

    <Panel title="Variation between participating hospitals" testId="cohort-variation">
      <p className="mb-3 text-xs leading-7 text-cp-text-muted">An observation about recorded practice, not evidence that one site’s approach is better. Sites below the minimum subgroup size are not shown separately.</p>
      {cohort.variation.length === 0 ? <Empty>No site can be shown at the configured minimum subgroup size.</Empty> : <ul className="flex list-none flex-col gap-3">{cohort.variation.map(site => <Site key={site.site} site={site} />)}</ul>}
    </Panel>

    <Panel title="De-identified comparable cases" testId="cohort-cases">
      {cohort.cases.length === 0 ? <Empty>Individual records are not shown for this cohort.</Empty> : <ul className="flex list-none flex-col gap-2">{cohort.cases.map(record => <Case key={record.id} record={record} open={openCase === record.id} toggle={() => setOpenCase(current => current === record.id ? null : record.id)} />)}</ul>}
    </Panel>

    <div className="mt-4 rounded-xl border border-cp-border bg-cp-bg-elevated p-4 text-xs leading-7 text-cp-text-muted" data-testid="cohort-warnings">
      <p className="flex items-center gap-2 text-cp-text"><Info size={15} />How to read this cohort</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">{cohort.warnings.map(note => <li key={note}>{note}</li>)}</ul>
      <p className="mt-2">Cohort definition: {cohort.definition.criteria.length} {cohort.definition.criteria.length === 1 ? 'criterion' : 'criteria'} over {cohort.definition.governed_total} governed records, {cohort.definition.date_range}, refreshed {cohort.definition.refreshed}. {cohort.definition.governance}</p>
      <ul className="mt-2 list-none space-y-1">{cohort.sources.map(source => <li key={source.hospital}><Users size={12} /> {source.hospital} ({source.country}) · {source.cases} governed records · {source.completeness}</li>)}</ul>
    </div>
  </section>;
}

function Panel({ title, testId, children }: { title: string; testId: string; children: ReactNode }) {
  return <section data-testid={testId} className="mt-4 rounded-xl border border-cp-border bg-cp-surface p-4"><h3 className="mb-3 text-sm">{title}</h3>{children}</section>;
}

function Bar({ item, quote, pending }: { item: DecisionSummary; quote?: () => void; pending?: boolean }) {
  return <div className="mb-3 last:mb-0">
    <div className="flex items-start justify-between gap-3"><strong className="text-xs">{item.label}</strong>{quote && <button className="text-button" disabled={pending} onClick={quote} aria-label={`Quote ${item.label} in the discussion`}><Quote size={13} />Quote</button>}</div>
    <div className="mt-1 h-2 w-full rounded-full bg-cp-surface-soft"><div className="h-2 rounded-full bg-cp-accent" style={{ width: barWidth(item.percentage) }} role="presentation" /></div>
    <p className="mt-1 text-xs leading-7 text-cp-text-muted">{share(item.count, item.denominator)} · {interval(item.interval_low, item.interval_high)}</p>
    {item.by_country.length > 0 && <p className="text-xs leading-7 text-cp-text-soft">By country: {item.by_country.map(group => `${group.name} ${group.count}/${group.denominator}`).join(' · ')}</p>}
  </div>;
}

function Site({ site }: { site: SiteVariation }) {
  return <li className="border-b border-cp-border pb-3 last:border-0">
    <div className="flex flex-wrap items-center gap-2"><strong className="text-xs">{site.site}</strong><Badge>{site.country}</Badge><Badge>{site.cases} matching cases</Badge>{site.suppressed && <Badge tone="warning">Aggregated: below minimum subgroup size</Badge>}</div>
    {!site.suppressed && <p className="mt-1 text-xs leading-7 text-cp-text-muted">{site.decisions.map(group => `${group.name}: ${group.count}/${group.denominator}`).join(' · ') || 'No decision categories recorded.'}</p>}
    <p className="text-xs leading-7 text-cp-text-soft">Outcome completeness: {site.outcome_completeness}{site.data_notes.length > 0 ? ` · ${site.data_notes.join(' · ')}` : ''}</p>
  </li>;
}

function Case({ record, open, toggle }: { record: ComparableCase; open: boolean; toggle: () => void }) {
  return <li className="rounded-lg border border-cp-border p-3">
    <button className="text-button" onClick={toggle} aria-expanded={open}><strong>{record.id}</strong> · {record.quality === 'EXACT' ? 'Exact match' : 'Near match'} · {record.period}</button>
    {open && <div className="mt-2 text-xs leading-7 text-cp-text-muted">
      <p><strong>Matched on:</strong> {record.matched_on.join(', ')}</p>
      <p><strong>Similarities:</strong> {record.similarities.join(' · ') || 'None recorded'}</p>
      <p><strong>Differences:</strong> {record.differences.join(' · ') || 'None recorded'}</p>
      <p><strong>Evidence completeness:</strong> {record.evidence_completeness}</p>
      <p><strong>Recorded decision:</strong> {record.decision}</p>
      <p><strong>Recorded outcome:</strong> {record.outcome}{record.followup_days === null ? '' : ` · ${record.followup_days} days follow-up`}</p>
      <p><strong>Source:</strong> {record.hospital}, {record.country}, {record.period}</p>
    </div>}
  </li>;
}
