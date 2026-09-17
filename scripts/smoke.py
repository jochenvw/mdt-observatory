"""Run and export the complete colorectal conversion workflow against a running API."""

import argparse
import os
import time
from pathlib import Path
from typing import Any

import httpx

from mdt.scenario import CASE


def run(base_url: str, mode: str, output: Path, timeout: int) -> dict[str, Any]:
    with httpx.Client(base_url=base_url, timeout=30) as client:
        client.get("/healthz").raise_for_status()
        if token := os.getenv("MDT_PRESENTER_TOKEN"):
            client.post("/api/auth", json={"token": token}).raise_for_status()

        def command(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            response = client.post(path, json=payload)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

        meeting = command("/api/meetings", {"mode": mode, "case_id": CASE["id"]})
        prefix = f"/api/meetings/{meeting['id']}"

        def wait() -> dict[str, Any]:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                response = client.get(prefix)
                response.raise_for_status()
                state: dict[str, Any] = response.json()
                if state["phase"] == "ERROR":
                    failures = {
                        role: value["error"]
                        for role, value in state["roles"].items()
                        if value["error"]
                    }
                    raise RuntimeError(f"Meeting analysis failed: {failures}")
                if not state["busy"]:
                    return state
                time.sleep(1)
            raise TimeoutError(f"Meeting did not settle within {timeout}s")

        meeting = wait()
        assert meeting["case"] == CASE, "Deployed case differs from the complete packaged dossier."
        dossier = meeting["case"]["dossier"]
        assert dossier["patient"]["age"] == 59
        assert dossier["imaging"]["baseline_liver_MRI"]["lesion_count"] == 9
        assert dossier["prior_cancer_treatment"]["systemic_regimen"]["cycles_completed"] == 4
        assert (
            dossier["response_assessment"]["biomarkers"]["ctDNA"]["BRAF_V600E_VAF_percent"] == 0.42
        )
        assert len(meeting["case"]["management_alternatives"]) == 3
        assert len(meeting["roles"]) == 7
        assert meeting["phase"] == "TARGETED_DISCUSSION"
        assert {f["id"] for f in meeting["frictions"] if not f["resolved"]} >= {
            "imaging",
            "applicability",
        }
        command(
            f"{prefix}/steer",
            {
                "role": "radiology",
                "guidance": (
                    "Review all nine liver sites, vessel margins and the indeterminate lung "
                    "nodule before clearance planning."
                ),
            },
        )
        wait()
        command(f"{prefix}/followup", {})
        meeting = wait()
        assert meeting["phase"] == "CONCURRENCE"
        assert not any(f["blocking"] and not f["resolved"] for f in meeting["frictions"])
        for role in meeting["roles"]:
            if role not in meeting["concurrences"]:
                meeting = command(
                    f"{prefix}/concur",
                    {
                        "role": role,
                        "plan_version": meeting["plan"]["version"],
                        "comment": "Demonstration workflow verification; not clinical approval.",
                    },
                )
        assert meeting["phase"] == "DECISION_CAPTURED"
        assert meeting["case"]["dossier"] == dossier
        response = client.get(f"{prefix}/export")
        response.raise_for_status()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(response.text, encoding="utf-8")
        assert all(
            vote["plan_version"] == meeting["plan"]["version"]
            for vote in meeting["concurrences"].values()
        )
        return {
            "meeting_id": meeting["id"],
            "mode": mode,
            "phase": meeting["phase"],
            "events": len(meeting["events"]),
            "roles": len(meeting["roles"]),
            "output": str(output),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=["rehearsal", "azure"], default="rehearsal")
    parser.add_argument("--output", type=Path, default=Path("artifacts/smoke-decision.json"))
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    print(run(args.url, args.mode, args.output, args.timeout))
