"""Case-bound source records and runtime policy; no mutable active-case global."""

from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any, Literal, Self

from pydantic import TypeAdapter, model_validator

from mdt.cohort import CohortProfile
from mdt.models import Claim, Contract, Evidence, Memory, Role
from mdt.scenario import (
    APPLICABILITY_CLAIMS,
    APPLICABILITY_CONDITION,
    ASSESSMENTS,
    CASE,
    COHORT_PROFILE,
    EVIDENCE,
    FRICTIONS,
    HYPOTHESIS,
    IMAGING_CONDITIONS,
    IMAGING_REVIEW_TERMS,
    LESION_METHOD,
    LESION_NOTES,
    LESION_SITES_LABEL,
    MEMORIES,
    OBSERVATIONS,
    PROPOSAL,
    PROTOCOL_CONDITION,
    RECOMMENDATION,
    RESIDUAL_CONDITIONS,
    ROLE_CONTEXTS,
    ROLE_LABELS,
    ROLE_PROMPTS,
)

APPLICABILITY_ROLES = frozenset({Role.ONCOLOGY, Role.RESEARCH, Role.PROTOCOL, Role.SURGERY})


class FrictionDefinition(Contract):
    question: str
    missing: list[str]


class ProposalDefinition(Contract):
    direction: Literal["INVESTIGATE_FURTHER", "PROCEED_TREATMENT"]
    title: str
    decision: str
    summary: str
    conditions: list[str]


class CaseRuntime(Contract):
    role_prompts: dict[Role, str]
    assessments: dict[Role, str]
    recommendations: dict[Role, str]
    observations: dict[Role, list[str]]
    residual_conditions: list[str]
    imaging_conditions: list[str]
    applicability_condition: str
    protocol_condition: str
    imaging_review_terms: list[str]
    hypothesis: str
    frictions: dict[str, FrictionDefinition]
    proposal: ProposalDefinition
    # Large dossiers are summarised before they reach the model so the token budget
    # is spent on findings rather than repeated source text. Cases with a compact
    # record send it whole.
    compact_context: bool = True
    # Claims every applicability role publishes in addition to those drawn from the
    # records its own tools returned.
    applicability_claims: list[Claim] = []
    # Descriptive lesion comparison wording; the site count is always derived from
    # the mapping. Case-specific findings belong in lesion_notes, never in code.
    lesion_sites_label: str = "mapped"
    lesion_method: str = (
        "Descriptive sum of mapped longest diameters, NOT a formal RECIST target set "
        "or measured volumetry."
    )
    lesion_notes: list[str] = []

    @model_validator(mode="after")
    def complete_roles(self) -> Self:
        for mapping in (
            self.role_prompts, self.assessments, self.recommendations, self.observations,
        ):
            if set(mapping) != set(Role):
                raise ValueError("Case runtime must define every specialist role.")
        if set(self.frictions) != {"imaging", "applicability"}:
            raise ValueError("Case runtime must define both blocking review questions.")
        if not self.imaging_review_terms or not self.residual_conditions:
            raise ValueError("Case runtime must retain targeted review and residual conditions.")
        if not set(self.imaging_conditions) <= set(self.residual_conditions):
            raise ValueError("Imaging conditions must be a subset of residual conditions.")
        if any(not values for values in self.observations.values()):
            raise ValueError("Every specialist needs source observations.")
        return self


class CasePackage(Contract):
    case: dict[str, Any]
    role_contexts: dict[Role, dict[str, Any]]
    runtime: CaseRuntime
    external_evidence_ids: list[str]
    # Characteristics this case offers to the descriptive similar-case comparison.
    cohort_profile: CohortProfile = CohortProfile()

    @model_validator(mode="after")
    def complete_case(self) -> Self:
        if set(self.role_contexts) != set(Role):
            raise ValueError("Case package must provide every specialist context.")
        for context in self.role_contexts.values():
            if not all(isinstance(context.get(key), str) for key in ("workspace", "question")):
                raise ValueError("Every specialist context needs a workspace and question.")
        for key in ("id", "diagnosis", "pseudonym", "stage", "question"):
            if not isinstance(self.case.get(key), str) or not self.case[key]:
                raise ValueError(f"Case package is missing its {key}.")
        return self


@dataclass(frozen=True)
class CaseDefinition:
    case: dict[str, Any]
    contexts: dict[Role, dict[str, Any]]
    evidence: list[Evidence]
    memories: list[Memory]
    labels: dict[Role, str]
    runtime: CaseRuntime
    cohort_profile: CohortProfile

    def role_evidence(self, role: Role) -> list[Evidence]:
        record_url = f"case://{self.case['id']}/{role.value}"
        return [
            item.model_copy(deep=True) for item in self.evidence
            if item.url == record_url
            or (item.kind != "CASE_RECORD" and role in APPLICABILITY_ROLES)
        ]


