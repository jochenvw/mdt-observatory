"""Post-consensus communication runtimes: patient summary and clinician letter.

These runtimes run after the chair state machine has captured a decision. They
receive role-scoped, read-only inputs built from the recorded meeting, never
search for new evidence and never approve their own output. Every statement
records the source entries it derives from, and advisory checks (coverage,
fidelity, readability, unexplained terms, citations) are computed for the human
reviewer. Live failures are raised, never replaced by scripted text.
"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

from opentelemetry import trace
from pydantic import Field

from mdt.config import Settings
from mdt.models import (
    Audience,
    CommunicationChecks,
    CommunicationCitation,
    CommunicationSection,
    Contract,
    Evidence,
    Friction,
    GlossaryTerm,
    Meeting,
    Plan,
    Role,
)

type Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

TRACER = trace.get_tracer("mdt.communications")
SKILLS_DIR = Path(__file__).with_name("skills")
AUTHOR_ROLE: dict[Audience, str] = {"patient": Role.PATIENT.value, "clinician": "chair"}
PATIENT_WORD_TARGET = (500, 1500)
LETTER_WORD_TARGET = (350, 600)
LETTER_READING_TARGET = "Professional clinical register; concise and scannable"
LETTER_LANGUAGE = "en"
MDT_TYPE = "Multidisciplinary team meeting (synthetic case)"
MAX_LIVE_SECONDS = 300
PATIENT_OUTPUT_TOKENS = 9000
LETTER_OUTPUT_TOKENS = 5000


class Language(Contract):
    code: str
    name: str
    native: str
    formula: str
    target: str
    # Flesch family: (constant, words-per-sentence weight, syllables-per-word weight).
    # Gulpease (Italian) is letter-based: 89 + (300 * sentences - 10 * letters) / words.
    kind: Literal["flesch", "gulpease"] = "flesch"
    weights: tuple[float, float, float] = (0, 0, 0)
    minimum: float = 60
    stopwords: frozenset[str]
    terms: tuple[str, ...]


LANGUAGES: dict[str, Language] = {
    "en": Language(
        code="en", name="English", native="English", formula="Flesch reading ease",
        target="Flesch reading ease ≥ 60 (about age 11–12, CEFR B1)",
        weights=(206.835, 1.015, 84.6),
        stopwords=frozenset("the and you your is are of to that this with for we not".split()),
        terms=(
            "ablation", "adenocarcinoma", "biopsy", "carcinoma", "chemotherapy", "ctDNA",
            "colectomy", "hepatectomy", "lesion", "lesions", "margin", "metastases",
            "metastasis", "metastatic", "multidisciplinary", "neuropathy", "nodule",
            "oncologist", "palliative", "pathologist", "prognosis", "radiologist", "remnant",
            "resection", "stoma", "systemic", "tumour", "tumor", "ultrasound", "anaesthetist",
            "anaesthesia", "pancreaticoduodenectomy",
        ),
    ),
    "de": Language(
        code="de", name="German", native="Deutsch", formula="Flesch-Lesbarkeit (Amstad)",
        target="Amstad reading ease ≥ 60 (plain German, CEFR B1)",
        weights=(180.0, 1.0, 58.5),
        stopwords=frozenset("und die der das sie ist nicht mit ein eine zu wir ihre ihr".split()),
        terms=(
            "Ablation", "Adenokarzinom", "Biopsie", "Karzinom", "Chemotherapie", "ctDNA",
            "Läsion", "Läsionen", "Metastase", "Metastasen", "metastasiert", "multidisziplinär",
            "Neuropathie", "Polyneuropathie", "Rundherd", "Onkologe", "Onkologin", "palliativ",
            "Pathologe", "Pathologin", "Prognose", "Radiologe", "Radiologin", "Resektion",
            "Stoma", "systemisch", "Tumor", "Ultraschall", "Anästhesie", "Anästhesist",
            "Anästhesistin", "Pankreatoduodenektomie",
        ),
    ),
    "it": Language(
        code="it", name="Italian", native="Italiano", formula="Gulpease index",
        target="Gulpease ≥ 60 (readable with lower-secondary schooling)",
        kind="gulpease",
        stopwords=frozenset("il la di che e non per una un lei sua suo con sono".split()),
        terms=(
            "ablazione", "adenocarcinoma", "biopsia", "carcinoma", "chemioterapia", "ctDNA",
            "lesione", "lesioni", "metastasi", "metastatico", "multidisciplinare", "neuropatia",
            "nodulo", "oncologo", "oncologa", "palliativo", "patologo", "patologa", "prognosi",
            "radiologo", "radiologa", "resezione", "stomia", "sistemico", "tumore", "ecografia",
            "anestesia", "anestesista", "duodenocefalopancreasectomia",
        ),
    ),
    "nl": Language(
        code="nl", name="Dutch", native="Nederlands", formula="Flesch–Douma",
        target="Flesch–Douma reading ease ≥ 60 (plain Dutch, B1)",
        weights=(206.835, 0.93, 77.0),
        stopwords=frozenset("de het een en van is niet u uw dat met voor wij we".split()),
        terms=(
            "ablatie", "adenocarcinoom", "biopsie", "carcinoom", "chemotherapie", "ctDNA",
            "laesie", "laesies", "metastase", "metastasen", "gemetastaseerd",
            "multidisciplinair", "neuropathie", "nodulus", "oncoloog", "palliatief",
            "patholoog", "prognose", "radioloog", "resectie", "stoma", "systemisch", "tumor",
            "echografie", "anesthesie", "anesthesioloog", "pancreatoduodenectomie",
        ),
    ),
}


def language_for(code: str | None) -> Language:
    """Known languages get calibrated checks; anything else is refused, not guessed."""
    found = LANGUAGES.get((code or "en").strip().lower())
    if found is None:
        raise CommunicationRuntimeError(
            f"No patient-summary checks exist for language '{code}'; nothing was drafted."
        )
    return found


PATIENT_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("why_we_met", "Why we met",
     "A team of specialists reviewed the case together and why that is normal. No findings."),
    ("what_we_looked_at", "What we looked at",
     "Scans, tissue tests and treatment so far, one plain sentence each."),
    ("what_we_know", "What we know so far",
     "The current situation, honestly. Introduce each medical term with a plain explanation."),
    ("less_sure", "What we are less sure about",
     "Every retained uncertainty, framed as things the team still needs to check."),
    ("recommendation", "What the team recommends",
     "The agreed actions in sequence, with why for each step."),
    ("day_to_day", "What this could mean for you day to day",
     "Treatment burden, recovery and support from the recorded patient perspective only."),
    ("your_choices", "Your choices and your voice",
     "The plan is a recommendation; the patient decides with their doctor. Cite recorded goals."),
    ("next_steps", "What happens next",
     "Concrete next steps and who the patient will talk to."),
)
PATIENT_SECTION_IDS = tuple(item[0] for item in PATIENT_SECTIONS)
# Capitalised words that are ordinary English in patient text, not abbreviations.
PLAIN_CAPITALS = {"I", "OK", "A"}
ACCESS_LABEL = {
    "PUBLIC_FULL_TEXT": "Public full text",
    "PUBLIC_ABSTRACT_ONLY": "Abstract only",
    "METADATA_ONLY": "Bibliographic record only",
    "LICENSED_INTERNAL": "Licensed, internal",
    "NOT_ACCESSIBLE": "Not accessible",
}
CASE_FIELDS = (
    "patient", "age", "diagnosis", "stage", "performance_status", "treatment",
    "previous_treatment", "question", "preferred_language",
)


class CommunicationRuntimeError(RuntimeError):
    """Explicit drafting, grounding or response-contract failure; shown to the reviewer."""


class CommunicationInput(Contract):
    """Role-scoped, read-only record handed to a communication runtime.

    Patient inputs hold the plan, retained frictions, basic case facts and the
    patient-perspective role only. Clinician inputs add the other specialties'
    published positions, recorded concurrences/objections and the metadata of
    evidence the specialists cited. Neither receives tools.
    """

    audience: Audience
    case_id: str
    mode: Literal["rehearsal", "azure"]
    language: str = LETTER_LANGUAGE
    plan: Plan
    case: dict[str, Any]
    frictions: list[Friction]
    positions: dict[str, dict[str, Any]]
    role_labels: dict[str, str]
    patient_context: dict[str, Any] = Field(default_factory=dict)
    concurrences: list[dict[str, Any]] = Field(default_factory=list)
    objections: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    closed_at: str | None = None
    revision: int = 1
    requested_changes: list[str] = Field(default_factory=list)
    refs: dict[str, str] = Field(default_factory=dict)
    required_refs: list[str] = Field(default_factory=list)


class DraftResult(Contract):
    title: str
    sections: list[CommunicationSection]
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    citations: list[CommunicationCitation] = Field(default_factory=list)
    checks: CommunicationChecks
    generated_by: Literal["rehearsal", "azure"]
    language: str = LETTER_LANGUAGE


# Strict structured-output contracts for the live model.
class DraftSection(Contract):
    id: str
    heading: str
    paragraphs: list[str]
    source_refs: list[str]


class PatientDraft(Contract):
    title: str
    sections: list[DraftSection]
    glossary: list[GlossaryTerm]
    questions_to_ask: list[str]


class DraftStatement(Contract):
    text: str
    source_refs: list[str]


class DraftGpAction(Contract):
    action: str
    timing: str
    source_refs: list[str]


class LetterDraft(Contract):
    intent: DraftStatement
    discussion: list[DraftStatement]
    gp_actions: list[DraftGpAction]


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _long_date(value: str | None) -> str:
    """Portable day-month-year formatting (no platform-specific strftime flags)."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value[:10]
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


