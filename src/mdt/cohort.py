"""Descriptive similar-case comparison over a governed historical cohort.

The cohort answers "what did comparable boards record?" and never "what should
this patient receive?". Every published number keeps its numerator, denominator,
cohort definition and provenance, matching is explained criterion by criterion,
and characteristics the current case does not have are disabled rather than
silently matched or read as negative findings.
"""

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from math import sqrt
from typing import Literal, Self

from pydantic import Field, model_validator

from mdt.models import Contract

Availability = Literal["AVAILABLE", "PENDING", "STALE", "MISSING"]
Verdict = Literal["EXACT", "NEAR", "DIFFERENT", "NOT_RECORDED"]

# Default suppression threshold; deployments override it with
# MDT_COHORT_MINIMUM_SUBGROUP (see Settings.cohort_minimum_subgroup).
MINIMUM_SUBGROUP = 15
CASE_SAMPLE_LIMIT = 12
LABEL = "Descriptive, not advisory"
DATE_RANGE = "January 2019 – December 2025"
REFRESHED = "2026-05-01"
GOVERNANCE = (
    "Synthetic governed cohort assembled for demonstration; not clinical evidence "
    "and not derived from real patient records."
)
STANDING_WARNINGS = (
    "Descriptive, not advisory: this comparison describes what comparable boards "
    "recorded and never recommends, ranks or endorses a treatment.",
    "Historical decisions do not determine what is right for the current patient.",
    "Recorded decisions and recorded outcomes are separate observations; no causal "
    "link between them is implied.",
    "Participating sites differ in completeness, follow-up length and referral "
    "patterns, so selection bias and differential follow-up are expected.",
)


@dataclass(frozen=True)
class Criterion:
    """One matching characteristic, its rule and the tolerance it allows."""

    key: str
    label: str
    rule: Literal["EXACT", "CATEGORY", "BAND", "OVERLAP"]
    tolerance: str
    automatic: bool = True


CRITERIA: tuple[Criterion, ...] = (
    Criterion("cancer_type", "Cancer type", "EXACT", "Identical tumour type; no substitution."),
    Criterion("primary_site", "Primary site", "CATEGORY", "Same recorded primary-site category."),
    Criterion("stage", "Disease stage", "CATEGORY", "Same recorded stage group."),
    Criterion(
        "metastatic_sites", "Metastatic sites", "OVERLAP",
        "At least one shared metastatic site; an identical set counts as an exact match.",
    ),
    Criterion(
        "metastatic_burden", "Metastatic burden", "CATEGORY", "Same recorded burden category.",
    ),
    Criterion(
        "molecular_profile", "Molecular profile and biomarkers", "OVERLAP",
        "At least one shared reported marker state; an identical set counts as exact.",
    ),
    Criterion(
        "performance_status", "Performance status", "BAND",
        "Same recorded ECOG value; one adjacent point counts as a near match.",
    ),
    Criterion(
        "age_band", "Age band", "BAND",
        "Same ten-year band; one adjacent band counts as a near match.",
    ),
    Criterion(
        "previous_lines", "Previous treatment lines", "BAND",
        "Same number of recorded previous lines; one line difference is a near match.",
    ),
    Criterion(
        "prior_procedures", "Prior procedures", "OVERLAP",
        "At least one shared recorded procedure.", automatic=False,
    ),
    Criterion(
        "comorbidities", "Relevant comorbidities", "OVERLAP",
        "At least one shared recorded comorbidity.", automatic=False,
    ),
    Criterion(
        "decision_point", "Current decision point", "EXACT",
        "Identical recorded board decision point.",
    ),
)
CRITERION_BY_KEY = {item.key: item for item in CRITERIA}

DECISIONS: tuple[tuple[str, str], ...] = (
    ("continue_current_treatment", "Continue current treatment"),
    ("change_systemic_therapy", "Change systemic therapy"),
    ("additional_diagnostics_first", "Additional diagnostics first"),
    ("surgery_or_local_intervention", "Surgery or local intervention"),
    ("clinical_trial_enrolment", "Clinical-trial enrolment"),
    ("radiation_therapy", "Radiation therapy"),
    ("best_supportive_care", "Best supportive care"),
    ("defer_to_later_mdt", "Defer to a later MDT"),
)
DECISION_LABELS = dict(DECISIONS)
RESPONSES: tuple[tuple[str, str], ...] = (
    ("complete_response", "Complete response"),
    ("partial_response", "Partial response"),
    ("stable_disease", "Stable disease"),
    ("progressive_disease", "Progressive disease"),
    ("not_evaluable", "Not evaluable"),
)
RESPONSE_LABELS = dict(RESPONSES)


