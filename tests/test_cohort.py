"""Similar-case cohort: matching, degradation, aggregation and safety guardrails."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mdt.app import create_app
from mdt.case_registry import case_ids, get_case
from mdt.cohort import (
    CRITERIA,
    CRITERION_BY_KEY,
    DECISION_LABELS,
    LABEL,
    MINIMUM_SUBGROUP,
    RESPONSE_LABELS,
    Characteristic,
    CohortProfile,
    automatic_criteria,
    build_cohort,
    cohort_dataset,
    compare,
    reference_statement,
)
from mdt.config import Settings

CASE_ID = "CASE-MDT-CRC-WT-2026-002"
ADVISORY_TERMS = (
    "best treatment", "preferred treatment", "recommended treatment", "we recommend",
    "should receive", "most effective", "superior", "optimal treatment", "treatment of choice",
)


def profile_for(case_id: str = CASE_ID) -> CohortProfile:
    return get_case(case_id).cohort_profile


def test_every_case_publishes_a_complete_matching_profile() -> None:
    for identifier in case_ids():
        profile = profile_for(identifier)
        assert set(profile.characteristics) == {item.key for item in CRITERIA}
        for key, characteristic in profile.characteristics.items():
            assert characteristic.display, f"{identifier}/{key} needs a clinician-facing value"
            if characteristic.status != "AVAILABLE":
                assert characteristic.reason
                assert not characteristic.values


def test_matching_rules_separate_exact_and_near_matches_and_never_guess() -> None:
    exact = CRITERION_BY_KEY["cancer_type"]
    assert compare(exact, ["Colorectal"], ["Colorectal"]) == "EXACT"
    assert compare(exact, ["Colorectal"], ["Pancreatic"]) == "DIFFERENT"
    overlap = CRITERION_BY_KEY["metastatic_sites"]
    assert compare(overlap, ["Liver"], ["Liver"]) == "EXACT"
    assert compare(overlap, ["Liver"], ["Liver", "Lung"]) == "NEAR"
    assert compare(overlap, ["Liver"], ["Lung"]) == "DIFFERENT"
    band = CRITERION_BY_KEY["age_band"]
    assert compare(band, ["50–59"], ["50–59"]) == "EXACT"
    assert compare(band, ["50–59"], ["60–69"]) == "NEAR"
    assert compare(band, ["50–59"], ["70–79"]) == "DIFFERENT"
    ecog = CRITERION_BY_KEY["performance_status"]
    assert compare(ecog, ["ECOG 1"], ["ECOG 2"]) == "NEAR"
    # An absent historical value is never read as a difference or a negative finding.
    assert compare(exact, ["Colorectal"], None) == "NOT_RECORDED"


def test_criteria_are_preselected_from_available_characteristics_only() -> None:
    profile = profile_for()
    selected = automatic_criteria(profile.characteristics)
    assert "cancer_type" in selected and "decision_point" in selected
    assert "metastatic_burden" not in selected, "pending characteristics stay disabled"
    assert "prior_procedures" not in selected, "missing characteristics stay disabled"
    assert "comorbidities" not in selected, "non-automatic criteria are opt-in"
    result = build_cohort(profile, case_id=CASE_ID)
    assert result.definition.criteria == selected


def test_adding_and_removing_criteria_recalculates_the_cohort() -> None:
    profile = profile_for()
    broad = build_cohort(profile, case_id=CASE_ID, criteria=["cancer_type"])
    narrower = build_cohort(profile, case_id=CASE_ID, criteria=["cancer_type", "stage"])
    widest = build_cohort(profile, case_id=CASE_ID, criteria=[])
    assert widest.matched == widest.governed_total
    assert broad.matched < widest.matched
    assert narrower.matched < broad.matched
    assert narrower.match_percentage == round(
        narrower.matched / narrower.governed_total * 100, 1
    )
    assert "Relevant comorbidities" in broad.ignored_criteria
    with pytest.raises(ValueError):
        build_cohort(profile, case_id=CASE_ID, criteria=["not_a_characteristic"])


def test_missing_stale_and_pending_data_disable_criteria_and_widen_the_cohort() -> None:
    profile = profile_for()
    result = build_cohort(profile, case_id=CASE_ID)
    pending = next(item for item in result.criteria if item.key == "metastatic_burden")
    assert pending.status == "PENDING"
    assert not pending.enabled
    assert pending.reason and pending.awaiting
    assert "Metastatic burden" in result.unavailable_in_case
    assert any(
        "broader than requested" in warning and "not a negative finding" in warning
        for warning in result.warnings
    )
    # The awaited result arriving recalculates automatically from the case record.
    resolved = build_cohort(profile, case_id=CASE_ID, resolved=["metastatic_burden"])
    assert "metastatic_burden" in resolved.definition.criteria
    assert resolved.matched < result.matched
    assert "Metastatic burden" not in resolved.unavailable_in_case
    stale = CohortProfile(characteristics={
        "cancer_type": Characteristic(values=["Colorectal"], display="Colorectal"),
        "stage": Characteristic(
            status="STALE", display="Stage IV (restaging overdue)",
            reason="the staging scan predates the current treatment line.",
            awaiting="A current restaging scan would allow stage matching.",
            pending_values=["Stage IV"],
        ),
    })
    degraded = build_cohort(stale, case_id=CASE_ID)
    assert degraded.definition.criteria == ["cancer_type"]
    assert build_cohort(stale, case_id=CASE_ID, resolved=["stage"]).matched < degraded.matched


def test_counts_percentages_and_denominators_are_internally_consistent() -> None:
    result = build_cohort(profile_for(), case_id=CASE_ID)
    assert result.matched == result.exact_matches + result.near_matches
    assert sum(item.count for item in result.decisions) == result.matched
    for decision in result.decisions:
        assert decision.denominator == result.matched
        assert decision.percentage == round(decision.count / result.matched * 100, 1)
        assert decision.interval_low <= decision.percentage <= decision.interval_high
        assert decision.label == DECISION_LABELS[decision.category]
    responses = [item for item in result.outcomes if item.measure in RESPONSE_LABELS]
    assert sum(item.numerator for item in responses) == responses[0].denominator
    for outcome in result.outcomes:
        assert outcome.denominator <= result.matched
        assert outcome.percentage == round(outcome.numerator / outcome.denominator * 100, 1)
    recorded = next(item for item in result.outcomes if item.measure == "partial_response")
    assert recorded.missing == result.matched - recorded.denominator
    for interval in result.intervals:
        assert interval.recorded + interval.missing == result.matched
        if interval.recorded:
            assert interval.minimum_days <= interval.median_days <= interval.maximum_days


def test_criterion_reports_explain_their_own_effect_on_the_cohort() -> None:
    result = build_cohort(profile_for(), case_id=CASE_ID)
    active = [item for item in result.criteria if item.enabled]
    assert active
    for report in active:
        assert report.tolerance and report.patient_value
        assert report.exact + report.near == result.matched
        assert report.removed or report.not_recorded_in_cohort or report.exact
    assert "No single similarity score" in result.why_these_cases
    for report in result.criteria:
        if not report.enabled:
            assert report.exact == report.near == report.removed == 0
    assert result.unavailable_in_cohort, "criteria the history cannot answer are named"


def test_hospital_variation_is_observational_and_suppresses_small_sites() -> None:
    result = build_cohort(profile_for(), case_id=CASE_ID)
    shown = [site for site in result.variation if not site.suppressed]
    assert shown, "at least one site meets the minimum subgroup size"
    for site in shown:
        assert site.cases >= MINIMUM_SUBGROUP
        assert site.outcome_completeness
        assert sum(item.count for item in site.decisions) <= site.cases
    withheld = [site for site in result.variation if site.suppressed]
    for site in withheld:
        assert site.site == "Sites below the minimum subgroup size"
        assert site.country == "Multiple"
        assert not site.decisions
    # A configured minimum governs every subgroup, including the breakdowns
    # reported inside a decision category.
    raised = build_cohort(profile_for(), case_id=CASE_ID, minimum=30)
    for site in raised.variation:
        assert site.suppressed or site.cases >= 30
    for decision in raised.decisions:
        for group in (*decision.by_hospital, *decision.by_country, *decision.by_period):
            assert group.denominator >= 30


def test_small_cohorts_are_suppressed_rather_than_described() -> None:
    profile = profile_for()
    result = build_cohort(
        profile, case_id=CASE_ID, criteria=automatic_criteria(profile.characteristics),
        include_cases=True, minimum=500,
    )
    assert result.suppressed
    assert not result.decisions and not result.outcomes and not result.variation
    assert not result.cases
    assert any("minimum subgroup size" in warning for warning in result.warnings)
    assert result.matched and result.governed_total


def test_case_level_exploration_stays_de_identified_and_explains_each_match() -> None:
    result = build_cohort(profile_for(), case_id=CASE_ID, include_cases=True)
    assert result.cases and len(result.cases) <= 12
    identifiers = {record.id for record in cohort_dataset()}
    for record in result.cases:
        assert record.id in identifiers and record.id.startswith("SYN-")
        assert record.matched_on and record.evidence_completeness
        assert record.similarities or record.differences
        assert record.decision in DECISION_LABELS.values()
        assert record.outcome in {*RESPONSE_LABELS.values(), "Not recorded"}
        assert all(part.isdigit() for part in record.period.split("–")), "periods only"
    for record in cohort_dataset():
        assert record.synthetic
        assert "age_band" not in record.characteristics or "–" in (
            record.characteristics["age_band"][0]
        )
        dumped = record.model_dump_json().lower()
        for forbidden in ("name", "birth", "nhs", "bsn", "address", "mrn"):
            assert forbidden not in dumped


def test_synthetic_cohort_is_deterministic_and_covers_varied_sites() -> None:
    first = cohort_dataset()
    cohort_dataset.cache_clear()
    assert [record.model_dump() for record in cohort_dataset()] == [
        record.model_dump() for record in first
    ]
    assert len({record.country for record in first}) >= 4
    assert len({record.hospital for record in first}) >= 5
    assert len({record.period for record in first}) >= 3
    completeness = {
        hospital: sum(
            1 for record in first
            if record.hospital == hospital and "molecular_profile" in record.characteristics
        ) / sum(1 for record in first if record.hospital == hospital)
        for hospital in {record.hospital for record in first}
    }
    assert max(completeness.values()) - min(completeness.values()) > 0.2
    assert any(record.outcome == "not_recorded" for record in first)


def test_result_never_recommends_ranks_or_endorses_a_treatment() -> None:
    result = build_cohort(profile_for(), case_id=CASE_ID, include_cases=True)
    text = result.model_dump_json().lower()
    for term in ADVISORY_TERMS:
        assert term not in text
    assert result.label == LABEL
    assert result.warnings[0].startswith("Descriptive, not advisory")
    assert any("do not determine what is right" in warning for warning in result.warnings)
    assert any("no causal link" in warning.lower() for warning in result.warnings)
    assert any("selection bias" in warning for warning in result.warnings)
    assert result.synthetic and "not clinical evidence" in result.definition.governance
    ordered = [item.count for item in result.decisions]
    assert ordered == sorted(ordered, reverse=True), "frequency order is descriptive only"


def test_reference_retains_definition_denominator_and_provenance() -> None:
    result = build_cohort(profile_for(), case_id=CASE_ID)
    top = result.decisions[0]
    payload = reference_statement(result, f"decision:{top.category}")
    assert f"{top.count}/{top.denominator}" in str(payload["summary"])
    assert payload["denominator"] == result.matched
    assert payload["label"] == LABEL
    assert payload["advisory"] is False
    assert payload["cohort_definition"]["criteria"] == result.definition.criteria
    assert payload["provenance"]["date_range"] == result.date_range
    assert payload["provenance"]["sources"]
    pending = reference_statement(result, "criterion:metastatic_burden")
    assert "could not be included" in str(pending["summary"])
    for unknown in ("decision:unknown", "outcome:unknown", "criterion:unknown", "other:x"):
        with pytest.raises(ValueError):
            reference_statement(result, unknown)


def test_api_serves_cohorts_and_records_a_non_binding_reference(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "cohort.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        automatic = client.get(f"/api/cases/{CASE_ID}/cohort")
        assert automatic.status_code == 200
        body = automatic.json()
        assert body["label"] == LABEL
        assert body["matched"] and body["governed_total"] > body["matched"]
        assert not body["cases"], "aggregated results are the default"
        narrowed = client.get(
            f"/api/cases/{CASE_ID}/cohort",
            params={"criteria": ["cancer_type", "stage"], "include_cases": "true"},
        )
        assert narrowed.status_code == 200
        assert narrowed.json()["matched"] > body["matched"]
        assert narrowed.json()["cases"]
        assert client.get("/api/cases/unknown-case/cohort").status_code == 404
        assert client.get(
            f"/api/cases/{CASE_ID}/cohort", params={"criteria": ["invented"]}
        ).status_code == 422

        started = client.post("/api/meetings", json={"mode": "rehearsal", "case_id": CASE_ID})
        assert started.status_code == 201
        meeting_id = started.json()["id"]
        deadline = time.monotonic() + 15
        while client.get("/api/meeting").json()["busy"] and time.monotonic() < deadline:
            time.sleep(0.01)
        before = client.get(f"/api/meetings/{meeting_id}").json()
        category = body["decisions"][0]["category"]
        recorded = client.post(
            f"/api/meetings/{meeting_id}/cohort-reference",
            json={"reference": f"decision:{category}"},
        )
        assert recorded.status_code == 200
        after = recorded.json()
        event = [item for item in after["events"] if item["type"] == "CohortReferenceAdded"][-1]
        assert str(body["matched"]) in event["payload"]["summary"]
        assert event["payload"]["cohort_definition"]["case_id"] == CASE_ID
        assert event["payload"]["provenance"]["refreshed"]
        # A quoted cohort finding is context only: it decides nothing.
        assert after["plan"] == before["plan"]
        assert after["phase"] == before["phase"]
        assert after["concurrences"] == before["concurrences"]
        assert after["frictions"] == before["frictions"]
        assert {role: state["position"] for role, state in after["roles"].items()} == {
            role: state["position"] for role, state in before["roles"].items()
        }
        refused = client.post(
            f"/api/meetings/{meeting_id}/cohort-reference",
            json={
                "reference": f"decision:{category}",
                "criteria": ["cancer_type", "stage", "metastatic_sites", "molecular_profile",
                             "performance_status", "age_band", "previous_lines", "primary_site",
                             "decision_point", "comorbidities", "metastatic_burden"],
                "resolved": ["metastatic_burden"],
            },
        )
        assert refused.status_code == 409
        assert "minimum subgroup size" in refused.json()["detail"]
