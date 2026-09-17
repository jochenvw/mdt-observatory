import asyncio
import json
import time
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


def test_azure_not_silently_enabled_without_config(tmp_path: Path, monkeypatch: object) -> None:
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with TestClient(create_app(Settings(db_path=str(tmp_path / "api.db")))) as client:
        assert client.get("/api/config").json()["modes"] == ["rehearsal"]
        assert client.post("/api/meetings", json={"mode": "azure"}).status_code == 422

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