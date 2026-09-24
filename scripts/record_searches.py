"""Capture the rehearsal search plans against the real sources.

Run from the repository root when the recorded searches should be refreshed:

    uv run --frozen python scripts/record_searches.py

It sends each case's concept-only research searches to the live, allowlisted sources,
trims every response to the fields the parsers read, replays the result offline to
prove it parses identically, and writes ``src/mdt/dossiers/recorded_searches.json``.
Rehearsal then shows real search behaviour, labelled RECORDED, without network access.
No credential is stored: request keys never include the NCBI API key.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mdt.case_registry import get_case
from mdt.literature import (
    LiteratureClient,
    RecordedSearches,
    SearchOutcome,
    case_identifiers,
    run_search,
    trim_for_recording,
)
from mdt.models import Evidence

OUTPUT = Path(__file__).resolve().parents[1] / "src" / "mdt" / "dossiers" / "recorded_searches.json"

Step = dict[str, Any]


def _search(tool: str, query: str, count: int, **extra: str) -> Step:
    return {"tool": tool, "arguments": {"query": query, "max_results": count, **extra}}


PLANS: dict[str, list[Step]] = {
    "CASE-MDT-CRC-BRAF-2026-001": [
        _search("search_dutch_guidelines", "levermetastasen", 3),
        _search(
            "search_clinical_trials", "BRAF V600E colorectal", 2,
            registry="ctis_then_clinicaltrials_gov",
        ),
        _search(
            "search_europepmc", "BRAF colorectal liver metastases hepatectomy", 3,
            publication_type="any", sort="most_cited",
        ),
        _search("search_preprints", "BRAF colorectal liver metastases", 2),
        {"tool": "fetch_abstract", "arguments": {"evidence_id": "first-pmid"}},
    ],
    "CASE-MDT-CRC-WT-2026-002": [
        _search("search_dutch_guidelines", "colorectale levermetastasen resectie", 3),
        _search(
            "search_europepmc", "disappearing colorectal liver metastases", 3,
            publication_type="any", sort="most_cited",
        ),
        _search(
            "search_clinical_trials", "colorectal liver metastases resection", 2,
            registry="ctis_then_clinicaltrials_gov",
        ),
    ],
    "CASE-MDT-PDAC-PERIOP-2026-003": [
        _search("search_dutch_guidelines", "pancreascarcinoom neoadjuvante behandeling", 3),
        _search(
            "search_clinical_trials", "pancreatic cancer FOLFIRINOX perioperative", 2,
            registry="ctis_then_clinicaltrials_gov",
        ),
        _search(
            "search_europepmc", "pancreatoduodenectomy elderly outcomes", 3,
            publication_type="any", sort="most_cited",
        ),
    ],
}


async def _run_plan(
    client: LiteratureClient, case_id: str, plan: list[Step]
) -> tuple[list[Step], list[SearchOutcome]]:
    definition = get_case(case_id)
    identifiers = case_identifiers(definition.case) | {case_id}
    returned: dict[str, Evidence] = {}
    resolved: list[Step] = []
    outcomes: list[SearchOutcome] = []
    for step in plan:
        arguments = dict(step["arguments"])
        if step["tool"] == "fetch_abstract" and arguments["evidence_id"] == "first-pmid":
            first = next((key for key in returned if "-PMID-" in key), None)
            if first is None:
                raise SystemExit(f"{case_id}: no PubMed record was found to open.")
            arguments["evidence_id"] = "REC-" + first.split("-", 1)[1]
            lookup = first
        else:
            lookup = str(arguments.get("evidence_id", ""))
        outcome = await run_search(
            client, str(step["tool"]),
            {**arguments, "evidence_id": lookup} if "evidence_id" in arguments else arguments,
            curated=definition.evidence, returned=returned, identifiers=identifiers,
        )
        if outcome.status != "completed":
            raise SystemExit(f"{case_id}: {step['tool']} {outcome.status}: {outcome.message}")
        for check in outcome.checks:
            if check.status != "completed":
                raise SystemExit(f"{case_id}: {check.source.label}: {check.message}")
        returned.update((item.id, item) for item in outcome.evidence)
        resolved.append({"tool": step["tool"], "arguments": arguments})
        outcomes.append(outcome)
    return resolved, outcomes


def _signature(outcomes: list[SearchOutcome]) -> list[Any]:
    return [
        [
            [(check.source.key, check.total, check.returned) for check in outcome.checks],
            [
                (item.id.split("-", 1)[1], item.title, len(item.passage))
                for item in outcome.evidence
            ],
        ]
        for outcome in outcomes
    ]


async def main() -> None:
    captured: dict[str, str] = {}
    live = LiteratureClient(recorder=captured)
    plans: dict[str, list[Step]] = {}
    signatures: dict[str, list[Any]] = {}
    try:
        for case_id, plan in PLANS.items():
            plans[case_id], outcomes = await _run_plan(live, case_id, plan)
            signatures[case_id] = _signature(outcomes)
    finally:
        await live.aclose()
    captured_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    responses = {key: trim_for_recording(key, text) for key, text in sorted(captured.items())}
    recorded = RecordedSearches(captured_at, responses, plans)
    for case_id, plan in plans.items():
        replay = LiteratureClient(retrieval="RECORDED", recorded=recorded)
        # Replay resolves fetch_abstract against REC- identifiers, as rehearsal does.
        definition = get_case(case_id)
        returned: dict[str, Evidence] = {}
        outcomes = []
        for step in plan:
            outcome = await run_search(
                replay, str(step["tool"]), dict(step["arguments"]),
                curated=definition.evidence, returned=returned,
                identifiers=case_identifiers(definition.case) | {case_id},
            )
            returned.update((item.id, item) for item in outcome.evidence)
            outcomes.append(outcome)
        if _signature(outcomes) != signatures[case_id]:
            raise SystemExit(f"{case_id}: the trimmed recording does not replay identically.")
    text = json.dumps(
        {"captured_at": captured_at, "plans": plans, "responses": responses},
        ensure_ascii=False, indent=1,
    )
    if "api_key" in text:
        raise SystemExit("Refusing to write a recording that mentions an API key.")
    OUTPUT.write_text(text + "\n", encoding="utf-8")
    found = sum(len(item[1]) for value in signatures.values() for item in value)
    print(f"Recorded {len(responses)} responses, {found} records, {OUTPUT.stat().st_size} bytes.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