def patient_language(meeting: Meeting) -> Language:
    """The patient's recorded preferred language; English when none is recorded."""
    return language_for(str(meeting.case.get("preferred_language") or "en"))


def communication_inputs(
    meeting: Meeting, audience: Audience, requested_changes: list[str] | None = None,
    revision: int = 1,
) -> CommunicationInput:
    """Build the read-only, role-scoped record one communication runtime may see."""
    if meeting.plan is None:
        raise CommunicationRuntimeError("A captured plan is required before drafting.")
    case = {key: meeting.case[key] for key in CASE_FIELDS if key in meeting.case}
    patient_state = meeting.roles.get(Role.PATIENT.value)
    patient_context = dict(patient_state.context) if patient_state else {}
    scoped_context: dict[str, Any] = {
        key: patient_context[key]
        for key in ("workspace", "question", "stated_priorities", "support", "language")
        if key in patient_context
    }
    labels = {key: state.label for key, state in meeting.roles.items()}
    roles = [Role.PATIENT.value] if audience == "patient" else list(meeting.roles)
    positions = {
        key: {
            "position": state.position.position,
            "recommendation": state.position.recommendation,
            "stance": state.position.stance,
        }
        for key in roles
        if (state := meeting.roles.get(key)) and state.position
    }
    inputs = CommunicationInput(
        audience=audience,
        case_id=str(meeting.case.get("id", "")),
        mode=meeting.mode,
        language=(
            patient_language(meeting).code if audience == "patient" else LETTER_LANGUAGE
        ),
        plan=meeting.plan.model_copy(deep=True),
        case=case,
        frictions=[item.model_copy(deep=True) for item in meeting.frictions],
        positions=positions,
        role_labels=labels,
        patient_context=scoped_context,
        closed_at=meeting.closed_at,
        revision=revision,
        requested_changes=list(requested_changes or []),
    )
    if audience == "clinician":
        inputs.case.update(
            {key: meeting.case[key] for key in ("pseudonym", "history", "biomarkers")
             if key in meeting.case}
        )
        toxicity = patient_context.get("treatment_toxicity") or patient_context.get("toxicity")
        if toxicity:
            inputs.case["toxicity"] = toxicity
        inputs.concurrences = [
            {"role": key, "actor": item.actor, "plan_version": item.plan_version,
             "comment": item.comment}
            for key, item in meeting.concurrences.items()
        ]
        inputs.objections = [dict(item) for item in meeting.objections]
        cited = set(meeting.plan.evidence_ids)
        inputs.evidence = [
            _evidence_metadata(item) for item in meeting.evidence if item.id in cited
        ]
    inputs.refs = _ref_map(inputs)
    inputs.required_refs = [
        *(f"plan.action.{index}" for index in range(len(inputs.plan.actions))),
        *(f"plan.condition.{index}" for index in range(len(inputs.plan.conditions))),
        *(
            [f"friction.{item.id}" for item in inputs.frictions]
            if audience == "clinician" else []
        ),
    ]
    return inputs


