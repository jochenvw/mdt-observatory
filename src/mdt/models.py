"""Shared contracts for agents, orchestration, persistence and the browser."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Role(StrEnum):
    RADIOLOGY = "radiology"
    ONCOLOGY = "oncology"
    SURGERY = "surgery"
    PATHOLOGY = "pathology"
    RESEARCH = "research"
    PROTOCOL = "protocol"
    PATIENT = "patient"


class Phase(StrEnum):
    IDLE = "IDLE"
    CASE_LOADING = "CASE_LOADING"
    INITIAL_ANALYSIS = "INITIAL_ANALYSIS"
    POSITION_COLLECTION = "POSITION_COLLECTION"
    FRICTION_ANALYSIS = "FRICTION_ANALYSIS"
    TARGETED_DISCUSSION = "TARGETED_DISCUSSION"
    POSITION_UPDATE = "POSITION_UPDATE"
    PLAN_PROPOSAL = "PLAN_PROPOSAL"
    CONCURRENCE = "CONCURRENCE"
    DECISION_CAPTURED = "DECISION_CAPTURED"
    ERROR = "ERROR"


class Evidence(Contract):
    id: str
    title: str
    url: str
    date: str
    authority: str
    region: Literal["NL", "EU", "INTERNATIONAL", "US"]
    kind: str
    access: Literal[
        "PUBLIC_FULL_TEXT", "PUBLIC_ABSTRACT_ONLY", "LICENSED_INTERNAL", "NOT_ACCESSIBLE"
    ]
    patient_match: Literal["HIGH", "PARTIAL", "LOW"]
    passage: str
    limitations: list[str]
    scrutiny: dict[str, str]
    synthetic: bool = False
    retrieval: str = "CURATED"


class Claim(Contract):
    claim: str
    evidence_ids: list[str] = Field(min_length=1)


class Trace(Contract):
    assessment: str = ""
    observations: list[str] = Field(default_factory=list)
    hypothesis: str = ""
    uncertainties: list[str] = Field(default_factory=list)
    evidence_checking: list[str] = Field(default_factory=list)
    next_action: str = ""


class Position(Contract):
    role: Role
    case_id: str
    position: str
    confidence: float = Field(ge=0, le=1)
    autonomy: Literal["AUTO", "REVIEW", "ESCALATE"]
    claims: list[Claim] = Field(min_length=1)
    uncertainties: list[str]
    recommendation: str
    questions_for_mdt: list[str]
    human_intervention: bool = False
    provenance: list[str]
    stance: Literal["SUPPORT", "CONDITIONAL", "UNCERTAIN"]
    friction_keys: list[str]
    trace: Trace


class RoleState(Contract):
    role: Role
    label: str
    status: str = "IDLE"
    context: dict[str, Any] = Field(default_factory=dict)
    trace: Trace = Field(default_factory=Trace)
    position: Position | None = None
    activity: list[dict[str, Any]] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    revision: int = 0
    error: str | None = None


class Friction(Contract):
    id: str
    question: str
    roles: list[Role]
    missing: list[str]
    blocking: bool = True
    resolved: bool = False
    resolution: str | None = None


class Memory(Contract):
    id: str
    role: Role
    clinician_id: str = "demo-clinician"
    category: Literal[
        "FACTUAL_PATIENT", "INSTITUTIONAL_PRACTICE", "CLINICIAN_PREFERENCE", "EXPERIENTIAL_NUDGE"
    ]
    text: str
    source: str
    date: str
    status: Literal["AVAILABLE", "USED", "IGNORED", "FORGOTTEN"] = "AVAILABLE"


class Plan(Contract):
    version: int
    title: str
    summary: str
    actions: list[str]
    conditions: list[str]
    evidence_ids: list[str]
    created_at: str = Field(default_factory=utcnow)


class Concurrence(Contract):
    role: Role
    plan_version: int
    actor: Literal["human", "agent"]
    comment: str = ""
    timestamp: str = Field(default_factory=utcnow)


class Event(Contract):
    id: int
    meeting_id: str
    type: str
    role: Role | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utcnow)


class Meeting(Contract):
    id: str
    phase: Phase = Phase.IDLE
    mode: Literal["rehearsal", "azure"] = "rehearsal"
    case: dict[str, Any] = Field(default_factory=dict)
    roles: dict[str, RoleState] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    frictions: list[Friction] = Field(default_factory=list)
    memories: list[Memory] = Field(default_factory=list)
    plan: Plan | None = None
    concurrences: dict[str, Concurrence] = Field(default_factory=dict)
    objections: list[dict[str, Any]] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    round: int = 0
    busy: bool = False
    error: str | None = None
    created_at: str = Field(default_factory=utcnow)
    closed_at: str | None = None
    cleared: bool = False
    """The orchestrator returned the room to standby; the record stays reviewable."""
