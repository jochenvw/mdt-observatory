"""Browser checks against an isolated API fixture; no application server is started.

Run after npm run build: python tests\\browser_smoke.py
Requires an existing Playwright Python installation and Chromium.
"""

import copy
import json
import mimetypes
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ROLES = ["radiology", "oncology", "surgery", "pathology", "research", "protocol", "patient"]
NOW = "2026-09-16T13:00:00Z"
TRACE = {
    "assessment": "Interval growth warrants focused review, not an automatic treatment change.",
    "observations": [
        "Target region increased from 17 to 23 mm in the synthetic case record.",
        "ACTUAL AZURE CALL deployment=fixture request_id=req_fixture total_tokens=888",
    ],
    "hypothesis": "Growth kinetics may matter more than a single borderline measurement.",
    "uncertainties": ["Tissue confirmation remains necessary."],
    "evidence_checking": ["Curated European guidance"],
    "next_action": "Compare the prior study and escalate the unresolved interpretation.",
}
CONTEXTS = {
    "radiology": {
        "measurements": [
            {"label": "Baseline", "diameter_mm": 14, "weeks_ago": 26},
            {"label": "Previous", "diameter_mm": 17, "weeks_ago": 11},
            {"label": "Current", "diameter_mm": 23, "weeks_ago": 0},
        ],
        "reports": [{"date": NOW, "finding": "Synthetic focal interval change"}],
    },
    "oncology": {
        "treatment_history": ["Prior systemic therapy"],
        "toxicity": "Previous grade 3 toxicity",
        "biomarkers": {"marker": "Recorded"},
    },
    "surgery": {
        "operability": "Conditional on tissue confirmation",
        "patient_fitness": "Review needed",
    },
    "pathology": {
        "specimen": "Prior resection",
        "molecular_findings": {"marker": "Recorded"},
        "new_biopsy": "Not yet obtained",
    },
    "research": {"clinical_question": "What evidence applies?", "sources_to_review": ["NL", "EU"]},
    "protocol": {"dutch_guideline": "Curated guidance", "protocol_access": "PROTOCOL_NOT_PUBLIC"},
    "patient": {
        "stated_preferences": ["Preserve independence", "Avoid severe toxicity"],
        "support": "Lives alone",
    },
}


def fixture():
    roles = {}
    for role in ROLES:
        roles[role] = {
            "role": role,
            "label": role.title(),
            "status": "PUBLISHED",
            "context": CONTEXTS[role],
            "trace": copy.deepcopy(TRACE),
            "activity": [
                {
                    "type": "ToolResult",
                    "timestamp": NOW,
                    "summary": "Inspected role-scoped context",
                    "tool": f"get_{role}_context",
                }
            ],
            "guidance": [],
            "revision": 1,
            "error": None,
            "position": {
                "role": role,
                "case_id": "demo-case",
                "position": "A conditional strategy pending targeted review.",
                "confidence": 0.72,
                "autonomy": "REVIEW",
                "claims": [
                    {
                        "claim": "Prior toxicity limits acceptable treatment burden.",
                        "evidence_ids": ["source-1"],
                    }
                ],
                "uncertainties": ["Confirmation required"],
                "recommendation": "Discuss the remaining friction.",
                "questions_for_mdt": ["What evidence would change the recommendation?"],
                "human_intervention": False,
                "provenance": ["Curated synthetic case"],
                "stance": "CONDITIONAL",
                "friction_keys": ["f-1"],
                "trace": copy.deepcopy(TRACE),
            },
        }
    return {
        "id": "browser-demo",
        "phase": "FRICTION_ANALYSIS",
        "mode": "rehearsal",
        "case": {
            "pseudonym": "DEMO-042",
            "age": 72,
            "diagnosis": "Non-small cell lung cancer",
            "stage": "Recurrent disease under review",
            "clinical_question": (
                "Does interval growth justify a change of strategy when prior toxicity "
                "and patient priorities pull in another direction?"
            ),
            "history": ["Prior systemic therapy", "Recorded toxicity"],
            "biomarkers": {"status": "In case record"},
            "treatment": "Previous therapy paused for toxicity",
        },
        "roles": roles,
        "evidence": [
            {
                "id": "source-1",
                "title": "Curated European evidence example",
                "url": "https://example.org/evidence",
                "date": "2026-01-01",
                "authority": "Demonstration evidence service",
                "region": "EU",
                "kind": "GUIDELINE",
                "access": "PUBLIC_ABSTRACT_ONLY",
                "patient_match": "PARTIAL",
                "passage": "Example supporting passage for UI verification only.",
                "limitations": ["Not a real clinical source"],
                "scrutiny": {"population": "Partial match", "protocol": "Not publicly available"},
                "synthetic": True,
                "retrieval": "CURATED",
            }
        ],
        "frictions": [
            {
                "id": "f-1",
                "question": "Is growth enough to change treatment?",
                "roles": ["radiology", "oncology", "research"],
                "missing": ["Growth kinetics review", "Patient applicability of evidence"],
                "blocking": True,
                "resolved": False,
                "resolution": None,
            }
        ],
        "memories": [
            {
                "id": "m-1",
                "role": "radiology",
                "clinician_id": "presenter",
                "category": "CLINICIAN_PREFERENCE",
                "text": "Consider growth kinetics in borderline lesions.",
                "source": "Synthetic clinician note",
                "date": NOW,
                "status": "AVAILABLE",
            }
        ],
        "plan": None,
        "concurrences": {},
        "objections": [],
        "events": [
            {
                "id": 1,
                "meeting_id": "browser-demo",
                "type": "FrictionDetected",
                "role": None,
                "payload": {"summary": "Focused review requested"},
                "timestamp": NOW,
            }
        ],
        "round": 1,
        "busy": False,
        "error": None,
        "created_at": NOW,
        "closed_at": None,
    }