class Characteristic(Contract):
    """A current-case characteristic offered to matching, with its availability."""

    values: list[str] = Field(default_factory=list)
    status: Availability = "AVAILABLE"
    display: str = ""
    reason: str = ""
    awaiting: str = ""
    # Value the characteristic takes once the awaited result is recorded. Supplied by
    # the case record so a pending result arriving recalculates from case data only.
    pending_values: list[str] = Field(default_factory=list)


class CohortProfile(Contract):
    """Matching characteristics published by one case record."""

    characteristics: dict[str, Characteristic] = Field(default_factory=dict)

    @model_validator(mode="after")
    def known_characteristics(self) -> Self:
        unknown = set(self.characteristics) - set(CRITERION_BY_KEY)
        if unknown:
            raise ValueError(f"Unknown cohort characteristics: {sorted(unknown)}")
        for key, item in self.characteristics.items():
            if item.status == "AVAILABLE" and not item.values:
                raise ValueError(f"Available characteristic {key} needs a value.")
            if item.status != "AVAILABLE" and not item.reason:
                raise ValueError(f"Unavailable characteristic {key} needs an explanation.")
        return self


class CohortCase(Contract):
    """One de-identified historical record. No direct identifiers are stored."""

    id: str
    hospital: str
    country: str
    period: str
    characteristics: dict[str, list[str]]
    decision: str
    outcome: str
    time_to_next_treatment_days: int | None = None
    time_to_progression_days: int | None = None
    rediscussed: bool | None = None
    discontinued: bool | None = None
    followup_days: int | None = None
    synthetic: bool = True


class CohortSource(Contract):
    hospital: str
    country: str
    cases: int
    completeness: str


class Subgroup(Contract):
    name: str
    count: int
    denominator: int
    percentage: float


class CriterionReport(Contract):
    key: str
    label: str
    rule: str
    tolerance: str
    patient_value: str
    values: list[str]
    status: Availability
    enabled: bool
    automatic: bool
    reason: str = ""
    awaiting: str = ""
    exact: int = 0
    near: int = 0
    removed: int = 0
    not_recorded_in_cohort: int = 0


class DecisionSummary(Contract):
    category: str
    label: str
    count: int
    denominator: int
    percentage: float
    interval_low: float
    interval_high: float
    by_hospital: list[Subgroup] = Field(default_factory=list)
    by_country: list[Subgroup] = Field(default_factory=list)
    by_period: list[Subgroup] = Field(default_factory=list)


class OutcomeSummary(Contract):
    measure: str
    label: str
    numerator: int
    denominator: int
    percentage: float
    interval_low: float
    interval_high: float
    missing: int
    followup_days_median: int | None = None
    note: str = ""


class IntervalSummary(Contract):
    measure: str
    label: str
    recorded: int
    denominator: int
    missing: int
    median_days: int | None = None
    minimum_days: int | None = None
    maximum_days: int | None = None
    note: str = ""


class SiteVariation(Contract):
    site: str
    country: str
    cases: int
    decisions: list[Subgroup] = Field(default_factory=list)
    outcome_completeness: str = ""
    data_notes: list[str] = Field(default_factory=list)
    suppressed: bool = False


class ComparableCase(Contract):
    id: str
    hospital: str
    country: str
    period: str
    quality: Literal["EXACT", "NEAR"]
    matched_on: list[str]
    similarities: list[str]
    differences: list[str]
    evidence_completeness: str
    decision: str
    outcome: str
    followup_days: int | None = None


class CohortDefinition(Contract):
    case_id: str
    criteria: list[str]
    criterion_values: dict[str, list[str]]
    resolved: list[str] = Field(default_factory=list)
    governed_total: int
    matched: int
    minimum_subgroup: int
    date_range: str = DATE_RANGE
    refreshed: str = REFRESHED
    governance: str = GOVERNANCE


class CohortResult(Contract):
    label: str = LABEL
    case_id: str
    definition: CohortDefinition
    governed_total: int
    matched: int
    match_percentage: float
    exact_matches: int
    near_matches: int
    criteria: list[CriterionReport]
    ignored_criteria: list[str]
    unavailable_in_case: list[str]
    unavailable_in_cohort: list[str]
    why_these_cases: str
    sources: list[CohortSource]
    hospitals: int
    countries: list[str]
    date_range: str = DATE_RANGE
    refreshed: str = REFRESHED
    decisions: list[DecisionSummary] = Field(default_factory=list)
    outcomes: list[OutcomeSummary] = Field(default_factory=list)
    intervals: list[IntervalSummary] = Field(default_factory=list)
    variation: list[SiteVariation] = Field(default_factory=list)
    cases: list[ComparableCase] = Field(default_factory=list)
    suppressed: bool = False
    warnings: list[str] = Field(default_factory=list)
    synthetic: bool = True


