import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from mdt.case_registry import case_ids, get_case
from mdt.cohort import build_cohort, reference_statement
from mdt.config import Settings
from mdt.models import (
    Concurrence,
    Event,
    Friction,
    Meeting,
    Phase,
    Plan,
    Position,
    Role,
    RoleState,
    utcnow,
)
from mdt.store import Persistence
from mdt.telemetry import error_counter, event_counter, tracer

log = logging.getLogger("mdt.engine")
Analyzer = Callable[..., Awaitable[Position]]


class Conflict(Exception):
    """A valid command that cannot apply to the current meeting state."""


class NotFound(Exception):
    """The requested meeting does not exist."""


class PersistenceFailure(RuntimeError):
    """The meeting cannot safely advance until durable storage recovers."""


class Engine:
    def __init__(self, store: Persistence, settings: Settings, analyzer: Analyzer) -> None:
        self.store = store
        self.settings = settings
        self.analyzer = analyzer
        self.lock = asyncio.Lock()
        # One worker keeps storage calls off the event loop, serializes access to
        # the single SQLite connection and preserves write order.
        self._io_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mdt-store")
        self.meeting = store.latest()
        self.tasks: set[asyncio.Task[None]] = set()
        self.subscribers: dict[str, set[asyncio.Queue[str]]] = {}
        self.room_subscribers: set[asyncio.Queue[str]] = set()
        self.cleared = bool(self.meeting and self.meeting.cleared)
        self.persistence_failed = False
        if self.meeting and self.meeting.busy:
            self.meeting.busy = False
            self.meeting.phase = Phase.ERROR
            self.meeting.error = (
                "Server restarted during analysis. Retry to resume unfinished roles."
            )
            for role in self.meeting.roles.values():
                if role.status in {"ANALYZING", "REASSESSING"}:
                    role.status = "ERROR"
                    role.error = "Analysis interrupted by server restart."
            # Runs before the app serves requests, so a direct write is safe here.
            self._append("AnalysisInterrupted", {"summary": self.meeting.error}, None)
            meeting = self.meeting
            store.save_snapshot(meeting.id, meeting.created_at, meeting.model_dump_json())

    async def _io[T](self, fn: Callable[..., T], *args: Any) -> T:
        return await asyncio.get_running_loop().run_in_executor(self._io_pool, fn, *args)

    def _current(self, meeting_id: str) -> Meeting:
        if self.cleared or not self.meeting or self.meeting.id != meeting_id:
            raise NotFound("Meeting is not the active demonstration room.")
        return self.meeting

    @property
    def active(self) -> Meeting | None:
        """The meeting participant screens should be showing, if any."""
        return None if self.cleared else self.meeting

    def get(self, meeting_id: str) -> Meeting:
        """Synchronous lookup for scripts and tests; request handlers use `load`."""
        if self.meeting and self.meeting.id == meeting_id:
            return self.meeting
        found = self.store.get(meeting_id)
        if not found:
            raise NotFound("Meeting not found.")
        return found

    async def load(self, meeting_id: str) -> Meeting:
        """Meeting as of the last completed transition; transitions await storage."""
        async with self.lock:
            if self.meeting and self.meeting.id == meeting_id:
                return self.meeting.model_copy(deep=True)
        found = await self._io(self.store.get, meeting_id)
        if not found:
            raise NotFound("Meeting not found.")
        return found

    async def current(self) -> Meeting | None:
        async with self.lock:
            meeting = self.active
            return meeting.model_copy(deep=True) if meeting else None

    async def room_state(self) -> str:
        async with self.lock:
            return self.room_snapshot()

    async def ready(self) -> None:
        await self._io(self.store.ready)

    def _append(self, kind: str, payload: dict[str, Any] | None, role: Role | None) -> None:
        assert self.meeting
        if self.persistence_failed:
            raise PersistenceFailure("Persistent storage is unavailable; the meeting is paused.")
        self.meeting.events.append(
            Event(
                id=len(self.meeting.events) + 1,
                meeting_id=self.meeting.id,
                type=kind,
                role=role,
                payload=payload or {},
            )
        )

    async def _event(
        self, kind: str, payload: dict[str, Any] | None = None, role: Role | None = None
    ) -> None:
        self._append(kind, payload, role)
        assert self.meeting
        meeting = self.meeting
        # Serialize once on the loop: the same bytes are persisted and then broadcast.
        snapshot = meeting.model_dump_json()
        try:
            await self._io(self.store.save_snapshot, meeting.id, meeting.created_at, snapshot)
        except Exception as exc:
            meeting.events.pop()
            self.persistence_failed = True
            meeting.busy = False
            meeting.phase = Phase.ERROR
            meeting.error = (
                "Persistence failed. Unsaved work is paused; retry after storage recovers."
            )
            self._broadcast()
            log.error("Persistence failed event=%s error_type=%s", kind, type(exc).__name__)
            raise PersistenceFailure(meeting.error) from exc
        self._broadcast(snapshot)
        event_counter.add(1, {"event.type": kind, "mdt.mode": meeting.mode})
        log.info("mdt.event type=%s meeting=%s role=%s", kind, meeting.id, role or "chair")

    def _broadcast(self, snapshot: str | None = None) -> None:
        assert self.meeting
        if snapshot is None:
            snapshot = self.meeting.model_dump_json()
        for queue in self.subscribers.get(self.meeting.id, set()):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(snapshot)
        self._broadcast_room(None if self.cleared else snapshot)

    def room_snapshot(self) -> str:
        """Envelope describing the room every participant screen follows.

        A null meeting is the standby state: participant screens clear and wait
        for the orchestrator to activate the next case.
        """
        meeting = None if self.cleared or not self.meeting else self.meeting
        body = "null" if meeting is None else meeting.model_dump_json()
        return f'{{"meeting":{body}}}'

    def _broadcast_room(self, meeting_snapshot: str | None) -> None:
        snapshot = f'{{"meeting":{meeting_snapshot or "null"}}}'
        for queue in self.room_subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(snapshot)

    async def clear(self) -> None:
        """Return every participant screen to standby without deleting the record.

        The concluded meeting stays in persistent storage and remains reviewable
        and exportable by id; only the shared room returns to its waiting state.
        """
        async with self.lock:
            if self.meeting and self.meeting.busy:
                raise Conflict("Wait for the active round to finish before clearing the room.")
            if self.meeting and not self.meeting.cleared:
                self.meeting.cleared = True
                self.cleared = True
                # Recording the event both persists the reset across a restart and
                # broadcasts standby to every open screen.
                await self._event("RoomCleared", {
                    "summary": "The meeting was closed on the shared screens. "
                    "The record stays available for review and export.",
                })
                return
            self.cleared = True
            self._broadcast_room(None)

    async def _phase(self, phase: Phase) -> None:
        assert self.meeting
        self.meeting.phase = phase
        await self._event("PhaseChanged", {"phase": phase.value})

    def _spawn(self, roles: list[Role], phase: str) -> None:
        task = asyncio.create_task(self._run_roles(roles, phase))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _editable(self, meeting_id: str, *, recovery: bool = False) -> Meeting:
        meeting = self._current(meeting_id)
        if meeting.case.get("id") not in case_ids():
            raise Conflict(
                "This meeting uses an earlier case version and is available for review/export. "
                "Start a new case to use the current dossier."
            )
        if self.persistence_failed and not recovery:
            raise PersistenceFailure("Retry storage recovery before changing the meeting.")
        if meeting.phase == Phase.DECISION_CAPTURED:
            raise Conflict("This decision is closed and immutable. Start a new meeting.")
        if meeting.busy:
            raise Conflict("An analysis round is already running.")
        return meeting

    async def start(self, mode: str, case_id: str | None = None) -> Meeting:
        async with self.lock:
            if case_id is not None and case_id not in case_ids():
                raise NotFound(
                    "Selected case is not available. Choose a case from the case selection screen."
                )
            if self.meeting and self.meeting.busy:
                raise Conflict("Wait for the active round before starting another meeting.")
            if self.persistence_failed:
                raise PersistenceFailure("Recover the interrupted meeting before starting another.")
            if mode not in {"rehearsal", "azure"}:
                raise Conflict("Unknown runtime mode.")
            if await self._io(self.store.count) >= self.settings.max_meetings:
                raise Conflict("Demo meeting retention limit reached. Archive the database first.")
            definition = get_case(case_id)
            memory_ids = {item.id for item in definition.memories}
            stored_memories = await self._io(self.store.memories, definition.memories)
            self.cleared = False
            self.meeting = Meeting(
                id=str(uuid4()),
                mode="azure" if mode == "azure" else "rehearsal",
                case=definition.case,
                roles={
                    role.value: RoleState(
                        role=role, label=definition.labels[role],
                        context=definition.contexts[role],
                    )
                    for role in Role
                },
                evidence=definition.evidence,
                memories=[item for item in stored_memories if item.id in memory_ids],
                busy=True,
                round=1,
            )
            await self._phase(Phase.CASE_LOADING)
            await self._event(
                "CaseActivated", {"case_id": definition.case["id"], "demonstration": True},
            )
            self._spawn(list(Role), "initial")
            return self.meeting.model_copy(deep=True)

    async def _analyze_one(self, role: Role, phase: str) -> None:
        assert self.meeting
        async with self.lock:
            state = self.meeting.roles[role]
            state.status = "ANALYZING" if phase == "initial" else "REASSESSING"
            state.error = None
            await self._event("RoleAnalysisStarted", {"round": self.meeting.round}, role)
            case_id = str(self.meeting.case["id"])
            guidance = list(state.guidance)
            mode = self.meeting.mode

        async def emit(kind: str, payload: dict[str, Any]) -> None:
            async with self.lock:
                assert self.meeting
                payload = self._reference_known_evidence(payload)
                current = self.meeting.roles[role]
                current.activity.append({"type": kind, "timestamp": utcnow(), **payload})
                current.activity = current.activity[-80:]
                summary = payload.get("summary")
                operational = (
                    payload.get("error")
                    or payload.get("error_type")
                    or payload.get("status") in {"RATE_WAIT", "RATE_LIMITED", "QUEUED", "RETRYING"}
                )
                if isinstance(summary, str) and not operational:
                    current.trace.next_action = summary
                    if kind == "ObservationAdded":
                        current.trace.observations.append(summary)
                await self._event(kind, payload, role)
            await asyncio.sleep(self.settings.step_delay)

        try:
            with tracer.start_as_current_span(
                "mdt.role.analyze", attributes={"mdt.role": role.value, "mdt.mode": mode}
            ):
                position = await self.analyzer(
                    role,
                    case_id=case_id,
                    mode=mode,
                    guidance=guidance,
                    phase=phase,
                    emit=emit,
                )
                if position.role != role or position.case_id != case_id:
                    raise ValueError("Agent output has mismatched role or case.")
                evidence_ids = {item.id for item in get_case(case_id).role_evidence(role)}
                if not set(position.provenance) <= evidence_ids or any(
                    source not in evidence_ids
                    for claim in position.claims
                    for source in claim.evidence_ids
                ):
                    raise ValueError("Agent output contains an unknown evidence reference.")
            async with self.lock:
                assert self.meeting
                current = self.meeting.roles[role]
                current.position = position
                current.trace = position.trace
                current.revision += 1
                current.status = "PUBLISHED"
                await self._event(
                    "PositionPublished" if phase == "initial" else "PositionUpdated",
                    {"revision": current.revision, "autonomy": position.autonomy},
                    role,
                )
        except PersistenceFailure:
            raise
        except Exception as exc:
            # Provider SDK errors vary; every failure becomes a persisted, visible failed role.
            await self._role_error(role, exc)

    def _reference_known_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Store an evidence id instead of a copy the meeting already holds.

        Every event persists the whole meeting, so repeating full evidence records in
        events and activity multiplies bytes written. Records that differ from the
        meeting's copy are kept in full so the audit trail never loses content.
        """
        assert self.meeting
        evidence = payload.get("evidence")
        if not isinstance(evidence, dict):
            return payload
        record = next((e for e in self.meeting.evidence if e.id == evidence.get("id")), None)
        if record is None or record.model_dump(mode="json") != evidence:
            return payload
        slim = {key: value for key, value in payload.items() if key != "evidence"}
        slim["evidence_id"] = record.id
        return slim

    async def _role_error(self, role: Role, exc: Exception) -> None:
        cause: BaseException | None = exc
        status: int | None = None
        for _ in range(5):
            if cause is None:
                break
            candidate = getattr(cause, "status_code", None)
            if isinstance(candidate, int):
                status = candidate
                break
            cause = cause.__cause__
        log.error(
            "Role failed role=%s error_type=%s provider_status=%s",
            role.value,
            type(exc).__name__,
            status,
        )
        error_counter.add(1, {"mdt.role": role.value, "error.type": type(exc).__name__})
        async with self.lock:
            assert self.meeting
            state = self.meeting.roles[role]
            state.status = "ERROR"
            reasons = {
                401: "Azure authentication failed. Renew credentials before retrying.",
                403: "Azure access denied. Verify the model identity role and network access.",
                429: "Azure model quota is busy. Retry budget exhausted; try again later.",
            }
            state.error = reasons.get(
                status or 0,
                f"{type(exc).__name__}: analysis failed. Check model configuration, "
                "permissions, quota and server diagnostics, then retry.",
            )
            await self._event("RoleAnalysisFailed", {"summary": state.error}, role)

    async def _run_roles(self, roles: list[Role], phase: str) -> None:
        try:
            async with self.lock:
                await self._phase(
                    Phase.INITIAL_ANALYSIS if phase == "initial" else Phase.POSITION_UPDATE
                )
            async with asyncio.TaskGroup() as group:
                for role in roles:
                    group.create_task(self._analyze_one(role, phase))
            async with self.lock:
                assert self.meeting
                self.meeting.busy = False
                if any(state.status == "ERROR" for state in self.meeting.roles.values()):
                    self.meeting.error = "One or more specialists failed. No consensus is possible."
                    await self._phase(Phase.ERROR)
                    return
                self.meeting.error = None
                await self._phase(Phase.POSITION_COLLECTION)
                await self._reconcile(roles if phase == "followup" else [])
        except asyncio.CancelledError:
            async with self.lock:
                assert self.meeting
                self.meeting.busy = False
                self.meeting.error = "Analysis interrupted by shutdown. Retry the round."
                if self.persistence_failed:
                    self.meeting.phase = Phase.ERROR
                    self._broadcast()
                else:
                    await self._phase(Phase.ERROR)
            raise
        except Exception as exc:
            log.error("Round aborted error_type=%s", type(exc).__name__)
            async with self.lock:
                assert self.meeting
                self.meeting.busy = False
                self.meeting.phase = Phase.ERROR
                self.meeting.error = (
                    "The round was aborted. Retry to reload durable state before continuing."
                )
                self._broadcast()

    async def _invalidate(self, reason: str) -> None:
        assert self.meeting
        if self.meeting.plan:
            self.meeting.concurrences.clear()
            await self._event("ConcurrenceInvalidated", {"summary": reason})

    async def _reconcile(self, reassessed: list[Role]) -> None:
        assert self.meeting
        meeting = self.meeting
        await self._phase(Phase.FRICTION_ANALYSIS)
        keys: dict[str, list[Role]] = {}
        for state in meeting.roles.values():
            if state.position is None:
                meeting.error = "A specialist has no position; retry before proposing a plan."
                await self._phase(Phase.ERROR)
                return
            for key in state.position.friction_keys:
                keys.setdefault(key, []).append(state.role)
        definitions = {
            key: (item.question, item.missing)
            for key, item in get_case(str(meeting.case["id"])).runtime.frictions.items()
        }
        for friction in meeting.frictions:
            if friction.id.startswith("objection-"):
                if set(friction.roles).issubset(reassessed):
                    friction.resolved = True
                    friction.resolution = (
                        "Specialist reassessed the objection. Fresh human concurrence is required."
                    )
                    await self._event("FrictionResolved", {"friction_id": friction.id})
            elif friction.id not in keys and not friction.resolved:
                friction.resolved = True
                friction.resolution = (
                    "Updated specialist position addresses the question; residual uncertainty "
                    "is retained in the conditional proposal."
                )
                await self._event("FrictionResolved", {"friction_id": friction.id})
        for key, roles in keys.items():
            existing = next((f for f in meeting.frictions if f.id == key), None)
            if existing:
                existing.roles = roles
                existing.resolved = False
                existing.resolution = None
            else:
                question, missing = definitions.get(key, (key, ["Specialist clarification"]))
                meeting.frictions.append(
                    Friction(id=key, question=question, roles=roles, missing=missing)
                )
                await self._event(
                    "FrictionDetected", {"friction_id": key, "question": question}
                )
        if any(f.blocking and not f.resolved for f in meeting.frictions):
            await self._phase(Phase.TARGETED_DISCUSSION)
        else:
            await self._propose()

    async def _propose(self) -> None:
        assert self.meeting
        meeting = self.meeting
        await self._phase(Phase.PLAN_PROPOSAL)
        positions = [state.position for state in meeting.roles.values() if state.position]
        runtime = get_case(str(meeting.case["id"])).runtime
        conditions = list(dict.fromkeys(u for p in positions for u in p.uncertainties))
        conditions.append(
            "Demonstration discussion only. A qualified MDT must independently verify "
            "diagnosis, current guidance, eligibility and patient consent."
        )
        conditions.extend(runtime.proposal.conditions)
        meeting.plan = Plan(
            version=meeting.plan.version + 1 if meeting.plan else 1,
            title=runtime.proposal.title,
            summary=runtime.proposal.summary,
            actions=[f"{meeting.roles[p.role].label}: {p.recommendation}" for p in positions],
            conditions=conditions,
            evidence_ids=list(
                dict.fromkeys(
                    e for p in positions for claim in p.claims for e in claim.evidence_ids
                )
            ),
        )
        meeting.concurrences.clear()
        await self._event("PlanProposed", {"version": meeting.plan.version})
        await self._phase(Phase.CONCURRENCE)
        objecting_roles = {obj["role"] for obj in meeting.objections}
        for position in positions:
            if position.autonomy == "AUTO" and position.role not in objecting_roles:
                meeting.concurrences[position.role] = Concurrence(
                    role=position.role,
                    plan_version=meeting.plan.version,
                    actor="agent",
                    comment="Automatic concurrence under demonstration policy.",
                )
                await self._event("ConcurrenceGiven", {"actor": "agent"}, position.role)
        await self._maybe_close()

    async def steer(self, meeting_id: str, role: Role, guidance: str) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id)
            if not guidance.strip():
                raise Conflict("Guidance must contain a substantive instruction.")
            state = meeting.roles[role]
            if len(state.guidance) >= 20:
                raise Conflict("Guidance limit reached for this demonstration role.")
            await self._invalidate("Human guidance changed a specialist position.")
            state.guidance.append(guidance.strip())
            meeting.busy = True
            meeting.round += 1
            await self._event("HumanGuidanceReceived", {"summary": guidance.strip()}, role)
            await self._phase(Phase.TARGETED_DISCUSSION)
            self._spawn([role], "followup")
            return meeting.model_copy(deep=True)

    async def followup(self, meeting_id: str) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id)
            if meeting.phase != Phase.TARGETED_DISCUSSION:
                raise Conflict("Targeted follow-up requires an open friction question.")
            roles = list(
                dict.fromkeys(
                    role
                    for friction in meeting.frictions
                    if not friction.resolved
                    for role in friction.roles
                )
            )
            if not roles:
                raise Conflict("There are no roles requiring follow-up.")
            if meeting.round >= 12:
                raise Conflict("Round budget reached. Start a new meeting.")
            await self._invalidate("Targeted evidence review is updating positions.")
            meeting.round += 1
            meeting.busy = True
            await self._event("EvidenceRequested", {"roles": [role.value for role in roles]})
            self._spawn(roles, "followup")
            return meeting.model_copy(deep=True)

    async def concur(
        self, meeting_id: str, role: Role, comment: str, plan_version: int | None = None
    ) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id)
            if meeting.phase != Phase.CONCURRENCE or not meeting.plan:
                raise Conflict("Concurrence requires a current proposed plan.")
            if plan_version is not None and plan_version != meeting.plan.version:
                raise Conflict("The plan changed. Review the current version before concurring.")
            meeting.concurrences[role] = Concurrence(
                role=role, plan_version=meeting.plan.version, actor="human", comment=comment
            )
            for objection in meeting.objections:
                if objection["role"] == role and not objection.get("addressed_at"):
                    objection["addressed_at"] = utcnow()
                    objection["accepted_plan_version"] = meeting.plan.version
            await self._event("ConcurrenceGiven", {"actor": "human", "comment": comment}, role)
            await self._maybe_close()
            return meeting.model_copy(deep=True)

    async def _maybe_close(self) -> None:
        assert self.meeting
        meeting = self.meeting
        if not meeting.plan or meeting.busy:
            return
        if any(f.blocking and not f.resolved for f in meeting.frictions):
            return
        if not all(
            role in meeting.concurrences
            and meeting.concurrences[role].plan_version == meeting.plan.version
            for role in Role
        ):
            return
        meeting.closed_at = utcnow()
        await self._phase(Phase.DECISION_CAPTURED)
        await self._event("CaseClosed", {"version": meeting.plan.version})

    async def object(
        self, meeting_id: str, role: Role, comment: str, plan_version: int | None = None
    ) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id)
            if meeting.phase != Phase.CONCURRENCE or not meeting.plan:
                raise Conflict("Objections require a proposed plan.")
            if plan_version is not None and plan_version != meeting.plan.version:
                raise Conflict("The plan changed. Review the current version before objecting.")
            if not comment.strip():
                raise Conflict("Explain the objection so the specialist can investigate.")
            meeting.objections.append(
                {
                    "role": role.value,
                    "comment": comment.strip(),
                    "plan_version": meeting.plan.version,
                    "timestamp": utcnow(),
                }
            )
            meeting.roles[role].guidance.append(f"Address this objection: {comment.strip()}")
            meeting.frictions.append(
                Friction(
                    id=f"objection-{len(meeting.objections)}",
                    question=comment.strip(),
                    roles=[role],
                    missing=["Reassessment and human concurrence"],
                )
            )
            await self._invalidate("A participant objected to the proposed plan.")
            await self._event("ObjectionRaised", {"comment": comment.strip()}, role)
            await self._phase(Phase.TARGETED_DISCUSSION)
            return meeting.model_copy(deep=True)

    async def memory(self, meeting_id: str, memory_id: str, action: str) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id)
            memory = next((m for m in meeting.memories if m.id == memory_id), None)
            if not memory or memory.status == "FORGOTTEN":
                raise NotFound("Memory nudge not found.")
            if action not in {"use", "ignore", "forget"}:
                raise Conflict("Unknown memory action.")
            if action == "use":
                memory.status = "USED"
            elif action == "ignore":
                memory.status = "IGNORED"
            else:
                memory.status = "FORGOTTEN"
            if action == "forget":
                memory.text = ""
                memory.source = ""
            try:
                await self._io(self.store.save_memory, memory)
            except Exception as exc:
                log.error("Memory persistence failed error_type=%s", type(exc).__name__)
                self.persistence_failed = True
                meeting.phase = Phase.ERROR
                meeting.error = (
                    "Memory persistence failed; retry storage recovery before continuing."
                )
                self._broadcast()
                raise PersistenceFailure(meeting.error) from exc
            await self._event(
                "MemoryAction", {"memory_id": memory_id, "action": action}, memory.role
            )
            if action == "use":
                note = f"Explicit memory nudge ({memory.category}, not medical fact): {memory.text}"
                await self._invalidate("A clinician explicitly applied a memory nudge.")
                meeting.roles[memory.role].guidance.append(note)
                meeting.round += 1
                meeting.busy = True
                await self._event("HumanGuidanceReceived", {"summary": note}, memory.role)
                self._spawn([memory.role], "followup")
            return meeting.model_copy(deep=True)

    async def cohort_reference(
        self,
        meeting_id: str,
        criteria: list[str] | None,
        resolved: list[str],
        reference: str,
    ) -> Meeting:
        """Quote one similar-case finding in the discussion, definition included.

        The reference is recorded as descriptive context with its cohort definition,
        denominator and provenance. It never changes the plan, the phase, existing
        concurrence or any specialist position: people still decide.
        """
        async with self.lock:
            meeting = self._editable(meeting_id)
            case_id = str(meeting.case["id"])
        profile = get_case(case_id).cohort_profile
        try:
            # Matching is CPU-bound and pure; it runs off the loop and outside the
            # chair lock so an analysis round is never delayed by a cohort query.
            result = await asyncio.to_thread(
                build_cohort,
                profile,
                case_id=case_id,
                criteria=criteria,
                resolved=tuple(resolved),
                minimum=self.settings.cohort_minimum_subgroup,
            )
            if result.suppressed:
                raise Conflict(
                    f"Only {result.matched} comparable cases match; below the minimum subgroup "
                    f"size of {result.definition.minimum_subgroup}. Widen the criteria before "
                    "quoting this cohort."
                )
            payload = reference_statement(result, reference)
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
        async with self.lock:
            meeting = self._editable(meeting_id)
            await self._event("CohortReferenceAdded", payload)
            return meeting.model_copy(deep=True)

    async def retry(self, meeting_id: str) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id, recovery=True)
            if meeting.phase != Phase.ERROR:
                raise Conflict("There is no failed round to retry.")
            if self.persistence_failed:
                try:
                    restored = await self._io(self.store.get, meeting_id)
                except Exception as exc:
                    log.error("Persistence recovery failed error_type=%s", type(exc).__name__)
                    raise PersistenceFailure("Persistent storage is still unavailable.") from exc
                if restored is not None:
                    self.meeting = meeting = restored
                self.persistence_failed = False
                meeting.busy = False
                if meeting.phase == Phase.DECISION_CAPTURED:
                    self._broadcast()
                    return meeting.model_copy(deep=True)
                for state in meeting.roles.values():
                    if state.status in {"ANALYZING", "REASSESSING"}:
                        state.status = "ERROR"
            roles = [
                role
                for role in Role
                if meeting.roles[role].status == "ERROR" or not meeting.roles[role].position
            ]
            if not roles:
                roles = list(Role)
            meeting.busy = True
            meeting.error = None
            await self._event("AnalysisRetried", {"roles": [role.value for role in roles]})
            self._spawn(roles, "initial" if meeting.round == 1 else "followup")
            return meeting.model_copy(deep=True)

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # Let queued writes finish before closing the connection they use.
        self._io_pool.shutdown(wait=True)
        self.store.close()
