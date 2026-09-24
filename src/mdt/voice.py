"""Voice configuration and spoken MDT discussion helpers.

The voice layer is deliberately separate from the chair state machine: it only
renders already-published meeting state into captions/audio and records human
transcript contributions for audit.
"""

from collections.abc import AsyncIterator
from typing import Literal

import httpx2
from pydantic import Field

from mdt.config import Settings
from mdt.models import Contract, Meeting, Role


class VoiceAgent(Contract):
    key: str
    label: str
    persona: str
    elevenlabs_voice_id: str
    preview_text: str
    role: Role | None = None


class VoiceSettings(Contract):
    provider: Literal["elevenlabs"]
    api_key_configured: bool
    external_processing_disclosure: str
    fallback: Literal["browser_speech_synthesis"]
    agents: list[VoiceAgent]


class VoiceTurn(Contract):
    id: str
    sequence: int
    agent_key: str
    speaker: str
    category: Literal["chair", "specialist", "human", "checkpoint"]
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    timestamp_offset_seconds: int


class VoiceDiscussion(Contract):
    mode: Literal["concise", "detailed"]
    turns: list[VoiceTurn]
    human_decision_checkpoint: str


class VoiceContribution(Contract):
    transcript: str = Field(min_length=1, max_length=4000)
    corrected_transcript: str | None = Field(default=None, max_length=4000)
    addressed_to: str | None = Field(default=None, max_length=200)
    confirmation_mode: bool = True


class VoiceContributionAccepted(Contract):
    meeting: Meeting
    routed_to: list[str]
    turns: list[VoiceTurn]


class SpeechRequest(Contract):
    agent_key: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1200)
    preview: bool = False


class VoiceSynthesisError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


VOICE_AGENTS: tuple[VoiceAgent, ...] = (
    VoiceAgent(
        key="chair",
        label="MDO chair",
        persona="Calm meeting chair who sequences speakers and stops at human review.",
        elevenlabs_voice_id="21m00Tcm4TlvDq8ikWAM",
        preview_text="I will chair the synthetic MDO and stop at the human decision checkpoint.",
    ),
    VoiceAgent(
        key="oncology",
        role=Role.ONCOLOGY,
        label="Medical oncologist",
        persona="Systemic treatment specialist focused on benefit, toxicity and sequencing.",
        elevenlabs_voice_id="AZnzlk1XvdvUeBnXmlld",
        preview_text="I will summarize the treatment trade-offs without approving a decision.",
    ),
    VoiceAgent(
        key="radiology",
        role=Role.RADIOLOGY,
        label="Radiologist",
        persona="Imaging specialist who distinguishes response, uncertainty and missing scans.",
        elevenlabs_voice_id="EXAVITQu4vr4xnSDxMaL",
        preview_text="I will describe the imaging findings and their limits.",
    ),
    VoiceAgent(
        key="pathology",
        role=Role.PATHOLOGY,
        label="Pathologist",
        persona=(
            "Tissue and molecular specialist who separates confirmed findings from assumptions."
        ),
        elevenlabs_voice_id="ErXwobaYiN019PkySvjV",
        preview_text="I will state which tissue findings are confirmed.",
    ),
    VoiceAgent(
        key="surgery",
        role=Role.SURGERY,
        label="Surgeon",
        persona="Operability specialist focused on technical feasibility and required safeguards.",
        elevenlabs_voice_id="MF3mGyEYCl7XYWbV9V6O",
        preview_text="I will explain procedural feasibility and what remains conditional.",
    ),
    VoiceAgent(
        key="radiation_oncology",
        role=Role.PROTOCOL,
        label="Radiation oncologist",
        persona=(
            "Local-treatment specialist who flags pathway limits and radiotherapy considerations."
        ),
        elevenlabs_voice_id="TxGEqnHWrfWFTfGW9XjX",
        preview_text="I will keep local treatment options conditional on human review.",
    ),
    VoiceAgent(
        key="specialist_nurse",
        role=Role.PATIENT,
        label="Specialist nurse",
        persona="Supportive-care voice for patient priorities, logistics and consent needs.",
        elevenlabs_voice_id="VR6AewLTigWG4xSOukaG",
        preview_text="I will reflect the recorded patient priorities and support needs.",
    ),
    VoiceAgent(
        key="clinical_trial",
        role=Role.RESEARCH,
        label="Clinical-trial specialist",
        persona="Evidence specialist who checks trial fit, access limits and uncertainty.",
        elevenlabs_voice_id="pNInz6obpgDQGcFmaJgB",
        preview_text="I will summarize trial evidence and eligibility uncertainty.",
    ),
)


