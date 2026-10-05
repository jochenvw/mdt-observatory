"""Shared test helpers: dossier source digests and a deterministic outcome drafter."""

import asyncio
import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mdt.communications import (
    PATIENT_SECTIONS,
    CommunicationInput,
    CommunicationRuntimeError,
    DraftAccountableDoctorAction,
    DraftResult,
    DraftSection,
    DraftStatement,
    LetterDraft,
    PatientDraft,
    compose_letter,
    compose_patient,
)
from mdt.models import GlossaryTerm


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never reach a real model unless a test configures one explicitly."""
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    yield


class FakeDrafter:
    """Deterministic stand-in for the language-model drafter.

    Records every input it receives, can be held on a gate to observe DRAFTING,
    and can be told to fail so tests can assert the failure stays visible.
    """

    def __init__(self) -> None:
        self.calls: list[CommunicationInput] = []
        self.gate: asyncio.Event | None = None
        self.error: str | None = None

    async def __call__(
        self, inputs: CommunicationInput, *, emit: Any, settings: Any
    ) -> DraftResult:
        self.calls.append(inputs)
        await emit(
            "CommunicationActivity",
            {"audience": inputs.audience, "summary": "Fake drafter applied the writing skill."},
        )
        if self.gate is not None:
            await self.gate.wait()
        if self.error:
            raise CommunicationRuntimeError(self.error)
        return fake_result(inputs)


def fake_result(inputs: CommunicationInput) -> DraftResult:
    actions = [f"plan.action.{index}" for index in range(len(inputs.plan.actions))]
    conditions = [f"plan.condition.{index}" for index in range(len(inputs.plan.conditions))]
    resolved = [
        f"plan.resolved_requirement.{index}"
        for index in range(len(inputs.plan.resolved_requirements))
    ]
    if inputs.audience == "patient":
        sections = [
            DraftSection(
                id=identifier, heading=heading,
                paragraphs=[f"The team talked about this part of your care. {hint}"],
                source_refs=(
                    ["plan.decision", *resolved, *actions] if identifier == "recommendation"
                    else conditions if identifier == "less_sure" else ["plan.summary"]
                ),
            )
            for identifier, heading, hint in PATIENT_SECTIONS
        ]
        return compose_patient(
            inputs,
            PatientDraft(
                title="Your care plan", sections=sections,
                glossary=[GlossaryTerm(term="scan", meaning="A picture inside the body.")],
                questions_to_ask=["What happens first?"],
            ),
        )
    return compose_letter(
        inputs,
        LetterDraft(
            intent=DraftStatement(
                text="Conditional plan agreed.",
                source_refs=["plan.decision", *resolved, "plan.summary"],
            ),
            discussion=[
                DraftStatement(
                    text=f"Retained: {item.question}", source_refs=[f"friction.{item.id}"]
                )
                for item in inputs.frictions
            ],
            accountable_doctor_actions=[
                DraftAccountableDoctorAction(
                    action="No action requested.", timing="Not applicable",
                    source_refs=actions[:1],
                )
            ],
        ),
    )


def source_digest(path: Path) -> str:
    """Digest a case source's content, independent of the checkout's line endings.

    Dossiers are packaged from text read with universal newlines, so the recorded
    provenance digest describes that content. Hashing the raw bytes would instead
    record whichever line endings a contributor's platform checked out, which made
    the same commit verify on one machine and fail on another.
    """
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
