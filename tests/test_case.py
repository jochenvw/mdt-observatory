"""Source fidelity, packaged dossier completeness and CRC-only case boundaries."""

import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from conftest import source_digest

from mdt import agents
from mdt.case_registry import APPLICABILITY_ROLES, case_ids, get_case
from mdt.models import Role
from mdt.scenario import CASE, EVIDENCE, MEMORIES, ROLE_CONTEXTS, ROLE_PROMPTS

SOURCE = Path(__file__).resolve().parents[1] / "case.md"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return re.sub("synthetic", "case", value, flags=re.I).replace("SYN-", "CASE-")
    return value


def _narrative(value: str) -> str:
    return re.sub(
        r"\ue200cite\ue202.*?\ue201",
        "[Source-supplied reference; not independently verified]",
        _normalize(value),
    )


def test_complete_yaml_is_preserved_with_only_documented_normalization() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*?)\n```", source, re.S)
    assert match
    expected = _normalize(yaml.safe_load(match.group(1)))
    expected["case"]["demo"] = expected["case"].pop("case")
    assert CASE["dossier"] == expected
    assert len(expected) == 22
    assert CASE["source_metadata"]["sha256"] == source_digest(SOURCE)
    packaged = json.loads(files("mdt").joinpath("dossiers", "crc_case.json").read_text("utf-8"))
    assert packaged["dossier"] == expected


def test_complete_relevant_narrative_and_tables_are_preserved() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    original = source[source.index("## Full synthetic MDT case dossier"):]
    expected = _narrative(re.sub(r"```yaml\n.*?\n```", "", original, flags=re.S))
    assert CASE["narrative"] == expected
    assert len(CASE["management_alternatives"]) == 3
    assert "management_options" not in CASE
    packaged = json.loads(files("mdt").joinpath("dossiers", "crc_case.json").read_text("utf-8"))
    assert CASE["management_alternatives"] == packaged["management_alternatives"]
    assert len(CASE["specialty_contributions"]) == 8
    for table in ("management_alternatives", "specialty_contributions"):
        for row in CASE[table]:
            assert all(value in expected for value in row.values())
    assert CASE["preferred_strategy"] in expected
    assert "human" in CASE["source_metadata"]["academic_profile_boundary"].lower() or (
        "No agent impersonates" in CASE["source_metadata"]["academic_profile_boundary"]
    )
    assert "\ue200cite" not in CASE["narrative"]


def test_all_nine_original_sites_are_mapped_without_inventing_clearance() -> None:
    mapping = CASE["lesion_mapping"]
    assert [row["site"] for row in mapping] == [
        "S8", "S4a", "S7", "S6", "S5", "S3", "S2", "S1", "S4b"
    ]
    assert [row["baseline_diameter_mm"] for row in mapping] == [
        48, 36, 33, 24, 14, 26, 13, 18, 11
    ]
    assert [row["response_diameter_mm"] for row in mapping] == [29, 20, 18, 12, 8, 14, 7, 10, 6]
    assert all("required" in row["clearance_status"] for row in mapping)
    assert "does not allocate treatment to S5/S2/S4b" in (
        CASE["source_metadata"]["treatment_mapping_limit"]
    )
    assert CASE["dossier"]["imaging"]["baseline_CT_CAP"]["liver"]["lesion_count_CT"] == 8
    assert CASE["dossier"]["imaging"]["baseline_liver_MRI"]["lesion_count"] == 9


def test_source_ambiguities_labs_variants_and_acquisition_are_not_flattened() -> None:
    dossier = CASE["dossier"]
    assert dossier["tumor_markers"]["after_cycle_4"]["date"] == "2026-09-01"
    assert dossier["response_assessment"]["biomarkers"]["date"] == "2026-09-09"
    assert dossier["post_cycle_4_labs"]["magnesium_mmol_L"] == 0.61
    assert [item["tissue_VAF_percent"] for item in dossier["molecular_profile"]["variants"]] == [
        34.6, 41.2, 28.7, 18.4
    ]
    assert dossier["pharmacogenomics"]["UGT1A1"] == "*1/*28"
    assert dossier["imaging"]["baseline_liver_MRI"]["technique"]["StudyInstanceUID"].endswith(
        "20260611.2001"
    )
    assert len(dossier["diagnostic_timeline"]) == 14
    assert len(dossier["unresolved_mdt_questions"]) == 6


def test_no_old_lung_case_or_repetitive_label_leaks_into_runtime_content() -> None:
    evidence = [item.model_dump(exclude={"synthetic"}) for item in EVIDENCE]
    text = json.dumps(
        [CASE, ROLE_CONTEXTS, evidence, [item.model_dump() for item in MEMORIES],
         ROLE_PROMPTS],
        ensure_ascii=False,
    ).lower()
    for obsolete in (
        "synthetic", "syn-", "noor", "nsclc", "checkmate", "pembrolizumab",
        "pneumonitis", "pd-l1", "ttf-1", "fev1", "dlco", "thoracic surgeon",
    ):
        assert obsolete not in text
    assert CASE["id"] == "CASE-MDT-CRC-BRAF-2026-001"
    assert CASE["age"] == 59 and CASE["demo"] is True
    assert CASE["dossier"]["patient"]["age"] == 59
    assert CASE["dossier"]["prior_cancer_treatment"]["systemic_regimen"]["cycles_completed"] == 4
    assert (
        CASE["dossier"]["response_assessment"]["biomarkers"]["ctDNA"]["BRAF_V600E_VAF_percent"]
        == 0.42
    )
    assert "NOT FOR CLINICAL USE" in CASE["disclaimer"]


def test_seven_roles_cover_consultations_without_additional_votes() -> None:
    assert len(Role) == len(ROLE_CONTEXTS) == 7
    context = ROLE_CONTEXTS[Role.SURGERY]
    assert len(context["consult_perspectives"]) == 4
    assert "not separate human votes" in context["consult_boundary"]
    assert len(ROLE_CONTEXTS[Role.ONCOLOGY]["treatment"]["maximum_toxicities"]) == 7
    assert len(ROLE_CONTEXTS[Role.PATHOLOGY]["biomarkers"]["variants"]) == 4
    assert ROLE_CONTEXTS[Role.PATIENT]["stated_priorities"] == CASE["dossier"]["patient"]["goals"]


def test_study_sources_have_independent_verification_and_separate_access_scopes() -> None:
    studies = [item for item in EVIDENCE if item.id.startswith("CRC-")]
    assert {item.id for item in studies} == {
        "CRC-BREAKWATER", "CRC-CAIRO5", "CRC-CAIRO5-LONGTERM", "CRC-PROVENC3", "CRC-NVMO-BOM",
    }
    for study in studies:
        assert study.access == (
            "PUBLIC_ABSTRACT_ONLY" if study.id == "CRC-CAIRO5" else "PUBLIC_FULL_TEXT"
        )
        assert study.url.startswith("https://")
        assert "independently reviewed" in study.passage
        assert study.date == "2026-09-17"
        assert "2026-09-17" in study.scrutiny["verification"]
        assert "\ue200cite" not in study.passage
    by_id = {item.id: item for item in studies}
    assert "europepmc" in by_id["CRC-CAIRO5"].url
    assert "EXT_ID:37329889" in by_id["CRC-CAIRO5"].url
    assert by_id["CRC-BREAKWATER"].scrutiny["funding"] == "Pfizer"
    assert "not a liver-only population" in by_id["CRC-BREAKWATER"].passage
    assert "does not establish a BRAF-only effect" in by_id["CRC-CAIRO5"].passage
    assert "PMC11583021" in by_id["CRC-CAIRO5-LONGTERM"].url
    assert "2025-12-24" in by_id["CRC-PROVENC3"].scrutiny["publication_date"]
    assert "2026-01-09" in by_id["CRC-PROVENC3"].scrutiny["publication_date"]
    assert by_id["CRC-NVMO-BOM"].region == "NL"
    assert "palliative" in by_id["CRC-NVMO-BOM"].passage
    assert "nonuniform" in by_id["CRC-NVMO-BOM"].passage
    assert by_id["CRC-NVMO-BOM"].scrutiny["official_listing"].startswith("https://www.nvmo.org/")
    assert "underpowered" in by_id["CRC-CAIRO5-LONGTERM"].passage
    assert "randomized surgery-versus-no-surgery" in by_id["CRC-CAIRO5-LONGTERM"].passage
    assert "[Source-supplied reference; not independently verified]" in CASE["narrative"]
    assert all(item.id.startswith(("CRC-", "CASE-CRC-")) for item in EVIDENCE)


def test_every_case_supplies_the_same_runtime_policy() -> None:
    """The engine and specialist runtime must not need to know which case is loaded.

    Each case carries its own prompts, conditions, review questions and proposal, so
    adding a case is a content change. A case that fails this contract would force a
    branch back into the shared runtime.
    """
    for case_id in case_ids():
        runtime = get_case(case_id).runtime
        assert set(runtime.role_prompts) == set(Role), case_id
        assert set(runtime.assessments) == set(Role), case_id
        assert set(runtime.recommendations) == set(Role), case_id
        assert set(runtime.observations) == set(Role), case_id
        assert set(runtime.frictions) == {"imaging", "applicability"}, case_id
        assert runtime.residual_conditions and runtime.imaging_review_terms, case_id
        assert runtime.proposal.title and runtime.proposal.summary, case_id
        assert runtime.proposal.conditions, case_id
        assert runtime.applicability_condition and runtime.protocol_condition, case_id
        for claim in runtime.applicability_claims:
            for role in APPLICABILITY_ROLES:
                available = {item.id for item in get_case(case_id).role_evidence(role)}
                assert set(claim.evidence_ids) <= available, (case_id, role)


def test_a_partial_lesion_mapping_yields_no_derived_comparison() -> None:
    """A mapping with unmeasured sites must not be summed into a misleading total."""
    complete = [
        {"baseline_diameter_mm": 10, "response_diameter_mm": 4},
        {"baseline_diameter_mm": 30, "response_diameter_mm": 16},
    ]
    derived = agents._lesion_comparison(complete)
    assert derived is not None
    assert derived[0]["baseline_diameter_sum_mm"] == 40
    assert derived[0]["response_diameter_sum_mm"] == 20
    assert derived[0]["diameter_sum_change_pct"] == -50.0
    partial = [*complete, {"baseline_diameter_mm": 12, "response_diameter_mm": None}]
    assert agents._lesion_comparison(partial) is None
    assert agents._lesion_comparison(None) is None
    assert agents._lesion_comparison([]) is None


def test_lesion_comparison_wording_comes_from_the_mapping_and_its_case() -> None:
    """Shared code derives counts; it never carries another case's findings."""
    three = [{"baseline_diameter_mm": 10, "response_diameter_mm": 5} for _ in range(3)]
    derived = agents._lesion_comparison(three)
    assert derived is not None
    context, observations = derived
    text = " ".join([context["method"], *observations])
    assert "3-site" in text and "All 3 original mapped sites" in text
    for foreign in ("nine", "Nine", "MRI", "S1-IVC", "S4a-MHV", "lung nodule"):
        assert foreign not in text
    crc = get_case(str(CASE["id"]))
    context, observations = agents._lesion_comparison(CASE["lesion_mapping"], crc.runtime) or (
        {}, [],
    )
    assert context["method"] == crc.runtime.lesion_method
    assert observations[0] == "All 9 original MRI liver sites remain represented."
    assert observations[-len(crc.runtime.lesion_notes):] == crc.runtime.lesion_notes
