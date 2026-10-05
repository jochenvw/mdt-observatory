import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeDrafter

from mdt.agents import analyze
from mdt.case_registry import get_case
from mdt.config import Settings
from mdt.engine import Conflict, Engine, NotFound
from mdt.models import Phase, Position, Role
from mdt.scenario import CASE
from mdt.store import Store

CLEARANCE_GUIDANCE = (
    "I reviewed all nine liver sites, vessel margins and the lung nodule. The sites are "
    "mapped, the margins and remnant are adequate, and the nodule is not suspicious."
)

ADDITIONAL_CASES = (
    (
        "CASE-MDT-CRC-WT-2026-002",
        "I reviewed all 11 baseline liver sites and the uncertain focus. The mapping, vessel "
        "interfaces and remnant are adequate for the proposed parenchymal-sparing treatment.",
    ),
    (
        "CASE-MDT-PDAC-PERIOP-2026-003",
        "I reviewed the pancreatic imaging alongside the echo: the SMV/portal interface is "
        "reconstructable and no arterial involvement is seen. Cardiac reserve and fitness for "
        "surgery stay with the perioperative review.",
    ),
)


@pytest.mark.parametrize(
    ("case_id", "guidance", "direction"),
    (
        (*ADDITIONAL_CASES[0], "PROCEED_TREATMENT"),
        (*ADDITIONAL_CASES[1], "INVESTIGATE_FURTHER"),
    ),
)
async def test_selected_case_complete_workflow_and_durable_source(
    tmp_path: Path, case_id: str, guidance: str, direction: str,
) -> None:
    definition = get_case(case_id)
    assert definition.runtime is not None
    engine = make_engine(tmp_path)
    started = await engine.start("rehearsal", case_id)
    await settled(engine)
    meeting = engine.get(started.id)
    assert meeting.case == definition.case
    assert meeting.phase == Phase.TARGETED_DISCUSSION
    assert {f.id for f in meeting.frictions if not f.resolved} == {"imaging", "applicability"}
    assert all(
        state.position and state.position.case_id == case_id for state in meeting.roles.values()
    )
    await engine.followup(started.id)
    await settled(engine)
    assert meeting.phase == Phase.TARGETED_DISCUSSION
    assert not next(f for f in meeting.frictions if f.id == "imaging").resolved
    await engine.steer(started.id, Role.RADIOLOGY, guidance)
    await settled(engine)
    assert meeting.phase == Phase.CONCURRENCE
    assert meeting.plan is not None
    assert meeting.plan.direction == direction
    assert meeting.plan.decision
    assert meeting.plan.title == definition.runtime.proposal.title
    expected_proposal_conditions = (
        set(definition.runtime.proposal.conditions) - set(definition.runtime.imaging_conditions)
    )
    expected_residual_conditions = (
        set(definition.runtime.residual_conditions) - set(definition.runtime.imaging_conditions)
    )
    assert expected_proposal_conditions <= set(meeting.plan.conditions)
    assert expected_residual_conditions <= set(meeting.plan.conditions)
    assert not set(definition.runtime.imaging_conditions) & set(meeting.plan.conditions)
    assert len(meeting.plan.resolved_requirements) == 1
    resolution = meeting.plan.resolved_requirements[0]
    assert resolution.requirement_id == "imaging"
    assert resolution.role == Role.RADIOLOGY
    assert resolution.human_input == guidance
    assert resolution.status == "CONFIRMED"
    assert all(
        not action.startswith(f"{state.label}:")
        for action in meeting.plan.actions
        for state in meeting.roles.values()
    )
    for forbidden in ("encorafenib", "cetuximab", "all nine", "5 mm lung", "hypomagnesemia"):
        assert forbidden not in meeting.plan.model_dump_json().lower()
    if case_id.endswith("003"):
        assert not any(item.id.startswith("CRC-") for item in meeting.evidence)
        assert "perioperative" in meeting.roles[Role.SURGERY].label.lower()
    assert set(meeting.concurrences) == {Role.PATHOLOGY}
    for role in Role:
        if role not in meeting.concurrences:
            await engine.concur(started.id, role, "Reviewed conditional demonstration proposal.")
    assert meeting.phase == Phase.DECISION_CAPTURED
    assert all(v.plan_version == meeting.plan.version for v in meeting.concurrences.values())
    await settled(engine)
    patient = meeting.communications["patient"]
    assert patient.status == "DRAFT"
    assert patient.language == definition.case["preferred_language"]
    assert meeting.communications["clinician"].language == "en"
    saved = meeting.model_dump()
    await engine.close()
    restored = Store(str(tmp_path / "mdt.db"))
    snapshot = restored.get(started.id)
    assert snapshot is not None and snapshot.model_dump() == saved
    restored.close()