def _unit(*parts: object) -> float:
    """Deterministic value in [0, 1) derived only from the supplied parts."""
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _weighted(options: Sequence[tuple[str, float]], *parts: object) -> str:
    total = sum(weight for _, weight in options)
    draw = _unit(*parts) * total
    for value, weight in options:
        draw -= weight
        if draw < 0:
            return value
    return options[-1][0]


def _subset(options: Sequence[tuple[str, float]], *parts: object) -> list[str]:
    chosen = [value for value, weight in options if _unit(*parts, value) < weight]
    return chosen or [_weighted(options, *parts, "fallback")]


def _span(low: int, high: int, *parts: object) -> int:
    return low + int(_unit(*parts) * (high - low + 1))


HOSPITALS: tuple[tuple[str, str, int, float, str], ...] = (
    ("Northern University Hospital", "Netherlands", 1000, 0.95, "High record completeness"),
    ("Riverside Cancer Centre", "Netherlands", 760, 0.82, "Molecular results often absent"),
    ("Rheintal Klinikum", "Germany", 680, 0.88, "Complete decisions, shorter follow-up"),
    ("Ostend Regional Hospital", "Belgium", 580, 0.72, "Outcome follow-up frequently missing"),
    ("Hôpital Saint-Cyr", "France", 480, 0.63, "Sparse molecular and burden recording"),
    ("Coastal District Hospital", "Ireland", 96, 0.55, "Small site; most fields incomplete"),
)
PERIODS = ("2019–2020", "2021–2022", "2023–2024", "2025")

_VALUES: dict[str, dict[str, tuple[tuple[str, float], ...]]] = {
    "colorectal": {
        "primary_site": (("Right-sided colon", 0.35), ("Left-sided colon", 0.4), ("Rectum", 0.25)),
        "stage": (("Stage IV", 0.72), ("Stage III", 0.28)),
        "metastatic_sites": (("Liver", 0.8), ("Lung", 0.3), ("Peritoneum", 0.18), ("Nodal", 0.2)),
        "metastatic_burden": (
            ("Oligometastatic", 0.38), ("Multifocal", 0.42), ("Widespread", 0.2),
        ),
        "molecular_profile": (
            ("RAS wild type", 0.45), ("RAS mutated", 0.4), ("BRAF V600E", 0.16),
            ("pMMR / MSS", 0.85), ("dMMR / MSI-high", 0.08), ("HER2 not amplified", 0.5),
        ),
        "performance_status": (("ECOG 0", 0.34), ("ECOG 1", 0.46), ("ECOG 2", 0.2)),
        "prior_procedures": (
            ("Primary tumour resection", 0.4), ("Liver resection", 0.18),
            ("Ablation", 0.12), ("Diverting stoma or stent", 0.14),
        ),
        "decision_point": (
            ("Post-induction local-treatment review", 0.42),
            ("Progression review", 0.3),
            ("Postoperative strategy review", 0.16),
            ("Perioperative fitness review", 0.12),
        ),
    },
    "pancreatic": {
        "primary_site": (("Pancreatic head", 0.68), ("Pancreatic body or tail", 0.32)),
        "stage": (("Stage IIB", 0.46), ("Stage III", 0.34), ("Stage IV", 0.2)),
        "metastatic_sites": (("No distant site recorded", 0.7), ("Liver", 0.3), ("Lung", 0.1)),
        "metastatic_burden": (
            ("No metastatic disease recorded", 0.62), ("Oligometastatic", 0.24),
            ("Multifocal", 0.14),
        ),
        "molecular_profile": (
            ("KRAS G12D", 0.5), ("KRAS other variant", 0.3), ("TP53 mutated", 0.6),
            ("SMAD4 retained", 0.4), ("Mismatch-repair proficient", 0.8),
            ("No BRCA1/2 or PALB2 variant", 0.55),
        ),
        "performance_status": (("ECOG 0", 0.26), ("ECOG 1", 0.5), ("ECOG 2", 0.24)),
        "prior_procedures": (
            ("Biliary stent", 0.45), ("Diagnostic laparoscopy", 0.18),
            ("Pancreaticoduodenectomy", 0.12),
        ),
        "decision_point": (
            ("Perioperative fitness review", 0.46),
            ("Post-induction local-treatment review", 0.24),
            ("Progression review", 0.2),
            ("Postoperative strategy review", 0.1),
        ),
    },
}
_AGE_BANDS = (
    ("40–49", 0.12), ("50–59", 0.24), ("60–69", 0.3), ("70–79", 0.24), ("80–89", 0.1),
)
_LINES = (
    ("0 previous lines", 0.3), ("1 previous line", 0.36),
    ("2 previous lines", 0.22), ("3 or more previous lines", 0.12),
)
_COMORBIDITIES = (
    ("Hypertension", 0.42), ("Type 2 diabetes", 0.26), ("Cardiac disease", 0.2),
    ("Chronic kidney disease", 0.14), ("Obstructive sleep apnoea", 0.1),
)
_DECISION_WEIGHTS: dict[str, tuple[tuple[str, float], ...]] = {
    "Post-induction local-treatment review": (
        ("surgery_or_local_intervention", 0.3), ("additional_diagnostics_first", 0.24),
        ("continue_current_treatment", 0.2), ("change_systemic_therapy", 0.1),
        ("clinical_trial_enrolment", 0.06), ("defer_to_later_mdt", 0.06),
        ("radiation_therapy", 0.03), ("best_supportive_care", 0.01),
    ),
    "Progression review": (
        ("change_systemic_therapy", 0.36), ("additional_diagnostics_first", 0.16),
        ("clinical_trial_enrolment", 0.14), ("best_supportive_care", 0.12),
        ("radiation_therapy", 0.1), ("continue_current_treatment", 0.06),
        ("defer_to_later_mdt", 0.04), ("surgery_or_local_intervention", 0.02),
    ),
    "Postoperative strategy review": (
        ("continue_current_treatment", 0.32), ("change_systemic_therapy", 0.2),
        ("additional_diagnostics_first", 0.18), ("defer_to_later_mdt", 0.12),
        ("radiation_therapy", 0.08), ("clinical_trial_enrolment", 0.06),
        ("best_supportive_care", 0.02), ("surgery_or_local_intervention", 0.02),
    ),
    "Perioperative fitness review": (
        ("additional_diagnostics_first", 0.32), ("surgery_or_local_intervention", 0.26),
        ("defer_to_later_mdt", 0.14), ("continue_current_treatment", 0.12),
        ("change_systemic_therapy", 0.08), ("best_supportive_care", 0.04),
        ("radiation_therapy", 0.03), ("clinical_trial_enrolment", 0.01),
    ),
}
_OUTCOME_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("complete_response", 0.08), ("partial_response", 0.3), ("stable_disease", 0.31),
    ("progressive_disease", 0.24), ("not_evaluable", 0.07),
)
# Fields that historical sites record least consistently; missing values are never
# read as negative findings, only as records that cannot answer that criterion.
_OMISSION = {
    "molecular_profile": 0.34,
    "metastatic_burden": 0.26,
    "prior_procedures": 0.2,
    "comorbidities": 0.18,
    "previous_lines": 0.12,
    "performance_status": 0.1,
}


