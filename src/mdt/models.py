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


Audience = Literal["patient", "clinician"]
CommunicationStatus = Literal["DRAFTING", "DRAFT", "CHANGES_REQUESTED", "APPROVED", "FAILED"]
AUDIENCES: tuple[Audience, ...] = ("patient", "clinician")


class CommunicationSection(Contract):
    """One ordered section; `source_refs` name the record entries it derives from."""

    id: str
    heading: str
    paragraphs: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class GlossaryTerm(Contract):
    term: str
    meaning: str


class CommunicationCitation(Contract):
    evidence_id: str
    title: str
    authority: str
    access: str
    verification: str


class CommunicationChecks(Contract):
    """Advisory quality signals shown to the reviewer; they never block approval."""

    word_count: int
    word_target: tuple[int, int]
    sentence_count: int
    average_sentence_words: float
    longest_sentence_words: int
    reading_ease: float
    reading_formula: str = "Flesch reading ease"
    grade_level: float | None = None
    reading_target: str
    language: str = "en"
    detected_language: str | None = None
    unexplained_terms: list[str] = Field(default_factory=list)
    uncovered_refs: list[str] = Field(default_factory=list)
    unsupported_numbers: list[str] = Field(default_factory=list)
    unresolved_citations: list[str] = Field(default_factory=list)
    unknown_refs: list[str] = Field(default_factory=list)


class CommunicationReview(Contract):
    action: Literal["approve", "request_changes", "regenerate"]
    reviewer: str
    role: Role | None = None
    actor: Literal["human"] = "human"
    comment: str = ""
    plan_version: int
    revision: int
    timestamp: str = Field(default_factory=utcnow)


class Communication(Contract):
    """A post-consensus document for one audience, bound to a plan version.

    Drafts come from a role runtime; only a named human reviewer can approve one.
    Status never changes the meeting phase.
    """

    audience: Audience
    plan_version: int
    revision: int = 1
    status: CommunicationStatus = "DRAFTING"
    generated_by: Literal["rehearsal", "azure"]
    author_role: str
    language: str = "en"
    title: str = ""
    sections: list[CommunicationSection] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    citations: list[CommunicationCitation] = Field(default_factory=list)
    checks: CommunicationChecks | None = None
    reviews: list[CommunicationReview] = Field(default_factory=list)
    requested_changes: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    approved_role: Role | None = None
    approved_at: str | None = None
    approved_revision: int | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


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
    communications: dict[str, Communication] = Field(default_factory=dict)
    """Post-consensus patient summary and clinician letter, keyed by audience."""
    cleared: bool = False
    """The orchestrator returned the room to standby; the record stays reviewable."""