def voice_settings(settings: Settings) -> VoiceSettings:
    return VoiceSettings(
        provider="elevenlabs",
        api_key_configured=bool(settings.elevenlabs_api_key),
        external_processing_disclosure=(
            "When enabled, only the selected caption text is sent server-side to ElevenLabs "
            "for speech generation. Microphone audio is not stored by default."
        ),
        fallback="browser_speech_synthesis",
        agents=list(VOICE_AGENTS),
    )


def agent_by_key(agent_key: str) -> VoiceAgent | None:
    return next((agent for agent in VOICE_AGENTS if agent.key == agent_key), None)


def validate_speech_request(settings: Settings, request: SpeechRequest) -> None:
    if agent_by_key(request.agent_key) is None:
        raise VoiceSynthesisError(404, "Configured voice agent is not available.")
    if not settings.elevenlabs_api_key:
        raise VoiceSynthesisError(
            503, "ElevenLabs API key is not configured; use browser speech synthesis fallback."
        )


def _role_agent(role: Role) -> VoiceAgent:
    return next(agent for agent in VOICE_AGENTS if agent.role == role)


def _case_label(meeting: Meeting) -> str:
    patient = meeting.case.get("pseudonym", "the synthetic patient")
    question = meeting.case.get("question", "the MDT decision question")
    return f"{patient}: {question}"


def build_voice_discussion(
    meeting: Meeting, mode: Literal["concise", "detailed"] = "concise"
) -> VoiceDiscussion:
    turns: list[VoiceTurn] = [
        VoiceTurn(
            id="chair-introduction",
            sequence=1,
            agent_key="chair",
            speaker="MDO chair",
            category="chair",
            text=(
                "This is a voice-enabled synthetic MDO rehearsal. "
                f"The decision question is {_case_label(meeting)}"
            ),
            timestamp_offset_seconds=0,
        )
    ]
    sequence = 2
    for role in Role:
        state = meeting.roles.get(role.value)
        if not state or not state.position:
            continue
        agent = _role_agent(role)
        position = state.position
        detail = ""
        if mode == "detailed" and position.uncertainties:
            detail = " Unresolved points: " + "; ".join(position.uncertainties[:3])
        turns.append(
            VoiceTurn(
                id=f"{agent.key}-assessment",
                sequence=sequence,
                agent_key=agent.key,
                speaker=agent.label,
                category="specialist",
                text=f"{position.position} Recommendation: {position.recommendation}.{detail}",
                evidence_ids=[
                    evidence_id
                    for claim in position.claims[:3]
                    for evidence_id in claim.evidence_ids[:3]
                ],
                timestamp_offset_seconds=(sequence - 1) * 30,
            )
        )
        sequence += 1
    unresolved = [item.question for item in meeting.frictions if not item.resolved]
    summary = (
        "The chair summary is that the published positions can inform discussion, "
        "but final approval remains a human decision."
    )
    if unresolved:
        summary += " Unresolved questions remain: " + "; ".join(unresolved[:3])
    elif meeting.plan:
        summary += f" Current proposal: {meeting.plan.summary}"
    turns.append(
        VoiceTurn(
            id="chair-final-summary",
            sequence=sequence,
            agent_key="chair",
            speaker="MDO chair",
            category="chair",
            text=summary,
            evidence_ids=meeting.plan.evidence_ids if meeting.plan else [],
            timestamp_offset_seconds=(sequence - 1) * 30,
        )
    )
    turns.append(
        VoiceTurn(
            id="human-decision-checkpoint",
            sequence=sequence + 1,
            agent_key="chair",
            speaker="Human decision checkpoint",
            category="checkpoint",
            text=(
                "The spoken MDO stops here. No agent may approve, finalize or capture the "
                "clinical decision without explicit human review in the existing workflow."
            ),
            timestamp_offset_seconds=sequence * 30,
        )
    )
    return VoiceDiscussion(
        mode=mode,
        turns=turns,
        human_decision_checkpoint="Existing version-bound human review remains required.",
    )