def _record(site: int, index: int, hospital: str, country: str, quality: float) -> CohortCase:
    seed = (hospital, index)
    cancer_type = _weighted((("colorectal", 0.62), ("pancreatic", 0.38)), *seed, "cancer")
    pools = _VALUES[cancer_type]
    characteristics: dict[str, list[str]] = {
        "cancer_type": ["Colorectal" if cancer_type == "colorectal" else "Pancreatic"],
        "primary_site": [_weighted(pools["primary_site"], *seed, "site")],
        "stage": [_weighted(pools["stage"], *seed, "stage")],
        "metastatic_sites": _subset(pools["metastatic_sites"], *seed, "mets"),
        "metastatic_burden": [_weighted(pools["metastatic_burden"], *seed, "burden")],
        "molecular_profile": _subset(pools["molecular_profile"], *seed, "molecular"),
        "performance_status": [_weighted(pools["performance_status"], *seed, "ecog")],
        "age_band": [_weighted(_AGE_BANDS, *seed, "age")],
        "previous_lines": [_weighted(_LINES, *seed, "lines")],
        "prior_procedures": _subset(pools["prior_procedures"], *seed, "procedures"),
        "comorbidities": _subset(_COMORBIDITIES, *seed, "comorbidities"),
        "decision_point": [_weighted(pools["decision_point"], *seed, "decision_point")],
    }
    decision_point = characteristics["decision_point"][0]
    for key, omission in _OMISSION.items():
        if _unit(*seed, "omit", key) < min(0.9, omission * (1 - quality) * 3):
            del characteristics[key]
    outcome_recorded = _unit(*seed, "outcome") < quality
    outcome = _weighted(_OUTCOME_WEIGHTS, *seed, "response") if outcome_recorded else "not_recorded"
    followup = _span(90, 1460, *seed, "followup") if outcome_recorded else None
    next_line = _unit(*seed, "next-line") < 0.62 * quality
    progression = _unit(*seed, "progression") < 0.58 * quality
    return CohortCase(
        id=f"SYN-{country[:2].upper()}-{site:02d}{index:04d}",
        hospital=hospital,
        country=country,
        period=PERIODS[int(_unit(*seed, "period") * len(PERIODS))],
        characteristics=characteristics,
        decision=_weighted(_DECISION_WEIGHTS[decision_point], *seed, "decision"),
        outcome=outcome,
        time_to_next_treatment_days=_span(45, 720, *seed, "ttnt") if next_line else None,
        time_to_progression_days=_span(60, 900, *seed, "ttp") if progression else None,
        rediscussed=_unit(*seed, "rediscussed") < 0.38,
        discontinued=_unit(*seed, "discontinued") < 0.27 if outcome_recorded else None,
        followup_days=followup,
    )


