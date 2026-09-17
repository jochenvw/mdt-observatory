"""Independent source fidelity and safety boundaries for the two additional dossiers."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "case_2.md"
ROLES = {"radiology", "oncology", "surgery", "pathology", "research", "protocol", "patient"}
PACKS = ("crc_wt_case", "pancreatic_case")


def _pack(name: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(
        (ROOT / "src" / "mdt" / "dossiers" / f"{name}.json").read_text(encoding="utf-8")
    )
    return value


def _normalize(text: str) -> str:
    return re.sub(
        r"\ue200cite\ue202.*?\ue201",
        "[Source-supplied reference; not independently verified]",
        re.sub("synthetic", "demonstration", text, flags=re.I),
    )


def _source_sections() -> dict[str, str]:
    source = SOURCE.read_text(encoding="utf-8")
    markers = {
        "source_introduction": "# Two fictional MDT cases:",
        "crc_research": "## Colorectal source-supplied research context",
        "crc_case": "## Colorectal MDT case",
        "perioperative_research": "## Perioperative source-supplied research context",
        "pancreatic_case": "## Pancreatic MDT case",
        "visual_introduction": "## Demo visual package and interaction design",
        "crc_visual": "For **colorectal conversion**",
        "pancreatic_visual": "For **pancreatic perioperative risk**",
        "comparison": "A second screen should compare",
        "boundaries": "## Assumptions, boundaries and direct-demo notes",
    }
    starts = [(key, source.index(marker)) for key, marker in markers.items()]
    return {
        key: _normalize(source[start:end])
        for (key, start), end in zip(
            starts, [start for _, start in starts[1:]] + [len(source)], strict=True
        )
    }


def _tables(text: str) -> list[dict[str, Any]]:
    tables = []
    for block in re.findall(r"(?m)(?:^\|.*\|\n?)+", text):
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        cells = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
        tables.append({"columns": cells[0], "rows": cells[2:]})
    return tables


@pytest.mark.parametrize("name", PACKS)
def test_full_new_pack_contract_and_source_hash(name: str) -> None:
    pack = _pack(name)
    assert set(pack) == {"case", "role_contexts", "runtime", "external_evidence_ids"}
    case = pack["case"]
    assert {
        "id", "kind", "demo", "patient", "pseudonym", "age", "diagnosis", "stage",
        "history", "biomarkers", "performance_status", "treatment", "previous_treatment",
        "question", "dossier", "narrative", "source_sections", "management_alternatives",
        "specialty_contributions", "source_metadata",
    } <= case.keys()
    assert case["demo"] is True
    assert "NOT FOR CLINICAL USE" in case["disclaimer"]
    metadata = case["source_metadata"]
    assert metadata["file"] == SOURCE.name
    assert metadata["sha256"] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert all(metadata[key] for key in (
        "simulation_date", "normalization", "exclusions", "provenance", "caveats"
    ))
    assert "synthetic" not in json.dumps(pack).lower()
    assert "\ue200cite" not in json.dumps(pack, ensure_ascii=False)
    assert set(pack["role_contexts"]) == ROLES
    for context in pack["role_contexts"].values():
        assert context["workspace"] and context["question"]
        assert context["source_sections"] and context["caveats"]
        assert "not separate human votes" in context["consult_boundary"]
    for row in case["management_alternatives"]:
        assert set(row) == {"name", "sequence", "advantages", "disadvantages", "evidence"}
        assert all(isinstance(value, str) and value for value in row.values())
    for row in case["specialty_contributions"]:
        assert set(row) == {"specialty", "interpretation", "contribution"}
        assert all(isinstance(value, str) and value for value in row.values())


def test_every_meaningful_source_section_and_table_is_preserved_exactly() -> None:
    source = _source_sections()
    found = {}
    for name in PACKS:
        case = _pack(name)["case"]
        sections = case["source_sections"]
        assert case["narrative"] == "".join(section["text"] for section in sections)
        for section in sections:
            assert section["text"] == source[section["id"]]
            assert section["tables"] == _tables(section["text"])
            found[section["id"]] = section["text"]
        assert case["dossier"]["source_tables"] == [
            {"section_id": section["id"], **table}
            for section in sections for table in section["tables"]
        ]
    assert found == source
    assert "".join(source.values()) == _normalize(SOURCE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", PACKS)
def test_runtime_fields_remain_typed_and_conditional(name: str) -> None:
    runtime = _pack(name)["runtime"]
    for key in ("role_prompts", "assessments", "recommendations", "observations"):
        assert set(runtime[key]) == ROLES
        for value in runtime[key].values():
            if key == "observations":
                assert isinstance(value, list) and value
                assert all(isinstance(item, str) and item for item in value)
            else:
                assert isinstance(value, str) and value
    for key in ("applicability_condition", "protocol_condition", "hypothesis"):
        assert isinstance(runtime[key], str) and runtime[key]
    for key in ("residual_conditions", "imaging_review_terms"):
        assert isinstance(runtime[key], list) and runtime[key]
        assert all(isinstance(item, str) and item for item in runtime[key])
    assert set(runtime["frictions"]) == {"imaging", "applicability"}
    for friction in runtime["frictions"].values():
        assert isinstance(friction["question"], str) and friction["question"]
        assert friction["missing"] and all(isinstance(item, str) for item in friction["missing"])
    assert set(runtime["proposal"]) == {"title", "summary", "conditions"}
    assert runtime["proposal"]["conditions"] == runtime["residual_conditions"]
    assert "conditional" in runtime["proposal"]["summary"].lower()
    assert "human" in runtime["frictions"]["imaging"]["question"].lower()
    assert "role-scoped" in " ".join(runtime["residual_conditions"])


def test_crc_identity_molecular_regimen_and_all_five_conceptual_rows() -> None:
    case = _pack("crc_wt_case")["case"]
    assert (case["id"], case["kind"], case["pseudonym"], case["age"]) == (
        "CASE-MDT-CRC-WT-2026-002", "crc_conversion_response", "CRC-2026-002", 58
    )
    dossier = case["dossier"]
    assert dossier["prior_cancer_treatment"]["systemic_regimen"]["name"] == (
        "mFOLFOX6 + bevacizumab"
    )
    assert dossier["prior_cancer_treatment"]["systemic_regimen"]["cycles_completed"] == 8
    assert dossier["imaging"]["original_lesion_count"] == 11
    assert dossier["imaging"]["complete_individual_mapping_supplied"] is False
    rows = case["lesion_mapping"]
    assert [row["site"] for row in rows] == ["L1", "L2", "L3", "L4", "L5"]
    assert [row["baseline_diameter_mm"] for row in rows] == [57, 31, 24, 18, 14]
    assert [row["source_mockup_response_mm"] for row in rows] == [29, 14, 9, 0, 0]
    assert [row["response_diameter_mm"] for row in rows] == [29, 14, 9, None, None]
    assert all("conceptual" in row["data_status"] for row in rows)
    assert all("required" in row["clearance_status"] for row in rows)
    assert dossier["imaging"]["unmapped_original_site_count"] == 6
    assert dossier["imaging"]["vascular_distances_mm"] is None
    assert dossier["imaging"]["future_liver_remnant_percent"] is None
    response = dossier["response_assessment"]
    assert response["clear_residual_lesions"] == 6
    assert response["radiologically_invisible_original_deposits"] == 3
    assert response["tiny_scars"] == 2
    assert response["uncertain_focus"]["diameter_mm"] == 7
    assert response["uncertain_focus"]["confirmed_progression"] is False
    assert response["ctDNA_VAF_percent"] == 0.18
    assert len(dossier["diagnostic_timeline"]) == 11
    assert len(case["management_alternatives"]) == 6
    assert len(case["specialty_contributions"]) == 11
    assert len(dossier["differential_diagnoses"]) == 5
    assert len(dossier["molecular_profile"]) == 13
    assert len(dossier["baseline_laboratory_results"]) == 13
    assert "encorafenib" not in json.dumps(case).lower()
    assert "cetuximab" not in case["treatment"].lower()


def test_pancreatic_record_keeps_source_discrepancies_and_unobserved_future() -> None:
    case = _pack("pancreatic_case")["case"]
    assert (case["id"], case["kind"], case["pseudonym"], case["age"]) == (
        "CASE-MDT-PDAC-PERIOP-2026-003", "pancreatic_perioperative", "PDAC-2026-003", 72
    )
    dossier = case["dossier"]
    assert dossier["renal"]["source_stage"] == "CKD stage 3a"
    assert dossier["renal"]["eGFR_mL_min_1_73m2"] == 44
    assert dossier["risk_scores"]["RCRI"]["source_score"] == 2
    assert dossier["risk_scores"]["RCRI"]["verified"] is False
    assert dossier["risk_scores"]["hypotension_model"]["probability_percent"] == 72
    assert dossier["risk_scores"]["AKI_model"]["probability_percent"] == 14
    assert dossier["risk_scores"]["hypotension_model"]["locally_validated"] is False
    assert dossier["medications"]["withholding_rules"] is None
    assert dossier["prior_cancer_treatment"]["regimen"] is None
    assert dossier["imaging"]["baseline_primary_cm"] == 3.4
    assert dossier["imaging"]["response_primary_cm"] == 2.6
    assert dossier["imaging"]["vascular_contact_degrees"] is None
    assert dossier["echocardiography"]["LVEF_percent"] == 58
    assert dossier["echocardiography"]["aortic_valve_area_cm2"] == 1.25
    assert dossier["echocardiography"]["mean_gradient_mmHg"] == 18
    scenario = dossier["hypothetical_scenario"]
    assert scenario["observed"] is False
    assert scenario["prose_start_MAP_mmHg"] == 82
    assert scenario["reveal_start_MAP_mmHg"] == 78
    assert scenario["measured_outcomes"] == []
    assert "little blood loss" in scenario["source_reveal"]
    assert dossier["followup_plan"]["observed_outcomes"] == []
    assert len(dossier["diagnostic_timeline"]) == 11
    assert len(dossier["preoperative_laboratory_results"]) == 13
    assert len(dossier["differential_diagnoses"]) == 7
    assert len(case["management_alternatives"]) == 5
    assert len(case["specialty_contributions"]) == 13
    contexts = _pack("pancreatic_case")["role_contexts"]
    assert {"anaesthesia", "cardiac", "renal"} <= set(
        contexts["surgery"]["consolidated_perspectives"]
    )
    assert all(key in contexts["protocol"] for key in (
        "medication_rules", "monitoring_rules", "ponv_rules", "alert_ownership"
    ))
    assert "anatomy" in contexts["radiology"]["question"]
    assert "echo" in contexts["radiology"]["question"]


def test_source_table_projections_retain_all_alternatives_and_consultation_perspectives() -> None:
    for name, section_id, strategy_header, specialty_header in (
        ("crc_wt_case", "crc_case", "Strategy", "Discipline"),
        ("pancreatic_case", "pancreatic_case", "Strategy", "Participant"),
    ):
        case = _pack(name)["case"]
        sections = {section["id"]: section for section in case["source_sections"]}
        tables = sections[section_id]["tables"]
        strategies = next(table for table in tables if table["columns"][0] == strategy_header)
        specialties = next(table for table in tables if table["columns"][0] == specialty_header)
        assert [item["name"] for item in case["management_alternatives"]] == [
            row[0] for row in strategies["rows"]
        ]
        for original, projected in zip(
            strategies["rows"], case["management_alternatives"], strict=True
        ):
            assert original[1] == projected["advantages"]
            assert original[2] == projected["disadvantages"]
            assert original[3] in projected["sequence"]
            assert "source-supplied" in projected["evidence"].lower()
        assert [
            (item["specialty"], item["contribution"]) for item in case["specialty_contributions"]
        ] == [tuple(row) for row in specialties["rows"]]


def test_perioperative_runtime_does_not_upgrade_abstract_evidence_to_causal_benefit() -> None:
    pack = _pack("pancreatic_case")
    context = pack["role_contexts"]["research"]
    assert context["external_evidence_access"] == "PUBLIC_ABSTRACT_ONLY"
    evidence_limits = " ".join(context["verified_evidence_limits"])
    assert "stopped for futility" in evidence_limits
    assert "six-month disability" in evidence_limits
    assert "before-after" in evidence_limits
    assert "not another RCT" in evidence_limits
    runtime = pack["runtime"]
    assert "futility" in runtime["assessments"]["research"]
    assert "before-after" in runtime["applicability_condition"]
    assert all(
        limit in runtime["residual_conditions"] for limit in context["verified_evidence_limits"]
    )
