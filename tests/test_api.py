import asyncio
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mdt import agents
from mdt.app import COOKIE, cookie_value, create_app, valid_cookie
from mdt.config import Settings
from mdt.models import Position, Role
from mdt.scenario import CASE


def test_application_passes_explicit_runtime_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        db_path=str(tmp_path / "configured.db"),
        step_delay=0,
        azure_max_concurrent_roles=7,
        azure_request_interval_seconds=0.5,
    )
    observed: list[Settings] = []
    original = agents.analyze

    async def record_settings(role: Role, **kwargs: Any) -> Position:
        observed.append(kwargs["settings"])
        return await original(role, **kwargs)

    monkeypatch.setattr(agents, "analyze", record_settings)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/meetings", json={"mode": "rehearsal"}).status_code == 201
        deadline = time.monotonic() + 5
        while client.get("/api/meeting").json()["busy"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(observed) == 7
        assert all(item is settings for item in observed)


def test_complete_case_is_available_in_authenticated_snapshot_and_export(tmp_path: Path) -> None:
    settings = Settings(
        db_path=str(tmp_path / "dossier.db"), step_delay=0, presenter_token="d" * 32
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/auth", json={"token": "d" * 32}).status_code == 200
        response = client.post("/api/meetings", json={"mode": "rehearsal"})
        assert response.status_code == 201
        meeting_id = response.json()["id"]
        deadline = time.monotonic() + 10
        while client.get("/api/meeting").json()["busy"] and time.monotonic() < deadline:
            time.sleep(0.01)
        latest = client.get("/api/meeting").json()
        assert latest["phase"] == "TARGETED_DISCUSSION"
        assert latest["case"]["dossier"] == CASE["dossier"]
        assert latest["case"]["management_alternatives"] == CASE["management_alternatives"]
        exported = client.get(f"/api/meetings/{meeting_id}/export")
        assert exported.status_code == 200
        assert exported.json()["case"] == latest["case"]
        assert exported.headers["cache-control"] == "no-store"
        client.cookies.clear()
        assert client.get(f"/api/meetings/{meeting_id}/export").status_code == 401


def test_auth_health_config_and_protected_state(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "api.db"), presenter_token="x" * 32, step_delay=0)
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        assert client.get("/api/config").json()["auth_required"]
        assert client.get("/api/config").json()["disclaimer"] == (
            "DEMONSTRATION SYSTEM. NOT FOR CLINICAL USE."
        )
        assert client.get("/api/meeting").status_code == 401
        assert client.post("/api/auth", json={"token": "incorrect"}).status_code == 401
        response = client.post("/api/auth", json={"token": "x" * 32})
        assert response.status_code == 200
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        assert client.cookies[COOKIE] != "x" * 32
        assert client.get("/api/meeting").json() is None


def test_cookie_expiry_and_tamper() -> None:
    secret = "correct-secret"
    assert valid_cookie(cookie_value(secret, int(time.time())), secret)
    assert not valid_cookie(cookie_value(secret, int(time.time()) - 43201), secret)
    assert not valid_cookie(cookie_value(secret, int(time.time()) + 60), secret)
    assert not valid_cookie(cookie_value("other-secret", int(time.time())), secret)
    assert not valid_cookie("malformed", secret)
    assert not valid_cookie("9" * 100 + ".x", secret)


def test_case_catalog_is_protected_and_only_configured_cases_can_start(tmp_path: Path) -> None:
    from mdt.case_registry import case_ids, get_case

    settings = Settings(db_path=str(tmp_path / "cases.db"), presenter_token="c" * 32, step_delay=0)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/cases").status_code == 401
        assert client.post("/api/auth", json={"token": "c" * 32}).status_code == 200
        response = client.get("/api/cases")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert len(response.json()) == 3
        assert response.json() == [
            {
                "id": case["id"], "title": case["diagnosis"],
                "patient_label": case["pseudonym"],
                "stage": case["stage"], "question": case["question"],
            }
            for identifier in case_ids() for case in (get_case(identifier).case,)
        ]
        assert client.post("/api/meetings", json={"case_id": "unavailable"}).status_code == 404
        assert client.get("/api/meeting").json() is None
        started = client.post(
            "/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]}
        )
        assert started.status_code == 201
        assert started.json()["case"] == CASE
        meeting_id = started.json()["id"]
        assert client.post("/api/meetings", json={"case_id": "unavailable"}).status_code == 404
        assert client.get("/api/meeting").json()["id"] == meeting_id


def test_api_validation_and_cross_origin_rejection(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "api.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/meetings", json={"mode": "invalid"}).status_code == 422
        assert (
            client.post(
                "/api/meetings", json={}, headers={"Origin": "https://attacker.invalid"}
            ).status_code
            == 403
        )
        assert client.post("/api/meetings", content="{}").status_code == 415
        assert client.get("/api/meetings/missing").status_code == 404
        response = client.post("/api/meetings", json={"mode": "rehearsal"})
        assert response.status_code == 201
        meeting_id = response.json()["id"]
        assert (
            client.post(
                f"/api/meetings/{meeting_id}/steer", json={"role": "invented", "guidance": "x"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/meetings/{meeting_id}/concur",
                json={"role": "radiology", "comment": "Stale client without a version"},
            ).status_code
            == 422
        )
        exported = client.get(f"/api/meetings/{meeting_id}/export")
        assert exported.status_code == 200
        assert "attachment" in exported.headers["content-disposition"]
        assert exported.headers["cache-control"] == "no-store"


def test_commands_without_a_declared_length_are_refused_before_parsing(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "api.db"), step_delay=0)
    json_type = {"content-type": "application/json"}
    oversized = b'{"token":"' + b"x" * 200_000 + b'"}'

    def chunked() -> Iterator[bytes]:
        yield oversized

    with TestClient(create_app(settings)) as client:
        assert client.post("/api/auth", content=chunked(), headers=json_type).status_code == 411
        declared = {**json_type, "transfer-encoding": "chunked", "content-length": "2"}
        assert client.post("/api/auth", content=b"{}", headers=declared).status_code == 411
        assert client.post("/api/auth", content=oversized, headers=json_type).status_code == 413
        invalid = {**json_type, "content-length": "abc"}
        assert client.post("/api/auth", content=b"{}", headers=invalid).status_code == 400
        assert client.post("/api/auth", json={"token": "any"}).status_code == 200


def test_valid_token_is_never_locked_out_by_failed_attempts(tmp_path: Path) -> None:
    token = "t" * 32
    settings = Settings(db_path=str(tmp_path / "api.db"), presenter_token=token, step_delay=0)
    application = create_app(settings)
    attacker = TestClient(application, client=("203.0.113.9", 5000))
    presenter = TestClient(application, client=("198.51.100.4", 5000))
    for _ in range(10):
        assert attacker.post("/api/auth", json={"token": "wrong"}).status_code == 401
    assert attacker.post("/api/auth", json={"token": "wrong"}).status_code == 429
    assert attacker.post("/api/auth", json={"token": token}).status_code == 200
    assert presenter.post("/api/auth", json={"token": "wrong"}).status_code == 401
    assert presenter.post("/api/auth", json={"token": token}).status_code == 200


async def test_only_the_ingress_subnet_may_supply_the_client_address() -> None:
    """Trusting the ACA subnet uses the address the ingress appended, not a spoofed one."""
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    seen: list[str] = []

    async def record(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["client"][0])

    middleware = ProxyHeadersMiddleware(record, trusted_hosts="10.64.0.0/23")
    forwarded = [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.9")]
    for peer in ("10.64.1.20", "192.0.2.1"):
        scope = {"type": "http", "client": (peer, 1), "headers": forwarded, "scheme": "http"}
        await middleware(scope, None, None)  # type: ignore[arg-type]
    assert seen == ["203.0.113.9", "192.0.2.1"]


def test_azure_not_silently_enabled_without_config(tmp_path: Path, monkeypatch: object) -> None:
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with TestClient(create_app(Settings(db_path=str(tmp_path / "api.db")))) as client:
        assert client.get("/api/config").json()["modes"] == ["rehearsal"]
        assert client.post("/api/meetings", json={"mode": "azure"}).status_code == 422


def test_voice_config_maps_agents_without_exposing_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MDT_ELEVENLABS_API_KEY", "server-side-test-key")
    settings = Settings(db_path=str(tmp_path / "voice.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        voice = client.get("/api/config").json()["voice"]
        assert voice["provider"] == "elevenlabs"
        assert voice["api_key_configured"] is True
        assert "server-side-test-key" not in json.dumps(voice)
        assert voice["fallback"] == "browser_speech_synthesis"
        agents = voice["agents"]
        assert len(agents) == 8
        assert {agent["label"] for agent in agents} == {
            "MDO chair",
            "Medical oncologist",
            "Radiologist",
            "Pathologist",
            "Surgeon",
            "Radiation oncologist",
            "Specialist nurse",
            "Clinical-trial specialist",
        }
        voice_ids = [agent["elevenlabs_voice_id"] for agent in agents]
        assert len(set(voice_ids)) == len(voice_ids)
        assert all(agent["preview_text"] for agent in agents)


def test_voice_discussion_is_sequenced_and_stops_at_human_checkpoint(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "voice-flow.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        started = client.post("/api/meetings", json={"mode": "rehearsal"})
        assert started.status_code == 201
        meeting = drain(client)
        response = client.get(f"/api/meetings/{meeting['id']}/voice/discussion?mode=detailed")
        assert response.status_code == 200
        discussion = response.json()
        assert discussion["mode"] == "detailed"
        turns = discussion["turns"]
        assert turns[0]["agent_key"] == "chair"
        assert "decision question" in turns[0]["text"]
        assert "demonstration MDO rehearsal" in turns[0]["text"]
        assert "synthetic" not in turns[0]["text"].lower()
        assert [turn["sequence"] for turn in turns] == list(range(1, len(turns) + 1))
        assert len([turn for turn in turns if turn["category"] == "specialist"]) == 7
        assert turns[-1]["category"] == "checkpoint"
        assert "No agent may approve" in turns[-1]["text"]


def test_voice_contribution_is_audited_and_routed_without_decision_approval(
    tmp_path: Path,
) -> None:
    settings = Settings(db_path=str(tmp_path / "voice-contribution.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        started = client.post("/api/meetings", json={"mode": "rehearsal"})
        assert started.status_code == 201
        meeting = drain(client)
        response = client.post(
            f"/api/meetings/{meeting['id']}/voice/contributions",
            json={
                "transcript": "radiology, please reconsider the new scan",
                "corrected_transcript": "Radiologist, please reconsider the new scan.",
                "addressed_to": "radiologist",
                "confirmation_mode": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["routed_to"] == ["radiology"]
        assert payload["turns"][0]["agent_key"] == "chair"
        latest = payload["meeting"]
        event = latest["events"][-1]
        assert event["type"] == "VoiceContribution"
        assert event["payload"]["source"] == "human speech-to-text transcription"
        assert event["payload"]["decision_status"] == "not an approved clinical decision"
        assert latest["phase"] == meeting["phase"]


def test_voice_contribution_rejects_blank_confirmed_transcript(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "voice-blank.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        started = client.post("/api/meetings", json={"mode": "rehearsal"})
        assert started.status_code == 201
        meeting = drain(client)
        response = client.post(
            f"/api/meetings/{meeting['id']}/voice/contributions",
            json={
                "transcript": "   ",
                "corrected_transcript": " ",
                "addressed_to": "chair",
                "confirmation_mode": True,
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "Voice transcription cannot be empty."


def test_voice_speech_requires_server_side_key_and_never_accepts_unknown_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Guard against a real MDT_ELEVENLABS_API_KEY leaking in from the runner
    # environment; this test asserts the behaviour when no key is configured.
    monkeypatch.delenv("MDT_ELEVENLABS_API_KEY", raising=False)
    settings = Settings(db_path=str(tmp_path / "voice-speech.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        missing = client.post(
            "/api/voice/speech",
            json={"agent_key": "chair", "text": "Preview the chair voice."},
        )
        assert missing.status_code == 503
        assert "browser speech synthesis fallback" in missing.json()["detail"]
        unknown = client.post(
            "/api/voice/speech",
            json={"agent_key": "invented", "text": "Preview an unknown voice."},
        )
        assert unknown.status_code == 404

def room_view(client: TestClient) -> dict[str, Any] | None:
    """The snapshot the room channel delivers to every open participant screen."""
    service = client.app.state.engine
    payload: dict[str, Any] = json.loads(service.room_snapshot())
    assert set(payload) == {"meeting"}
    delivered: dict[str, Any] | None = payload["meeting"]
    served: dict[str, Any] | None = client.get("/api/meeting").json()
    # The room channel and the snapshot endpoint always agree on which case is open.
    assert (delivered or {}).get("id") == (served or {}).get("id")
    return delivered


def drain(client: TestClient) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while client.get("/api/meeting").json()["busy"] and time.monotonic() < deadline:
        time.sleep(0.01)
    state: dict[str, Any] = client.get("/api/meeting").json()
    return state


def test_room_channel_syncs_screens_opened_before_any_case_is_activated(tmp_path: Path) -> None:
    """A participant screen opens empty and is handed the case by the room channel."""
    settings = Settings(db_path=str(tmp_path / "room.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.engine
        # Two screens open before any case exists; both are standing by, not stale.
        screens: list[asyncio.Queue[str]] = [asyncio.Queue(maxsize=2) for _ in range(2)]
        service.room_subscribers.update(screens)
        assert room_view(client) is None

        started = client.post("/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]})
        assert started.status_code == 201
        meeting_id = started.json()["id"]

        room = room_view(client)
        assert room is not None
        assert room["id"] == meeting_id
        assert room["case"]["id"] == CASE["id"]
        assert set(room["roles"]) == {role.value for role in Role}
        # Every screen that was already open was pushed the activated case.
        for screen in screens:
            assert not screen.empty()
            assert json.loads(screen.get_nowait())["meeting"]["id"] == meeting_id


def test_room_returns_to_standby_and_the_record_stays_reviewable(tmp_path: Path) -> None:
    """Clearing wipes every screen without destroying the meeting record."""
    settings = Settings(db_path=str(tmp_path / "standby.db"), step_delay=0)
    with TestClient(create_app(settings)) as client:
        service = client.app.state.engine
        started = client.post("/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]})
        meeting_id = started.json()["id"]
        drain(client)
        screen: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
        service.room_subscribers.add(screen)

        assert client.post("/api/room/clear", json={}).json() == {"cleared": True}
        assert room_view(client) is None
        assert json.loads(screen.get_nowait())["meeting"] is None

        # The concluded meeting is retained, still readable and still exportable.
        assert client.get(f"/api/meetings/{meeting_id}").json()["id"] == meeting_id
        assert client.get(f"/api/meetings/{meeting_id}/export").status_code == 200
        # A cleared room accepts no further steering of the closed meeting.
        assert client.post(f"/api/meetings/{meeting_id}/followup", json={}).status_code == 404

        # Starting the next case repopulates every screen with a different meeting.
        nxt = client.post("/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]})
        assert nxt.status_code == 201
        room = room_view(client)
        assert room is not None
        assert room["id"] != meeting_id
        assert room["events"]
        assert all(event["meeting_id"] == room["id"] for event in room["events"])
        assert json.loads(screen.get_nowait())["meeting"]["id"] == room["id"]


def test_room_clear_is_protected_and_refused_during_an_active_round(tmp_path: Path) -> None:
    settings = Settings(db_path=str(tmp_path / "guard.db"), presenter_token="e" * 32, step_delay=0)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/room/clear", json={}).status_code == 401
        assert client.get("/api/room/stream").status_code == 401
        assert client.post("/api/auth", json={"token": "e" * 32}).status_code == 200
        client.post("/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]})
        drain(client)
        # Screens are never wiped out from under a round that is still running.
        client.app.state.engine.meeting.busy = True
        assert client.post("/api/room/clear", json={}).status_code == 409
        client.app.state.engine.meeting.busy = False
        assert client.post("/api/room/clear", json={}).status_code == 200


def test_a_cleared_room_stays_cleared_after_a_restart(tmp_path: Path) -> None:
    """A reset screen must not resurrect the previous case when the server restarts."""
    database = str(tmp_path / "restart.db")
    settings = Settings(db_path=database, step_delay=0)
    with TestClient(create_app(settings)) as client:
        meeting_id = client.post(
            "/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]}
        ).json()["id"]
        drain(client)
        assert client.post("/api/room/clear", json={}).json() == {"cleared": True}
        # Clearing is recorded on the meeting's own audit trail, in clinical language.
        events = client.get(f"/api/meetings/{meeting_id}").json()["events"]
        assert events[-1]["type"] == "RoomCleared"
        assert "review and export" in events[-1]["payload"]["summary"]

    with TestClient(create_app(Settings(db_path=database, step_delay=0))) as restarted:
        assert room_view(restarted) is None
        assert restarted.get(f"/api/meetings/{meeting_id}").json()["id"] == meeting_id
        assert restarted.get(f"/api/meetings/{meeting_id}/export").status_code == 200
        # The next case still activates normally on every screen.
        nxt = restarted.post("/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]})
        assert nxt.status_code == 201
        room = room_view(restarted)
        assert room is not None
        assert room["id"] == nxt.json()["id"] != meeting_id


def test_an_uncleared_room_still_survives_a_restart(tmp_path: Path) -> None:
    """A restart mid-demonstration must not silently empty the participants' screens."""
    database = str(tmp_path / "resume.db")
    with TestClient(create_app(Settings(db_path=database, step_delay=0))) as client:
        meeting_id = client.post(
            "/api/meetings", json={"mode": "rehearsal", "case_id": CASE["id"]}
        ).json()["id"]
        drain(client)

    with TestClient(create_app(Settings(db_path=database, step_delay=0))) as restarted:
        room = room_view(restarted)
        assert room is not None
        assert room["id"] == meeting_id

def test_readiness_is_unavailable_when_storage_fails(tmp_path: Path) -> None:
    from mdt.agents import analyze
    from mdt.engine import Engine
    from mdt.store import Store

    class Unready(Store):
        def ready(self) -> None:
            raise OSError("Simulated storage outage")

    settings = Settings(db_path=str(tmp_path / "unready.db"), step_delay=0)
    engine = Engine(Unready(settings.db_path), settings, analyze)
    with TestClient(create_app(settings, engine=engine)) as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/readyz")
        assert response.status_code == 503
        assert "Simulated" not in response.text