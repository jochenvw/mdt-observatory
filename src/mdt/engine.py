import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from mdt.agents import MEMORY_NUDGE_PREFIX, confirmed_imaging_review
from mdt.case_registry import case_ids, get_case
from mdt.cohort import build_cohort, reference_statement
from mdt.communications import (
    AUTHOR_ROLE,
    LETTER_LANGUAGE,
    CommunicationRuntimeError,
    DraftResult,
    communication_inputs,
    draft,
)
from mdt.config import Settings
from mdt.models import (
    AUDIENCES,
    Audience,
    Communication,
    CommunicationReview,
    Concurrence,
    Event,
    Evidence,
    Friction,
    Meeting,
    Phase,
    Plan,
    Position,
    RequirementResolution,
    Role,
    RoleState,
    utcnow,
)
from mdt.store import Persistence
from mdt.telemetry import error_counter, event_counter, tracer

log = logging.getLogger("mdt.engine")
Analyzer = Callable[..., Awaitable[Position]]
Drafter = Callable[..., Awaitable[DraftResult]]
OUTCOME_UNAVAILABLE = "Outcome documents are available only after the decision is captured."


class Conflict(Exception):
    """A valid command that cannot apply to the current meeting state."""


class NotFound(Exception):
    """The requested meeting does not exist."""


class PersistenceFailure(RuntimeError):
    """The meeting cannot safely advance until durable storage recovers."""


