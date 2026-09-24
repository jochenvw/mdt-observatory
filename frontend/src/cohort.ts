import { request } from './api';

// Mirrors src/mdt/cohort.py. The cohort is descriptive context: it reports what
// comparable boards recorded, never what this board should decide.
export interface Subgroup { name: string; count: number; denominator: number; percentage: number }
export interface CohortSource { hospital: string; country: string; cases: number; completeness: string }
export interface CriterionReport {
  key: string; label: string; rule: string; tolerance: string; patient_value: string;
  values: string[]; status: string; enabled: boolean; automatic: boolean;
  reason: string; awaiting: string; exact: number; near: number; removed: number;
  not_recorded_in_cohort: number;
}
export interface DecisionSummary {
  category: string; label: string; count: number; denominator: number; percentage: number;
  interval_low: number; interval_high: number;
  by_hospital: Subgroup[]; by_country: Subgroup[]; by_period: Subgroup[];
}
export interface OutcomeSummary {
  measure: string; label: string; numerator: number; denominator: number; percentage: number;
  interval_low: number; interval_high: number; missing: number;
  followup_days_median: number | null; note: string;
}
export interface IntervalSummary {
  measure: string; label: string; recorded: number; denominator: number; missing: number;
  median_days: number | null; minimum_days: number | null; maximum_days: number | null; note: string;
}
export interface SiteVariation {
  site: string; country: string; cases: number; decisions: Subgroup[];
  outcome_completeness: string; data_notes: string[]; suppressed: boolean;
}
export interface ComparableCase {
  id: string; hospital: string; country: string; period: string; quality: 'EXACT' | 'NEAR';
  matched_on: string[]; similarities: string[]; differences: string[];
  evidence_completeness: string; decision: string; outcome: string; followup_days: number | null;
}
export interface CohortDefinition {
  case_id: string; criteria: string[]; criterion_values: Record<string, string[]>; resolved: string[];
  governed_total: number; matched: number; minimum_subgroup: number;
  date_range: string; refreshed: string; governance: string;
}
export interface Cohort {
  label: string; case_id: string; definition: CohortDefinition;
  governed_total: number; matched: number; match_percentage: number;
  exact_matches: number; near_matches: number;
  criteria: CriterionReport[]; ignored_criteria: string[];
  unavailable_in_case: string[]; unavailable_in_cohort: string[]; why_these_cases: string;
  sources: CohortSource[]; hospitals: number; countries: string[];
  date_range: string; refreshed: string;
  decisions: DecisionSummary[]; outcomes: OutcomeSummary[]; intervals: IntervalSummary[];
  variation: SiteVariation[]; cases: ComparableCase[];
  suppressed: boolean; warnings: string[]; synthetic: boolean;
}

// `criteria === null` asks the server for its automatic preselection; an empty list
// deliberately asks for the unrestricted governed cohort.
export function fetchCohort(caseId: string, criteria: string[] | null, resolved: string[], includeCases: boolean, signal?: AbortSignal): Promise<Cohort> {
  const query = new URLSearchParams();
  if (criteria !== null && criteria.length === 0) query.append('criteria', '');
  for (const key of criteria ?? []) query.append('criteria', key);
  for (const key of resolved) query.append('resolved', key);
  if (includeCases) query.set('include_cases', 'true');
  return request<Cohort>(`/cases/${encodeURIComponent(caseId)}/cohort?${query.toString()}`, undefined, signal);
}

// Counts and denominators stay attached to every percentage: a bar on its own
// cannot be quoted back into a discussion.
export function share(count: number, denominator: number): string {
  if (denominator <= 0) return 'No cases in the cohort';
  return `${count} of ${denominator} cases (${Math.round((count / denominator) * 1000) / 10}%)`;
}
export function interval(low: number, high: number): string {
  return `95% CI ${low}–${high}%`;
}
export function barWidth(percentage: number): string {
  return `${Math.max(0, Math.min(100, percentage))}%`;
}
export function days(value: number | null): string {
  return value === null ? 'Not recorded' : `${value} days`;
}
export function spread(summary: IntervalSummary): string {
  if (summary.median_days === null) return 'No records with this interval';
  return `median ${summary.median_days} days (range ${summary.minimum_days}–${summary.maximum_days})`;
}
export function criterionState(report: CriterionReport): string {
  if (report.status === 'AVAILABLE') return report.enabled ? 'Applied' : 'Available, not applied';
  if (report.status === 'PENDING') return 'Pending result — cannot be used';
  if (report.status === 'STALE') return 'Result too old — cannot be used';
  return 'Not recorded — cannot be used';
}
export function degraded(cohort: Cohort): string[] {
  return cohort.criteria
    .filter(report => report.status !== 'AVAILABLE')
    .map(report => `${report.label}: ${report.reason} The cohort is broader than requested.${report.awaiting ? ` ${report.awaiting}` : ''}`);
}