def _evidence_metadata(item: Evidence) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "authority": item.authority,
        "access": item.access,
        "synthetic": item.synthetic,
        "verification": item.scrutiny.get("verification")
        or (item.limitations[0] if item.limitations else ""),
    }


def _ref_map(inputs: CommunicationInput) -> dict[str, str]:
    plan = inputs.plan
    refs: dict[str, str] = {"plan.title": plan.title, "plan.summary": plan.summary}
    refs.update({f"plan.action.{i}": text for i, text in enumerate(plan.actions)})
    refs.update({f"plan.condition.{i}": text for i, text in enumerate(plan.conditions)})
    for key, value in inputs.case.items():
        if key == "history" and isinstance(value, list):
            refs.update({f"case.history.{i}": _text(item) for i, item in enumerate(value)})
        elif key == "biomarkers" and isinstance(value, dict):
            refs.update(
                {f"case.biomarkers.{i}": f"{name}: {_text(item)}"
                 for i, (name, item) in enumerate(value.items())}
            )
        else:
            refs[f"case.{key}"] = _text(value)
    for key, value in inputs.patient_context.items():
        refs[f"patient.{key}"] = _text(value)
    for role, position in inputs.positions.items():
        refs[f"position.{role}"] = (
            f"{inputs.role_labels.get(role, role)}: {position['position']} "
            f"Recommendation: {position['recommendation']}"
        )
    for friction in inputs.frictions:
        status = "Resolved" if friction.resolved else "Retained"
        refs[f"friction.{friction.id}"] = (
            f"{friction.question} {status}."
            + (f" {friction.resolution}" if friction.resolution else "")
        )
    for item in inputs.concurrences:
        refs[f"concurrence.{item['role']}"] = (
            f"{inputs.role_labels.get(item['role'], item['role'])}: {item['actor']} concurrence "
            f"with plan version {item['plan_version']}. {item['comment']}".strip()
        )
    for index, item in enumerate(inputs.objections):
        refs[f"objection.{index}"] = _text(item)
    for item in inputs.evidence:
        refs[f"evidence.{item['id']}"] = (
            f"{item['title']} ({item['authority']}); access {item['access']}; "
            f"{item['verification']}"
        )
    if inputs.closed_at:
        refs["meeting.closed_at"] = f"{inputs.closed_at} {_long_date(inputs.closed_at)}"
    refs["meeting.plan_version"] = f"plan version {plan.version}"
    return refs


