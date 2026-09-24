import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CohortView } from './SimilarCases';
import { criterionState, degraded, interval, share, spread } from './cohort';
import type { Cohort, CriterionReport } from './cohort';

function criterion(overrides: Partial<CriterionReport> = {}): CriterionReport {
  return {
    key: 'stage', label: 'Disease stage', rule: 'CATEGORY', tolerance: 'Same stage grouping',
    patient_value: 'Stage IV', values: ['Stage IV'], status: 'AVAILABLE', enabled: true,
    automatic: true, reason: '', awaiting: '', exact: 40, near: 4, removed: 12,
    not_recorded_in_cohort: 3, ...overrides,
  };
}
function cohortWith(overrides: Partial<Cohort> = {}): Cohort {
  return {
    label: 'Descriptive, not advisory', case_id: 'CASE-1',
    definition: {
      case_id: 'CASE-1', criteria: ['stage'], criterion_values: { stage: ['Stage IV'] }, resolved: [],
      governed_total: 400, matched: 44, minimum_subgroup: 15,
      date_range: '2019–2025', refreshed: '2026-08-01', governance: 'Synthetic demonstration cohort.',
    },
    governed_total: 400, matched: 44, match_percentage: 11, exact_matches: 8, near_matches: 36,
    criteria: [criterion(), criterion({ key: 'molecular_profile', label: 'Molecular profile', status: 'PENDING', enabled: false, reason: 'The extended panel is still pending.', awaiting: 'The pending molecular panel' })],
    ignored_criteria: ['Relevant comorbidities'], unavailable_in_case: ['Molecular profile'],
    unavailable_in_cohort: ['Prior procedures'],
    why_these_cases: 'These cases match on 1 criterion selected from the current record.',
    sources: [{ hospital: 'Northern University Hospital', country: 'Netherlands', cases: 200, completeness: 'high completeness' }],
    hospitals: 2, countries: ['Netherlands', 'Germany'], date_range: '2019–2025', refreshed: '2026-08-01',
    decisions: [{ category: 'additional_diagnostics_first', label: 'Additional diagnostics first', count: 13, denominator: 44, percentage: 29.5, interval_low: 18, interval_high: 44, by_hospital: [], by_country: [{ name: 'Netherlands', count: 9, denominator: 30, percentage: 30 }], by_period: [] }],
    outcomes: [{ measure: 'partial_response', label: 'Partial response', numerator: 9, denominator: 38, percentage: 23.7, interval_low: 13, interval_high: 39, missing: 6, followup_days_median: 420, note: '' }],
    intervals: [{ measure: 'time_to_next_treatment', label: 'Time to next treatment', recorded: 30, denominator: 44, missing: 14, median_days: 180, minimum_days: 40, maximum_days: 610, note: '' }],
    variation: [
      { site: 'Northern University Hospital', country: 'Netherlands', cases: 24, decisions: [{ name: 'Additional diagnostics first', count: 7, denominator: 24, percentage: 29.2 }], outcome_completeness: '22 of 24 cases with a recorded outcome', data_notes: [], suppressed: false },
      { site: 'Sites below the minimum subgroup size', country: 'Multiple', cases: 8, decisions: [], outcome_completeness: 'Not shown', data_notes: ['2 sites aggregated'], suppressed: true },
    ],
    cases: [{ id: 'SYN-NE-000010', hospital: 'Northern University Hospital', country: 'Netherlands', period: '2021–2022', quality: 'NEAR', matched_on: ['Disease stage'], similarities: ['Disease stage: Stage IV'], differences: ['Performance status not recorded'], evidence_completeness: '9 of 12 characteristics recorded', decision: 'Change systemic therapy', outcome: 'Stable disease', followup_days: 300 }],
    suppressed: false,
    warnings: ['Recorded outcomes are observational and are not caused by the recorded decision.'],
    synthetic: true, ...overrides,
  };
}
function view(cohort: Cohort) {
  return renderToStaticMarkup(<CohortView cohort={cohort} resolved={[]} toggle={() => {}} arrive={() => {}} quote={() => {}} />);
}