@cache
def _catalog() -> dict[str, CaseDefinition]:
    packaged_runtime = CaseRuntime(
        role_prompts=ROLE_PROMPTS,
        assessments=ASSESSMENTS,
        recommendations=dict.fromkeys(Role, RECOMMENDATION),
        observations=OBSERVATIONS,
        residual_conditions=RESIDUAL_CONDITIONS,
        imaging_conditions=IMAGING_CONDITIONS,
        applicability_condition=APPLICABILITY_CONDITION,
        protocol_condition=PROTOCOL_CONDITION,
        imaging_review_terms=IMAGING_REVIEW_TERMS,
        hypothesis=HYPOTHESIS,
        frictions={key: FrictionDefinition(**value) for key, value in FRICTIONS.items()},
        proposal=ProposalDefinition(**PROPOSAL),
        compact_context=False,
        applicability_claims=[Claim(**item) for item in APPLICABILITY_CLAIMS],
        lesion_sites_label=LESION_SITES_LABEL,
        lesion_method=LESION_METHOD,
        lesion_notes=LESION_NOTES,
    )
    definitions = {
        str(CASE["id"]): CaseDefinition(
            CASE, ROLE_CONTEXTS, EVIDENCE, MEMORIES, ROLE_LABELS, packaged_runtime,
            CohortProfile.model_validate(COHORT_PROFILE),
        ),
    }
    directory = files("mdt").joinpath("dossiers")
    external = {item.id: item for item in EVIDENCE if item.kind != "CASE_RECORD"}
    additional = TypeAdapter(list[Evidence]).validate_json(
        directory.joinpath("additional_evidence.json").read_text(encoding="utf-8")
    )
    if len({item.id for item in additional}) != len(additional):
        raise ValueError("Additional evidence identifiers must be unique.")
    external.update({item.id: item for item in additional})
    for filename in ("crc_wt_case.json", "pancreatic_case.json"):
        package = CasePackage.model_validate_json(
            directory.joinpath(filename).read_text(encoding="utf-8")
        )
        case_id = str(package.case["id"])
        if case_id in definitions:
            raise ValueError("Case identifiers must be unique.")
        labels = dict(ROLE_LABELS)
        if package.case["kind"] == "pancreatic_perioperative":
            labels[Role.SURGERY] = "Surgical / perioperative review"
            labels[Role.PROTOCOL] = "Perioperative protocol specialist"
        records = [
            Evidence(
                id=f"{case_id}-{role.value.upper()}",
                title=f"{package.case['pseudonym']} case record: {labels[role]}",
                url=f"case://{case_id}/{role.value}",
                date=package.case["source_metadata"]["simulation_date"],
                authority="Case dossier supplied for MDT demonstration",
                region="NL",
                kind="CASE_RECORD",
                access="PUBLIC_FULL_TEXT",
                patient_match="HIGH",
                passage=" ".join(package.runtime.observations[role]),
                limitations=[
                    "Demonstration case data, not external medical evidence or clinical imaging.",
                    "Source preferences are conditional proposals, not treatment authorisation.",
                ],
                scrutiny={
                    "source_authority": "Supplied case_2.md",
                    "study_type": "Not a study",
                    "patient_relevance": f"Only {case_id}",
                },
                synthetic=True,
            )
            for role in Role
        ]
        for identifier in package.external_evidence_ids:
            if identifier not in external:
                raise ValueError(f"Case {case_id} cites unavailable evidence {identifier}.")
            item = external[identifier].model_copy(deep=True)
            item.scrutiny["patient_relevance"] = package.runtime.applicability_condition
            records.append(item)
        memories = [
            Memory(
                id=f"MEM-{case_id}-{role.value}",
                role=role,
                category="FACTUAL_PATIENT",
                text=package.runtime.observations[role][0],
                source=f"Supplied case record: case://{case_id}/{role.value}",
                date=package.case["source_metadata"]["simulation_date"],
            )
            for role in (Role.RADIOLOGY, Role.ONCOLOGY, Role.PATIENT)
        ]
        definitions[case_id] = CaseDefinition(
            package.case, package.role_contexts, records, memories, labels, package.runtime,
            package.cohort_profile,
        )
    return definitions


def case_ids() -> tuple[str, ...]:
    return tuple(_catalog())


def get_case(case_id: str | None = None) -> CaseDefinition:
    identifier = str(CASE["id"]) if case_id is None else case_id
    try:
        definition = _catalog()[identifier]
    except KeyError:
        raise ValueError("Selected case is not configured.") from None
    # Each meeting/run owns its nested records; callers cannot change the catalog.
    return deepcopy(definition)
