"""Opt-in real-browser acceptance; builds must exist before MDT_BROWSER_TESTS=1."""

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.sync_api import Locator, Page, Route, expect, sync_playwright

pytestmark = pytest.mark.skipif(
    os.getenv("MDT_BROWSER_TESTS") != "1",
    reason="Set MDT_BROWSER_TESTS=1 after building the frontend and installing Chromium.",
)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(tmp_path: Path) -> Iterator[str]:
    if external := os.getenv("MDT_BROWSER_URL"):
        assert external.startswith("https://"), "Remote browser verification requires HTTPS."
        yield external.rstrip("/")
        return
    assert (ROOT / "frontend" / "dist" / "index.html").exists(), "Build the frontend first."
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "MDT_DB_PATH": str(tmp_path / "browser.db"),
        "MDT_STEP_DELAY": "0.03",
        "MDT_PRESENTER_TOKEN": "",
    }
    env.pop("CONTAINER_APP_NAME", None)
    env.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)
    url = f"http://127.0.0.1:{port}"
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mdt.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if httpx.get(f"{url}/readyz", timeout=1).status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.1)
                if process.poll() is not None:
                    pytest.fail("Browser test server exited; inspect the fixture server.log.")
            else:
                pytest.fail("Browser test server did not become ready.")
            yield url
        finally:
            process.terminate()
            process.wait(timeout=15)


def state(page: Page) -> dict[str, Any]:
    response = page.request.get("/api/meeting")
    assert response.ok
    value: dict[str, Any] = response.json()
    return value


def wait_settled(page: Page) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        meeting = state(page)
        if not meeting["busy"]:
            assert meeting["phase"] != "ERROR", meeting["error"]
            return meeting
        page.wait_for_timeout(100)
    raise AssertionError("Browser meeting did not settle.")


def navigate(page: Page, label: str) -> None:
    if not page.get_by_role("navigation").is_visible():
        page.get_by_role("button", name="Toggle workspace navigation", exact=True).click()
    page.get_by_role("navigation").get_by_role("button", name=re.compile(label)).click()


def click_command(page: Page, control: Locator, suffix: str) -> None:
    with page.expect_response(lambda response: response.url.endswith(suffix)) as pending:
        control.click()
    response = pending.value
    assert response.ok, response.text()


@pytest.mark.parametrize(
    ("case_id", "record_text"),
    (
        ("CASE-MDT-CRC-WT-2026-002", "neuropathy"),
        ("CASE-MDT-PDAC-PERIOP-2026-003", "perioperative"),
    ),
)
def test_browser_added_case_selection_and_specialty_records(
    server: str, case_id: str, record_text: str,
) -> None:
    if os.getenv("MDT_BROWSER_URL"):
        pytest.skip("Additional-case acceptance must not replace the shared cloud room.")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            base_url=server, viewport={"width": 1920, "height": 1080}, reduced_motion="reduce",
        )
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(server)
        expect(page.get_by_role("radio")).to_have_count(3)
        page.locator(f'input[type="radio"][value="{case_id}"]').check()
        page.get_by_role("combobox").first.select_option("rehearsal")
        click_command(
            page, page.get_by_role("button", name=re.compile("^Start (new )?case$")),
            "/api/meetings",
        )
        meeting = wait_settled(page)
        assert meeting["case"]["id"] == case_id
        assert meeting["phase"] == "TARGETED_DISCUSSION"
        for theme in ("light", "dark"):
            if page.locator("html").get_attribute("data-theme") != theme:
                page.get_by_test_id("theme-toggle").click()
            for role in (
                "radiology", "oncology", "surgery", "pathology", "research", "protocol", "patient",
            ):
                page.get_by_test_id(f"view-{role}").click()
                expect(
                    page.get_by_test_id(f"role-identity-{role}")
                    .get_by_role("heading", level=1)
                ).to_be_visible()
                assert "encorafenib" not in page.locator("main").inner_text().lower()
        page.get_by_role("button", name="View case record", exact=True).first.click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        dialog.locator("details").evaluate_all(
            "(nodes) => nodes.forEach(node => { node.open = true; })"
        )
        expect(dialog.get_by_text(re.compile(record_text, re.I)).first).to_be_visible()
        if case_id.endswith("003"):
            expect(dialog).to_contain_text(re.compile(r"72\s*%"))
            expect(dialog).to_contain_text(re.compile(r"14\s*%"))
            expect(dialog).to_contain_text(re.compile(r"illustrative|fictional", re.I))
        else:
            expect(dialog).to_contain_text("0.18")
        page.keyboard.press("Escape")
        page.reload()
        page.get_by_test_id("resume-meeting").click()
        assert state(page)["id"] == meeting["id"]
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert not errors
        context.close()
        browser.close()


