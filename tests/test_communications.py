"""Communication runtime: role scoping, skills, language, checks and the model contract."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import FakeDrafter, fake_result

from mdt import agents
from mdt.agents import analyze
from mdt.case_registry import get_case
from mdt.communications import (
    LANGUAGES,
    PATIENT_SECTIONS,
    CommunicationInput,
    CommunicationRuntimeError,
    DraftResult,
    DraftSection,
    PatientDraft,
    _empty_checks,
    check,
    communication_inputs,
    detect_language,
    draft,
    revision_findings,
    skill_instructions,
)
from mdt.config import Settings
from mdt.engine import Engine
from mdt.models import CommunicationSection, GlossaryTerm, Meeting, Phase, Role
from mdt.store import Store

CASES = {
    "CASE-MDT-CRC-BRAF-2026-001": (
        "I reviewed all nine liver sites, vessel margins and the lung nodule. The sites are "
        "mapped, the margins and remnant are adequate, and the nodule is not suspicious.", "en",
    ),
    "CASE-MDT-CRC-WT-2026-002": (
        "I reviewed all 11 baseline liver sites. The mapping, vessel interfaces and remnant "
        "are adequate for the proposed parenchymal-sparing treatment.", "de",
    ),
    "CASE-MDT-PDAC-PERIOP-2026-003": (
        "I reviewed the pancreatic imaging, vascular anatomy, echo and physiological reserve. "
        "The interface is reconstructable and the completed reserve review is acceptable.", "it",
    ),
}
SETTINGS = Settings(step_delay=0, azure_request_interval_seconds=0)


async def _decide(tmp: Path, case_id: str, guidance: str) -> Meeting:
    settings = Settings(db_path=str(tmp / f"{case_id}.db"), step_delay=0)
    engine = Engine(Store(settings.db_path), settings, analyze, drafter=FakeDrafter())

    async def settle() -> None:
        while engine.tasks:
            await asyncio.gather(*list(engine.tasks))

    started = await engine.start("rehearsal", case_id)
    await settle()
    await engine.followup(started.id)
    await settle()
    await engine.steer(started.id, Role.RADIOLOGY, guidance)
    await settle()
    meeting = engine.get(started.id)
    assert meeting.plan is not None
    for role in Role:
        if role not in meeting.concurrences:
            await engine.concur(started.id, role, "Reviewed.", meeting.plan.version)
    await settle()
    assert meeting.phase == Phase.DECISION_CAPTURED
    result = meeting.model_copy(deep=True)
    await engine.close()
    return result


@pytest.fixture(scope="module")
def decided(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Meeting]:
    tmp = tmp_path_factory.mktemp("decided")

    async def build() -> dict[str, Meeting]:
        return {
            case_id: await _decide(tmp, case_id, guidance)
            for case_id, (guidance, _) in CASES.items()
        }

    return asyncio.run(build())


def fictional(meeting: Meeting, language: str) -> Meeting:
    """A fourth case the skills were never written against."""
    other = meeting.model_copy(deep=True)
    other.case.update(
        {
            "id": "CASE-FICTIONAL-LUNG-9999",
            "patient": "Fictional · LNG-9999",
            "diagnosis": "Fictional left upper-lobe lung adenocarcinoma",
            "stage": "Fictional stage for a generic-skill test",
            "preferred_language": language,
        }
    )
    return other


# ------------------------------------------------------------------- scoping
@pytest.mark.parametrize("case_id", list(CASES))
def test_inputs_are_role_scoped_and_bound_to_the_case_language(
    decided: dict[str, Meeting], case_id: str,
) -> None:
    meeting = decided[case_id]
    patient = communication_inputs(meeting, "patient")
    clinician = communication_inputs(meeting, "clinician")
    assert patient.language == CASES[case_id][1]
    assert clinician.language == "en"
    assert set(patient.positions) == {Role.PATIENT.value}
    assert not patient.evidence and not patient.concurrences and not patient.objections
    assert "history" not in patient.case and "biomarkers" not in patient.case
    assert not any(ref.startswith(("evidence.", "concurrence.")) for ref in patient.refs)
    assert set(clinician.positions) == {role.value for role in Role}
    assert {item["role"] for item in clinician.concurrences} == {role.value for role in Role}
    assert clinician.evidence
    for inputs in (patient, clinician):
        assert inputs.required_refs
        assert set(inputs.required_refs) <= set(inputs.refs)


def test_inputs_are_copies_of_the_record(decided: dict[str, Meeting]) -> None:
    meeting = decided["CASE-MDT-CRC-BRAF-2026-001"].model_copy(deep=True)
    assert meeting.plan is not None
    inputs = communication_inputs(meeting, "clinician")
    inputs.plan.actions.append("Injected action")
    inputs.case["diagnosis"] = "Changed"
    assert "Injected action" not in meeting.plan.actions
    assert meeting.case["diagnosis"] != "Changed"


def test_drafting_requires_a_captured_plan(decided: dict[str, Meeting]) -> None:
    meeting = decided["CASE-MDT-CRC-BRAF-2026-001"].model_copy(deep=True)
    meeting.plan = None
    with pytest.raises(CommunicationRuntimeError, match="captured plan"):
        communication_inputs(meeting, "patient")


# ------------------------------------------------------------------- skills
@pytest.mark.parametrize("case_id", list(CASES))
def test_patient_skill_is_case_agnostic_and_names_the_language(
    decided: dict[str, Meeting], case_id: str,
) -> None:
    inputs = communication_inputs(decided[case_id], "patient")
    text = skill_instructions(inputs)
    language = LANGUAGES[CASES[case_id][1]]
    assert f"{language.name} ({language.native})" in text
    assert "{{" not in text
    for section_id, _, _ in PATIENT_SECTIONS:
        assert f"`{section_id}`" in text
    for case in CASES:
        assert case not in text
    assert decided[case_id].case["diagnosis"] not in text


def test_clinician_skill_has_no_unfilled_placeholders(decided: dict[str, Meeting]) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-WT-2026-002"], "clinician")
    text = skill_instructions(inputs)
    assert "{{" not in text and "British English" in text


def test_letter_labels_the_synthetic_record_once_per_line(decided: dict[str, Meeting]) -> None:
    # The UI renders "synthetic" as "demonstration"; one label per line avoids repetition.
    letter = fake_result(communication_inputs(decided["CASE-MDT-CRC-WT-2026-002"], "clinician"))
    lines = [line for section in letter.sections for line in section.paragraphs]
    assert any("synthetic" in line for line in lines)
    assert all(line.lower().count("synthetic") + line.lower().count("demonstration") <= 1
               for line in lines)


def test_confirmed_radiology_review_is_completed_not_pending_in_both_documents(
    decided: dict[str, Meeting],
) -> None:
    meeting = decided["CASE-MDT-CRC-BRAF-2026-001"]
    assert meeting.plan is not None
    patient = fake_result(communication_inputs(meeting, "patient"))
    letter = fake_result(communication_inputs(meeting, "clinician"))
    combined = " ".join(
        text
        for result in (patient, letter)
        for section in result.sections
        for text in (
            *section.paragraphs,
            *section.bullets,
            *(cell for row in section.rows for cell in row),
        )
    )
    assert meeting.plan.decision in combined
    assert meeting.plan.resolved_requirements[0].finding in combined
    for pending in get_case(meeting.case["id"]).runtime.imaging_conditions:
        assert pending not in combined
    doctor = next(
        section for section in letter.sections
        if section.id == "accountable_doctor_actions"
    )
    assert doctor.heading == "For the accountable medical doctor"


def test_unresolved_requirement_remains_visible_to_communication_generation(
    decided: dict[str, Meeting],
) -> None:
    meeting = decided["CASE-MDT-CRC-BRAF-2026-001"].model_copy(deep=True)
    assert meeting.plan is not None
    requirement = get_case(meeting.case["id"]).runtime.imaging_conditions[0]
    meeting.plan.resolved_requirements = []
    meeting.plan.conditions.insert(0, requirement)
    imaging = next(item for item in meeting.frictions if item.id == "imaging")
    imaging.resolved = False
    imaging.resolution = None
    inputs = communication_inputs(meeting, "clinician")
    letter = fake_result(inputs)
    combined = " ".join(
        [cell for section in letter.sections for row in section.rows for cell in row]
        + [bullet for section in letter.sections for bullet in section.bullets]
    )
    assert requirement in combined
    assert f"Retained: {imaging.question}" in combined


def test_a_fictional_fourth_case_drafts_through_the_same_skill(
    decided: dict[str, Meeting],
) -> None:
    meeting = fictional(decided["CASE-MDT-CRC-BRAF-2026-001"], "nl")
    patient = communication_inputs(meeting, "patient")
    assert patient.language == "nl"
    assert "Dutch" in skill_instructions(patient)
    result = fake_result(patient)
    assert result.language == "nl"
    assert result.checks.reading_formula == LANGUAGES["nl"].formula
    letter = fake_result(communication_inputs(meeting, "clinician"))
    assert letter.language == "en"
    awareness = next(item for item in letter.sections if item.id == "patient_awareness")
    assert "Dutch" in " ".join(awareness.paragraphs)


def test_unknown_patient_language_is_refused_not_guessed(decided: dict[str, Meeting]) -> None:
    meeting = fictional(decided["CASE-MDT-CRC-BRAF-2026-001"], "fr")
    with pytest.raises(CommunicationRuntimeError, match="language 'fr'"):
        communication_inputs(meeting, "patient")


# ------------------------------------------------------------------- checks
def _prose_result(inputs: CommunicationInput, text: str) -> DraftResult:
    return DraftResult(
        title="t",
        sections=[CommunicationSection(id="x", heading="h", paragraphs=[text])],
        checks=_empty_checks(inputs),
        generated_by="azure",
        language=inputs.language,
    )


@pytest.mark.parametrize(
    ("language", "text", "formula", "ease"),
    [
        ("en", "The cat sat.", "Flesch", 119.2),
        ("de", "Der Hund lief.", "Amstad", 118.5),
        ("it", "Il sole è alto.", "Gulpease", 136.5),
    ],
)
def test_readability_uses_the_language_formula(
    decided: dict[str, Meeting], language: str, text: str, formula: str, ease: float,
) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    inputs = inputs.model_copy(update={"language": language})
    checks = check(_prose_result(inputs, text), inputs)
    assert formula in checks.reading_formula
    assert checks.reading_ease == ease
    assert checks.language == language
    assert (checks.grade_level is not None) == (language == "en")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The team looked at your scans and they will talk with you about what this means "
         "for you and your family, and what you would like to do next.", "en"),
        ("Das Team hat Ihre Bilder angesehen und wird mit Ihnen über das sprechen, was das "
         "für Sie und Ihre Familie bedeutet, und was Sie als Nächstes tun möchten.", "de"),
        ("Il team ha guardato le sue immagini e parlerà con lei di che cosa significa per "
         "lei e per la sua famiglia, e di che cosa vuole fare dopo.", "it"),
        ("Het team heeft uw beelden bekeken en zal met u praten over wat dit voor u en uw "
         "familie betekent, en wat u als volgende stap wilt doen.", "nl"),
        ("Short text.", None),
    ],
)
def test_language_detection(text: str, expected: str | None) -> None:
    assert detect_language(text) == expected


def test_patient_checks_flag_jargon_numbers_and_missing_refs(
    decided: dict[str, Meeting],
) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    result = _prose_result(inputs, "Your ctDNA was 987654 in the latest test.")
    result.checks = check(result, inputs)
    assert "ctDNA" in result.checks.unexplained_terms
    assert "987654" in result.checks.unsupported_numbers
    assert set(result.checks.uncovered_refs) == set(inputs.required_refs)
    findings = revision_findings(result, inputs)
    assert any("ctDNA" in item for item in findings)
    assert any("987654" in item for item in findings)
    result.glossary = [GlossaryTerm(term="ctDNA", meaning="Tiny bits of tumour material.")]
    assert "ctDNA" not in check(result, inputs).unexplained_terms


# ------------------------------------------------------------------- model contract
PLAIN = "The team met to talk about your care. They want to be sure about each step."


def patient_draft(
    inputs: CommunicationInput, paragraph: str = PLAIN, order: list[str] | None = None,
) -> PatientDraft:
    ids = order or [item[0] for item in PATIENT_SECTIONS]
    actions = [f"plan.action.{index}" for index in range(len(inputs.plan.actions))]
    conditions = [f"plan.condition.{index}" for index in range(len(inputs.plan.conditions))]
    resolved = [
        f"plan.resolved_requirement.{index}"
        for index in range(len(inputs.plan.resolved_requirements))
    ]
    return PatientDraft(
        title="Your care plan",
        sections=[
            DraftSection(
                id=section_id, heading=section_id.replace("_", " ").title(),
                paragraphs=[paragraph],
                source_refs=(
                    ["plan.decision", *resolved, *actions, *conditions]
                    if index == 0 else ["plan.summary"]
                ),
            )
            for index, section_id in enumerate(ids)
        ],
        glossary=[],
        questions_to_ask=["What happens first?"],
    )


class FakeClient:
    def __init__(self, *drafts: Any) -> None:
        self.drafts = list(drafts)
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(parse=self.parse)

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="completed", error=None, output=[], id="resp-1", model="fake",
            usage=SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30),
            output_parsed=self.drafts.pop(0),
        )


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "fake-deployment")

    def install(*drafts: Any) -> FakeClient:
        client = FakeClient(*drafts)

        async def factory(endpoint: str) -> FakeClient:
            return client

        monkeypatch.setattr(agents, "_azure_client", factory)
        return client

    return install


async def _noop(kind: str, payload: dict[str, Any]) -> None:
    return None


async def test_missing_model_fails_without_substitution(decided: dict[str, Meeting]) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    with pytest.raises(CommunicationRuntimeError, match="not configured"):
        await draft(inputs, emit=_noop, settings=SETTINGS)


async def test_model_gets_the_skill_no_tools_and_a_passing_draft_is_not_revised(
    decided: dict[str, Meeting], model: Any,
) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    client = model(patient_draft(inputs))
    events: list[dict[str, Any]] = []

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append(payload)

    result = await draft(inputs, emit=emit, settings=SETTINGS)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert "tools" not in call and "tool_choice" not in call
    assert call["store"] is False
    assert call["input"][0]["role"] == "system"
    assert call["input"][0]["content"] == skill_instructions(inputs)
    assert result.generated_by == "azure" and result.language == "en"
    assert [section.id for section in result.sections] == [item[0] for item in PATIENT_SECTIONS]
    assert any("Self-check passed" in str(item.get("summary")) for item in events)


async def test_a_failing_self_check_triggers_exactly_one_revision(
    decided: dict[str, Meeting], model: Any,
) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    rambling = " ".join(["the team will look again at every part of your care"] * 5) + "."
    client = model(patient_draft(inputs, rambling), patient_draft(inputs, rambling))
    result = await draft(inputs, emit=_noop, settings=SETTINGS)
    assert len(client.calls) == 2
    revision = client.calls[1]["input"]
    assert [item["role"] for item in revision] == ["system", "user", "assistant", "user"]
    assert "30 words" in revision[-1]["content"]
    assert result.checks.longest_sentence_words > 30


@pytest.mark.parametrize(
    ("paragraph", "message"),
    [
        (PLAIN + " See https://example.org for more.", "URL"),
        (PLAIN + " The study NCT01234567 is relevant.", "identifier"),
        ("Das Team hat Ihre Bilder angesehen und wird mit Ihnen über das sprechen, was das "
         "für Sie und Ihre Familie bedeutet.", "German"),
    ],
)
async def test_unsafe_or_wrong_language_drafts_fail(
    decided: dict[str, Meeting], model: Any, paragraph: str, message: str,
) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    model(patient_draft(inputs, paragraph))
    with pytest.raises(CommunicationRuntimeError, match=message):
        await draft(inputs, emit=_noop, settings=SETTINGS)


async def test_unknown_refs_and_wrong_section_order_fail(
    decided: dict[str, Meeting], model: Any,
) -> None:
    inputs = communication_inputs(decided["CASE-MDT-CRC-BRAF-2026-001"], "patient")
    invented = patient_draft(inputs)
    invented.sections[1].source_refs = ["evidence.INVENTED-TRIAL"]
    model(invented)
    with pytest.raises(CommunicationRuntimeError, match="do not exist"):
        await draft(inputs, emit=_noop, settings=SETTINGS)
    order = [item[0] for item in PATIENT_SECTIONS]
    order[0], order[4] = order[4], order[0]
    model(patient_draft(inputs, order=order))
    with pytest.raises(CommunicationRuntimeError, match="order"):
        await draft(inputs, emit=_noop, settings=SETTINGS)
