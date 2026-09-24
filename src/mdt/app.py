import asyncio
import hashlib
import hmac
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import Field
from starlette.middleware.base import RequestResponseEndpoint

from mdt.case_registry import case_ids, get_case
from mdt.cohort import CohortResult, build_cohort
from mdt.config import Settings
from mdt.engine import Conflict, Engine, NotFound, PersistenceFailure
from mdt.models import Contract, Meeting, Role
from mdt.store import Persistence, Store
from mdt.telemetry import configure

COOKIE = "mdt_presenter"
MAX_COMMAND_BYTES = 16384


class Start(Contract):
    mode: Literal["rehearsal", "azure"] = "rehearsal"
    case_id: str | None = Field(default=None, min_length=1, max_length=100)


class CaseSummary(Contract):
    id: str
    title: str
    patient_label: str
    stage: str
    question: str


class Steering(Contract):
    role: Role
    guidance: str = Field(min_length=1, max_length=2000)


class Vote(Contract):
    role: Role
    plan_version: int = Field(ge=1)
    comment: str = Field(default="", max_length=2000)


class CohortReference(Contract):
    """One cohort finding a clinician chooses to quote in the discussion."""

    reference: str = Field(min_length=1, max_length=120)
    criteria: list[str] | None = Field(default=None, max_length=12)
    resolved: list[str] = Field(default_factory=list, max_length=12)


class MemoryAction(Contract):
    memory_id: str = Field(min_length=1, max_length=100)
    action: Literal["use", "ignore", "forget"]


class Login(Contract):
    token: str = Field(min_length=1, max_length=512)