def route_voice_contribution(meeting: Meeting, contribution: VoiceContribution) -> list[VoiceTurn]:
    text = (contribution.corrected_transcript or contribution.transcript).lower()
    addressed = (contribution.addressed_to or "").lower()
    targets = [
        agent
        for agent in VOICE_AGENTS
        if agent.role is not None
        and (
            agent.key in text
            or agent.key.replace("_", " ") in text
            or agent.label.lower() in text
            or agent.role.value in text
            or agent.key in addressed
            or agent.label.lower() in addressed
        )
    ]
    if not targets:
        friction_roles = {
            role for item in meeting.frictions if not item.resolved for role in item.roles
        }
        targets = [_role_agent(role) for role in friction_roles]
        if not targets:
            chair = agent_by_key("chair")
            if chair is not None:
                targets = [chair]
    routed = [agent for agent in targets if agent is not None]
    turns = [
        VoiceTurn(
            id="chair-routes-human-contribution",
            sequence=1,
            agent_key="chair",
            speaker="MDO chair",
            category="chair",
            text=(
                "I have recorded the confirmed human contribution as transcription, not as an "
                "approved clinical decision, and will route it to the relevant specialists."
            ),
            timestamp_offset_seconds=0,
        )
    ]
    for index, agent in enumerate(routed, start=2):
        if agent.role is None:
            continue
        state = meeting.roles.get(agent.role.value)
        response = (
            state.position.recommendation
            if state and state.position
            else "I cannot respond until my published assessment is available."
        )
        turns.append(
            VoiceTurn(
                id=f"{agent.key}-response-to-human",
                sequence=index,
                agent_key=agent.key,
                speaker=agent.label,
                category="specialist",
                text=f"In response to the human contribution: {response}",
                evidence_ids=[
                    item
                    for claim in (state.position.claims[:2] if state and state.position else [])
                    for item in claim.evidence_ids[:2]
                ],
                timestamp_offset_seconds=(index - 1) * 30,
            )
        )
    return turns


async def elevenlabs_audio_stream(
    settings: Settings, request: SpeechRequest
) -> AsyncIterator[bytes]:
    validate_speech_request(settings, request)
    agent = agent_by_key(request.agent_key)
    assert agent is not None
    url = (
        f"{settings.elevenlabs_base_url.rstrip('/')}/text-to-speech/"
        f"{agent.elevenlabs_voice_id}/stream"
    )
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(45.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "accept": "audio/mpeg",
                    "content-type": "application/json",
                },
                json={
                    "text": agent.preview_text if request.preview else request.text,
                    "model_id": settings.elevenlabs_model_id,
                    "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
                },
            ) as response:
                if response.status_code == 429:
                    raise VoiceSynthesisError(429, "ElevenLabs rate limit reached.")
                if response.status_code == 404:
                    raise VoiceSynthesisError(502, "Configured ElevenLabs voice is unavailable.")
                if response.status_code >= 400:
                    raise VoiceSynthesisError(502, "ElevenLabs speech generation failed.")
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
    except VoiceSynthesisError:
        raise
    except Exception as exc:
        raise VoiceSynthesisError(502, "ElevenLabs speech generation failed.") from exc
