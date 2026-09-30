"""Execution-mode regressions against the built frontend and isolated HTTP fixtures."""

import copy
import json
import mimetypes
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = pytest.mark.skipif(
    os.getenv("MDT_BROWSER_TESTS") != "1",
    reason="Set MDT_BROWSER_TESTS=1 after building the frontend and installing Chromium.",
)
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
CATALOG = [{
    "id": "CASE-CURRENT", "title": "Available demonstration case",
    "patient_label": "Demo case", "stage": "For review", "question": "Review the current dossier.",
}]
EVENT_SOURCE = """
window.__streams = [];
window.EventSource = class extends EventTarget {
  constructor() {
    super();
    window.__streams.push(this);
    setTimeout(() => this.onopen?.({}), 0);
  }
  close() { this.closed = true; }
};
window.__state = value => window.__streams.filter(s => !s.closed).forEach(
  s => s.dispatchEvent(new MessageEvent('state', {data: JSON.stringify(value)}))
);
"""


def snapshot(mode, identifier="historical-meeting"):
    return {
        "id": identifier,
        "phase": "DECISION_CAPTURED",
        "mode": mode,
        "case": {"id": "CASE-OLD", "diagnosis": "Historical case"},
        "roles": {},
        "evidence": [],
        "frictions": [],
        "memories": [],
        "plan": None,
        "concurrences": {},
        "objections": [],
        "events": [],
        "round": 1,
        "busy": False,
        "error": None,
        "created_at": "2026-09-16",
        "closed_at": "2026-09-16",
    }


@pytest.mark.parametrize(
    ("chosen", "historical"),
    [("rehearsal", "azure"), ("azure", "rehearsal")],
)
def test_explicit_mode_survives_late_initial_snapshot_and_start_payload(chosen, historical):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(EVENT_SOURCE)
        delayed_latest = []
        starts = []
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_handler(route):
            path = route.request.url.split("http://mdt.test", 1)[-1].split("?", 1)[0]
            if path == "/api/config":
                return route.fulfill(
                    json={
                        "modes": ["rehearsal", "azure"], "default_mode": "azure",
                        "auth_required": False, "version": "test"
                    }
                )
            if path == "/api/meeting":
                delayed_latest.append(route)
                return None
            if path == "/api/cases":
                return route.fulfill(json=CATALOG)
            if path == "/api/meetings":
                starts.append(route.request.post_data_json)
                return route.fulfill(json=snapshot(chosen, "new-meeting"))
            if path.startswith("/api/"):
                return route.fulfill(status=405)
            asset = DIST / path.lstrip("/") if path.startswith("/assets/") else DIST / "index.html"
            return route.fulfill(
                body=asset.read_bytes(),
                content_type=mimetypes.guess_type(str(asset))[0] or "application/octet-stream",
            )

        page.route("**/*", route_handler)
        page.goto("http://mdt.test/")
        selector = page.get_by_test_id("mode-select")
        expect(selector).to_be_enabled()
        selector.select_option(chosen)
        assert len(delayed_latest) == 1
        delayed_latest[0].fulfill(json=snapshot(historical))
        expect(page.get_by_test_id("start-case")).to_be_enabled()
        expect(selector).to_have_value(chosen)
        page.wait_for_function("window.__streams.length > 0")
        update = snapshot(historical)
        update["events"] = [{"id": 1}]
        page.evaluate("value => window.__state(value)", update)
        expect(selector).to_have_value(chosen)
        page.get_by_test_id("start-case").click()
        expect(page.get_by_test_id("choose-case")).to_be_enabled()
        assert starts == [{"mode": chosen, "case_id": "CASE-CURRENT"}]
        expect(selector).to_have_value(chosen)
        assert not errors
        browser.close()


def test_active_mode_initializes_once_and_explicit_choice_survives_reconnect():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(EVENT_SOURCE)
        current = snapshot("azure")
        starts = []
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_handler(route):
            path = route.request.url.split("http://mdt.test", 1)[-1].split("?", 1)[0]
            if path == "/api/config":
                return route.fulfill(
                    json={
                        "modes": ["rehearsal", "azure"], "default_mode": "azure",
                        "auth_required": False, "version": "test"
                    }
                )
            if path == "/api/meeting" or path == "/api/meetings/historical-meeting":
                return route.fulfill(body=json.dumps(current), content_type="application/json")
            if path == "/api/cases":
                return route.fulfill(json=CATALOG)
            if path == "/api/meetings":
                starts.append(route.request.post_data_json)
                return route.fulfill(json=snapshot("rehearsal", "new-meeting"))
            if path.startswith("/api/"):
                return route.fulfill(status=405)
            asset = DIST / path.lstrip("/") if path.startswith("/assets/") else DIST / "index.html"
            return route.fulfill(
                body=asset.read_bytes(),
                content_type=mimetypes.guess_type(str(asset))[0] or "application/octet-stream",
            )

        page.route("**/*", route_handler)
        page.goto("http://mdt.test/")
        selector = page.get_by_test_id("mode-select")
        expect(selector).to_have_value("azure")
        selector.select_option("rehearsal")
        page.wait_for_function("window.__streams.length > 0")
        update = copy.deepcopy(current)
        update["events"] = [{"id": 1}]
        page.evaluate("value => window.__state(value)", update)
        expect(selector).to_have_value("rehearsal")
        page.evaluate("window.__streams.at(-1).onerror()")
        expect(page.get_by_role("button", name="Reconnect now")).to_be_visible()
        current = snapshot("azure", "another-historical-meeting")
        page.get_by_role("button", name="Reconnect now").click()
        expect(page.get_by_test_id("start-case")).to_be_enabled()
        expect(selector).to_have_value("rehearsal")
        page.get_by_test_id("start-case").click()
        expect(page.get_by_test_id("choose-case")).to_be_enabled()
        assert starts == [{"mode": "rehearsal", "case_id": "CASE-CURRENT"}]
        expect(selector).to_have_value("rehearsal")
        assert not errors
        browser.close()


def test_new_room_defaults_to_live_ai_mode():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(EVENT_SOURCE)
        starts = []

        def route_handler(route):
            path = route.request.url.split("http://mdt.test", 1)[-1].split("?", 1)[0]
            if path == "/api/config":
                return route.fulfill(json={
                    "modes": ["rehearsal", "azure"], "default_mode": "azure",
                    "auth_required": False, "version": "test",
                })
            if path == "/api/meeting":
                return route.fulfill(body="null", content_type="application/json")
            if path == "/api/cases":
                return route.fulfill(json=CATALOG)
            if path == "/api/meetings":
                starts.append(route.request.post_data_json)
                return route.fulfill(json=snapshot("azure", "new-meeting"))
            if path.startswith("/api/"):
                return route.fulfill(status=405)
            asset = DIST / path.lstrip("/") if path.startswith("/assets/") else DIST / "index.html"
            return route.fulfill(
                body=asset.read_bytes(),
                content_type=mimetypes.guess_type(str(asset))[0] or "application/octet-stream",
            )

        page.route("**/*", route_handler)
        page.goto("http://mdt.test/")
        expect(page.get_by_test_id("mode-select")).to_have_value("azure")
        expect(page.get_by_test_id("start-case")).to_be_enabled()
        page.get_by_test_id("start-case").click()
        expect(page.get_by_test_id("choose-case")).to_be_enabled()
        assert starts == [{"mode": "azure", "case_id": "CASE-CURRENT"}]
        browser.close()