class Engine:
    def __init__(
        self, store: Persistence, settings: Settings, analyzer: Analyzer,
        drafter: Drafter | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.analyzer = analyzer
        self.drafter = drafter or draft
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
        drafting = [
            item for item in (self.meeting.communications.values() if self.meeting else [])
            if item.status == "DRAFTING"
        ]
        if self.meeting and drafting:
            for item in drafting:
                item.status = "FAILED"
                item.error = "Server restarted while drafting. Regenerate to try again."
                item.updated_at = utcnow()
            self._append(
                "CommunicationFailed",
                {
                    "audiences": [item.audience for item in drafting],
                    "summary": "Outcome drafting was interrupted by a server restart.",
                    "error": True,
                },
                None,
            )
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
            if self.meeting and any(
                item.status == "DRAFTING" for item in self.meeting.communications.values()
            ):
                raise Conflict("Wait for the outcome documents to finish drafting.")
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

        searched: set[str] = set()

        async def emit(kind: str, payload: dict[str, Any]) -> None:
            async with self.lock:
                assert self.meeting
                self._accept_searched_evidence(kind, payload, searched)
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
                evidence_ids |= searched
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

    def _accept_searched_evidence(
        self, kind: str, payload: dict[str, Any], searched: set[str]
    ) -> None:
        """Add a LIVE or RECORDED search result to the meeting's evidence, labelled as such.

        Curated records are never replaced. A later fetch of the same record (its full
        abstract) replaces the earlier search snippet.
        """
        assert self.meeting
        evidence = payload.get("evidence")
        if kind != "EvidenceFound" or not isinstance(evidence, dict):
            return
        if evidence.get("retrieval") not in {"LIVE", "RECORDED"}:
            return
        record = Evidence.model_validate(evidence)
        for index, known in enumerate(self.meeting.evidence):
            if known.id == record.id:
                if known.retrieval == "CURATED":
                    return
                self.meeting.evidence[index] = record
                break
        else:
            self.meeting.evidence.append(record)
        searched.add(record.id)

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
                human_input = (
                    confirmed_imaging_review(
                        meeting.roles[Role.RADIOLOGY].guidance,
                        get_case(str(meeting.case["id"])).runtime.imaging_review_terms,
                    )
                    if friction.id == "imaging" and Role.RADIOLOGY in reassessed
                    else None
                )
                if human_input is not None:
                    finding = f"Radiologist reported: {human_input}"
                    resolution = RequirementResolution(
                        requirement_id="imaging",
                        role=Role.RADIOLOGY,
                        status="CONFIRMED",
                        human_input=human_input,
                        finding=finding,
                    )
                    meeting.requirement_resolutions = [
                        item for item in meeting.requirement_resolutions
                        if item.requirement_id != resolution.requirement_id
                    ]
                    meeting.requirement_resolutions.append(resolution)
                    friction.resolution = (
                        "Radiologist confirmed the targeted review was completed and acceptable. "
                        "The original human input is preserved in the audit record."
                    )
                    await self._event(
                        "RequirementResolved",
                        {
                            "requirement_id": resolution.requirement_id,
                            "status": resolution.status,
                            "human_input": resolution.human_input,
                            "finding": resolution.finding,
                        },
                        Role.RADIOLOGY,
                    )
                else:
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
                if existing.id == "imaging" and any(
                    item.requirement_id == "imaging"
                    for item in meeting.requirement_resolutions
                ):
                    meeting.requirement_resolutions = [
                        item for item in meeting.requirement_resolutions
                        if item.requirement_id != "imaging"
                    ]
                    await self._event(
                        "RequirementReopened",
                        {
                            "requirement_id": "imaging",
                            "summary": (
                                "Later radiology input no longer supports treating the review "
                                "requirement as completed."
                            ),
                        },
                        Role.RADIOLOGY,
                    )
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
        resolved_ids = {item.requirement_id for item in meeting.requirement_resolutions}
        excluded_conditions = (
            set(runtime.imaging_conditions) if "imaging" in resolved_ids else set()
        )
        conditions = list(
            dict.fromkeys(
                [
                    *(u for p in positions for u in p.uncertainties),
                    "Demonstration discussion only. A qualified MDT must independently verify "
                    "diagnosis, current guidance, eligibility and patient consent.",
                    *runtime.proposal.conditions,
                ]
            )
        )
        conditions = [item for item in conditions if item not in excluded_conditions]
        actions = list(dict.fromkeys(p.recommendation for p in positions))
        meeting.plan = Plan(
            version=meeting.plan.version + 1 if meeting.plan else 1,
            direction=runtime.proposal.direction,
            title=runtime.proposal.title,
            decision=runtime.proposal.decision,
            summary=runtime.proposal.summary,
            actions=actions,
            conditions=conditions,
            resolved_requirements=[
                item.model_copy(deep=True) for item in meeting.requirement_resolutions
            ],
            evidence_ids=list(
                dict.fromkeys(
                    e for p in positions for claim in p.claims for e in claim.evidence_ids
                )
            ),
        )
        meeting.concurrences.clear()
        await self._event(
            "PlanProposed",
            {"version": meeting.plan.version, "direction": meeting.plan.direction},
        )
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
        # Drafts are recorded with the closing snapshot, so a restart can mark them failed.
        for audience in AUDIENCES:
            meeting.communications[audience] = Communication(
                audience=audience, plan_version=meeting.plan.version,
                generated_by="azure", author_role=AUTHOR_ROLE[audience],
                language=self._language(meeting, audience),
            )
        await self._phase(Phase.DECISION_CAPTURED)
        await self._event("CaseClosed", {"version": meeting.plan.version})
        for audience in AUDIENCES:
            self._spawn_draft(meeting.id, audience, 1)

    @staticmethod
    def _language(meeting: Meeting, audience: Audience) -> str:
        if audience != "patient":
            return LETTER_LANGUAGE
        return str(meeting.case.get("preferred_language") or "en").strip().lower()

    def _spawn_draft(self, meeting_id: str, audience: Audience, revision: int) -> None:
        task = asyncio.create_task(self._draft(meeting_id, audience, revision))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _drafting(self, meeting_id: str, audience: Audience, revision: int) -> Communication | None:
        """The draft this task owns, or None if the room, audience or revision moved on."""
        meeting = self.meeting
        if not meeting or meeting.id != meeting_id:
            return None
        item = meeting.communications.get(audience)
        if not item or item.revision != revision or item.status != "DRAFTING":
            return None
        return item

    async def _draft(self, meeting_id: str, audience: Audience, revision: int) -> None:
        async with self.lock:
            item = self._drafting(meeting_id, audience, revision)
            if item is None or self.meeting is None:
                return
            try:
                inputs = communication_inputs(
                    self.meeting, audience, list(item.requested_changes), revision
                )
            except CommunicationRuntimeError as exc:
                item.status = "FAILED"
                item.error = str(exc)
                item.updated_at = utcnow()
                await self._event(
                    "CommunicationFailed",
                    {"audience": audience, "revision": revision, "summary": item.error,
                     "error": True},
                )
                return

        async def emit(kind: str, payload: dict[str, Any]) -> None:
            async with self.lock:
                if self._drafting(meeting_id, audience, revision) is None:
                    return
                await self._event(
                    "CommunicationActivity",
                    {**payload, "audience": audience, "activity": kind, "revision": revision},
                )

        result: DraftResult | None = None
        error: str | None = None
        try:
            with tracer.start_as_current_span(
                "mdt.communication", attributes={"mdt.audience": audience, "mdt.mode": inputs.mode}
            ):
                result = await self.drafter(inputs, emit=emit, settings=self.settings)
        except PersistenceFailure:
            raise
        except Exception as exc:
            error = self._draft_error(audience, exc)
        async with self.lock:
            current = self._drafting(meeting_id, audience, revision)
            if current is None:
                return
            current.updated_at = utcnow()
            if result is None:
                current.status = "FAILED"
                current.error = error
                await self._event(
                    "CommunicationFailed",
                    {"audience": audience, "revision": revision, "summary": error, "error": True},
                )
                return
            current.title = result.title
            current.sections = result.sections
            current.glossary = result.glossary
            current.questions_to_ask = result.questions_to_ask
            current.citations = result.citations
            current.checks = result.checks
            current.generated_by = result.generated_by
            current.language = result.language
            current.error = None
            current.status = "DRAFT"
            await self._event(
                "CommunicationDrafted",
                {
                    "audience": audience,
                    "revision": revision,
                    "summary": (
                        "Patient summary drafted; awaiting clinician review."
                        if audience == "patient"
                        else "Clinician letter drafted; awaiting clinician sign-off."
                    ),
                },
            )

    @staticmethod
    def _draft_error(audience: Audience, exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        log.error(
            "Communication failed audience=%s error_type=%s provider_status=%s provider_code=%s",
            audience, type(exc).__name__, status, getattr(exc, "code", None),
        )
        error_counter.add(1, {"mdt.audience": audience, "error.type": type(exc).__name__})
        reasons = {
            401: "Azure authentication failed. Renew credentials, then regenerate.",
            403: "Azure access denied. Verify the model identity role, then regenerate.",
            429: "Azure model quota is busy. Retry budget exhausted; regenerate later.",
        }
        if isinstance(status, int) and status in reasons:
            return reasons[status]
        if isinstance(exc, CommunicationRuntimeError):
            return f"{exc} No scripted text was substituted; regenerate to try again."
        if isinstance(exc, TimeoutError):
            return "Drafting timed out. No scripted text was substituted; regenerate to try again."
        return (
            f"{type(exc).__name__}: drafting failed. No scripted text was substituted; "
            "check model configuration and diagnostics, then regenerate."
        )

    def _outcome(self, meeting_id: str, audience: str) -> tuple[Meeting, Plan]:
        meeting = self._current(meeting_id)
        if audience not in AUDIENCES:
            raise NotFound("Unknown outcome document.")
        if self.persistence_failed:
            raise PersistenceFailure("Retry storage recovery before changing the meeting.")
        if meeting.phase != Phase.DECISION_CAPTURED or not meeting.plan:
            raise Conflict(OUTCOME_UNAVAILABLE)
        return meeting, meeting.plan

    @staticmethod
    def _bound(item: Communication, plan: Plan, plan_version: int, revision: int) -> None:
        if plan_version != plan.version or item.plan_version != plan.version:
            raise Conflict("The plan version changed. Review the current document.")
        if revision != item.revision:
            raise Conflict("A newer draft revision exists. Review it before continuing.")

    @staticmethod
    def _reviewer(reviewer: str) -> str:
        name = reviewer.strip()
        if not name:
            raise Conflict("Name the reviewing clinician.")
        return name

    async def approve_communication(
        self, meeting_id: str, audience: Audience, *, reviewer: str, role: Role | None,
        plan_version: int, revision: int, comment: str = "",
    ) -> Meeting:
        async with self.lock:
            meeting, plan = self._outcome(meeting_id, audience)
            name = self._reviewer(reviewer)
            item = meeting.communications.get(audience)
            if item is None or item.status != "DRAFT":
                raise Conflict(
                    "Already approved." if item and item.status == "APPROVED"
                    else "Only a completed draft can be approved."
                )
            self._bound(item, plan, plan_version, revision)
            now = utcnow()
            item.reviews.append(
                CommunicationReview(
                    action="approve", reviewer=name, role=role, comment=comment.strip(),
                    plan_version=plan.version, revision=item.revision, timestamp=now,
                )
            )
            item.status = "APPROVED"
            item.approved_by = name
            item.approved_role = role
            item.approved_at = now
            item.approved_revision = item.revision
            item.updated_at = now
            await self._event(
                "CommunicationApproved",
                {
                    "audience": audience, "revision": item.revision, "reviewer": name,
                    "summary": f"{name} approved revision {item.revision} for plan "
                    f"version {plan.version}.",
                },
                role,
            )
            return meeting.model_copy(deep=True)

    async def request_communication_changes(
        self, meeting_id: str, audience: Audience, *, reviewer: str, role: Role | None,
        plan_version: int, revision: int, comment: str,
    ) -> Meeting:
        async with self.lock:
            meeting, plan = self._outcome(meeting_id, audience)
            name = self._reviewer(reviewer)
            request = comment.strip()
            if not request:
                raise Conflict("Describe the change the draft needs.")
            item = meeting.communications.get(audience)
            if item is None or item.status not in {"DRAFT", "APPROVED"}:
                raise Conflict("Changes can be requested on a completed draft only.")
            self._bound(item, plan, plan_version, revision)
            item.reviews.append(
                CommunicationReview(
                    action="request_changes", reviewer=name, role=role, comment=request,
                    plan_version=plan.version, revision=item.revision,
                )
            )
            item.requested_changes.append(request)
            item.status = "CHANGES_REQUESTED"
            item.approved_by = item.approved_at = None
            item.approved_role = None
            item.approved_revision = None
            item.updated_at = utcnow()
            await self._event(
                "CommunicationChangesRequested",
                {"audience": audience, "revision": item.revision, "reviewer": name,
                 "summary": request},
                role,
            )
            await self._redraft(meeting, item)
            return meeting.model_copy(deep=True)

    async def regenerate_communication(
        self, meeting_id: str, audience: Audience, *, reviewer: str, role: Role | None,
    ) -> Meeting:
        async with self.lock:
            meeting, plan = self._outcome(meeting_id, audience)
            name = self._reviewer(reviewer)
            item = meeting.communications.get(audience)
            if item is not None and item.status == "DRAFTING":
                raise Conflict("This document is already being drafted.")
            if item is not None and item.status == "APPROVED":
                raise Conflict("Request changes to replace an approved document.")
            if item is None:
                item = Communication(
                    audience=audience, plan_version=plan.version, revision=0,
                    generated_by="azure", author_role=AUTHOR_ROLE[audience],
                    language=self._language(meeting, audience),
                )
                meeting.communications[audience] = item
            item.reviews.append(
                CommunicationReview(
                    action="regenerate", reviewer=name, role=role,
                    plan_version=plan.version, revision=item.revision,
                )
            )
            await self._redraft(meeting, item)
            return meeting.model_copy(deep=True)

    async def _redraft(self, meeting: Meeting, item: Communication) -> None:
        item.revision += 1
        item.status = "DRAFTING"
        item.error = None
        item.sections = []
        item.glossary = []
        item.questions_to_ask = []
        item.citations = []
        item.checks = None
        item.updated_at = utcnow()
        await self._event(
            "CommunicationDraftingStarted",
            {"audience": item.audience, "revision": item.revision,
             "summary": f"Drafting revision {item.revision}."},
        )
        self._spawn_draft(meeting.id, item.audience, item.revision)

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
                note = f"{MEMORY_NUDGE_PREFIX}{memory.category}, not medical fact): {memory.text}"
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