def cookie_value(secret: str, timestamp: int) -> str:
    signature = hmac.new(secret.encode(), str(timestamp).encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def valid_cookie(value: str, secret: str) -> bool:
    timestamp, separator, _ = value.partition(".")
    if not separator or not timestamp.isdigit() or len(timestamp) > 12:
        return False
    age = int(time.time()) - int(timestamp)
    return 0 <= age < 43200 and hmac.compare_digest(value, cookie_value(secret, int(timestamp)))


def snapshot_stream(
    request: Request,
    queue: asyncio.Queue[str],
    event: str,
    token: str,
    release: Callable[[], None],
) -> StreamingResponse:
    """Stream queued snapshots to one screen until it disconnects or its session expires.

    Heartbeats keep the connection open through idle periods and are the point at
    which an expired presenter session is noticed and the stream closed.
    """

    async def snapshots() -> AsyncIterator[str]:
        try:
            while not await request.is_disconnected():
                try:
                    snapshot = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {event}\ndata: {snapshot}\n\n"
                except TimeoutError:
                    if token and not valid_cookie(request.cookies.get(COOKIE, ""), token):
                        return
                    yield ": heartbeat\n\n"
        finally:
            release()

    return StreamingResponse(
        snapshots(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _discard_room(service: Engine, queue: asyncio.Queue[str]) -> None:
    service.room_subscribers.discard(queue)


def _discard_meeting(service: Engine, meeting_id: str, queue: asyncio.Queue[str]) -> None:
    service.subscribers[meeting_id].discard(queue)
    if not service.subscribers[meeting_id]:
        del service.subscribers[meeting_id]


def get_engine(request: Request) -> Engine:
    service = request.app.state.engine
    assert isinstance(service, Engine)
    return service


EngineDep = Annotated[Engine, Depends(get_engine)]


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    config = settings or Settings()
    if os.getenv("CONTAINER_APP_NAME") and len(config.presenter_token) < 24:
        raise RuntimeError(
            "Cloud deployment requires MDT_PRESENTER_TOKEN of at least 24 characters."
        )
    failed_attempts: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if engine is None:
            from mdt.agents import analyze

            storage: Persistence
            if config.storage_backend == "azure_blob":
                from mdt.blob_store import BlobStore

                storage = BlobStore(config.blob_account_url, config.blob_container)
            else:
                storage = Store(config.db_path)
            application.state.engine = Engine(storage, config, partial(analyze, settings=config))
        else:
            application.state.engine = engine
        yield
        await application.state.engine.close()
        from mdt.agents import aclose_azure_clients

        await aclose_azure_clients()

    application = FastAPI(
        title="MDT Observatory",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.middleware("http")
    async def boundaries(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin commands are not permitted."}, 403)
            if "application/json" not in request.headers.get("content-type", ""):
                return JSONResponse({"detail": "Commands require application/json."}, 415)
            # Without a declared length the body would be read in full before any
            # size check, so chunked or unsized commands are refused outright.
            length = request.headers.get("content-length")
            if length is None or "transfer-encoding" in request.headers:
                return JSONResponse({"detail": "Commands require Content-Length."}, 411)
            if not length.isdigit():
                return JSONResponse({"detail": "Invalid Content-Length."}, 400)
            if int(length) > MAX_COMMAND_BYTES:
                return JSONResponse({"detail": "Request exceeds the demo command size limit."}, 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def authorized(request: Request) -> None:
        if config.presenter_token and not valid_cookie(
            request.cookies.get(COOKIE, ""), config.presenter_token
        ):
            raise HTTPException(401, "Presenter access required.")

    protected = [Depends(authorized)]

    @application.exception_handler(Conflict)
    async def conflict_handler(request: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @application.exception_handler(NotFound)
    async def missing_handler(request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @application.exception_handler(PersistenceFailure)
    async def persistence_handler(request: Request, exc: PersistenceFailure) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "mdt-observatory"}

    @application.get("/readyz")
    async def ready(service: EngineDep) -> dict[str, str]:
        try:
            await service.ready()
        except Exception as exc:
            raise HTTPException(503, "Persistent storage is not ready.") from exc
        return {"status": "ready"}

    @application.get("/api/config")
    async def configuration() -> dict[str, object]:
        modes = ["rehearsal"]
        if os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_DEPLOYMENT"):
            modes.append("azure")
        return {
            "modes": modes,
            "auth_required": bool(config.presenter_token),
            "version": "0.1.0",
            "disclaimer": "DEMONSTRATION SYSTEM. NOT FOR CLINICAL USE.",
        }

    @application.post("/api/auth")
    async def login(body: Login, request: Request, response: Response) -> dict[str, bool]:
        if not config.presenter_token:
            return {"authenticated": True}
        # A correct token is never throttled, so failures from others (who may share
        # an address behind the ingress) cannot lock the presenter out. Only failed
        # attempts count toward the per-client limit.
        if not hmac.compare_digest(body.token, config.presenter_token):
            host = request.client.host if request.client else "unknown"
            now = time.monotonic()
            attempts = [t for t in failed_attempts.get(host, []) if now - t < 60]
            if len(attempts) >= 10:
                failed_attempts[host] = attempts
                raise HTTPException(429, "Too many access attempts. Wait one minute.")
            attempts.append(now)
            failed_attempts[host] = attempts
            if len(failed_attempts) > 2048:
                for key in [k for k, v in failed_attempts.items() if now - v[-1] >= 60]:
                    del failed_attempts[key]
            raise HTTPException(401, "Invalid presenter token.")
        response.set_cookie(
            COOKIE,
            cookie_value(config.presenter_token, int(time.time())),
            httponly=True,
            secure=config.secure_cookie or bool(os.getenv("CONTAINER_APP_NAME")),
            samesite="strict",
            max_age=43200,
        )
        return {"authenticated": True}

    @application.get("/api/meeting", dependencies=protected)
    async def latest(service: EngineDep) -> Meeting | None:
        return await service.current()

    @application.get("/api/room/stream", dependencies=protected)
    async def room_stream(service: EngineDep, request: Request) -> StreamingResponse:
        """Live room channel every participant screen follows, meeting or not.

        Screens that open before a case is activated, and screens still showing a
        previous case, both receive the current room state here; no manual reload.
        """
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
        initial_room = await service.room_state()
        service.room_subscribers.add(queue)
        queue.put_nowait(initial_room)
        return snapshot_stream(
            request, queue, "room", config.presenter_token, lambda: _discard_room(service, queue)
        )

    @application.post("/api/room/clear", dependencies=protected)
    async def clear_room(service: EngineDep) -> dict[str, bool]:
        """Return all participant screens to standby. The record is retained."""
        await service.clear()
        return {"cleared": True}

    @application.get("/api/cases", dependencies=protected)
    async def cases() -> list[CaseSummary]:
        return [
            CaseSummary(
                id=case["id"],
                title=case["diagnosis"],
                patient_label=case["pseudonym"],
                stage=case["stage"],
                question=case["question"],
            )
            for identifier in case_ids()
            for case in (get_case(identifier).case,)
        ]

    @application.get("/api/cases/{case_id}/cohort", dependencies=protected)
    async def cohort(
        case_id: str,
        criteria: Annotated[list[str] | None, Query(max_length=12)] = None,
        resolved: Annotated[list[str] | None, Query(max_length=12)] = None,
        include_cases: bool = False,
    ) -> CohortResult:
        """Descriptive comparison against the governed historical cohort.

        Omitting `criteria` preselects the clinically meaningful characteristics the
        current case actually has; supplying it selects exactly those criteria.
        """
        try:
            definition = get_case(case_id)
        except ValueError:
            raise HTTPException(404, "Selected case is not available.") from None
        selected = None if criteria is None else [key for key in criteria if key]
        try:
            # Matching is pure computation over the governed cohort; running it off the
            # event loop keeps streams, health probes and the chair responsive.
            return await asyncio.to_thread(
                build_cohort,
                definition.cohort_profile,
                case_id=case_id,
                criteria=selected,
                resolved=tuple(resolved or ()),
                include_cases=include_cases,
                minimum=config.cohort_minimum_subgroup,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.post("/api/meetings", dependencies=protected, status_code=201)
    async def start(body: Start, service: EngineDep) -> Meeting:
        if body.mode == "azure" and not (
            os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_DEPLOYMENT")
        ):
            raise HTTPException(422, "Azure mode requires endpoint and deployment configuration.")
        return await service.start(body.mode, body.case_id)

    @application.get("/api/meetings/{meeting_id}", dependencies=protected)
    async def meeting(meeting_id: str, service: EngineDep) -> Meeting:
        return await service.load(meeting_id)

    @application.get("/api/meetings/{meeting_id}/stream", dependencies=protected)
    async def stream(meeting_id: str, service: EngineDep, request: Request) -> StreamingResponse:
        initial = await service.load(meeting_id)
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
        service.subscribers.setdefault(meeting_id, set()).add(queue)
        queue.put_nowait(initial.model_dump_json())
        return snapshot_stream(
            request,
            queue,
            "state",
            config.presenter_token,
            lambda: _discard_meeting(service, meeting_id, queue),
        )

    @application.post("/api/meetings/{meeting_id}/steer", dependencies=protected)
    async def steer(meeting_id: str, body: Steering, service: EngineDep) -> Meeting:
        return await service.steer(meeting_id, body.role, body.guidance)

    @application.post("/api/meetings/{meeting_id}/followup", dependencies=protected)
    async def followup(meeting_id: str, service: EngineDep) -> Meeting:
        return await service.followup(meeting_id)

    @application.post("/api/meetings/{meeting_id}/concur", dependencies=protected)
    async def concur(meeting_id: str, body: Vote, service: EngineDep) -> Meeting:
        return await service.concur(meeting_id, body.role, body.comment, body.plan_version)

    @application.post("/api/meetings/{meeting_id}/object", dependencies=protected)
    async def objection(meeting_id: str, body: Vote, service: EngineDep) -> Meeting:
        return await service.object(meeting_id, body.role, body.comment, body.plan_version)

    @application.post("/api/meetings/{meeting_id}/memory", dependencies=protected)
    async def memory(meeting_id: str, body: MemoryAction, service: EngineDep) -> Meeting:
        return await service.memory(meeting_id, body.memory_id, body.action)

    @application.post("/api/meetings/{meeting_id}/cohort-reference", dependencies=protected)
    async def cohort_reference(
        meeting_id: str, body: CohortReference, service: EngineDep
    ) -> Meeting:
        """Record a cohort finding in the discussion. It never decides the meeting."""
        return await service.cohort_reference(
            meeting_id, body.criteria, body.resolved, body.reference
        )

    @application.post("/api/meetings/{meeting_id}/retry", dependencies=protected)
    async def retry(meeting_id: str, service: EngineDep) -> Meeting:
        return await service.retry(meeting_id)

    @application.get("/api/meetings/{meeting_id}/export", dependencies=protected)
    async def export(meeting_id: str, service: EngineDep) -> Response:
        result = await service.load(meeting_id)
        return Response(
            result.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="mdt-{result.id}.json"'},
        )

    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @application.get("/")
    async def index() -> Response:
        path = frontend / "index.html"
        if not path.is_file():
            return JSONResponse(
                {"detail": "Frontend is not built. Run npm ci and npm run build in frontend."}, 503
            )
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    FastAPIInstrumentor.instrument_app(
        application, excluded_urls="healthz,readyz,.*/stream", exclude_spans=["receive", "send"]
    )
    return application


configure()
app = create_app()