@cache
def cohort_dataset() -> tuple[CohortCase, ...]:
    """Deterministic synthetic governed cohort; identical on every run and machine."""
    return tuple(
        _record(site, index, hospital, country, quality)
        for site, (hospital, country, size, quality, _) in enumerate(HOSPITALS)
        for index in range(size)
    )


def cohort_sources() -> list[CohortSource]:
    return [
        CohortSource(hospital=hospital, country=country, cases=size, completeness=note)
        for hospital, country, size, _, note in HOSPITALS
    ]


def _ordinal(key: str, value: str) -> int | None:
    digits = "".join(character if character.isdigit() else " " for character in value).split()
    if not digits:
        return None
    number = int(digits[0])
    return number // 10 if key == "age_band" else number


def compare(
    criterion: Criterion, patient: Sequence[str], recorded: Sequence[str] | None
) -> Verdict:
    """Compare one characteristic; absent history is never treated as a difference."""
    if recorded is None:
        return "NOT_RECORDED"
    if criterion.rule in {"EXACT", "CATEGORY"}:
        if set(patient) == set(recorded):
            return "EXACT"
        if criterion.rule == "CATEGORY" and set(patient) & set(recorded):
            return "NEAR"
        return "DIFFERENT"
    if criterion.rule == "OVERLAP":
        if set(patient) == set(recorded):
            return "EXACT"
        return "NEAR" if set(patient) & set(recorded) else "DIFFERENT"
    left = min((value for value in (_ordinal(criterion.key, item) for item in patient)
                if value is not None), default=None)
    right = min((value for value in (_ordinal(criterion.key, item) for item in recorded)
                 if value is not None), default=None)
    if left is None or right is None:
        return "NOT_RECORDED"
    if left == right:
        return "EXACT"
    return "NEAR" if abs(left - right) == 1 else "DIFFERENT"


def _wilson(count: int, total: int) -> tuple[float, float]:
    """Wilson 95% interval; a descriptive precision statement, not a comparison."""
    if total == 0:
        return (0.0, 0.0)
    proportion = count / total
    z = 1.96
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    margin /= denominator
    return (round(max(0.0, centre - margin) * 100, 1), round(min(1.0, centre + margin) * 100, 1))


