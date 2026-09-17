import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from mdt.case_registry import case_ids, get_case
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
            self._event("AnalysisInterrupted", {"summary": self.meeting.error})

    def _current(self, meeting_id: str) -> Meeting:
        if self.cleared or not self.meeting or self.meeting.id != meeting_id:
            raise NotFound("Meeting is not the active demonstration room.")
        return self.meeting

    @property
    def active(self) -> Meeting | None:
        """The meeting participant screens should be showing, if any."""
        return None if self.cleared else self.meeting

    def get(self, meeting_id: str) -> Meeting:
        if self.meeting and self.meeting.id == meeting_id:
            return self.meeting
        found = self.store.get(meeting_id)
        if not found:
            raise NotFound("Meeting not found.")
        return found

    def _event(
        self, kind: str, payload: dict[str, Any] | None = None, role: Role | None = None
    ) -> None:
        assert self.meeting
        if self.persistence_failed:
            raise PersistenceFailure("Persistent storage is unavailable; the meeting is paused.")
        meeting = self.meeting
        event = Event(
            id=len(meeting.events) + 1,
            meeting_id=meeting.id,
            type=kind,
            role=role,
            payload=payload or {},
        )
        meeting.events.append(event)
        try:
            self.store.save(meeting)
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
        self._broadcast()
        event_counter.add(1, {"event.type": kind, "mdt.mode": meeting.mode})
        log.info("mdt.event type=%s meeting=%s role=%s", kind, meeting.id, role or "chair")

    def _broadcast(self) -> None:
        assert self.meeting
        snapshot = self.meeting.model_dump_json()
        for queue in self.subscribers.get(self.meeting.id, set()):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(snapshot)
        self._broadcast_room()

    def room_snapshot(self) -> str:
        """Envelope describing the room every participant screen follows.

        A null meeting is the standby state: participant screens clear and wait
        for the orchestrator to activate the next case.
        """
        meeting = None if self.cleared or not self.meeting else self.meeting
        body = "null" if meeting is None else meeting.model_dump_json()
        return f'{{"meeting":{body}}}'

    def _broadcast_room(self) -> None:
        snapshot = self.room_snapshot()
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
                self._event("RoomCleared", {
                    "summary": "The meeting was closed on the shared screens. "
                    "The record stays available for review and export.",
                })
                return
            self.cleared = True
            self._broadcast_room()

    def _phase(self, phase: Phase) -> None:
        assert self.meeting
        self.meeting.phase = phase
        self._event("PhaseChanged", {"phase": phase.value})

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
            if self.store.count() >= self.settings.max_meetings:
                raise Conflict("Demo meeting retention limit reached. Archive the database first.")
            definition = get_case(case_id)
            memory_ids = {item.id for item in definition.memories}
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
                memories=[
                    item for item in self.store.memories(definition.memories)
                    if item.id in memory_ids
                ],
                busy=True,
                round=1,
            )
            self._phase(Phase.CASE_LOADING)
            self._event(
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
            self._event("RoleAnalysisStarted", {"round": self.meeting.round}, role)
            case_id = str(self.meeting.case["id"])
            guidance = list(state.guidance)
            mode = self.meeting.mode

        async def emit(kind: str, payload: dict[str, Any]) -> None:
            async with self.lock:
                assert self.meeting
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
                self._event(kind, payload, role)
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
                self._event(
                    "PositionPublished" if phase == "initial" else "PositionUpdated",
                    {"revision": current.revision, "autonomy": position.autonomy},
                    role,
                )
        except PersistenceFailure:
            raise
        except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
            await self._role_error(role, exc)
        except Exception as exc:
            # Provider SDK errors vary; every failure becomes a persisted, visible failed role.
            await self._role_error(role, exc)

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
            self._event("RoleAnalysisFailed", {"summary": state.error}, role)

    async def _run_roles(self, roles: list[Role], phase: str) -> None:
        try:
            async with self.lock:
                self._phase(Phase.INITIAL_ANALYSIS if phase == "initial" else Phase.POSITION_UPDATE)
            async with asyncio.TaskGroup() as group:
                for role in roles:
                    group.create_task(self._analyze_one(role, phase))
            async with self.lock:
                assert self.meeting
                self.meeting.busy = False
                if any(state.status == "ERROR" for state in self.meeting.roles.values()):
                    self.meeting.error = "One or more specialists failed. No consensus is possible."
                    self._phase(Phase.ERROR)
                    return
                self.meeting.error = None
                self._phase(Phase.POSITION_COLLECTION)
                self._reconcile(roles if phase == "followup" else [])
        except asyncio.CancelledError:
            async with self.lock:
                assert self.meeting
                self.meeting.busy = False
                self.meeting.error = "Analysis interrupted by shutdown. Retry the round."
                if self.persistence_failed:
                    self.meeting.phase = Phase.ERROR
                    self._broadcast()
                else:
                    self._phase(Phase.ERROR)
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

    def _invalidate(self, reason: str) -> None:
        assert self.meeting
        if self.meeting.plan:
            self.meeting.concurrences.clear()
            self._event("ConcurrenceInvalidated", {"summary": reason})

    def _reconcile(self, reassessed: list[Role]) -> None:
        assert self.meeting
        meeting = self.meeting
        self._phase(Phase.FRICTION_ANALYSIS)
        keys: dict[str, list[Role]] = {}
        for state in meeting.roles.values():
            if state.position is None:
                meeting.error = "A specialist has no position; retry before proposing a plan."
                self._phase(Phase.ERROR)
                return
            for key in state.position.friction_keys:
                keys.setdefault(key, []).append(state.role)
        definitions = {
            "imaging": (
                "Can all nine original liver sites be cleared while preserving vessels "
                "and an adequate remnant, with the lung nodule still indeterminate?",
                [
                    "Human review of baseline-to-current mapping for all nine liver sites",
                    "Segment 1 / IVC and segment 4a / middle hepatic vein margins",
                    "Repeat thin-section chest CT; PET cannot classify the 5 mm nodule",
                ],
            ),
            "applicability": (
                "Does early response justify local treatment now, or is more systemic "
                "disease control needed before conversion surgery?",
                [
                    "BREAKWATER systemic efficacy versus CAIRO5 conversion evidence",
                    "PROVENC3 setting mismatch: ctDNA is not a binary surgical veto",
                    "Primary-tumor sequence, perioperative treatment and patient goals",
                ],
            ),
        }
        if runtime := get_case(str(meeting.case["id"])).runtime:
            definitions = {
                key: (item.question, item.missing) for key, item in runtime.frictions.items()
            }
        for friction in meeting.frictions:
            if friction.id.startswith("objection-"):
                if set(friction.roles).issubset(reassessed):
                    friction.resolved = True
                    friction.resolution = (
                        "Specialist reassessed the objection. Fresh human concurrence is required."
                    )
                    self._event("FrictionResolved", {"friction_id": friction.id})
            elif friction.id not in keys and not friction.resolved:
                friction.resolved = True
                friction.resolution = (
                    "Updated specialist position addresses the question; residual uncertainty "
                    "is retained in the conditional proposal."
                )
                self._event("FrictionResolved", {"friction_id": friction.id})
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
                self._event("FrictionDetected", {"friction_id": key, "question": question})
        if any(f.blocking and not f.resolved for f in meeting.frictions):
            self._phase(Phase.TARGETED_DISCUSSION)
        else:
            self._propose()

    def _propose(self) -> None:
        assert self.meeting
        meeting = self.meeting
        self._phase(Phase.PLAN_PROPOSAL)
        positions = [state.position for state in meeting.roles.values() if state.position]
        runtime = get_case(str(meeting.case["id"])).runtime
        conditions = list(dict.fromkeys(u for p in positions for u in p.uncertainties))
        conditions.append(
            "Demonstration discussion only. A qualified MDT must independently verify "
            "diagnosis, current guidance, eligibility and patient consent."
        )
        conditions.extend(
            runtime.proposal.conditions if runtime else [
                "Choose explicitly between local clearance now, additional systemic treatment "
                "with reassessment, and a systemic disease-control strategy. No option is "
                "authorized automatically by this proposal.",
                "Complete local clearance remains conditional on every original liver site, "
                "vessel safety, remnant function, repeat chest imaging and patient preference.",
                "Persistent ctDNA and the stable 5 mm lung nodule remain unresolved risk "
                "information, not proof of incurability or benignity.",
            ]
        )
        meeting.plan = Plan(
            version=meeting.plan.version + 1 if meeting.plan else 1,
            title=(
                runtime.proposal.title if runtime
                else "Conditional colorectal conversion MDT proposal"
            ),
            summary=runtime.proposal.summary if runtime else (
                "After four cycles of encorafenib, cetuximab and mFOLFOX6, nine bilobar "
                "liver metastases appear potentially clearable, but technical feasibility "
                "does not establish durable disease control. Review local treatment now "
                "against additional systemic therapy and deferred local treatment. "
                "The source's liver-first preference is conditional, not an automatic decision."
            ),
            actions=[f"{meeting.roles[p.role].label}: {p.recommendation}" for p in positions],
            conditions=conditions,
            evidence_ids=list(
                dict.fromkeys(
                    e for p in positions for claim in p.claims for e in claim.evidence_ids
                )
            ),
        )
        meeting.concurrences.clear()
        self._event("PlanProposed", {"version": meeting.plan.version})
        self._phase(Phase.CONCURRENCE)
        objecting_roles = {obj["role"] for obj in meeting.objections}
        for position in positions:
            if position.autonomy == "AUTO" and position.role not in objecting_roles:
                meeting.concurrences[position.role] = Concurrence(
                    role=position.role,
                    plan_version=meeting.plan.version,
                    actor="agent",
                    comment="Automatic concurrence under demonstration policy.",
                )
                self._event("ConcurrenceGiven", {"actor": "agent"}, position.role)
        self._maybe_close()

    async def steer(self, meeting_id: str, role: Role, guidance: str) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id)
            if not guidance.strip():
                raise Conflict("Guidance must contain a substantive instruction.")
            state = meeting.roles[role]
            if len(state.guidance) >= 20:
                raise Conflict("Guidance limit reached for this demonstration role.")
            self._invalidate("Human guidance changed a specialist position.")
            state.guidance.append(guidance.strip())
            meeting.busy = True
            meeting.round += 1
            self._event("HumanGuidanceReceived", {"summary": guidance.strip()}, role)
            self._phase(Phase.TARGETED_DISCUSSION)
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
            self._invalidate("Targeted evidence review is updating positions.")
            meeting.round += 1
            meeting.busy = True
            self._event("EvidenceRequested", {"roles": [role.value for role in roles]})
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
            self._event("ConcurrenceGiven", {"actor": "human", "comment": comment}, role)
            self._maybe_close()
            return meeting.model_copy(deep=True)

    def _maybe_close(self) -> None:
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
        self._phase(Phase.DECISION_CAPTURED)
        self._event("CaseClosed", {"version": meeting.plan.version})

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
            self._invalidate("A participant objected to the proposed plan.")
            self._event("ObjectionRaised", {"comment": comment.strip()}, role)
            self._phase(Phase.TARGETED_DISCUSSION)
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
                self.store.save_memory(memory)
            except Exception as exc:
                log.error("Memory persistence failed error_type=%s", type(exc).__name__)
                self.persistence_failed = True
                meeting.phase = Phase.ERROR
                meeting.error = (
                    "Memory persistence failed; retry storage recovery before continuing."
                )
                self._broadcast()
                raise PersistenceFailure(meeting.error) from exc
            self._event("MemoryAction", {"memory_id": memory_id, "action": action}, memory.role)
            if action == "use":
                note = f"Explicit memory nudge ({memory.category}, not medical fact): {memory.text}"
                self._invalidate("A clinician explicitly applied a memory nudge.")
                meeting.roles[memory.role].guidance.append(note)
                meeting.round += 1
                meeting.busy = True
                self._event("HumanGuidanceReceived", {"summary": note}, memory.role)
                self._spawn([memory.role], "followup")
            return meeting.model_copy(deep=True)

    async def retry(self, meeting_id: str) -> Meeting:
        async with self.lock:
            meeting = self._editable(meeting_id, recovery=True)
            if meeting.phase != Phase.ERROR:
                raise Conflict("There is no failed round to retry.")
            if self.persistence_failed:
                try:
                    restored = self.store.get(meeting_id)
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
            self._event("AnalysisRetried", {"roles": [role.value for role in roles]})
            self._spawn(roles, "initial" if meeting.round == 1 else "followup")
            return meeting.model_copy(deep=True)

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.store.close()
