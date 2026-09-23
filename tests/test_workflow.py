import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from mdt.agents import analyze
from mdt.case_registry import get_case
from mdt.config import Settings
from mdt.engine import Conflict, Engine, NotFound
from mdt.models import Phase, Position, Role
from mdt.scenario import CASE
from mdt.store import Store

CLEARANCE_GUIDANCE = (
    "Review all nine liver sites, vessel margins and the indeterminate lung nodule "
    "before clearance planning."
)

ADDITIONAL_CASES = (
    ("CASE-MDT-CRC-WT-2026-002", "Review liver mapping, vascular margins and all baseline sites."),
    (
        "CASE-MDT-PDAC-PERIOP-2026-003",
        "Review pancreatic imaging, vascular anatomy and the limitations of cardiac imaging.",
    ),
)


@pytest.mark.parametrize(("case_id", "guidance"), ADDITIONAL_CASES)
async def test_selected_case_complete_workflow_and_durable_source(
    tmp_path: Path, case_id: str, guidance: str,
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
    assert meeting.plan.title == definition.runtime.proposal.title
    assert set(definition.runtime.proposal.conditions) <= set(meeting.plan.conditions)
    assert set(definition.runtime.residual_conditions) <= set(meeting.plan.conditions)
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


def make_engine(tmp_path: Path) -> Engine:
    settings = Settings(db_path=str(tmp_path / "mdt.db"), step_delay=0)
    return Engine(Store(settings.db_path), settings, analyze)


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
    # Regression bound: 51.1 MB before references; 37.9 MB measured after.
    assert store.written < 40_000_000
    await engine.close()