def _percentage(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _median(values: Sequence[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def _resolved_profile(
    profile: CohortProfile, resolved: Iterable[str]
) -> dict[str, Characteristic]:
    arrived = set(resolved)
    characteristics: dict[str, Characteristic] = {}
    for key, item in profile.characteristics.items():
        if key in arrived and item.status != "AVAILABLE" and item.pending_values:
            characteristics[key] = Characteristic(
                values=list(item.pending_values),
                status="AVAILABLE",
                display=", ".join(item.pending_values),
                reason="",
                awaiting="",
            )
        else:
            characteristics[key] = item
    return characteristics


def automatic_criteria(characteristics: dict[str, Characteristic]) -> list[str]:
    """Clinically meaningful criteria preselected from the current case."""
    return [
        item.key for item in CRITERIA
        if item.automatic and characteristics.get(item.key, Characteristic()).status == "AVAILABLE"
    ]


def _subgroups(
    records: Sequence[CohortCase], category: str, attribute: str, minimum: int
) -> list[Subgroup]:
    names: list[str] = []
    for record in records:
        value = getattr(record, attribute)
        if value not in names:
            names.append(value)
    groups = []
    for name in sorted(names):
        members = [record for record in records if getattr(record, attribute) == name]
        if len(members) < minimum:
            continue
        count = sum(1 for record in members if record.decision == category)
        groups.append(Subgroup(
            name=name, count=count, denominator=len(members),
            percentage=_percentage(count, len(members)),
        ))
    return groups


def _decisions(matched: Sequence[CohortCase], minimum: int) -> list[DecisionSummary]:
    total = len(matched)
    summaries = []
    for category, label in DECISIONS:
        count = sum(1 for record in matched if record.decision == category)
        low, high = _wilson(count, total)
        summaries.append(DecisionSummary(
            category=category, label=label, count=count, denominator=total,
            percentage=_percentage(count, total), interval_low=low, interval_high=high,
            by_hospital=_subgroups(matched, category, "hospital", minimum),
            by_country=_subgroups(matched, category, "country", minimum),
            by_period=_subgroups(matched, category, "period", minimum),
        ))
    return sorted(summaries, key=lambda item: (-item.count, item.label))


def _outcomes(matched: Sequence[CohortCase]) -> list[OutcomeSummary]:
    evaluated = [record for record in matched if record.outcome != "not_recorded"]
    missing = len(matched) - len(evaluated)
    followup = _median([record.followup_days for record in evaluated if record.followup_days])
    summaries = []
    for measure, label in RESPONSES:
        count = sum(1 for record in evaluated if record.outcome == measure)
        low, high = _wilson(count, len(evaluated))
        summaries.append(OutcomeSummary(
            measure=measure, label=label, numerator=count, denominator=len(evaluated),
            percentage=_percentage(count, len(evaluated)), interval_low=low, interval_high=high,
            missing=missing, followup_days_median=followup,
            note="Recorded observation only; not attributed to any board decision.",
        ))
    for measure, label, values in (
        ("rediscussed", "Re-discussed at a later MDT",
         [record for record in matched if record.rediscussed]),
        ("discontinued", "Treatment discontinuation recorded",
         [record for record in evaluated if record.discontinued]),
    ):
        denominator = len(matched) if measure == "rediscussed" else len(evaluated)
        low, high = _wilson(len(values), denominator)
        summaries.append(OutcomeSummary(
            measure=measure, label=label, numerator=len(values), denominator=denominator,
            percentage=_percentage(len(values), denominator), interval_low=low,
            interval_high=high, missing=0 if measure == "rediscussed" else missing,
            followup_days_median=followup,
            note="Recorded observation only; not attributed to any board decision.",
        ))
    return summaries


def _intervals(matched: Sequence[CohortCase]) -> list[IntervalSummary]:
    summaries = []
    for measure, label, attribute in (
        ("time_to_next_treatment", "Time to next treatment", "time_to_next_treatment_days"),
        ("time_to_progression", "Time to progression", "time_to_progression_days"),
        ("followup", "Follow-up recorded", "followup_days"),
    ):
        values = [
            value for value in (getattr(record, attribute) for record in matched)
            if value is not None
        ]
        summaries.append(IntervalSummary(
            measure=measure, label=label, recorded=len(values), denominator=len(matched),
            missing=len(matched) - len(values), median_days=_median(values),
            minimum_days=min(values) if values else None,
            maximum_days=max(values) if values else None,
            note="Observational record with incomplete and unequal follow-up.",
        ))
    return summaries


def _variation(matched: Sequence[CohortCase], minimum: int) -> list[SiteVariation]:
    sites = sorted({record.hospital for record in matched})
    variation: list[SiteVariation] = []
    withheld: list[CohortCase] = []
    for site in sites:
        members = [record for record in matched if record.hospital == site]
        if len(members) < minimum:
            withheld.extend(members)
            continue
        recorded = sum(1 for record in members if record.outcome != "not_recorded")
        counts = {
            label: sum(1 for record in members if record.decision == category)
            for category, label in DECISIONS
        }
        top = sorted(
            (
                Subgroup(
                    name=label, count=count, denominator=len(members),
                    percentage=_percentage(count, len(members)),
                )
                for label, count in counts.items()
            ),
            key=lambda item: (-item.count, item.name),
        )
        notes = [
            f"{sum(1 for record in members if key not in record.characteristics)} of "
            f"{len(members)} records have no {CRITERION_BY_KEY[key].label.lower()} value."
            for key in ("molecular_profile", "metastatic_burden")
            if any(key not in record.characteristics for record in members)
        ]
        variation.append(SiteVariation(
            site=members[0].hospital, country=members[0].country, cases=len(members),
            decisions=[group for group in top if group.count],
            outcome_completeness=(
                f"{recorded}/{len(members)} records have a recorded outcome "
                f"({_percentage(recorded, len(members))}%)"
            ),
            data_notes=notes,
        ))
    if withheld:
        variation.append(SiteVariation(
            site="Sites below the minimum subgroup size",
            country="Multiple",
            cases=len(withheld),
            outcome_completeness="Withheld to prevent identification of individual patients.",
            data_notes=[
                f"{len({record.hospital for record in withheld})} site(s) contributed fewer "
                f"than {minimum} matching cases each and are not shown separately.",
            ],
            suppressed=True,
        ))
    return variation


def _comparable_cases(
    matched: Sequence[tuple[CohortCase, dict[str, Verdict]]],
    enabled: Sequence[Criterion],
) -> list[ComparableCase]:
    # The dataset is generated site by site, so taking the head would show one
    # hospital only. A stable hash keeps the sample deterministic while spreading
    # it across the sites and periods the variation section describes.
    sample = sorted(matched, key=lambda item: _unit(item[0].id, "sample"))
    cases = []
    for record, verdicts in sample[:CASE_SAMPLE_LIMIT]:
        exact = [item.label for item in enabled if verdicts[item.key] == "EXACT"]
        near = [
            f"{item.label}: {', '.join(record.characteristics.get(item.key, []))} "
            f"(near match within tolerance)"
            for item in enabled if verdicts[item.key] == "NEAR"
        ]
        absent = [
            item.label for item in CRITERIA if item.key not in record.characteristics
        ]
        recorded = len(record.characteristics)
        cases.append(ComparableCase(
            id=record.id, hospital=record.hospital, country=record.country, period=record.period,
            quality="EXACT" if not near else "NEAR",
            matched_on=[item.label for item in enabled],
            similarities=exact,
            differences=near + [f"{label}: not recorded in this historical case"
                               for label in absent],
            evidence_completeness=(
                f"{recorded} of {len(CRITERIA)} matching characteristics recorded; "
                f"outcome {'recorded' if record.outcome != 'not_recorded' else 'not recorded'}"
            ),
            decision=DECISION_LABELS[record.decision],
            outcome=RESPONSE_LABELS.get(record.outcome, "Not recorded"),
            followup_days=record.followup_days,
        ))
    return cases


def build_cohort(
    profile: CohortProfile,
    *,
    case_id: str,
    criteria: Sequence[str] | None = None,
    resolved: Sequence[str] = (),
    include_cases: bool = False,
    minimum: int = MINIMUM_SUBGROUP,
) -> CohortResult:
    """Match the current case against the governed cohort and describe the result."""
    characteristics = _resolved_profile(profile, resolved)
    if criteria is None:
        requested = automatic_criteria(characteristics)
    else:
        unknown = [key for key in criteria if key not in CRITERION_BY_KEY]
        if unknown:
            raise ValueError(f"Unknown matching criteria: {sorted(unknown)}")
        requested = list(dict.fromkeys(criteria))
    enabled = [
        CRITERION_BY_KEY[key] for key in requested
        if characteristics.get(key, Characteristic(status="MISSING")).status == "AVAILABLE"
    ]
    dataset = cohort_dataset()
    verdicts = [
        (
            record,
            {
                item.key: compare(
                    item,
                    characteristics[item.key].values,
                    record.characteristics.get(item.key),
                )
                for item in enabled
            },
        )
        for record in dataset
    ]
    matched = [
        (record, result) for record, result in verdicts
        if all(value in {"EXACT", "NEAR"} for value in result.values())
    ]
    records = [record for record, _ in matched]
    reports: list[CriterionReport] = []
    for item in CRITERIA:
        characteristic = characteristics.get(item.key, Characteristic(status="MISSING"))
        active = item in enabled
        removed = not_recorded = exact = near = 0
        if active:
            others = [item_key.key for item_key in enabled if item_key.key != item.key]
            for _, result in verdicts:
                if not all(result[key] in {"EXACT", "NEAR"} for key in others):
                    continue
                verdict = result[item.key]
                if verdict == "DIFFERENT":
                    removed += 1
                elif verdict == "NOT_RECORDED":
                    not_recorded += 1
                elif verdict == "EXACT":
                    exact += 1
                else:
                    near += 1
        reports.append(CriterionReport(
            key=item.key, label=item.label, rule=item.rule, tolerance=item.tolerance,
            patient_value=characteristic.display or ", ".join(characteristic.values),
            values=list(characteristic.values), status=characteristic.status, enabled=active,
            automatic=item.automatic, reason=characteristic.reason,
            awaiting=characteristic.awaiting, exact=exact, near=near, removed=removed,
            not_recorded_in_cohort=not_recorded,
        ))
    exact_matches = sum(
        1 for _, result in matched if all(value == "EXACT" for value in result.values())
    )
    considered = set(requested) | {item.key for item in CRITERIA if item.automatic}
    unavailable = [
        report for report in reports
        if report.status != "AVAILABLE" and report.key in considered
    ]
    sparse = [
        item.label for item in CRITERIA
        if sum(1 for record in dataset if item.key not in record.characteristics)
        > len(dataset) // 10
    ]
    suppressed = len(records) < minimum
    warnings = list(STANDING_WARNINGS)
    for report in unavailable:
        warnings.append(
            f"{report.label} could not be used: {report.reason} The resulting cohort is broader "
            f"than requested and this absence is not a negative finding."
            + (f" {report.awaiting}" if report.awaiting else "")
        )
    if suppressed:
        warnings.append(
            f"Only {len(records)} matching cases: below the configured minimum subgroup size of "
            f"{minimum}. Decision, outcome and site distributions are suppressed to prevent "
            "identification of individual patients. Remove criteria to widen the comparison."
        )
    return CohortResult(
        case_id=case_id,
        definition=CohortDefinition(
            case_id=case_id,
            criteria=[item.key for item in enabled],
            criterion_values={item.key: list(characteristics[item.key].values) for item in enabled},
            resolved=[key for key in resolved if key in profile.characteristics],
            governed_total=len(dataset),
            matched=len(records),
            minimum_subgroup=minimum,
        ),
        governed_total=len(dataset),
        matched=len(records),
        match_percentage=_percentage(len(records), len(dataset)),
        exact_matches=exact_matches,
        near_matches=len(records) - exact_matches,
        criteria=reports,
        ignored_criteria=[
            report.label for report in reports
            if not report.enabled and report.status == "AVAILABLE"
        ],
        unavailable_in_case=[report.label for report in reports if report.status != "AVAILABLE"],
        unavailable_in_cohort=sparse,
        why_these_cases=(
            f"{len(records)} of {len(dataset)} governed historical cases match "
            f"{len(enabled)} active criteria: "
            + ("; ".join(
                f"{item.label} ({item.rule.lower()} rule, "
                f"{', '.join(characteristics[item.key].values)})" for item in enabled
            ) or "no criteria are active, so the cohort is unrestricted")
            + f". {exact_matches} match every active criterion exactly and "
            f"{len(records) - exact_matches} match within the stated tolerance. "
            "No single similarity score is used; each criterion is listed with its own "
            "rule, tolerance and effect on the cohort."
        ),
        sources=cohort_sources(),
        hospitals=len(HOSPITALS),
        countries=sorted({country for _, country, _, _, _ in HOSPITALS}),
        decisions=[] if suppressed else _decisions(records, minimum),
        outcomes=[] if suppressed else _outcomes(records),
        intervals=[] if suppressed else _intervals(records),
        variation=[] if suppressed else _variation(records, minimum),
        cases=[] if suppressed or not include_cases else _comparable_cases(matched, enabled),
        suppressed=suppressed,
        warnings=warnings,
    )


def reference_statement(result: CohortResult, reference: str) -> dict[str, object]:
    """Describe one cohort finding for the discussion, with its definition retained."""
    kind, _, key = reference.partition(":")
    if kind == "decision":
        summary = next((item for item in result.decisions if item.category == key), None)
        if summary is None:
            raise ValueError("Unknown cohort decision reference.")
        statement = (
            f"Among {summary.denominator} comparable historical cases, "
            f"{summary.percentage}% ({summary.count}/{summary.denominator}) recorded "
            f"{summary.label.lower()}."
        )
    elif kind == "outcome":
        outcome = next((item for item in result.outcomes if item.measure == key), None)
        if outcome is None:
            raise ValueError("Unknown cohort outcome reference.")
        statement = (
            f"Among {outcome.denominator} comparable historical cases with a recorded outcome, "
            f"{outcome.percentage}% ({outcome.numerator}/{outcome.denominator}) recorded "
            f"{outcome.label.lower()}; {outcome.missing} records have no recorded outcome."
        )
    elif kind == "criterion":
        report = next((item for item in result.criteria if item.key == key), None)
        if report is None:
            raise ValueError("Unknown cohort criterion reference.")
        statement = (
            f"{report.label} could not be included in the comparison because "
            f"{report.reason or 'the current value is unavailable.'}"
            if report.status != "AVAILABLE"
            else f"{report.label} was matched using the {report.rule.lower()} rule "
            f"({report.tolerance})."
        )
    else:
        raise ValueError("Unknown cohort reference.")
    return {
        "summary": statement,
        "reference": reference,
        "label": LABEL,
        "cohort_definition": result.definition.model_dump(),
        "denominator": result.matched,
        "governed_total": result.governed_total,
        "provenance": {
            "sources": [source.model_dump() for source in result.sources],
            "date_range": result.date_range,
            "refreshed": result.refreshed,
            "governance": GOVERNANCE,
        },
        "synthetic": True,
        "advisory": False,
    }