describe('cohort formatting', () => {
  it('keeps the count and denominator attached to every percentage', () => {
    expect(share(13, 44)).toBe('13 of 44 cases (29.5%)');
    expect(share(0, 0)).toBe('No cases in the cohort');
    expect(interval(18, 44)).toBe('95% CI 18–44%');
    expect(spread({ measure: 'x', label: 'x', recorded: 3, denominator: 5, missing: 2, median_days: 180, minimum_days: 40, maximum_days: 610, note: '' })).toBe('median 180 days (range 40–610)');
  });

  it('explains why an unusable characteristic was not matched on', () => {
    expect(criterionState(criterion())).toBe('Applied');
    expect(criterionState(criterion({ enabled: false }))).toBe('Available, not applied');
    expect(criterionState(criterion({ status: 'PENDING' }))).toBe('Pending result — cannot be used');
    expect(criterionState(criterion({ status: 'STALE' }))).toBe('Result too old — cannot be used');
    expect(criterionState(criterion({ status: 'MISSING' }))).toBe('Not recorded — cannot be used');
    const notes = degraded(cohortWith());
    expect(notes).toHaveLength(1);
    expect(notes[0]).toContain('The cohort is broader than requested.');
    expect(notes[0]).toContain('The pending molecular panel would narrow it.');
  });
});

describe('similar cases panel', () => {
  it('labels the feature as descriptive and never as advice', () => {
    const markup = view(cohortWith());
    expect(markup).toContain('data-testid="similar-cases"');
    expect(markup).toContain('Descriptive, not advisory');
    expect(markup).toContain('Synthetic demonstration cohort');
    expect(markup).toContain('Historical decisions and outcomes do not determine what is right for this patient');
    expect(markup).not.toMatch(/recommended treatment|best option|preferred option|we recommend|should receive/i);
  });

  it('shows cohort size, denominators, provenance and coverage', () => {
    const markup = view(cohortWith());
    expect(markup).toContain('of 400 governed records');
    expect(markup).toContain('13 of 44 cases (29.5%)');
    expect(markup).toContain('9 of 38 cases (23.7%)');
    expect(markup).toContain('6 missing or unevaluable');
    expect(markup).toContain('2019–2025');
    expect(markup).toContain('Northern University Hospital');
  });

  it('warns when a characteristic could not be used for matching', () => {
    const markup = view(cohortWith());
    expect(markup).toContain('data-testid="cohort-degraded"');
    expect(markup).toContain('Matching is degraded.');
    expect(markup).toContain('The extended panel is still pending.');
  });

  it('marks hospital variation as an observation and hides small subgroups', () => {
    const markup = view(cohortWith());
    expect(markup).toContain('not evidence that one site');
    expect(markup).toContain('Sites below the minimum subgroup size');
    expect(markup).toContain('Aggregated: below minimum subgroup size');
  });

  it('suppresses a cohort that is smaller than the minimum subgroup size', () => {
    const markup = view(cohortWith({ matched: 9, suppressed: true, decisions: [], outcomes: [], variation: [], cases: [] }));
    expect(markup).toContain('data-testid="cohort-suppressed"');
    expect(markup).toContain('Fewer than 15 comparable cases');
    expect(markup).toContain('No decisions can be shown for this cohort.');
    expect(markup).toContain('Individual records are not shown for this cohort.');
  });

  it('keeps comparable cases de-identified and explains each match', () => {
    const markup = view(cohortWith());
    expect(markup).toContain('SYN-NE-000010');
    expect(markup).toContain('Near match');
    expect(markup).toContain('2021–2022');
    // Only a synthetic identifier and a year range reach the screen: no dates of
    // birth, admission dates or direct identifiers that could rebuild a patient.
    expect(markup).not.toMatch(/2021-\d\d-\d\d/);
  });
});