EVENT_SOURCE = """
window.__streams = [];
window.EventSource = class extends EventTarget {
  constructor(url) {
    super();
    this.url = url;
    window.__streams.push(this);
    setTimeout(() => this.onopen?.({}), 10);
  }
  close() { this.closed = true; }
};
window.__state = value => window.__streams.filter(s => !s.closed).forEach(
  s => s.dispatchEvent(new MessageEvent('state', {data: JSON.stringify(value)}))
);
"""


def run():
    current = None
    fail_steer = True
    auth_required = False
    authenticated = False
    errors = []
    calls = []
    artifacts = ROOT / "tests" / "artifacts"
    artifacts.mkdir(exist_ok=True)

    def route_handler(route):
        nonlocal current, fail_steer, authenticated
        path = route.request.url.split("http://mdt.test", 1)[-1].split("?", 1)[0]
        method = route.request.method
        if path.startswith("/api/"):
            calls.append((method, path))
            body = route.request.post_data_json if method == "POST" else {}
            if path == "/api/config":
                return route.fulfill(
                    json={
                        "modes": ["rehearsal", "azure"],
                        "default_mode": "azure",
                        "auth_required": auth_required,
                        "version": "test",
                    }
                )
            if path == "/api/auth":
                if body["token"] != "browser-fixture":
                    return route.fulfill(status=401, json={"detail": "Invalid presenter secret"})
                authenticated = True
                return route.fulfill(status=204)
            if auth_required and not authenticated:
                return route.fulfill(status=401, json={"detail": "Presenter access required"})
            if path == "/api/meeting":
                return route.fulfill(body=json.dumps(current), content_type="application/json")
            if path == "/api/meetings":
                current = fixture()
                current["mode"] = body["mode"]
                return route.fulfill(json=current)
            if path.endswith("/export"):
                return route.fulfill(
                    body=json.dumps(current),
                    content_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=meeting.json"},
                )
            if path.endswith(("/concur", "/object")):
                if body.get("plan_version") != current["plan"]["version"]:
                    return route.fulfill(
                        status=409,
                        json={"detail": "Review the current plan version before voting."},
                    )
            if path.endswith("/steer"):
                if fail_steer:
                    fail_steer = False
                    return route.fulfill(
                        status=409, json={"detail": "The team is busy. Please retry your guidance."}
                    )
                state = current["roles"][body["role"]]
                state["guidance"].append(body["guidance"])
                state["revision"] += 1
                state["position"]["human_intervention"] = True
                state["trace"]["assessment"] = (
                    "Updated after human guidance: distinguish concerning growth "
                    "from confirmed progression."
                )
            elif path.endswith("/memory"):
                status = {"use": "USED", "ignore": "IGNORED", "forget": "FORGOTTEN"}[body["action"]]
                current["memories"][0]["status"] = status
            elif path.endswith("/followup"):
                current["phase"] = "CONCURRENCE"
                current["round"] = 2
                current["frictions"][0].update(
                    resolved=True,
                    resolution=(
                        "Review confirmed a conditional plan with explicit diagnostic safeguards."
                    ),
                )
                current["plan"] = {
                    "version": 1,
                    "title": "A conditional, patient-centred strategy",
                    "summary": (
                        "Confirm the finding before changing treatment; "
                        "preserve patient priorities."
                    ),
                    "actions": [
                        "Targeted diagnostic confirmation",
                        "Review tolerability and discuss preferences",
                        "Return to MDT after results",
                    ],
                    "conditions": ["No treatment decision without clinical review"],
                    "evidence_ids": ["source-1"],
                    "created_at": NOW,
                }
            elif path.endswith("/concur"):
                current["concurrences"][body["role"]] = {
                    "role": body["role"],
                    "plan_version": body["plan_version"],
                    "actor": "human",
                    "comment": body["comment"],
                    "timestamp": NOW,
                }
                if len(current["concurrences"]) == 7:
                    current["phase"] = "DECISION_CAPTURED"
                    current["closed_at"] = NOW
            elif path.endswith("/object"):
                current["objections"].append(body)
                current["phase"] = "TARGETED_DISCUSSION"
            elif method != "GET":
                raise AssertionError(f"Unexpected mutation {path}")
            if method == "POST":
                current["events"].append(
                    {
                        "id": len(current["events"]) + 1,
                        "meeting_id": current["id"],
                        "type": "PositionUpdated",
                        "role": None,
                        "payload": {"summary": path.rsplit("/", 1)[-1]},
                        "timestamp": NOW,
                    }
                )
            return route.fulfill(json=current)
        target = ROOT / "dist" / (path.lstrip("/") if path != "/" else "index.html")
        if target.is_file():
            return route.fulfill(
                body=target.read_bytes(),
                content_type=mimetypes.guess_type(target)[0] or "application/octet-stream",
            )
        return route.fulfill(status=404, body="Not found")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        context.route("http://mdt.test/**", route_handler)
        context.add_init_script(EVENT_SOURCE)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://mdt.test/?scoutTheme=light")
        expect(page.get_by_test_id("start-case")).to_be_enabled()
        expect(page.get_by_test_id("mode-select")).to_be_visible()
        for name in ["central", "chair", "wall", *ROLES]:
            expect(page.get_by_test_id(f"view-{name}")).to_be_visible()
        page.screenshot(path=str(artifacts / "welcome-desktop.png"), full_page=True)

        def no_overflow():
            offenders = page.evaluate("""() => [...document.querySelectorAll('main *')]
              .filter(el => {
                let parent = el.parentElement;
                while (parent && parent.tagName !== 'MAIN') {
                  const overflow = getComputedStyle(parent).overflowX;
                  if (['auto', 'hidden', 'scroll'].includes(overflow)) return false;
                  parent = parent.parentElement;
                }
                return el.getBoundingClientRect().right > innerWidth + 1
                  && getComputedStyle(el).position !== 'absolute';
              })
              .slice(0, 12).map(el => ({
                tag: el.tagName,
                class: el.className,
                right: el.getBoundingClientRect().right,
                text: el.textContent.slice(0, 80)
              }))""")
            if not page.evaluate("document.documentElement.scrollWidth <= innerWidth"):
                page.screenshot(path=str(artifacts / "overflow.png"), full_page=True)
                sizes = page.evaluate(
                    """() => ({
                      width: innerWidth,
                      document: document.documentElement.scrollWidth,
                      boxes: [...document.querySelectorAll(
                        'main, .specialist-grid, .specialist-grid > .stack > .panel, .table-scroll'
                      )].map(e => [
                        e.className, e.clientWidth, e.scrollWidth, e.getBoundingClientRect().right
                      ])
                    })"""
                )
                raise AssertionError(
                    f"Horizontal page overflow in {page.locator('.breadcrumb').inner_text()}: "
                    f"{offenders}; {sizes}"
                )

        no_overflow()
        page.set_viewport_size({"width": 375, "height": 812})
        no_overflow()
        page.screenshot(path=str(artifacts / "welcome-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_test_id("start-case").click()
        expect(page.get_by_role("heading", name="Specialists at work")).to_be_visible()
        expect(page.get_by_test_id("phase")).to_have_attribute("data-phase", "FRICTION_ANALYSIS")
        expect(page.get_by_test_id("phase")).to_contain_text("MEETING PROGRESS")
        expect(page.get_by_test_id("phase")).to_contain_text("Review meeting stages")
        expect(page.get_by_test_id("mode-select")).to_contain_text("Scripted demonstration")
        expect(page.get_by_test_id("mode-select")).to_contain_text("Live AI review")
        expect(
            page.locator(".role-grid").get_by_text("Position published", exact=True)
        ).to_have_count(7)
        current["busy"] = True
        page.evaluate("value => window.__state(value)", current)
        expect(page.get_by_test_id("start-case")).to_be_disabled()
        expect(page.get_by_test_id("mode-select")).to_be_disabled()
        current["busy"] = False
        page.evaluate("value => window.__state(value)", current)
        expect(page.get_by_test_id("start-case")).to_be_enabled()
        expect(page.locator(".case-context-summary")).to_contain_text(
            "Previous therapy paused for toxicity"
        )
        page.screenshot(path=str(artifacts / "central-desktop.png"), full_page=True)

        page.get_by_test_id("view-radiology").click()
        expect(page.locator(".lesion-history")).to_contain_text("14 mm")
        expect(page.locator(".lesion-history")).to_contain_text("17 mm")
        expect(page.locator(".lesion-history")).to_contain_text("23 mm")
        guidance = page.get_by_test_id("guidance-input")
        guidance.fill("Preserve this typed guidance across live snapshots.")
        guidance.focus()
        current["events"].append(
            {
                "id": 2,
                "meeting_id": "browser-demo",
                "type": "ObservationAdded",
                "role": "radiology",
                "payload": {"summary": "New observation"},
                "timestamp": NOW,
            }
        )
        page.evaluate("value => window.__state(value)", current)
        expect(guidance).to_have_value("Preserve this typed guidance across live snapshots.")
        expect(guidance).to_be_focused()
        page.get_by_test_id("send-guidance").click()
        expect(page.get_by_role("alert")).to_contain_text("The team is busy")
        expect(guidance).to_have_value("Preserve this typed guidance across live snapshots.")
        page.get_by_test_id("send-guidance").click()
        expect(guidance).to_have_value("")
        expect(page.get_by_text("Human guidance received", exact=True)).to_be_visible()
        page.get_by_role("button", name="Inspect", exact=True).click()
        expect(page.get_by_role("dialog", name="Memory provenance")).to_contain_text(
            "Synthetic clinician note"
        )
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Use", exact=True).click()
        expect(page.locator(".memory-card")).to_contain_text("Used")
        page.get_by_role("button", name="Ignore", exact=True).click()
        expect(page.locator(".memory-card")).to_contain_text("Ignored")
        page.get_by_role("button", name="Forget", exact=True).click()
        expect(page.locator(".memory-card")).to_contain_text("This memory has been forgotten")
        page.locator(".claim-list > button").first.click()
        expect(page.get_by_test_id("source-drawer")).to_contain_text(
            "Full text has not been retrieved."
        )
        link = page.get_by_role("link", name="Open original source")
        expect(link).to_have_attribute("rel", "noopener noreferrer")
        page.keyboard.press("Escape")
        page.screenshot(path=str(artifacts / "radiology-desktop.png"), full_page=True)

        for role in ROLES:
            page.locator("nav .nav-item").nth(ROLES.index(role) + 3).click()
            expect(page.locator(".workspace-heading")).to_be_visible()
            expect(page.get_by_test_id(f"role-layout-{role}")).to_be_visible()
            expect(page.get_by_test_id(f"workspace-{role}")).to_be_visible()
            expect(page.get_by_test_id(f"clinical-{role}")).to_be_visible()
            expect(page.locator("body")).not_to_contain_text("req_fixture")
            page.screenshot(path=str(artifacts / f"{role}-light-desktop.png"), full_page=True)
            page.get_by_test_id("theme-toggle").click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.screenshot(path=str(artifacts / f"{role}-dark-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 375, "height": 812})
            no_overflow()
            page.get_by_test_id("theme-toggle").click()
            expect(page.locator("html")).to_have_attribute("data-theme", "light")
            no_overflow()
            if role == "radiology":
                page.screenshot(path=str(artifacts / "radiology-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
        navigation_names = [
            "Central MDT",
            "Chair / orchestrator",
            "Workspace wall",
            "Radiology",
            "Oncology",
            "Surgery",
            "Pathology",
            "Research",
            "Protocol",
            "Patient perspective",
            "Central MDT",
        ]
        for width in (390, 1440):
            page.set_viewport_size({"width": width, "height": 1000})
            for name in navigation_names:
                if width == 390:
                    page.get_by_role("button", name="Toggle workspace navigation").click()
                button = page.get_by_role("navigation").get_by_role("button", name=name, exact=True)
                expect(button).to_have_attribute("aria-label", name)
                button.click()
                expect(page.locator("nav button[aria-current='page']")).to_have_attribute(
                    "aria-label", name
                )
                no_overflow()
        page.get_by_role("button", name="Workspace wall", exact=False).click()
        expect(page.locator(".wall-grid .role-card")).to_have_count(7)
        page.screenshot(path=str(artifacts / "wall-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        no_overflow()
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Central MDT", exact=False).click()
        page.get_by_test_id("followup").click()
        expect(page.get_by_role("heading", name="The perspectives become a plan.")).to_be_visible()
        page.get_by_role("textbox", name="Review comment").fill("Keep this review draft")
        page.evaluate("value => window.__state(value)", current)
        expect(page.get_by_role("textbox", name="Review comment")).to_have_value(
            "Keep this review draft"
        )
        page.evaluate("window.__streams.filter(s => !s.closed).forEach(s => s.onerror?.({}))")
        expect(page.locator(".reconnect-notice")).to_contain_text("your input is preserved")
        expect(page.get_by_role("textbox", name="Review comment")).to_have_value(
            "Keep this review draft"
        )
        page.evaluate("window.__streams.filter(s => !s.closed).forEach(s => s.onopen?.({}))")
        expect(page.locator(".connection")).to_contain_text("Live connection")
        page.screenshot(path=str(artifacts / "plan-desktop.png"), full_page=True)
        current["concurrences"]["radiology"] = {
            "role": "radiology",
            "plan_version": 1,
            "actor": "human",
            "comment": "Old version only",
            "timestamp": NOW,
        }
        current["plan"]["version"] = 2
        current["events"].append(
            {
                "id": len(current["events"]) + 1,
                "meeting_id": current["id"],
                "type": "PlanUpdated",
                "role": None,
                "payload": {"summary": "Review version 2"},
                "timestamp": NOW,
            }
        )
        page.evaluate("value => window.__state(value)", current)
        expect(page.get_by_text("Review new version", exact=True)).to_be_visible()
        expect(page.get_by_role("textbox", name="Review comment")).to_have_value(
            "Keep this review draft"
        )
        for role in ROLES:
            page.get_by_test_id("review-role").select_option(role)
            page.get_by_test_id(f"concur-{role}").click()
            expect(page.get_by_test_id(f"concur-{role}")).to_have_count(0)
        expect(page.get_by_role("heading", name="A considered decision. Captured.")).to_be_visible()
        assert (
            page.locator(".plan-panel").evaluate("element => getComputedStyle(element).opacity")
            == "1"
        )
        assert (
            page.locator(".plan-panel").evaluate(
                "element => getComputedStyle(element).animationName"
            )
            == "none"
        )
        page.emulate_media(reduced_motion="no-preference")
        page.locator(".plan-panel").scroll_into_view_if_needed()
        assert (
            page.locator(".plan-panel").evaluate("element => getComputedStyle(element).opacity")
            == "1"
        )
        page.emulate_media(reduced_motion="reduce")
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Export meeting and provenance as JSON").click()
        assert downloaded.value.suggested_filename.endswith(".json")
        assert "req_fixture" in Path(downloaded.value.path()).read_text(encoding="utf-8")
        page.set_viewport_size({"width": 375, "height": 812})
        no_overflow()
        page.screenshot(path=str(artifacts / "decision-mobile.png"), full_page=True)
        page.get_by_role("button", name="Switch to dark mode").click()
        assert page.locator("html").get_attribute("data-theme") == "dark"
        no_overflow()
        page.reload()
        expect(page.get_by_role("heading", name="A considered decision. Captured.")).to_be_visible()
        expect(page.get_by_test_id("start-case")).to_be_enabled()
        expect(page.get_by_test_id("mode-select")).to_be_enabled()
        no_overflow()
        page.get_by_role("button", name="Toggle workspace navigation").click()
        page.get_by_test_id("view-chair").click()
        expect(page.get_by_test_id("start-case")).to_be_visible()
        page.get_by_test_id("mode-select").select_option("azure")
        page.get_by_test_id("start-case").click()
        expect(page.get_by_role("heading", name="Specialists at work")).to_be_visible()
        assert current["mode"] == "azure"
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Request targeted follow-up").click()
        expect(page.get_by_role("button", name="Object", exact=True)).to_be_disabled()
        page.get_by_role("textbox", name="Review comment").fill(
            "Confirm tissue before final concurrence."
        )
        page.get_by_role("button", name="Object", exact=True).click()
        expect(page.get_by_test_id("phase")).to_have_attribute("data-phase", "TARGETED_DISCUSSION")
        expect(page.locator(".plan-objections")).to_contain_text(
            "Objections & discussion history (1)"
        )
        auth_required = True
        page.reload()
        expect(page.get_by_role("dialog", name="Presenter access")).to_be_visible()
        page.get_by_label("Presenter secret", exact=True).fill("wrong-fixture")
        page.get_by_role("button", name="Unlock presenter controls").click()
        expect(page.get_by_role("dialog")).to_contain_text("The presenter secret was not accepted")
        page.get_by_label("Presenter secret", exact=True).fill("browser-fixture")
        page.get_by_role("button", name="Unlock presenter controls").click()
        expect(page.get_by_role("dialog", name="Presenter access")).not_to_be_visible()
        expect(page.locator(".connection")).to_contain_text("Live connection")
        current["phase"] = "DECISION_CAPTURED"
        current["closed_at"] = NOW
        current["roles"]["pathology"]["position"]["autonomy"] = "AUTO"
        current["concurrences"] = {
            role: {
                "role": role,
                "actor": "agent" if role == "pathology" else "human",
                "plan_version": current["plan"]["version"],
                "comment": "",
                "timestamp": NOW,
            }
            for role in ROLES
        }
        page.evaluate("value => window.__state(value)", current)
        expect(page.locator(".concurrence-panel")).to_contain_text("7 / 7")
        expect(page.locator(".concurrence-panel")).to_contain_text("6 human, 1 agent")
        expect(page.locator(".concurrence-list")).to_contain_text("Auto-concurred (demo policy)")
        expect(page.locator(".concurrence-list")).not_to_contain_text("human pending")
        assert page.evaluate("localStorage.getItem('mdt-theme')") in ("light", "dark")
        assert page.evaluate("localStorage.getItem('presenter-token')") is None
        assert not errors, errors
        assert len([call for call in calls if call[1].endswith("/concur")]) == 7
        print(
            "PASS: desktop/mobile layout, seven roles, live draft retention, reconnect, "
            "mutation failure, memory controls, evidence, follow-up, human concurrence, "
            "objection, export, repeat demo and 401/204 authentication. "
            f"{len(calls)} API calls; no browser errors."
        )
        browser.close()


if __name__ == "__main__":
    run()