async def test_switching_cases_scopes_memories_and_preserves_previous_room(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    snapshots: list[dict[str, Any]] = []
    for case_id in (str(CASE["id"]), *(item[0] for item in ADDITIONAL_CASES), str(CASE["id"])):
        started = await engine.start("rehearsal", case_id)
        await settled(engine)
        meeting = engine.get(started.id)
        expected_memories = {item.id for item in get_case(case_id).memories}
        assert {item.id for item in meeting.memories} == expected_memories
        assert all(
            state.context == get_case(case_id).contexts[state.role]
            for state in meeting.roles.values()
        )
        snapshots.append(meeting.model_dump())
        for saved in snapshots:
            assert engine.get(saved["id"]).model_dump() == saved
    await engine.close()


@pytest.mark.parametrize(("case_id", "guidance"), ADDITIONAL_CASES)
async def test_added_case_rejects_cross_case_evidence_before_proposal(
    tmp_path: Path, case_id: str, guidance: str,
) -> None:
    async def wrong_evidence(role: Role, **kwargs: Any) -> Position:
        position = await analyze(role, **kwargs)
        position.claims[0].evidence_ids = ["CASE-CRC-RADIOLOGY"]
        position.provenance = ["CASE-CRC-RADIOLOGY"]
        return position

    settings = Settings(db_path=str(tmp_path / "rejected.db"), step_delay=0)
    engine = Engine(Store(settings.db_path), settings, wrong_evidence)
    started = await engine.start("rehearsal", case_id)
    await settled(engine)
    meeting = engine.get(started.id)
    assert meeting.phase == Phase.ERROR
    assert meeting.plan is None
    assert all(role.error for role in meeting.roles.values())
    await engine.close()


def _example_replies() -> dict[str, str]:
    """Radiology example replies the frontend offers when its agent asks for input."""
    import re

    source = (Path(__file__).parents[1] / "frontend" / "src" / "caseProfiles.ts").read_text(
        encoding="utf-8"
    )
    conversion, pancreatic = source.split("const pancreaticProfiles", 1)
    reply = r"radiology: \{.*?reply: '([^']+)'"
    return {
        str(CASE["id"]): re.search(r"DEFAULT_RADIOLOGY_REPLY = '([^']+)'", source).group(1),  # type: ignore[union-attr]
        "CASE-MDT-CRC-WT-2026-002": re.search(reply, conversion, re.S).group(1),  # type: ignore[union-attr]
        "CASE-MDT-PDAC-PERIOP-2026-003": re.search(reply, pancreatic, re.S).group(1),  # type: ignore[union-attr]
    }


@pytest.mark.parametrize("case_id", sorted(_example_replies()))
async def test_general_approval_keeps_the_imaging_question_open_until_a_review_is_reported(
    tmp_path: Path, case_id: str,
) -> None:
    engine = make_engine(tmp_path)
    started = await engine.start("rehearsal", case_id)
    await settled(engine)
    meeting = engine.get(started.id)
    await engine.steer(started.id, Role.RADIOLOGY, "It's fine - we can do it - go ahead")
    await settled(engine)
    imaging = next(f for f in meeting.frictions if f.id == "imaging")
    assert not imaging.resolved, "approval that names no review must not close the question"
    assert meeting.roles[Role.RADIOLOGY].position.autonomy == "ESCALATE"
    assert not meeting.requirement_resolutions
    await engine.steer(started.id, Role.RADIOLOGY, _example_replies()[case_id])
    await settled(engine)
    assert next(f for f in meeting.frictions if f.id == "imaging").resolved
    assert meeting.roles[Role.RADIOLOGY].position.autonomy == "REVIEW"
    assert meeting.requirement_resolutions[0].human_input == _example_replies()[case_id]
    await engine.close()


async def test_incomplete_radiology_review_stays_pending_and_cannot_create_a_plan(
    tmp_path: Path,
) -> None:
    engine = make_engine(tmp_path)
    started = await engine.start("rehearsal", "CASE-MDT-PDAC-PERIOP-2026-003")
    await settled(engine)
    await engine.steer(
        started.id,
        Role.RADIOLOGY,
        "I reviewed the pancreatic imaging. The interface is reconstructable, but the echo "
        "and anaesthetic reserve review are still needed before surgery.",
    )
    await settled(engine)
    meeting = engine.get(started.id)
    imaging = next(item for item in meeting.frictions if item.id == "imaging")
    assert not imaging.resolved
    assert meeting.plan is None
    assert not meeting.requirement_resolutions
    assert meeting.roles[Role.RADIOLOGY].position.autonomy == "ESCALATE"
    await engine.close()


async def test_later_rejected_radiology_finding_overrides_an_earlier_confirmation(
    tmp_path: Path,
) -> None:
    engine = make_engine(tmp_path)
    started = await engine.start("rehearsal")
    await settled(engine)
    await engine.steer(started.id, Role.RADIOLOGY, CLEARANCE_GUIDANCE)
    await settled(engine)
    meeting = engine.get(started.id)
    assert next(item for item in meeting.frictions if item.id == "imaging").resolved
    assert meeting.requirement_resolutions

    await engine.steer(
        started.id,
        Role.RADIOLOGY,
        "I reviewed the liver mapping again. The vessel margin is inadequate and the sites "
        "are not acceptable for the proposed treatment.",
    )
    await settled(engine)
    imaging = next(item for item in meeting.frictions if item.id == "imaging")
    assert not imaging.resolved
    assert not meeting.requirement_resolutions
    assert meeting.roles[Role.RADIOLOGY].position.autonomy == "ESCALATE"
    assert any(event.type == "RequirementReopened" for event in meeting.events)
    await engine.close()


def make_engine(tmp_path: Path, drafter: FakeDrafter | None = None) -> Engine:
    settings = Settings(db_path=str(tmp_path / "mdt.db"), step_delay=0)
    return Engine(Store(settings.db_path), settings, analyze, drafter=drafter or FakeDrafter())


async def settled(engine: Engine) -> None:
    while engine.tasks:
        await asyncio.gather(*list(engine.tasks))


async def proposal(engine: Engine) -> str:
    meeting = await engine.start("rehearsal")
    await settled(engine)
    await engine.steer(meeting.id, Role.RADIOLOGY, CLEARANCE_GUIDANCE)
    await settled(engine)
    await engine.followup(meeting.id)
    await settled(engine)
    assert engine.get(meeting.id).phase == Phase.CONCURRENCE
    return meeting.id


async def test_complete_demo_and_durable_audit(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    state = engine.get(meeting.id)
    assert state.phase == Phase.TARGETED_DISCUSSION
    assert len(state.roles) == 7
    assert all(role.position for role in state.roles.values())
    assert {f.id for f in state.frictions if not f.resolved} == {"imaging", "applicability"}
    await engine.steer(meeting.id, Role.RADIOLOGY, CLEARANCE_GUIDANCE)
    await settled(engine)
    state = engine.get(meeting.id)
    assert next(f for f in state.frictions if f.id == "imaging").resolved
    before = {role: state.roles[role].revision for role in Role}
    await engine.followup(meeting.id)
    await settled(engine)
    state = engine.get(meeting.id)
    assert state.phase == Phase.CONCURRENCE
    assert state.roles[Role.RADIOLOGY].revision == before[Role.RADIOLOGY]
    assert state.plan and state.plan.conditions
    assert state.plan.direction == "PROCEED_TREATMENT"
    assert state.plan.decision
    assert state.plan.resolved_requirements[0].human_input == CLEARANCE_GUIDANCE
    assert not set(get_case(str(CASE["id"])).runtime.imaging_conditions) & set(
        state.plan.conditions
    )
    for role in Role:
        if role not in state.concurrences:
            await engine.concur(meeting.id, role, "Reviewed demonstration proposal.")
    state = engine.get(meeting.id)
    assert state.phase == Phase.DECISION_CAPTURED
    assert state.closed_at
    assert all(v.plan_version == state.plan.version for v in state.concurrences.values())
    assert [e.id for e in state.events] == list(range(1, len(state.events) + 1))
    assert state.events[-1].type == "CaseClosed"
    saved = state.model_dump()
    await engine.close()
    store = Store(str(tmp_path / "mdt.db"))
    restored = store.get(meeting.id)
    assert restored and restored.model_dump() == saved
    store.close()


async def test_case_selection_cannot_replace_an_active_round(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    with pytest.raises(NotFound, match="Selected case is not available"):
        await engine.start("rehearsal", "CASE-NOT-CONFIGURED")
    assert engine.meeting is None
    assert engine.store.count() == 0
    meeting = await engine.start("rehearsal", str(CASE["id"]))
    with pytest.raises(Conflict, match="active round"):
        await engine.start("rehearsal", str(CASE["id"]))
    await settled(engine)
    state = engine.get(meeting.id)
    assert state.case == CASE
    assert state.phase == Phase.TARGETED_DISCUSSION
    assert {item.id for item in state.frictions if not item.resolved} == {
        "imaging", "applicability"
    }
    saved = state.model_dump()
    with pytest.raises(NotFound, match="Selected case is not available"):
        await engine.start("rehearsal", "CASE-NOT-CONFIGURED")
    assert engine.get(meeting.id).model_dump() == saved
    assert engine.store.count() == 1
    await engine.close()


async def test_full_crc_dossier_survives_proposal_capture_and_restart(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await proposal(engine)
    state = engine.get(meeting_id)
    assert state.case["dossier"] == CASE["dossier"]
    assert state.case["management_alternatives"] == CASE["management_alternatives"]
    assert state.case["specialty_contributions"] == CASE["specialty_contributions"]
    assert state.plan
    text = state.plan.model_dump_json().lower()
    for marker in ("ctdna", "lung nodule", "nine", "systemic", "conditional"):
        assert marker in text
    assert "authorized automatically" in text
    assert "synthetic" not in text
    assert "checkmate" not in text and "pembrolizumab" not in text
    for role in Role:
        if role not in state.concurrences:
            await engine.concur(meeting_id, role, "Reviewed this version.", state.plan.version)
    await settled(engine)
    assert {item.status for item in state.communications.values()} == {"DRAFT"}
    expected = state.model_dump()
    await engine.close()
    restored = make_engine(tmp_path)
    assert restored.get(meeting_id).model_dump() == expected
    await restored.close()


async def test_old_case_cannot_mix_with_new_runtime_or_be_rewritten(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    old = engine.get(meeting.id)
    old.case["id"] = "SYN-LUNG-042"
    old.case["diagnosis"] = "Historical lung case"
    engine.store.save(old)
    snapshot = old.model_dump()
    with pytest.raises(Conflict, match="earlier case version"):
        await engine.steer(meeting.id, Role.RADIOLOGY, CLEARANCE_GUIDANCE)
    with pytest.raises(Conflict, match="earlier case version"):
        await engine.followup(meeting.id)
    with pytest.raises(Conflict, match="earlier case version"):
        await engine.retry(meeting.id)
    assert engine.get(meeting.id).model_dump() == snapshot
    new = await engine.start("rehearsal")
    await settled(engine)
    assert new.case["id"] == CASE["id"]
    assert engine.get(meeting.id).model_dump() == snapshot
    await engine.close()


async def test_case_record_is_snapshot_not_mutable_scenario_alias(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    first = await engine.start("rehearsal")
    await settled(engine)
    current = engine.get(first.id)
    current.case["dossier"]["patient"]["age"] = 999
    assert CASE["dossier"]["patient"]["age"] == 59
    second = await engine.start("rehearsal")
    await settled(engine)
    assert second.case["dossier"]["patient"]["age"] == 59
    await engine.close()


async def test_unrelated_steering_does_not_resolve_imaging(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    await engine.steer(meeting.id, Role.RADIOLOGY, "Make the wording shorter.")
    await settled(engine)
    assert any(f.id == "imaging" and not f.resolved for f in engine.get(meeting.id).frictions)
    await engine.close()


async def test_followup_cannot_bypass_human_imaging_review(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    await engine.followup(meeting.id)
    await settled(engine)
    state = engine.get(meeting.id)
    assert state.phase == Phase.TARGETED_DISCUSSION
    assert any(f.id == "imaging" and not f.resolved for f in state.frictions)
    with pytest.raises(Conflict):
        await engine.concur(meeting.id, Role.RADIOLOGY, "")
    await engine.close()


async def test_objection_invalidates_votes_and_requires_new_human_review(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await proposal(engine)
    state = engine.get(meeting_id)
    assert state.plan
    version = state.plan.version
    await engine.concur(meeting_id, Role.RADIOLOGY, "")
    await engine.object(
        meeting_id, Role.RESEARCH, "Please retain the trial population uncertainty."
    )
    assert state.phase == Phase.TARGETED_DISCUSSION
    assert not state.concurrences
    await engine.followup(meeting_id)
    await settled(engine)
    assert state.phase == Phase.CONCURRENCE
    assert state.plan.version == version + 1
    assert Role.RESEARCH not in state.concurrences
    await engine.concur(meeting_id, Role.RESEARCH, "The revised conditions address my objection.")
    assert state.objections[0]["accepted_plan_version"] == state.plan.version
    await engine.close()


async def test_closed_decisions_are_immutable(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await proposal(engine)
    state = engine.get(meeting_id)
    for role in Role:
        if role not in state.concurrences:
            await engine.concur(meeting_id, role, "")
    with pytest.raises(Conflict):
        await engine.steer(meeting_id, Role.RADIOLOGY, "Change the growth assessment.")
    with pytest.raises(Conflict):
        await engine.object(meeting_id, Role.RADIOLOGY, "Change the decision.")
    await settled(engine)
    await engine.start("rehearsal")
    await settled(engine)
    assert engine.get(meeting_id).phase == Phase.DECISION_CAPTURED
    await engine.close()


async def test_busy_commands_rejected(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    with pytest.raises(Conflict):
        await engine.start("rehearsal")
    with pytest.raises(Conflict):
        await engine.steer(meeting.id, Role.RADIOLOGY, "Review growth")
    await settled(engine)
    await engine.close()


async def test_failed_agent_blocks_consensus_and_retry_recovers(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    original = engine.analyzer

    async def fail(role: Role, **kwargs: Any) -> Position:
        if role == Role.RESEARCH:
            raise RuntimeError("Simulated provider outage")
        return await original(role, **kwargs)

    engine.analyzer = fail
    meeting = await engine.start("rehearsal")
    await settled(engine)
    assert engine.get(meeting.id).phase == Phase.ERROR
    assert engine.get(meeting.id).roles[Role.RESEARCH].error
    assert engine.get(meeting.id).plan is None
    engine.analyzer = original
    await engine.retry(meeting.id)
    await settled(engine)
    assert engine.get(meeting.id).phase == Phase.TARGETED_DISCUSSION
    await engine.close()


async def test_runtime_failure_never_becomes_a_clinical_question(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    original = engine.analyzer
    question = "Review the recorded treatment response and remaining uncertainty."
    error = "Specialist analysis failed: APITimeoutError; no rehearsal fallback."

    async def fail(role: Role, **kwargs: Any) -> Position:
        if role != Role.ONCOLOGY:
            return await original(role, **kwargs)
        emit = kwargs["emit"]
        await emit("ObservationAdded", {"summary": question})
        await emit("ReviewRetryScheduled", {
            "summary": "Another review attempt is scheduled.",
            "status": "RETRYING", "error_type": "APITimeoutError",
        })
        await emit("UncertaintyRaised", {
            "summary": error, "error": True, "error_type": "APITimeoutError",
        })
        raise RuntimeError(error)

    engine.analyzer = fail
    meeting = await engine.start("rehearsal")
    await settled(engine)
    state = engine.get(meeting.id)
    role = state.roles[Role.ONCOLOGY]
    assert state.phase == Phase.ERROR and state.plan is None
    assert role.status == "ERROR" and role.error and role.position is None
    assert role.trace.next_action == question
    assert error not in role.trace.observations
    assert any(event.payload.get("summary") == error for event in state.events)
    assert any(item.get("error_type") == "APITimeoutError" for item in role.activity)
    await engine.close()


async def test_restart_marks_interrupted_work_recoverable(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    state = engine.get(meeting.id)
    state.busy = True
    state.roles[Role.RADIOLOGY].status = "ANALYZING"
    engine.store.save(state)
    engine.store.close()
    recovered = make_engine(tmp_path)
    assert recovered.meeting and recovered.meeting.phase == Phase.ERROR
    assert not recovered.meeting.busy
    assert recovered.meeting.roles[Role.RADIOLOGY].status == "ERROR"
    await recovered.retry(meeting.id)
    await settled(recovered)
    assert recovered.get(meeting.id).phase != Phase.ERROR
    await recovered.close()


async def test_memory_is_explicit_and_forget_removes_active_nudge(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    state = engine.get(meeting.id)
    memory = state.memories[0]
    assert memory.status == "AVAILABLE"
    assert not state.roles[memory.role].guidance
    await engine.memory(meeting.id, memory.id, "ignore")
    assert memory.status == "IGNORED"
    assert not state.roles[memory.role].guidance
    await engine.memory(meeting.id, memory.id, "use")
    await settled(engine)
    assert memory.status == "USED"
    assert state.roles[memory.role].guidance
    await engine.memory(meeting.id, memory.id, "forget")
    assert memory.status == "FORGOTTEN"
    assert memory.text == ""
    await engine.close()


async def test_snapshot_subscriber_receives_latest_without_unbounded_queue(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
    engine.subscribers[meeting.id] = {queue}
    await settled(engine)
    assert queue.qsize() == 2
    queue.get_nowait()
    assert '"TARGETED_DISCUSSION"' in queue.get_nowait()
    assert len(engine.get(meeting.id).events) > 2
    await engine.close()


async def test_stale_plan_vote_rejected(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await proposal(engine)
    with pytest.raises(Conflict, match="plan changed"):
        await engine.concur(meeting_id, Role.ONCOLOGY, "", plan_version=999)
    with pytest.raises(Conflict, match="plan changed"):
        await engine.object(meeting_id, Role.ONCOLOGY, "Concern", plan_version=999)
    await engine.close()


async def test_forgotten_memory_does_not_return_in_new_meeting(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting = await engine.start("rehearsal")
    await settled(engine)
    memory_id = engine.get(meeting.id).memories[0].id
    await engine.memory(meeting.id, memory_id, "forget")
    second = await engine.start("rehearsal")
    await settled(engine)
    memory = next(m for m in engine.get(second.id).memories if m.id == memory_id)
    assert memory.status == "FORGOTTEN"
    assert memory.text == ""
    await engine.close()


async def test_provider_error_is_actionable_without_exposing_response_body(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)

    class ProviderQuotaError(RuntimeError):
        status_code = 429

    async def limited(role: Role, **kwargs: Any) -> Position:
        try:
            raise ProviderQuotaError("DO_NOT_EXPOSE_PROVIDER_BODY")
        except ProviderQuotaError as cause:
            raise RuntimeError("Wrapped SDK failure") from cause

    engine.analyzer = limited
    meeting = await engine.start("azure")
    await settled(engine)
    state = engine.get(meeting.id)
    assert state.phase == Phase.ERROR
    assert all("quota" in (role.error or "") for role in state.roles.values())
    assert "DO_NOT_EXPOSE_PROVIDER_BODY" not in state.model_dump_json()
    await engine.close()


async def test_storage_failure_stops_round_and_reloads_before_retry(tmp_path: Path) -> None:
    from mdt.engine import PersistenceFailure

    class FailingStore(Store):
        fail = False

        def save_snapshot(self, meeting_id: str, created_at: str, payload: str) -> None:
            if self.fail:
                raise OSError("Simulated storage outage")
            super().save_snapshot(meeting_id, created_at, payload)

    settings = Settings(db_path=str(tmp_path / "failure.db"), step_delay=0)
    store = FailingStore(settings.db_path)
    engine = Engine(store, settings, analyze)
    meeting = await engine.start("rehearsal")
    store.fail = True
    await settled(engine)
    assert engine.get(meeting.id).phase == Phase.ERROR
    assert not engine.get(meeting.id).busy
    with pytest.raises(PersistenceFailure):
        await engine.steer(meeting.id, Role.RADIOLOGY, "Review growth")
    store.fail = False
    await engine.retry(meeting.id)
    await settled(engine)
    assert engine.get(meeting.id).phase == Phase.TARGETED_DISCUSSION
    assert not engine.persistence_failed
    await engine.close()


class SlowStore(Store):
    """SQLite store whose snapshot writes block like a slow Blob upload."""

    delay = 0.0
    writes = 0
    written = 0

    def save_snapshot(self, meeting_id: str, created_at: str, payload: str) -> None:
        time.sleep(self.delay)
        self.writes += 1
        self.written += len(payload)
        super().save_snapshot(meeting_id, created_at, payload)


def slow_engine(tmp_path: Path, delay: float = 0.0) -> tuple[Engine, SlowStore]:
    settings = Settings(db_path=str(tmp_path / "slow.db"), step_delay=0)
    store = SlowStore(settings.db_path)
    store.delay = delay
    return Engine(store, settings, analyze), store


async def test_blocked_storage_write_does_not_freeze_the_event_loop(tmp_path: Path) -> None:
    import httpx

    from mdt.app import create_app

    engine, store = slow_engine(tmp_path, delay=1.0)
    application = create_app(Settings(db_path=str(tmp_path / "unused.db")), engine=engine)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = asyncio.create_task(engine.start("rehearsal"))
        await asyncio.sleep(0.1)
        assert not start.done(), "the first write should still be blocked"
        began = time.monotonic()
        assert (await client.get("/healthz")).status_code == 200
        assert time.monotonic() - began < 0.2
        await start
    store.delay = 0
    await engine.close()


async def test_persisted_events_are_numbered_in_write_order(tmp_path: Path) -> None:
    engine, store = slow_engine(tmp_path)
    started = await engine.start("rehearsal")
    await settled(engine)
    persisted = store.get(started.id)
    assert persisted is not None
    assert [event.id for event in persisted.events] == list(range(1, len(persisted.events) + 1))
    assert store.writes == len(persisted.events)
    assert persisted.model_dump() == engine.get(started.id).model_dump()
    await engine.close()


async def test_readers_never_see_a_half_applied_transition(tmp_path: Path) -> None:
    engine, _ = slow_engine(tmp_path, delay=0.001)
    await engine.start("rehearsal")
    transitional = {Phase.POSITION_COLLECTION, Phase.FRICTION_ANALYSIS, Phase.PLAN_PROPOSAL}
    while engine.tasks:
        seen = await engine.current()
        assert seen is not None
        assert seen.busy or seen.phase not in transitional
        await asyncio.sleep(0)
    await engine.close()


async def test_each_event_serializes_the_meeting_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdt.models import Meeting

    engine = make_engine(tmp_path)
    room: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
    engine.room_subscribers.add(room)
    calls = 0
    original = Meeting.model_dump_json

    def counted(self: Meeting, **kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        return original(self, **kwargs)

    monkeypatch.setattr(Meeting, "model_dump_json", counted)
    started = await engine.start("rehearsal")
    engine.subscribers.setdefault(started.id, set()).add(asyncio.Queue(maxsize=1000))
    await settled(engine)
    meeting = engine.get(started.id)
    assert calls == len(meeting.events)
    monkeypatch.undo()
    last = room.get_nowait()
    while not room.empty():
        last = room.get_nowait()
    assert last == f'{{"meeting":{meeting.model_dump_json()}}}' == engine.room_snapshot()
    await engine.close()


async def test_known_evidence_is_referenced_not_copied_into_events(tmp_path: Path) -> None:
    engine, store = slow_engine(tmp_path)
    started = await engine.start("rehearsal", "CASE-MDT-CRC-WT-2026-002")
    await settled(engine)
    meeting = engine.get(started.id)
    known = {item.id for item in meeting.evidence}
    found = [event.payload for event in meeting.events if event.type == "EvidenceFound"]
    assert found and all("evidence" not in payload for payload in found)
    assert {payload["evidence_id"] for payload in found} <= known
    activity = [
        a for s in meeting.roles.values() for a in s.activity if a["type"] == "EvidenceFound"
    ]
    assert activity and all(a["evidence_id"] in known and "evidence" not in a for a in activity)
    changed = meeting.evidence[0].model_dump(mode="json") | {"title": "Different record"}
    kept = engine._reference_known_evidence({"summary": "x", "evidence": changed})
    assert kept["evidence"] == changed, "differing records stay in full for the audit trail"
    # Full snapshots were 37.9 MB for this round (46 MB now that the research role also
    # replays 16 recorded search events); the dossier is stored once either way.
    assert store.written < 48_000_000
    print(f"stored {store.bytes_written:,} bytes of {store.written:,} serialized")
    assert store.bytes_written <= 25_500_000
    await engine.close()


async def test_split_snapshots_rebuild_the_exact_meeting(tmp_path: Path) -> None:
    engine, _ = slow_engine(tmp_path)
    started = await engine.start("rehearsal")
    await settled(engine)
    live = engine.get(started.id).model_dump()
    await engine.close()
    reopened = Store(str(tmp_path / "slow.db"))
    dynamic = reopened.connection.execute(
        "SELECT snapshot FROM meetings WHERE id=?", (started.id,)
    ).fetchone()[0]
    assert '"case"' not in dynamic and '"evidence":[{' not in dynamic
    statics = reopened.connection.execute("SELECT COUNT(*) FROM meeting_static").fetchone()[0]
    assert statics == 1
    rebuilt = reopened.get(started.id)
    assert rebuilt is not None and rebuilt.model_dump() == live
    latest = reopened.latest()
    assert latest is not None and latest.model_dump() == live
    reopened.close()


async def test_recorded_searches_join_the_record_without_settling_applicability(
    tmp_path: Path,
) -> None:
    engine = make_engine(tmp_path)
    started = await engine.start("rehearsal")
    await settled(engine)
    meeting = engine.get(started.id)
    curated = {item.id for item in get_case(str(CASE["id"])).evidence}
    searched = [item for item in meeting.evidence if item.id not in curated]
    assert searched, "the research specialist replays its recorded public searches"
    assert all(item.retrieval == "RECORDED" and item.id.startswith("REC-") for item in searched)
    assert all(item.retrieved_at and item.source_tier and item.query for item in searched)
    assert all(item.patient_match == "NOT_ASSESSED" for item in searched)
    assert {item.id for item in meeting.evidence} >= curated, "curated records are never replaced"
    for item in meeting.evidence:
        if item.id in curated:
            assert item.retrieval == "CURATED" and "retrieved_at" not in item.model_dump()
    research = meeting.roles[Role.RESEARCH].position
    assert research and set(research.provenance) & {item.id for item in searched}
    assert not next(f for f in meeting.frictions if f.id == "applicability").resolved, (
        "finding papers never settles the patient-applicability question"
    )
    saved = meeting.model_dump(mode="json")
    exported = meeting.model_dump_json()
    assert all(item.id in exported for item in searched)
    await engine.close()
    reopened = Store(str(tmp_path / "mdt.db"))
    restored = reopened.get(started.id)
    assert restored is not None and restored.model_dump(mode="json") == saved
    reopened.close()


def test_legacy_full_snapshots_stay_readable(tmp_path: Path) -> None:
    from mdt.models import Meeting

    store = Store(str(tmp_path / "legacy.db"))
    legacy = Meeting(id="legacy-1", created_at="2025-01-01T00:00:00Z", case={"id": "CASE-LEGACY"})
    with store.connection:
        store.connection.execute(
            "INSERT INTO meetings VALUES (?, ?, ?)",
            (legacy.id, legacy.created_at, legacy.model_dump_json()),
        )
    loaded = store.get(legacy.id)
    assert loaded is not None and loaded.model_dump() == legacy.model_dump()
    latest = store.latest()
    assert latest is not None and latest.case == {"id": "CASE-LEGACY"}
    store.save(loaded)
    assert store.connection.execute("SELECT COUNT(*) FROM meeting_static").fetchone()[0] == 1
    resaved = store.get(legacy.id)
    assert resaved is not None and resaved.model_dump() == legacy.model_dump()
    store.close()

# ------------------------------------------------------------ outcome communications
async def decide(engine: Engine, case_id: str | None = None) -> str:
    """Drive a case to a captured decision without letting drafting run yet."""
    if case_id is None:
        meeting_id = await proposal(engine)
    else:
        guidance = dict(ADDITIONAL_CASES)[case_id]
        started = await engine.start("rehearsal", case_id)
        await settled(engine)
        await engine.followup(started.id)
        await settled(engine)
        await engine.steer(started.id, Role.RADIOLOGY, guidance)
        await settled(engine)
        meeting_id = started.id
    state = engine.get(meeting_id)
    assert state.plan is not None
    for role in Role:
        if role not in state.concurrences:
            await engine.concur(meeting_id, role, "Reviewed.", state.plan.version)
    assert state.phase == Phase.DECISION_CAPTURED
    return meeting_id


async def test_outcome_documents_are_drafted_only_after_the_decision(tmp_path: Path) -> None:
    drafter = FakeDrafter()
    engine = make_engine(tmp_path, drafter)
    meeting_id = await proposal(engine)
    state = engine.get(meeting_id)
    assert state.plan is not None
    assert not state.communications
    with pytest.raises(Conflict):
        await engine.regenerate_communication(meeting_id, "patient", reviewer="Dr A", role=None)
    for role in Role:
        if role not in state.concurrences:
            await engine.concur(meeting_id, role, "Reviewed.", state.plan.version)
    assert {item.status for item in state.communications.values()} == {"DRAFTING"}
    assert {item.plan_version for item in state.communications.values()} == {state.plan.version}
    closed = [event.type for event in state.events].index("CaseClosed")
    assert "CommunicationDrafted" not in [event.type for event in state.events[:closed]]
    await settled(engine)
    assert {item.status for item in state.communications.values()} == {"DRAFT"}
    assert {item.generated_by for item in state.communications.values()} == {"azure"}
    assert state.phase == Phase.DECISION_CAPTURED
    patient = next(call for call in drafter.calls if call.audience == "patient")
    clinician = next(call for call in drafter.calls if call.audience == "clinician")
    # The patient runtime sees only the patient perspective, never other specialists.
    assert set(patient.positions) == {Role.PATIENT.value}
    assert not patient.evidence and not patient.concurrences and not patient.objections
    assert set(clinician.positions) == {role.value for role in Role}
    assert patient.language == "en" and clinician.language == "en"
    assert all(ref in patient.refs for ref in patient.required_refs)
    await engine.close()


async def test_patient_documents_follow_the_case_language(tmp_path: Path) -> None:
    drafter = FakeDrafter()
    engine = make_engine(tmp_path, drafter)
    for case_id, language in (
        ("CASE-MDT-CRC-WT-2026-002", "de"), ("CASE-MDT-PDAC-PERIOP-2026-003", "it"),
    ):
        drafter.calls.clear()
        meeting_id = await decide(engine, case_id)
        await settled(engine)
        state = engine.get(meeting_id)
        assert state.communications["patient"].language == language
        assert state.communications["clinician"].language == "en"
        assert {call.audience: call.language for call in drafter.calls} == {
            "patient": language, "clinician": "en",
        }
    await engine.close()


async def test_approval_is_human_named_and_bound_to_plan_and_revision(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await decide(engine)
    state = engine.get(meeting_id)
    assert state.plan is not None
    version = state.plan.version
    with pytest.raises(Conflict, match="completed draft"):
        await engine.approve_communication(
            meeting_id, "patient", reviewer="Dr A", role=None, plan_version=version, revision=1
        )
    await settled(engine)
    with pytest.raises(Conflict, match="Name the reviewing"):
        await engine.approve_communication(
            meeting_id, "patient", reviewer="   ", role=None, plan_version=version, revision=1
        )
    with pytest.raises(Conflict, match="plan version"):
        await engine.approve_communication(
            meeting_id, "patient", reviewer="Dr A", role=None, plan_version=version - 1,
            revision=1,
        )
    with pytest.raises(Conflict, match="newer draft"):
        await engine.approve_communication(
            meeting_id, "patient", reviewer="Dr A", role=None, plan_version=version, revision=2
        )
    await engine.approve_communication(
        meeting_id, "patient", reviewer=" Dr A ", role=Role.ONCOLOGY, plan_version=version,
        revision=1, comment="Plain and accurate.",
    )
    patient = state.communications["patient"]
    assert patient.status == "APPROVED"
    assert (patient.approved_by, patient.approved_role, patient.approved_revision) == (
        "Dr A", Role.ONCOLOGY, 1,
    )
    assert patient.reviews[-1].action == "approve"
    assert state.communications["clinician"].status == "DRAFT"
    with pytest.raises(Conflict, match="Already approved"):
        await engine.approve_communication(
            meeting_id, "patient", reviewer="Dr A", role=None, plan_version=version, revision=1
        )
    with pytest.raises(NotFound):
        await engine.approve_communication(
            meeting_id, "family", reviewer="Dr A", role=None,  # type: ignore[arg-type]
            plan_version=version, revision=1,
        )
    assert state.phase == Phase.DECISION_CAPTURED
    await engine.close()


async def test_requested_changes_redraft_and_revoke_approval(tmp_path: Path) -> None:
    drafter = FakeDrafter()
    engine = make_engine(tmp_path, drafter)
    meeting_id = await decide(engine)
    await settled(engine)
    state = engine.get(meeting_id)
    assert state.plan is not None
    version = state.plan.version
    await engine.approve_communication(
        meeting_id, "clinician", reviewer="Dr B", role=None, plan_version=version, revision=1
    )
    with pytest.raises(Conflict, match="Describe the change"):
        await engine.request_communication_changes(
            meeting_id, "clinician", reviewer="Dr B", role=None, plan_version=version,
            revision=1, comment="  ",
        )
    await engine.request_communication_changes(
        meeting_id, "clinician", reviewer="Dr B", role=None, plan_version=version, revision=1,
        comment="Name the surgeon who will follow up.",
    )
    letter = state.communications["clinician"]
    assert (letter.status, letter.revision, letter.approved_by) == ("DRAFTING", 2, None)
    with pytest.raises(Conflict):
        await engine.approve_communication(
            meeting_id, "clinician", reviewer="Dr B", role=None, plan_version=version,
            revision=1,
        )
    await settled(engine)
    assert letter.status == "DRAFT"
    assert drafter.calls[-1].requested_changes == ["Name the surgeon who will follow up."]
    assert drafter.calls[-1].revision == 2
    assert [review.action for review in letter.reviews] == ["approve", "request_changes"]
    assert state.phase == Phase.DECISION_CAPTURED
    assert state.plan.version == version
    await engine.close()


async def test_failed_drafts_stay_visible_and_can_be_regenerated(tmp_path: Path) -> None:
    drafter = FakeDrafter()
    drafter.error = "Language model is not configured."
    engine = make_engine(tmp_path, drafter)
    meeting_id = await decide(engine)
    await settled(engine)
    state = engine.get(meeting_id)
    patient = state.communications["patient"]
    assert patient.status == "FAILED"
    assert patient.error and "No scripted text was substituted" in patient.error
    assert not patient.sections and patient.checks is None
    assert "CommunicationFailed" in [event.type for event in state.events]
    assert state.plan is not None
    with pytest.raises(Conflict):
        await engine.approve_communication(
            meeting_id, "patient", reviewer="Dr A", role=None,
            plan_version=state.plan.version, revision=1,
        )
    drafter.error = None
    await engine.regenerate_communication(meeting_id, "patient", reviewer="Dr A", role=None)
    assert patient.status == "DRAFTING" and patient.revision == 2
    await settled(engine)
    assert patient.status == "DRAFT" and patient.error is None and patient.sections
    await engine.close()


async def test_default_drafter_fails_visibly_without_a_model(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "mdt.db"), step_delay=0)
    engine = Engine(Store(settings.db_path), settings, analyze)
    meeting_id = await decide(engine)
    await settled(engine)
    for item in engine.get(meeting_id).communications.values():
        assert item.status == "FAILED"
        assert item.error and "No scripted text was substituted" in item.error
        assert not item.sections
    await engine.close()


async def test_new_meeting_waits_for_drafting_and_restart_fails_open_drafts(
    tmp_path: Path,
) -> None:
    drafter = FakeDrafter()
    drafter.gate = asyncio.Event()
    engine = make_engine(tmp_path, drafter)
    meeting_id = await decide(engine)
    await asyncio.sleep(0)
    with pytest.raises(Conflict, match="finish drafting"):
        await engine.start("rehearsal")
    await engine.close()
    restored = make_engine(tmp_path)
    state = restored.get(meeting_id)
    assert {item.status for item in state.communications.values()} == {"FAILED"}
    assert all(
        item.error and "Server restarted" in item.error for item in state.communications.values()
    )
    assert state.events[-1].type == "CommunicationFailed"
    await restored.regenerate_communication(meeting_id, "clinician", reviewer="Dr B", role=None)
    await settled(restored)
    assert state.communications["clinician"].status == "DRAFT"
    await restored.close()
    again = make_engine(tmp_path)
    assert again.get(meeting_id).communications["clinician"].status == "DRAFT"
    await again.close()


async def test_clearing_the_room_keeps_outcome_documents_in_the_record(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await decide(engine)
    await settled(engine)
    documents = engine.get(meeting_id).model_dump()["communications"]
    await engine.clear()
    with pytest.raises(NotFound):
        await engine.regenerate_communication(meeting_id, "patient", reviewer="Dr A", role=None)
    assert (await engine.load(meeting_id)).model_dump()["communications"] == documents
    await engine.close()


@pytest.mark.parametrize("case_id", [None, *(item[0] for item in ADDITIONAL_CASES)])
async def test_captured_plans_never_repeat_conditions_or_actions(
    tmp_path: Path, case_id: str | None,
) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await decide(engine, case_id)
    plan = engine.get(meeting_id).plan
    assert plan is not None
    assert len(plan.conditions) == len(set(plan.conditions))
    assert len(plan.actions) == len(set(plan.actions))
    await engine.close()
    await engine.close()


async def test_cohort_reference_is_recorded_without_deciding_the_meeting(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    meeting_id = await proposal(engine)
    before = engine.get(meeting_id).model_dump()
    await engine.cohort_reference(meeting_id, None, [], "decision:additional_diagnostics_first")
    state = engine.get(meeting_id)
    event = next(item for item in state.events if item.type == "CohortReferenceAdded")
    assert "comparable historical cases" in event.payload["summary"]
    assert event.payload["advisory"] is False
    assert event.payload["cohort_definition"]["criteria"]
    assert event.payload["denominator"] == event.payload["cohort_definition"]["matched"]
    after = state.model_dump()
    for field in ("phase", "plan", "concurrences", "frictions", "roles", "round", "objections"):
        assert after[field] == before[field], f"{field} must be unchanged by cohort context"
    with pytest.raises(Conflict):
        await engine.cohort_reference(meeting_id, None, [], "decision:not_a_category")
    for role in Role:
        if role not in state.concurrences:
            await engine.concur(meeting_id, role, "Reviewed demonstration proposal.")
    assert engine.get(meeting_id).phase == Phase.DECISION_CAPTURED
    with pytest.raises(Conflict):
        # A captured decision stays immutable; cohort context cannot be appended later.
        await engine.cohort_reference(meeting_id, None, [], "decision:continue_current_treatment")
    await engine.close()