def test_browser_full_demo_repeatability_and_mobile(server: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            base_url=server, viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        if os.getenv("MDT_BROWSER_URL"):
            token = os.environ["MDT_PRESENTER_TOKEN"]
            response = context.request.post("/api/auth", data={"token": token})
            assert response.ok, "Remote presenter authentication failed."
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(server)
        page.get_by_role("combobox").first.select_option("rehearsal")
        start = page.get_by_role("button", name=re.compile("^Start (new )?case$"))
        expect(start).to_be_visible()
        click_command(page, start, "/api/meetings")
        assert state(page)["mode"] == "rehearsal", "Start must preserve the selected mode."
        first = wait_settled(page)
        assert first["phase"] == "TARGETED_DISCUSSION"
        expect(
            page.get_by_text("Can all nine original liver sites", exact=False).first
        ).to_be_visible()
        navigate(page, "Workspace wall")
        expect(page.get_by_text("Radiology", exact=True).first).to_be_visible()
        navigate(page, "Radiology")
        expect(page.locator("svg").first).to_be_visible()
        question = page.get_by_test_id("agent-question")
        expect(question).to_contain_text("I cannot settle this from the record alone")
        expect(question).to_contain_text("Can all nine original liver sites")
        page.locator("#guidance-radiology").fill(
            "Review all nine liver sites, vessel margins and the indeterminate lung nodule "
            "before clearance planning."
        )
        click_command(page, page.get_by_role("button", name="Send reply", exact=True), "/steer")
        after_guidance = wait_settled(page)
        assert after_guidance["roles"]["radiology"]["position"]["human_intervention"]
        navigate(page, "Chair")
        click_command(
            page, page.get_by_role("button", name="Request targeted round", exact=True), "/followup"
        )
        proposed = wait_settled(page)
        assert proposed["phase"] == "CONCURRENCE"
        navigate(page, "Research")
        page.get_by_role("button", name=re.compile("evidence", re.I)).first.click()
        expect(page.get_by_role("dialog")).to_be_visible()
        expect(
            page.get_by_role("dialog").get_by_text(re.compile("CURATED|Curated")).first
        ).to_be_visible()
        page.keyboard.press("Escape")
        navigate(page, "Chair")
        for role in proposed["roles"]:
            if role not in state(page)["concurrences"]:
                navigate(page, "Patient perspective" if role == "patient" else role.capitalize())
                expect(page.get_by_role("button", name="Concur", exact=True)).to_be_in_viewport()
                click_command(
                    page, page.get_by_role("button", name="Concur", exact=True), "/concur"
                )
        final = state(page)
        assert final["phase"] == "DECISION_CAPTURED"
        navigate(page, "Central MDT")
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        prefix = "cloud" if os.getenv("MDT_BROWSER_URL") else "browser"
        page.screenshot(path=str(artifacts / f"{prefix}-decision-desktop.png"), full_page=True)
        page.reload()
        expect(page.get_by_text("Decision captured", exact=False).first).to_be_visible()
        assert state(page)["id"] == first["id"]
        page.get_by_test_id("resume-meeting").click()
        assert state(page)["id"] == first["id"]
        navigate(page, "Chair")
        page.get_by_test_id("choose-case").click()
        click_command(
            page,
            page.get_by_test_id("start-case"),
            "/api/meetings",
        )
        next_meeting = wait_settled(page)
        assert next_meeting["id"] != first["id"]
        assert page.request.get(f"/api/meetings/{first['id']}").json()["closed_at"]
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (
            "Mobile page has horizontal overflow"
        )
        page.screenshot(path=str(artifacts / f"{prefix}-mobile.png"), full_page=True)
        assert not errors, errors
        context.close()
        browser.close()


def test_specialty_layouts_themes_and_clinical_presentation(server: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            base_url=server,
            viewport={"width": 1440, "height": 1000},
            reduced_motion="reduce",
            color_scheme="light",
        )
        if os.getenv("MDT_BROWSER_URL"):
            response = context.request.post(
                "/api/auth", data={"token": os.environ["MDT_PRESENTER_TOKEN"]}
            )
            assert response.ok
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(server)
        page.get_by_role("combobox").first.select_option("rehearsal")
        click_command(
            page,
            page.get_by_role("button", name=re.compile("^Start (new )?case$")),
            "/api/meetings",
        )
        assert state(page)["mode"] == "rehearsal", "Start must preserve the selected mode."
        snapshot = wait_settled(page)
        assert snapshot["case"]["dossier"]["patient"]["age"] == 59
        assert len(snapshot["case"]["management_alternatives"]) == 3
        assert len(snapshot["case"]["specialty_contributions"]) == 8
        page.get_by_role("button", name=re.compile("View case record")).first.click()
        dossier_view = page.get_by_test_id("case-dossier")
        expect(dossier_view).to_be_visible()
        dossier_text = dossier_view.text_content() or ""
        for supplied_value in (
            "losartan",
            "48 mmol/mol",
            "UGT1A1",
            "*1/*28",
            "0.42",
            "2026-06-11",
            "2026-09-08",
            "300 mg",
            "500 mg/m2",
        ):
            assert supplied_value in dossier_text, f"Missing dossier value: {supplied_value}"
        assert not re.search(r"synthetic|syntetic|SYN-", dossier_text, re.I)
        page.keyboard.press("Escape")
        timestamp = snapshot["events"][-1]["timestamp"]
        metadata = {
            "summary": "Azure model internal-deployment-browser completed tool selection.",
            "deployment": "internal-deployment-browser",
            "model_request_id": "req-browser-internal-123",
            "request_id": "req-browser-internal-123",
            "token_usage": {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
        }
        for role, specialist in snapshot["roles"].items():
            technical = (
                "ACTUAL AZURE CALL: deployment=internal-deployment-browser; "
                "request_id=req-browser-internal-123; input_tokens=100."
            )
            specialist["trace"]["observations"].append(technical)
            specialist["position"]["trace"]["observations"].append(technical)
            specialist["trace"]["next_action"] = "Pacing Azure requests; waiting 20 seconds."
            specialist["activity"].append(
                {"type": "ObservationAdded", "timestamp": timestamp, **metadata}
            )
            snapshot["events"].append(
                {
                    "id": snapshot["events"][-1]["id"] + 1,
                    "meeting_id": snapshot["id"],
                    "timestamp": timestamp,
                    "type": "ObservationAdded",
                    "role": role,
                    "payload": metadata,
                }
            )

        # Project genuine event/trace shapes without altering the durable meeting.
        page.route("**/api/meeting", lambda route: route.fulfill(json=snapshot))

        def stream_snapshot(route: Route) -> None:
            route.fulfill(
                content_type="text/event-stream",
                body=f'event: room\ndata: {json.dumps({"meeting": snapshot})}\n\n',
            )

        page.route("**/api/room/stream", stream_snapshot)
        page.add_init_script("""
            window.EventSource = class extends EventTarget {
                constructor() {
                    super(); window.__reviewStream = this;
                    setTimeout(() => this.onopen?.({}), 0);
                }
                close() {}
            };
        """)
        page.reload()
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        prefix = "cloud" if os.getenv("MDT_BROWSER_URL") else "browser"
        technical_text = re.compile(
            r"ACTUAL AZURE CALL|Azure model|input_tokens|request_id|internal-deployment-browser"
            r"|req-browser-internal|Pacing Azure|ToolStarted|ToolCompleted|ObservationAdded"
            r"|compare_imaging|inspect_pathology|inspect_curated_study|RateLimitError"
            r"|PROTOCOL_NOT_PUBLIC"
            r"|synthetic|syntetic",
            re.I,
        )
        headings: dict[str, tuple[str, ...]] = {}
        backgrounds: dict[str, str] = {}
        role_surfaces: dict[tuple[str, str], str] = {}
        role_identities: dict[tuple[str, str], str] = {}
        for theme in ("light", "dark"):
            if page.locator("html").get_attribute("data-theme") != theme:
                page.get_by_role("button", name=f"Switch to {theme} mode", exact=True).click()
            expect(page.locator("html")).to_have_attribute("data-theme", theme)
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-theme", theme)
            backgrounds[theme] = page.evaluate("getComputedStyle(document.body).backgroundColor")
            for role in snapshot["roles"]:
                page.set_viewport_size({"width": 1440, "height": 900})
                page.evaluate("window.scrollTo(0, 700)")
                navigate(page, "Patient perspective" if role == "patient" else role.capitalize())
                workspace = page.get_by_test_id(f"workspace-{role}")
                expect(workspace).to_be_visible()
                page.wait_for_function("window.scrollY === 0")
                expect(page.locator("main")).to_have_attribute("data-specialty", role)
                identity = page.get_by_test_id(f"role-identity-{role}")
                expect(identity.get_by_role("heading", level=1)).to_be_in_viewport()
                expect(page.get_by_test_id("specialty-case-summary")).to_be_visible()
                expect(page.get_by_test_id(f"view-{role}")).to_have_attribute(
                    "aria-current", "page"
                )
                desk = page.get_by_test_id("activity-desk")
                desk_box = desk.bounding_box()
                rail_box = page.get_by_test_id("case-rail").bounding_box()
                assert desk_box and desk_box["y"] < 530, f"{role}/{theme}: activity starts too low"
                assert rail_box and rail_box["x"] > desk_box["x"] + desk_box["width"]
                expect(page.get_by_test_id("send-guidance")).to_be_in_viewport()
                expect(page.get_by_test_id("role-attention")).to_be_in_viewport()
                expect(page.get_by_test_id("view-case-record")).to_be_in_viewport()
                ids = workspace.locator("[data-activity-id]").evaluate_all(
                    "nodes => nodes.map(node => Number(node.dataset.activityId))"
                )
                assert ids == sorted(ids, reverse=True)
                assert workspace.locator(".clinical-update").first.evaluate(
                    "node => getComputedStyle(node).animationName"
                ) == "none"
                role_surfaces[theme, role] = page.locator("main").evaluate(
                    "node => getComputedStyle(node).backgroundColor"
                )
                role_identities[theme, role] = identity.evaluate(
                    """node => {
                        const style = getComputedStyle(node);
                        const title = getComputedStyle(node.querySelector('h1'));
                        return JSON.stringify([
                            style.backgroundColor, style.borderTopWidth,
                            style.borderLeftWidth, style.borderBottomStyle,
                            style.borderTopLeftRadius, title.fontFamily, title.textAlign
                        ]);
                    }"""
                )
                headings[role] = tuple(workspace.get_by_role("heading").all_text_contents())
                assert len(headings[role]) >= 2
                page.screenshot(path=str(artifacts / f"{prefix}-{role}-{theme}.png"))
                source_toggle = workspace.locator("summary").filter(
                    has_text=re.compile(r"Open .* clinical workspace and source records")
                )
                source_toggle.click()
                clinical = page.get_by_test_id(f"clinical-{role}").inner_text()
                if role == "oncology":
                    assert "encorafenib" in clinical.lower()
                    assert "cetuximab" in clinical.lower()
                    assert "neuropathy" in clinical.lower()
                if role == "surgery":
                    assert "23" in clinical and "65" in clinical
                if role == "pathology":
                    assert all(label in clinical for label in ("BRAF", "APC", "TP53", "SMAD4"))
                if role in ("oncology", "surgery", "protocol", "patient"):
                    assert "Not specified in the available case record" not in clinical
                if role == "protocol":
                    assert "perioperative" in clinical.lower()
                source_toggle.click()
                page.evaluate("window.scrollTo(0, 0)")
                assert not technical_text.search(page.locator("body").text_content() or "")
                page.set_viewport_size({"width": 390, "height": 844})
                expect(identity.get_by_role("heading", level=1)).to_be_in_viewport()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 1"
                ), f"{role}/{theme} overflows on mobile"
            for label in ("Central MDT", "Chair", "Workspace wall"):
                navigate(page, label)
                assert not technical_text.search(page.locator("body").text_content() or "")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 1"
                ), f"{label}/{theme} overflows on mobile"
            assert len({role_surfaces[theme, role] for role in snapshot["roles"]}) == 7
            assert len({role_identities[theme, role] for role in snapshot["roles"]}) == 7
        assert backgrounds["light"] != backgrounds["dark"]
        assert len(set(headings.values())) == 7, "Specialty sections must be distinct."
        page.set_viewport_size({"width": 1440, "height": 900})
        navigate(page, "Radiology")
        page.get_by_test_id("guidance-input").fill("Keep this clinician draft during updates.")
        page.emulate_media(reduced_motion="no-preference")
        assert page.locator(".clinical-update").first.evaluate(
            "node => getComputedStyle(node).animationDuration"
        ) == "0.9s"
        page.evaluate("""
            window.__previousEntry = document.querySelector('[data-activity-id]');
            window.__previousScroll = window.scrollY;
        """)
        update_id = snapshot["events"][-1]["id"] + 1
        snapshot["events"].append({
            "id": update_id, "meeting_id": snapshot["id"], "timestamp": timestamp,
            "type": "ObservationAdded", "role": "radiology",
            "payload": {
                "summary": "A clinician requested another review of the recorded measurements."
            },
        })
        page.evaluate("""value => window.__reviewStream.dispatchEvent(
            new MessageEvent('room', {data: JSON.stringify({meeting: value})}))""", snapshot)
        expect(page.locator("[data-activity-id]").first).to_have_attribute(
            "data-activity-id", str(update_id)
        )
        expect(page.get_by_test_id("guidance-input")).to_have_value(
            "Keep this clinician draft during updates."
        )
        assert page.evaluate("""
            window.__previousEntry.isConnected && window.scrollY === window.__previousScroll
                && document.querySelector('.activity-stream').scrollTop === 0
        """)
        page.emulate_media(reduced_motion="reduce")
        page.goto(server + "?scoutTheme=light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.goto(server + "?scoutTheme=invalid")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.goto(server)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_test_id("theme-system").click()
        page.emulate_media(color_scheme="light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.get_by_test_id("theme-toggle").focus()
        page.keyboard.press("Enter")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        snapshot["phase"] = "ERROR"
        snapshot["error"] = (
            "Specialist analysis failed: RateLimitError; request_id=req-browser-internal-123."
        )
        snapshot["roles"]["radiology"]["error"] = snapshot["error"]
        snapshot["roles"]["radiology"]["status"] = "ERROR"
        page.reload()
        navigate(page, "Radiology")
        expect(page.get_by_role("alert").first).to_be_visible()
        assert not technical_text.search(page.locator("body").text_content() or "")
        expect(page.get_by_role("alert").first).to_contain_text(
            "No new conclusion has been recorded"
        )
        timeout = "Specialist analysis failed: APITimeoutError; no rehearsal fallback."
        snapshot["error"] = None
        snapshot["roles"]["oncology"]["status"] = "ERROR"
        snapshot["roles"]["oncology"]["error"] = None
        snapshot["roles"]["oncology"]["trace"]["next_action"] = timeout
        page.reload()
        navigate(page, "Oncology")
        expect(page.get_by_test_id("role-attention")).to_contain_text("did not respond in time")
        page.get_by_role("button", name="Full assessment").click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_role("alert")).to_contain_text("No new conclusion")
        expect(dialog.locator(".next-action")).to_have_count(0)
        assert "APITimeoutError" not in (page.locator("body").text_content() or "")
        assert "no rehearsal fallback" not in (page.locator("body").text_content() or "")
        assert snapshot["roles"]["oncology"]["trace"]["next_action"] == timeout
        page.screenshot(path=str(artifacts / f"{prefix}-timeout-review.png"))
        assert not errors, errors
        context.close()
        browser.close()


PARTICIPANT_ROLES = (
    "Radiology",
    "Oncology",
    "Surgery",
    "Pathology",
    "Research",
    "Patient perspective",
)
ROLE_KEYS = ("radiology", "oncology", "surgery", "pathology", "research", "patient")


def test_participant_screens_follow_the_orchestrator_across_cases(server: str) -> None:
    """Six participant screens plus the orchestrator share one live room.

    Each participant opens the app in its own browser session, picks a specialty and
    waits. The orchestrator activates a case and every screen populates with that
    specialty's own reasoning. Returning the room to standby wipes them all, and the
    next case repopulates them from scratch with no trace of the previous meeting.
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        errors: list[str] = []

        def open_screen() -> Page:
            context = browser.new_context(
                base_url=server,
                viewport={"width": 1440, "height": 1000},
                reduced_motion="reduce",
            )
            if os.getenv("MDT_BROWSER_URL"):
                token = os.environ["MDT_PRESENTER_TOKEN"]
                assert context.request.post("/api/auth", data={"token": token}).ok
            screen = context.new_page()
            screen.on("pageerror", lambda error: errors.append(str(error)))
            screen.goto(server)
            return screen

        orchestrator = open_screen()
        participants = [open_screen() for _ in PARTICIPANT_ROLES]

        # 1. Every participant picks a specialty before any case exists.
        for screen, label, key in zip(participants, PARTICIPANT_ROLES, ROLE_KEYS, strict=True):
            navigate(screen, label)
            standby = screen.get_by_test_id(f"standby-{key}")
            expect(standby).to_be_visible()
            expect(standby).to_contain_text("Waiting for the orchestrator to open a case")
            assert screen.get_by_test_id(f"workspace-{key}").count() == 0
            # A waiting screen shows no patient record at all.
            assert "CRC-2026-001" not in (screen.locator("main").text_content() or "")

        def populated(screen: Page, key: str) -> None:
            expect(screen.get_by_test_id(f"workspace-{key}")).to_be_visible(timeout=30_000)
            expect(screen.get_by_test_id(f"standby-{key}")).to_have_count(0)

        # 2. The orchestrator activates a case; no participant reloads anything.
        orchestrator.get_by_role("combobox").first.select_option("rehearsal")
        click_command(
            orchestrator,
            orchestrator.get_by_role("button", name=re.compile("^Start (new )?case$")),
            "/api/meetings",
        )
        first = wait_settled(orchestrator)

        for screen, key in zip(participants, ROLE_KEYS, strict=True):
            populated(screen, key)
            # Each screen shows its own specialty's reasoning, not a shared script.
            steps = screen.get_by_test_id("reasoning-steps")
            expect(steps).to_be_visible()
            expect(steps).to_contain_text("HOW THIS SPECIALTY REACHED ITS POSITION")
            assert screen.locator("main").get_attribute("data-specialty") == key

        traces = {
            key: screen.get_by_test_id("reasoning-steps").text_content() or ""
            for screen, key in zip(participants, ROLE_KEYS, strict=True)
        }
        assert len(set(traces.values())) == len(ROLE_KEYS), "Specialties must reason distinctly."

        # 3. The orchestrator returns the room to standby; every screen clears.
        navigate(orchestrator, "Chair")
        click_command(
            orchestrator,
            orchestrator.get_by_test_id("clear-room"),
            "/api/room/clear",
        )
        for screen, key in zip(participants, ROLE_KEYS, strict=True):
            expect(screen.get_by_test_id(f"standby-{key}")).to_be_visible(timeout=30_000)
            expect(screen.get_by_test_id(f"workspace-{key}")).to_have_count(0)
            assert first["case"]["pseudonym"] not in (screen.locator("main").text_content() or "")

        # The cleared meeting is still on record for review and export.
        export = orchestrator.request.get(f"/api/meetings/{first['id']}/export")
        assert export.ok

        # 4. The next case repopulates every screen with a fresh reasoning chain.
        navigate(orchestrator, "Case selection")
        orchestrator.locator('input[type="radio"][value="CASE-MDT-PDAC-PERIOP-2026-003"]').check()
        click_command(
            orchestrator,
            orchestrator.get_by_role("button", name=re.compile("^Start (new )?case$")),
            "/api/meetings",
        )
        second = wait_settled(orchestrator)
        assert second["id"] != first["id"]

        for screen, key in zip(participants, ROLE_KEYS, strict=True):
            populated(screen, key)
            body = screen.locator("main").text_content() or ""
            assert first["case"]["pseudonym"] not in body, "Previous case must not linger."
            assert second["case"]["pseudonym"] in body
            expect(screen.get_by_test_id("reasoning-steps")).to_be_visible()

        # 5. The same reset is available on the case-selection screen, so the
        #    orchestrator can empty the room from where the next case is chosen.
        navigate(orchestrator, "Case selection")
        expect(orchestrator.get_by_test_id("clear-room")).to_be_enabled(timeout=30_000)
        click_command(
            orchestrator,
            orchestrator.get_by_test_id("clear-room"),
            "/api/room/clear",
        )
        for screen, key in zip(participants, ROLE_KEYS, strict=True):
            expect(screen.get_by_test_id(f"standby-{key}")).to_be_visible(timeout=30_000)
            assert second["case"]["pseudonym"] not in (screen.locator("main").text_content() or "")
        expect(orchestrator.get_by_test_id("clear-room")).to_have_count(0)
        assert orchestrator.request.get(f"/api/meetings/{second['id']}/export").ok

        assert not errors, errors
        browser.close()