def _known(refs: list[str], inputs: CommunicationInput) -> tuple[list[str], list[str]]:
    """Split cited ids into record entries and ids that do not exist in the record."""
    unique = list(dict.fromkeys(refs))
    return [ref for ref in unique if ref in inputs.refs], [
        ref for ref in unique if ref not in inputs.refs
    ]


# --------------------------------------------------------------------------- checks
_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:['’.\-][A-Za-zÀ-ÿ0-9]+)*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"“‘„«(]?[A-ZÀ-Ý0-9])")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
_CAPITALS = re.compile(r"\b[A-Z][A-Z0-9]*[A-Z](?:[a-z]{0,2})?\b|\b[a-z]{1,3}[A-Z]{2,}[A-Za-z]*\b")
_URL = re.compile(r"(?:https?://|www\.|case://)\S+", re.IGNORECASE)
_IDENTIFIER = re.compile(r"\b(?:NCT\d{8}|PMC\d+|PMID:?\s*\d+|10\.\d{4,9}/[\w.()/-]+)\b")
# Minimum stopword hits before the language guess is trusted.
_DETECTION_MINIMUM = 8


def _sentences(block: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_END.split(block.strip()) if part.strip()]
    return [part for part in parts if _WORD.search(part)]


def _syllables(word: str, language: str) -> int:
    lower = word.lower()
    if any(char.isdigit() for char in lower):
        return 1
    groups = re.findall(r"[aeiouyàáâäéèêëíìïîóòôöúùûü]+", lower)
    count = len(groups)
    if (
        language == "en" and lower.endswith("e")
        and not lower.endswith(("le", "ee", "ye")) and count > 1
    ):
        count -= 1
    return max(1, count)


def detect_language(text: str) -> str | None:
    """Stopword vote across the supported languages; None when the text is too short."""
    words = [word.lower() for word in _WORD.findall(text)]
    hits = {
        code: sum(1 for word in words if word in language.stopwords)
        for code, language in LANGUAGES.items()
    }
    best = max(hits, key=lambda code: hits[code])
    return best if hits[best] >= _DETECTION_MINIMUM else None


def _prose(result: DraftResult, audience: Audience) -> list[str]:
    blocks = [p for section in result.sections for p in (*section.paragraphs, *section.bullets)]
    if audience == "patient":
        blocks.extend(result.questions_to_ask)
    return blocks


def _numbers(text: str) -> set[str]:
    return {match.replace(",", ".") for match in _NUMBER.findall(text)}


def _explained(term: str, glossary: list[GlossaryTerm]) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
    return any(pattern.search(item.term) for item in glossary)


def check(result: DraftResult, inputs: CommunicationInput) -> CommunicationChecks:
    """Advisory quality signals for the reviewer; never an approval gate."""
    language = language_for(inputs.language)
    blocks = _prose(result, inputs.audience)
    sentences = [sentence for block in blocks for sentence in _sentences(block)]
    lengths = [len(_WORD.findall(sentence)) for sentence in sentences]
    words = [word for block in blocks for word in _WORD.findall(block)]
    syllables = sum(_syllables(word, language.code) for word in words)
    count = max(1, len(words))
    per_sentence = count / max(1, len(sentences))
    per_word = syllables / count
    if language.kind == "gulpease":
        letters = sum(len(word) for word in words)
        ease = 89 + (300 * max(1, len(sentences)) - 10 * letters) / count
    else:
        constant, sentence_weight, syllable_weight = language.weights
        ease = constant - sentence_weight * per_sentence - syllable_weight * per_word
    grade = (
        round(0.39 * per_sentence + 11.8 * per_word - 15.59, 1) if language.code == "en" else None
    )
    text = "\n".join(blocks)
    unexplained: list[str] = []
    if inputs.audience == "patient":
        for term in language.terms:
            pattern = rf"(?<![\w-]){re.escape(term)}(?![\w-])"
            # Mixed-case abbreviations (ctDNA) match exactly; words match in any case.
            flags = 0 if any(char.isupper() for char in term[1:]) else re.IGNORECASE
            if re.search(pattern, text, flags) and not _explained(term, result.glossary):
                unexplained.append(term)
        for token in dict.fromkeys(_CAPITALS.findall(text)):
            if token not in PLAIN_CAPITALS and not _explained(token, result.glossary):
                unexplained.append(token)
    cited = {ref for section in result.sections for ref in section.source_refs}
    source_numbers = _numbers(" ".join(inputs.refs.values()))
    unsupported = sorted(
        (number for number in _numbers(text) if number not in source_numbers),
        key=lambda value: float(value),
    )
    evidence_ids = {item["id"] for item in inputs.evidence}
    unresolved = [
        item.evidence_id for item in result.citations
        if item.evidence_id not in evidence_ids
        or item.evidence_id not in inputs.plan.evidence_ids
    ]
    return CommunicationChecks(
        word_count=len(words),
        word_target=PATIENT_WORD_TARGET if inputs.audience == "patient" else LETTER_WORD_TARGET,
        sentence_count=len(sentences),
        average_sentence_words=round(per_sentence, 1),
        longest_sentence_words=max(lengths, default=0),
        reading_ease=round(ease, 1),
        reading_formula=language.formula,
        grade_level=grade,
        reading_target=(
            language.target if inputs.audience == "patient" else LETTER_READING_TARGET
        ),
        language=language.code,
        detected_language=detect_language(text),
        unexplained_terms=list(dict.fromkeys(unexplained)),
        uncovered_refs=[ref for ref in inputs.required_refs if ref not in cited],
        unsupported_numbers=list(dict.fromkeys(unsupported)),
        unresolved_citations=unresolved,
        unknown_refs=sorted(ref for ref in cited if ref not in inputs.refs),
    )


def _empty_checks(inputs: CommunicationInput) -> CommunicationChecks:
    return CommunicationChecks(
        word_count=0, word_target=PATIENT_WORD_TARGET, sentence_count=0,
        average_sentence_words=0, longest_sentence_words=0, reading_ease=0,
        reading_target="", language=inputs.language,
    )


# --------------------------------------------------------------------------- composers
def compose_patient(inputs: CommunicationInput, draft: PatientDraft) -> DraftResult:
    """Patient summary from a skill draft; ids and order are enforced, checks computed."""
    if tuple(section.id for section in draft.sections) != PATIENT_SECTION_IDS:
        raise CommunicationRuntimeError(
            "Draft sections are missing or out of the required gentle order."
        )
    unknown: list[str] = []
    sections: list[CommunicationSection] = []
    for item in draft.sections:
        known, missing = _known(item.source_refs, inputs)
        unknown.extend(missing)
        sections.append(
            CommunicationSection(
                id=item.id, heading=item.heading, paragraphs=list(item.paragraphs),
                source_refs=known + missing,
            )
        )
    result = DraftResult(
        title=draft.title, sections=sections, glossary=list(draft.glossary),
        questions_to_ask=list(draft.questions_to_ask), checks=_empty_checks(inputs),
        generated_by="azure", language=inputs.language,
    )
    result.checks = check(result, inputs)
    return result

def _owner_and_action(action: str) -> tuple[str, str]:
    owner, separator, text = action.partition(": ")
    return (owner, text) if separator else ("MDT", action)


def compose_letter(inputs: CommunicationInput, narrative: LetterDraft) -> DraftResult:
    """Clinician-to-clinician outcome letter; record facts are quoted, not paraphrased."""
    case = inputs.case
    plan = inputs.plan
    unknown: list[str] = []

    def refs(items: list[str]) -> list[str]:
        found, missing = _known(items, inputs)
        unknown.extend(missing)
        return found

    patient_label = str(case.get("patient", "")).split("·")[-1].strip()
    represented = [
        f"{inputs.role_labels.get(item['role'], item['role'])}"
        + (" (automatic agent concurrence, demo policy)" if item["actor"] == "agent" else "")
        for item in inputs.concurrences
    ]
    header = CommunicationSection(
        id="header", heading="MDT outcome",
        paragraphs=[
            f"Re: {patient_label or 'synthetic patient'} · case reference "
            f"{case.get('pseudonym', inputs.case_id)} (synthetic record).",
            f"{MDT_TYPE} · decision captured {_long_date(inputs.closed_at)} · "
            f"plan version {plan.version}.",
            "Specialties represented: " + ("; ".join(represented) or "none recorded") + ".",
            "To: the general practitioner or referring colleague. "
            "No named recipient is recorded in this demonstration.",
        ],
        source_refs=[
            ref for ref in ("case.patient", "case.pseudonym", "meeting.closed_at",
                            "meeting.plan_version") if ref in inputs.refs
        ] + [f"concurrence.{item['role']}" for item in inputs.concurrences],
    )
    diagnosis_bullets = [
        f"Diagnosis: {case['diagnosis']}" if "diagnosis" in case else "",
        f"Stage: {case['stage']}" if "stage" in case else "",
        f"Performance status: {case['performance_status']}" if "performance_status" in case
        else "",
    ]
    biomarkers = case.get("biomarkers") if isinstance(case.get("biomarkers"), dict) else {}
    history = case.get("history") if isinstance(case.get("history"), list) else []
    diagnosis = CommunicationSection(
        id="diagnosis", heading="Diagnosis",
        bullets=[
            *(item for item in diagnosis_bullets if item),
            *(f"{name}: {_text(value)}" for name, value in (biomarkers or {}).items()),
            *(f"Background: {_text(item)}" for item in history or []),
        ],
        source_refs=[
            ref for ref in ("case.diagnosis", "case.stage", "case.performance_status")
            if ref in inputs.refs
        ] + [f"case.biomarkers.{i}" for i in range(len(biomarkers or {}))]
        + [f"case.history.{i}" for i in range(len(history or []))],
    )
    toxicity = case.get("toxicity")
    toxicity_text = (
        "; ".join(f"{name.replace('_', ' ')} {value}" for name, value in toxicity.items())
        if isinstance(toxicity, dict) else _text(toxicity) if toxicity else ""
    )
    treatment = CommunicationSection(
        id="treatment", heading="Treatment to date",
        bullets=[
            item for item in (
                f"Treatment: {case['treatment']}" if "treatment" in case else "",
                f"Timeline and response: {case['previous_treatment']}"
                if "previous_treatment" in case else "",
                f"Recorded toxicity: {toxicity_text}" if toxicity_text else "",
            ) if item
        ],
        source_refs=[
            ref for ref in ("case.treatment", "case.previous_treatment", "case.toxicity")
            if ref in inputs.refs
        ],
    )
    friction_bullets = [
        f"{'Resolved' if item.resolved else 'Retained'}: {item.question}"
        + (f" ({item.resolution})" if item.resolution else "")
        for item in inputs.frictions
    ]
    objection_bullets = [
        f"Objection ({inputs.role_labels.get(str(item.get('role')), item.get('role'))}, "
        f"plan v{item.get('plan_version')}): {item.get('comment')} — "
        + (f"addressed at plan v{item.get('accepted_plan_version')}."
           if item.get("addressed_at") else "not recorded as addressed.")
        for item in inputs.objections
    ]
    discussion = CommunicationSection(
        id="discussion", heading="MDT discussion",
        bullets=[
            f"Question: {case['question']}" if "question" in case else "",
            *(item.text for item in narrative.discussion),
            *friction_bullets,
            *objection_bullets,
        ],
        source_refs=[
            *(["case.question"] if "question" in case else []),
            *(ref for item in narrative.discussion for ref in refs(item.source_refs)),
            *(f"friction.{item.id}" for item in inputs.frictions),
            *(f"objection.{i}" for i in range(len(inputs.objections))),
        ],
    )
    discussion.bullets = [item for item in discussion.bullets if item]
    outcome = CommunicationSection(
        id="outcome", heading="MDT outcome and recommendation",
        paragraphs=[narrative.intent.text, plan.summary],
        source_refs=["plan.summary", *refs(narrative.intent.source_refs)],
    )
    conditions = CommunicationSection(
        id="conditions", heading="Conditions and outstanding uncertainties",
        columns=["#", "Condition"],
        rows=[[str(i + 1), text] for i, text in enumerate(plan.conditions)],
        source_refs=[f"plan.condition.{i}" for i in range(len(plan.conditions))],
    )
    actions = CommunicationSection(
        id="actions", heading="Actions and owners",
        columns=["Action", "Owner", "Timing"],
        rows=[
            [text, owner, "Not set by the MDT; to be agreed by the treating team"]
            for owner, text in map(_owner_and_action, plan.actions)
        ],
        source_refs=[f"plan.action.{i}" for i in range(len(plan.actions))],
    )
    gp = CommunicationSection(
        id="gp_actions", heading="For the GP",
        paragraphs=[] if narrative.gp_actions else [
            "No GP-specific action is supported by the record."
        ],
        columns=["GP action", "Timing"],
        rows=[[item.action, item.timing] for item in narrative.gp_actions],
        source_refs=[ref for item in narrative.gp_actions for ref in refs(item.source_refs)],
    )
    spoken = language_for(str(case.get("preferred_language") or "en"))
    awareness = CommunicationSection(
        id="patient_awareness", heading="Patient awareness",
        paragraphs=[
            "The outcome is to be discussed with the patient in clinic. The patient has not "
            "yet been informed of this MDT outcome, and no consent is recorded.",
            f"Preferred language: {spoken.name} ({spoken.native}). A plain-language patient "
            f"summary in {spoken.name} is prepared separately to support that conversation; "
            "check its review status before sharing it.",
        ],
        source_refs=[
            ref for ref in ("position.patient", "case.preferred_language") if ref in inputs.refs
        ],
    )
    external = [item for item in inputs.evidence if not item["synthetic"]]
    synthetic = [item for item in inputs.evidence if item["synthetic"]]
    citations = [
        CommunicationCitation(
            evidence_id=item["id"], title=item["title"], authority=item["authority"],
            access=ACCESS_LABEL.get(item["access"], item["access"]),
            verification=str(item["verification"]),
        )
        for item in external
    ]
    evidence = CommunicationSection(
        id="evidence", heading="Key evidence cited by the specialists",
        paragraphs=[
            "Case facts come from the synthetic case record, not external evidence."
            if synthetic else "",
        ],
        columns=["Source", "Authority", "Access", "Verification"],
        rows=[[item.title, item.authority, item.access, item.verification] for item in citations],
        source_refs=[f"evidence.{item['id']}" for item in inputs.evidence],
    )
    evidence.paragraphs = [item for item in evidence.paragraphs if item]
    sign_off = CommunicationSection(
        id="sign_off", heading="Sign-off",
        paragraphs=[
            "Drafted with agent support from the recorded MDT outcome"
            + " (language-model draft; "
            + ("live" if inputs.mode == "azure" else "scripted demonstration")
            + " meeting)."
            + " Not valid until reviewed and signed off by a named clinician.",
        ],
        source_refs=["meeting.plan_version"],
    )
    result = DraftResult(
        title=f"MDT outcome letter · {case.get('pseudonym', inputs.case_id)}",
        sections=[
            header, diagnosis, treatment, discussion, outcome, conditions, actions, gp,
            awareness, evidence, sign_off,
        ],
        citations=citations,
        checks=_empty_checks(inputs),
        generated_by="azure",
    )
    result.checks = check(result, inputs)
    result.checks.unknown_refs = sorted({*result.checks.unknown_refs, *unknown})
    return result


# --------------------------------------------------------------------------- live runtime
SKILL_FILES: dict[Audience, str] = {
    "patient": "patient_summary.md",
    "clinician": "clinician_letter.md",
}


@cache
def skill(audience: Audience) -> str:
    """The case-agnostic writing skill for one audience, loaded from `mdt/skills`."""
    return (SKILLS_DIR / SKILL_FILES[audience]).read_text(encoding="utf-8")


def skill_instructions(inputs: CommunicationInput) -> str:
    text = skill(inputs.audience)
    if inputs.audience == "patient":
        language = language_for(inputs.language)
        sections = "\n".join(
            f"{index}. `{sid}` (English working title: \"{heading}\"): {purpose}"
            for index, (sid, heading, purpose) in enumerate(PATIENT_SECTIONS, start=1)
        )
        text = text.replace("{{language}}", f"{language.name} ({language.native})")
        text = text.replace("{{sections}}", sections)
    return text


def _model_messages(inputs: CommunicationInput) -> list[dict[str, str]]:
    payload: dict[str, Any] = {
        "record": inputs.refs,
        "required_refs": inputs.required_refs,
        "requested_changes": inputs.requested_changes,
    }
    if inputs.audience == "patient":
        language = language_for(inputs.language)
        payload["write_in"] = f"{language.name} ({language.native})"
        payload["terms_to_explain_if_used"] = list(language.terms)
    return [
        {"role": "system", "content": skill_instructions(inputs)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _validate_live_text(text: str, cited: set[str], inputs: CommunicationInput) -> None:
    if _URL.search(text):
        raise CommunicationRuntimeError("Draft included a URL; no source links are permitted.")
    if _IDENTIFIER.search(text):
        raise CommunicationRuntimeError("Draft included a publication or trial identifier.")
    unknown = cited - set(inputs.refs)
    if unknown:
        raise CommunicationRuntimeError(
            f"Draft cited {len(unknown)} record entries that do not exist; nothing was published."
        )


def _validate_language(result: DraftResult, inputs: CommunicationInput) -> None:
    expected = language_for(inputs.language)
    detected = result.checks.detected_language
    if detected is not None and detected != expected.code:
        found = LANGUAGES[detected].name
        raise CommunicationRuntimeError(
            f"Draft was written in {found}, not the patient's language ({expected.name})."
        )


def _model_target() -> tuple[str, str]:
    from mdt.agents import AgentRuntimeError, _azure_target

    try:
        return _azure_target()
    except AgentRuntimeError:
        raise CommunicationRuntimeError(
            "Outcome documents are written by the language model, which is not configured "
            "on this server. Nothing was drafted."
        ) from None


def revision_findings(result: DraftResult, inputs: CommunicationInput) -> list[str]:
    """Advisory check findings the skill is asked to fix in its single self-revision."""
    checks = result.checks
    findings: list[str] = []
    if inputs.audience == "patient":
        language = language_for(inputs.language)
        if checks.reading_ease < language.minimum:
            findings.append(
                f"{checks.reading_formula} is {checks.reading_ease}; target {language.target}. "
                "Use shorter sentences and shorter, everyday words; drop technical detail."
            )
        if checks.longest_sentence_words > 30:
            findings.append(
                f"The longest sentence has {checks.longest_sentence_words} words; keep every "
                "sentence at 30 words or fewer."
            )
        if checks.word_count > checks.word_target[1]:
            findings.append(f"{checks.word_count} words is too long; aim for 600–900.")
    if checks.unexplained_terms:
        findings.append(
            "Explain these terms in the glossary or replace them with plain words: "
            + ", ".join(checks.unexplained_terms) + "."
        )
    if checks.uncovered_refs:
        findings.append(
            "Cover these required record entries in source_refs: "
            + ", ".join(checks.uncovered_refs) + "."
        )
    if checks.unsupported_numbers:
        findings.append(
            "Remove numbers that are not in the record: "
            + ", ".join(checks.unsupported_numbers) + "."
        )
    return findings


async def _model_draft(
    inputs: CommunicationInput, emit: Emit, settings: Settings
) -> DraftResult:
    """Draft, self-check and, if the advisory checks miss a target, revise once."""
    # Reuse the specialists' bounded Azure client, pacing and retry policy; no tools.
    from mdt.agents import _azure_client

    endpoint, deployment = _model_target()
    client = await _azure_client(endpoint)
    messages: list[dict[str, str]] = _model_messages(inputs)
    result, output = await _model_attempt(inputs, client, deployment, messages, emit, settings)
    findings = revision_findings(result, inputs)
    if not findings:
        await emit("ObservationAdded", {"summary": "Self-check passed; no revision needed."})
        return result
    await emit(
        "ObservationAdded",
        {
            "summary": f"Self-check found {len(findings)} issue(s); revising the draft once.",
            "findings": findings,
        },
    )
    messages = [
        *messages,
        {"role": "assistant", "content": output},
        {
            "role": "user",
            "content": json.dumps(
                {"revise": findings, "instruction": "Return the complete revised draft."},
                ensure_ascii=False,
            ),
        },
    ]
    revised, _ = await _model_attempt(inputs, client, deployment, messages, emit, settings)
    remaining = revision_findings(revised, inputs)
    await emit(
        "ObservationAdded",
        {
            "summary": (
                "Revision passed the self-check."
                if not remaining
                else f"{len(remaining)} advisory issue(s) remain for the clinician reviewer."
            ),
            "findings": remaining,
        },
    )
    return revised


async def _model_attempt(
    inputs: CommunicationInput, client: Any, deployment: str,
    conversation: list[dict[str, str]], emit: Emit, settings: Settings,
) -> tuple[DraftResult, str]:
    from mdt.agents import _azure_request, _validate_response

    messages: Any = conversation
    model: type[PatientDraft] | type[LetterDraft] = (
        PatientDraft if inputs.audience == "patient" else LetterDraft
    )
    budget = PATIENT_OUTPUT_TOKENS if inputs.audience == "patient" else LETTER_OUTPUT_TOKENS
    with TRACER.start_as_current_span(
        "mdt.communication.model", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attribute("mdt.audience", inputs.audience)
        span.set_attribute("mdt.language", inputs.language)
        completion = await _azure_request(
            lambda: client.responses.parse(
                model=deployment,
                input=messages,
                text_format=model,
                reasoning={"effort": "low"},
                store=False,
                max_output_tokens=budget,
            ),
            emit,
            interval_seconds=settings.azure_request_interval_seconds,
        )
        usage = completion.usage
        if usage is None or usage.total_tokens <= 0:
            raise CommunicationRuntimeError("Azure response omitted token usage metadata.")
        span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
        span.set_attribute("gen_ai.request.model", deployment)
        span.set_attribute("gen_ai.response.model", completion.model)
        request_id = getattr(completion, "_request_id", None)
        await emit(
            "ObservationAdded",
            {
                "summary": "The model returned a structured draft for clinician review.",
                "deployment": deployment,
                "model_request_id": request_id or completion.id,
                "token_usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
            },
        )
    try:
        _validate_response(completion)
    except Exception as error:
        raise CommunicationRuntimeError(str(error)) from None
    parsed = completion.output_parsed
    if inputs.audience == "patient":
        if not isinstance(parsed, PatientDraft):
            raise CommunicationRuntimeError("Azure returned no parsed patient summary.")
        cited = {ref for section in parsed.sections for ref in section.source_refs}
        _validate_live_text(parsed.model_dump_json(), cited, inputs)
        result = compose_patient(inputs, parsed)
        _validate_language(result, inputs)
        return result, parsed.model_dump_json()
    if not isinstance(parsed, LetterDraft):
        raise CommunicationRuntimeError("Azure returned no parsed letter content.")
    cited = {
        *parsed.intent.source_refs,
        *(ref for item in parsed.discussion for ref in item.source_refs),
        *(ref for item in parsed.gp_actions for ref in item.source_refs),
    }
    _validate_live_text(parsed.model_dump_json(), cited, inputs)
    return compose_letter(inputs, parsed), parsed.model_dump_json()


async def draft(inputs: CommunicationInput, *, emit: Emit, settings: Settings) -> DraftResult:
    """Apply the audience's writing skill to the recorded outcome of any case.

    Rehearsal and live meetings draft the same way; there is no scripted substitute,
    so a missing model or a failed check leaves the document visibly failed.
    """
    with TRACER.start_as_current_span(
        "mdt.communication.draft", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attribute("mdt.audience", inputs.audience)
        span.set_attribute("mdt.mode", inputs.mode)
        language = language_for(inputs.language)
        await emit(
            "ObservationAdded",
            {
                "summary": (
                    f"Writing the patient summary in {language.name} with the "
                    "patient-summary skill."
                    if inputs.audience == "patient"
                    else "Writing the colleague letter with the clinician-letter skill."
                ),
                "skill": SKILL_FILES[inputs.audience],
                "language": language.code,
            },
        )
        async with asyncio.timeout(MAX_LIVE_SECONDS):
            return await _model_draft(inputs, emit, settings)