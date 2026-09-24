"""Live research search: bounded tools, honest labels, visible failures, no network in CI."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2
import pytest
from test_agents import _completion, _mock_azure, _run

from mdt import agents, literature
from mdt.agents import AgentRuntimeError, RunState
from mdt.case_registry import get_case
from mdt.config import Settings
from mdt.literature import LiteratureClient, RecordedSearches, run_search
from mdt.models import Evidence, Position, Role
from mdt.scenario import CASE

CASE_ID = str(CASE["id"])


@pytest.fixture(autouse=True)
async def _fresh_state() -> AsyncIterator[None]:
    literature.clear_cache()
    yield
    literature.clear_cache()
    await agents.aclose_azure_clients()


def _europepmc(*records: dict[str, Any], hits: int = 42) -> dict[str, Any]:
    return {"hitCount": hits, "resultList": {"result": list(records)}}


PAPER = {
    "id": "30000001", "source": "MED", "pmid": "30000001", "doi": "10.1000/demo.1",
    "title": "Hepatectomy for <i>BRAF</i> mutant colorectal liver metastases",
    "journalInfo": {"journal": {"title": "Demo Journal of Surgery"}},
    "firstPublicationDate": "2020-05-01", "pubYear": "2020",
    "pubTypeList": {"pubType": ["Journal Article", "Multicenter Study"]},
    "abstractText": "Background. " + "Outcomes after resection were analysed. " * 40,
    "isOpenAccess": "N",
}
PREPRINT = {
    "id": "PPR900001", "source": "PPR", "title": "A preprint on liver metastases",
    "firstPublicationDate": "2026-01-02", "pubTypeList": {"pubType": ["Preprint"]},
    "abstractText": "Short preprint abstract.",
}


def _transport(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> tuple[httpx2.MockTransport, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    return httpx2.MockTransport(record), seen


async def _search(
    client: LiteratureClient, name: str, arguments: dict[str, Any], **kwargs: Any,
) -> literature.SearchOutcome:
    return await run_search(
        client, name, arguments, curated=kwargs.get("curated", []),
        returned=kwargs.get("returned", {}), identifiers=kwargs.get("identifiers", set()),
    )


EPMC_ARGS = {
    "query": "BRAF colorectal liver metastases", "max_results": 3,
    "publication_type": "any", "sort": "most_cited",
}


async def test_europepmc_results_are_labelled_live_and_not_assessed() -> None:
    transport, seen = _transport(
        lambda request: httpx2.Response(200, json=_europepmc(PAPER))
    )
    client = LiteratureClient(transport=transport)
    outcome = await _search(client, "search_europepmc", EPMC_ARGS)
    await client.aclose()
    assert outcome.status == "completed"
    assert [(c.source.key, c.status, c.total, c.returned) for c in outcome.checks] == [
        ("europepmc", "completed", 42, 1)
    ]
    item = outcome.evidence[0]
    assert item.id == "LIVE-PMID-30000001"
    assert item.retrieval == "LIVE" and item.source_tier == "INTL"
    assert item.patient_match == "NOT_ASSESSED"
    assert item.access == "PUBLIC_ABSTRACT_ONLY"
    assert item.url == "https://pubmed.ncbi.nlm.nih.gov/30000001/"
    assert item.title == "Hepatectomy for BRAF mutant colorectal liver metastases"
    assert item.identifiers == {"pmid": "30000001", "doi": "10.1000/demo.1"}
    assert item.query == EPMC_ARGS["query"] and item.retrieved_at and item.endpoint
    assert len(item.passage) <= literature.SEARCH_PASSAGE_CHARS
    assert any("not curated" in value for value in item.limitations)
    assert any("applicability" in value.lower() for value in item.limitations)
    request = seen[0]
    assert request.url.host == "www.ebi.ac.uk"
    assert request.url.params["sort"] == "CITED desc"
    assert request.url.params["query"] == (
        "TITLE_ABS:(BRAF AND colorectal AND liver AND metastases) AND NOT SRC:PPR"
    )
    assert request.headers["user-agent"].startswith("python-httpx/")


async def test_preprints_and_us_registers_carry_their_caveats() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "www.ebi.ac.uk":
            return httpx2.Response(200, json=_europepmc(PREPRINT))
        if request.url.host == "euclinicaltrials.eu":
            body = json.loads(request.content)
            assert body["searchCriteria"]["containAll"] == "BRAF,colorectal"
            return httpx2.Response(200, json={
                "pagination": {"totalRecords": 1},
                "data": [{
                    "ctNumber": "2023-509564-22-00", "ctTitle": "An EU trial",
                    "decisionDateOverall": "06/03/2025", "sponsor": "Demo sponsor",
                    "trialCountries": ["Netherlands:1"], "trialPhase": "Phase 2",
                }],
            })
        return httpx2.Response(200, json={"totalCount": 1, "studies": [{
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001", "briefTitle": "A US trial"},
                "statusModule": {"overallStatus": "RECRUITING"},
            },
        }]})

    transport, _ = _transport(handler)
    client = LiteratureClient(transport=transport)
    preprints = await _search(
        client, "search_preprints", {"query": "liver metastases", "max_results": 2}
    )
    trials = await _search(client, "search_clinical_trials", {
        "query": "BRAF colorectal", "max_results": 2,
        "registry": "ctis_then_clinicaltrials_gov",
    })
    await client.aclose()
    preprint = preprints.evidence[0]
    assert preprint.source_tier == "PREPRINT" and preprint.kind == "PREPRINT"
    assert "PREPRINT — not peer reviewed." in preprint.limitations
    eu, us = trials.evidence
    assert [c.source.key for c in trials.checks] == ["ctis", "clinicaltrials_gov"]
    assert eu.source_tier == "EU" and eu.date == "2025-03-06"
    assert eu.url.endswith("EUCT=2023-509564-22-00")
    assert us.source_tier == "US" and us.region == "US"
    assert "US context — not European standard of care." in us.limitations
    assert us.url == "https://clinicaltrials.gov/study/NCT00000001"


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"query": "x", "max_results": 3}, "3-256 characters"),
        ({"query": "liver", "max_results": 11}, "between 1 and 10"),
        ({"query": "liver", "max_results": True}, "whole number"),
        ({"query": "liver"}, "did not match"),
        ({"query": "liver", "max_results": 3, "extra": 1}, "did not match"),
        ({"query": "resection 2026-09-16", "max_results": 3}, "a date"),
        ({"query": "73-year-old liver resection", "max_results": 3}, "an age"),
        ({"query": "CASE-MDT-CRC-BRAF-2026-001 liver", "max_results": 3}, "case identifier"),
        ({"query": "record 1234567 liver", "max_results": 3}, "record number"),
        ({"query": "patient@example.org", "max_results": 3}, "e-mail"),
    ],
)
async def test_unsafe_or_malformed_searches_are_refused_before_any_request(
    arguments: dict[str, Any], reason: str,
) -> None:
    transport, seen = _transport(lambda request: httpx2.Response(500))
    client = LiteratureClient(transport=transport)
    outcome = await _search(client, "search_dutch_guidelines", arguments)
    await client.aclose()
    assert outcome.status == "refused" and reason in outcome.message
    assert not seen and not outcome.evidence


async def test_case_identifiers_are_never_sent() -> None:
    identifiers = literature.case_identifiers(get_case(CASE_ID).case) | {CASE_ID}
    assert identifiers
    value = next(iter(sorted(identifiers, key=len, reverse=True)))
    transport, seen = _transport(lambda request: httpx2.Response(500))
    client = LiteratureClient(transport=transport)
    outcome = await _search(
        client, "search_dutch_guidelines",
        {"query": f"liver {value}"[:256], "max_results": 3}, identifiers=identifiers,
    )
    await client.aclose()
    assert outcome.status == "refused" and not seen


async def test_only_allowlisted_https_hosts_are_reachable() -> None:
    client = LiteratureClient(transport=httpx2.MockTransport(lambda r: httpx2.Response(200)))
    source = literature.SOURCES["europepmc"]
    for url in (
        "http://www.ebi.ac.uk/europepmc/webservices/rest/search",
        "https://evil.example.org/search",
        "https://clinicaltrials.gov/api/v2/studies",
    ):
        with pytest.raises(literature.LiteratureError, match="not an allowlisted"):
            await client.request(source, "GET", url)
    await client.aclose()
    assert literature.ALLOWED_HOSTS == {
        "richtlijnendatabase.nl", "euclinicaltrials.eu", "www.ebi.ac.uk",
        "eutils.ncbi.nlm.nih.gov", "clinicaltrials.gov",
    }


async def test_unavailable_source_is_visible_and_retries_once() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(503, headers={"retry-after": "0"})

    transport, _ = _transport(handler)
    client = LiteratureClient(transport=transport)
    outcome = await _search(client, "search_europepmc", EPMC_ARGS)
    await client.aclose()
    assert calls == 2
    assert outcome.status == "unavailable" and not outcome.evidence
    assert outcome.checks[0].status == "unavailable"
    assert outcome.checks[0].message == "Europe PMC is temporarily unavailable (status 503)."


async def test_oversized_and_unreadable_responses_fail_visibly() -> None:
    big = httpx2.Response(200, content=b"x" * (literature.MAX_RESPONSE_BYTES + 1))
    transport, _ = _transport(lambda request: big)
    client = LiteratureClient(transport=transport)
    outcome = await _search(client, "search_europepmc", EPMC_ARGS)
    assert "too much data" in outcome.checks[0].message
    await client.aclose()
    transport, _ = _transport(lambda request: httpx2.Response(200, text="<html>"))
    client = LiteratureClient(transport=transport)
    outcome = await _search(client, "search_europepmc", EPMC_ARGS)
    await client.aclose()
    assert outcome.status == "unavailable"
    assert "could not be read" in outcome.checks[0].message


async def test_ncbi_key_is_sent_but_never_part_of_a_recorded_key() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.params["api_key"] == "secret-demo-key"
        assert request.url.params["tool"] == "mdt-observatory"
        if "esearch" in request.url.path:
            return httpx2.Response(200, json={
                "esearchresult": {"count": "1", "idlist": ["30000001"]}
            })
        return httpx2.Response(200, json={"result": {"30000001": {
            "title": "A PubMed record", "fulljournalname": "Demo",
            "sortpubdate": "2020/05/01 00:00", "articleids": [
                {"idtype": "doi", "value": "10.1000/demo.1"}
            ],
        }}})

    recorder: dict[str, str] = {}
    transport, _ = _transport(handler)
    client = LiteratureClient(
        transport=transport, ncbi_api_key="secret-demo-key", recorder=recorder
    )
    outcome = await _search(client, "search_pubmed", {
        "query": "liver metastases", "max_results": 1, "publication_type": "review",
    })
    await client.aclose()
    item = outcome.evidence[0]
    assert item.access == "METADATA_ONLY" and item.date == "2020-05-01"
    assert "Only the bibliographic record" in " ".join(item.limitations)
    assert recorder and not any("secret" in key or "api_key" in key for key in recorder)
    assert not any("secret" in value for value in recorder.values())


async def test_duplicates_of_curated_evidence_are_not_added_again() -> None:
    curated = get_case(CASE_ID).evidence
    by_pmid = next(item for item in curated if "EXT_ID:" in item.url)
    by_pmcid = next(item for item in curated if "/articles/PMC" in item.url)
    pmid = by_pmid.url.split("EXT_ID:", 1)[1].split("%", 1)[0]
    pmcid = by_pmcid.url.rstrip("/").rsplit("/", 1)[1]
    records = [
        {**PAPER, "id": pmid, "pmid": pmid, "doi": None},
        {**PAPER, "id": "30000009", "pmid": "30000009", "pmcid": pmcid, "doi": None},
        {**PAPER, "id": f"{pmid}1", "pmid": f"{pmid}1", "doi": None},
    ]
    transport, _ = _transport(lambda request: httpx2.Response(200, json=_europepmc(*records)))
    client = LiteratureClient(transport=transport)
    outcome = await _search(client, "search_europepmc", EPMC_ARGS, curated=curated)
    await client.aclose()
    assert outcome.already_curated == [by_pmid.id, by_pmcid.id]
    assert [item.identifiers["pmid"] for item in outcome.evidence] == [f"{pmid}1"]


async def test_fetch_abstract_opens_only_records_returned_in_this_review() -> None:
    transport, seen = _transport(lambda request: httpx2.Response(200, json=_europepmc(PAPER)))
    client = LiteratureClient(transport=transport)
    refused = await _search(client, "fetch_abstract", {"evidence_id": "CRC-PROVENC3"})
    assert refused.status == "refused" and not seen
    found = await _search(client, "search_europepmc", EPMC_ARGS)
    returned = {item.id: item for item in found.evidence}
    opened = await _search(
        client, "fetch_abstract", {"evidence_id": "LIVE-PMID-30000001"}, returned=returned
    )
    await client.aclose()
    assert opened.status == "completed"
    assert opened.evidence[0].id == "LIVE-PMID-30000001"
    assert len(opened.evidence[0].passage) > literature.SEARCH_PASSAGE_CHARS
    assert opened.evidence[0].access == "PUBLIC_ABSTRACT_ONLY"


async def test_recorded_client_never_uses_the_network_and_fails_visibly() -> None:
    def forbidden(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("RECORDED retrieval must not send requests")

    client = LiteratureClient(
        retrieval="RECORDED", transport=httpx2.MockTransport(forbidden),
        recorded=RecordedSearches("2026-01-01T00:00:00+00:00", {}, {}),
    )
    outcome = await _search(client, "search_europepmc", EPMC_ARGS)
    await client.aclose()
    assert outcome.status == "unavailable"
    assert "No recorded response" in outcome.checks[0].message


def test_recorded_plans_cover_every_case_and_hold_no_credentials() -> None:
    recorded = literature.recorded_searches()
    assert set(recorded.plans) == {
        "CASE-MDT-CRC-BRAF-2026-001", "CASE-MDT-CRC-WT-2026-002",
        "CASE-MDT-PDAC-PERIOP-2026-003",
    }
    assert recorded.captured_at
    text = json.dumps(recorded.responses)
    assert "api_key" not in text
    for plan in recorded.plans.values():
        for step in plan:
            assert step["tool"] in literature.TOOL_SPECS
            if "query" in step["arguments"]:
                assert literature.query_violation(step["arguments"]["query"], set()) is None


async def test_rehearsal_research_replays_recorded_searches_deterministically() -> None:
    runs: list[list[tuple[str, dict[str, Any]]]] = []
    for _ in range(2):
        events: list[tuple[str, dict[str, Any]]] = []

        async def emit(kind: str, payload: dict[str, Any], sink: list[Any] = events) -> None:
            sink.append((kind, payload))

        position = await _run(Role.RESEARCH, emit=emit)
        runs.append(events)
    first, second = ([
        payload["evidence"]["id"] for kind, payload in run if kind == "EvidenceFound"
    ] for run in runs)
    assert first == second
    recorded = [item for item in first if item.startswith("REC-")]
    assert recorded and any("-NLGUIDE-" in item for item in recorded)
    started = [payload for kind, payload in runs[0] if kind == "ToolStarted"]
    assert started[0]["retrieval"] == "RECORDED"
    assert started[0]["summary"].startswith("Replaying a recorded search")
    assert started[-1]["tool"] == agents.CORE_TOOLS[Role.RESEARCH]
    completed = [
        payload for kind, payload in runs[0]
        if kind == "ToolCompleted" and payload["retrieval"] == "RECORDED"
    ]
    assert all(payload["checks"] for payload in completed)
    assert any(item.startswith("REC-") for item in position.provenance)
    assert "friction_keys" in position.model_dump()


async def test_rehearsal_search_can_be_switched_off_and_is_initial_only() -> None:
    events: list[str] = []

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        if kind == "EvidenceFound":
            events.append(payload["evidence"]["retrieval"])

    await _run(Role.RESEARCH, emit=emit, settings=Settings(literature_search=False))
    await _run(Role.RESEARCH, emit=emit, phase="followup")
    assert set(events) == {"CURATED"}


def _live_mock(monkeypatch: pytest.MonkeyPatch, handler: Callable[..., httpx2.Response]) -> None:
    original = agents.LiteratureClient

    def factory(**kwargs: Any) -> LiteratureClient:
        return original(transport=httpx2.MockTransport(handler), **kwargs)

    monkeypatch.setattr(agents, "LiteratureClient", factory)


def _calls(*calls: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    response = _completion(tool="placeholder")
    template = response["output"][0]
    response["output"] = [
        {**template, "id": f"fc-{index}", "call_id": f"call-{index}", "name": name,
         "arguments": json.dumps(arguments)}
        for index, (name, arguments) in enumerate(calls)
    ]
    return response


def _position(evidence_ids: list[str], text: str = "") -> str:
    expected = get_case(CASE_ID).runtime
    return Position.model_validate({
        "role": "research", "case_id": CASE_ID, "position": "Conditional research view.",
        "confidence": 0.6, "autonomy": "REVIEW",
        "claims": [{"claim": text or "Searched literature informs, not settles.",
                    "evidence_ids": evidence_ids}],
        "uncertainties": [], "recommendation": expected.recommendations[Role.RESEARCH],
        "questions_for_mdt": [], "provenance": evidence_ids, "stance": "CONDITIONAL",
        "friction_keys": [],
        "trace": {"assessment": "a", "observations": [], "hypothesis": "h",
                  "uncertainties": [], "evidence_checking": [], "next_action": "n"},
    }).model_dump_json()


async def test_azure_research_searches_in_parallel_and_cites_live_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _live_mock(monkeypatch, lambda request: httpx2.Response(200, json=_europepmc(PAPER)))
    curated = get_case(CASE_ID).role_evidence(Role.RESEARCH)[0].id
    requests, _ = _mock_azure(monkeypatch, [
        _calls((agents.CORE_TOOLS[Role.RESEARCH], {}), ("search_europepmc", EPMC_ARGS)),
        _completion(content="No further searches."),
        _completion(content=_position([curated, "LIVE-PMID-30000001"])),
    ])
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    position = await _run(Role.RESEARCH, mode="azure", emit=emit)
    assert position.provenance == [curated, "LIVE-PMID-30000001"]
    assert "applicability" in position.friction_keys, "a search never settles friction"
    first = requests[0]
    assert first["parallel_tool_calls"] is True
    offered = {tool["name"] for tool in first["tools"]}
    assert set(agents.LIVE_TOOLS[Role.RESEARCH]) <= offered
    assert "live searches of public sources" in first["input"][0]["content"].lower()
    outputs = [
        json.loads(item["output"]) for item in requests[1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert outputs[0]["retrieval"] == "CURATED" and outputs[0]["context"]
    assert outputs[1]["retrieval"] == "LIVE"
    assert outputs[1]["evidence"][0]["id"] == "LIVE-PMID-30000001"
    assert "never settles" in outputs[1]["rule"]
    started = next(p for k, p in events if k == "ToolStarted" and p["tool"] == "search_europepmc")
    assert started["query"] == EPMC_ARGS["query"] and started["retrieval"] == "LIVE"
    assert started["summary"] == f"Searching Europe PMC for “{EPMC_ARGS['query']}”"
    found = [p["evidence"] for k, p in events if k == "EvidenceFound"]
    assert any(item["retrieval"] == "LIVE" for item in found)


async def test_azure_live_citation_of_an_unreturned_identifier_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _live_mock(monkeypatch, lambda request: httpx2.Response(200, json=_europepmc(PAPER)))
    curated = get_case(CASE_ID).role_evidence(Role.RESEARCH)[0].id
    _mock_azure(monkeypatch, [
        _calls((agents.CORE_TOOLS[Role.RESEARCH], {}), ("search_europepmc", EPMC_ARGS)),
        _completion(content="Done."),
        _completion(content=_position([curated], "See PMID 39999999 and NCT09999999.")),
    ])
    with pytest.raises(AgentRuntimeError, match="uncurated"):
        await _run(Role.RESEARCH, mode="azure")


async def test_unavailable_live_source_becomes_a_visible_uncertainty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _live_mock(monkeypatch, lambda request: httpx2.Response(404))
    curated = get_case(CASE_ID).role_evidence(Role.RESEARCH)[0].id
    _mock_azure(monkeypatch, [
        _calls((agents.CORE_TOOLS[Role.RESEARCH], {}), ("search_europepmc", EPMC_ARGS)),
        _completion(content="Done."),
        _completion(content=_position([curated])),
    ])
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    position = await _run(Role.RESEARCH, mode="azure", emit=emit)
    message = (
        "Live search of Europe PMC was unavailable: "
        "Europe PMC could not be searched (status 404)."
    )
    assert message in position.uncertainties
    raised = [p for k, p in events if k == "UncertaintyRaised" and p["summary"] == message]
    assert raised and not raised[0].get("error")


async def test_live_search_budget_refuses_softly_and_curated_budget_stays_hard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _live_mock(monkeypatch, lambda request: httpx2.Response(200, json=_europepmc(PAPER)))
    curated = get_case(CASE_ID).role_evidence(Role.RESEARCH)[0].id
    searches = [
        ("search_europepmc", {**EPMC_ARGS, "query": f"liver metastases topic {index}"})
        for index in "abcdefg"
    ]
    pending = [_calls((agents.CORE_TOOLS[Role.RESEARCH], {}), *searches)]

    def respond(body: dict[str, Any]) -> dict[str, Any]:
        if "text" in body:
            return _completion(content=_position([curated]))
        return pending.pop(0) if pending else _completion(content="Done.")

    requests, _ = _mock_azure(monkeypatch, respond)
    await _run(Role.RESEARCH, mode="azure")
    outputs = [
        json.loads(item["output"]) for item in requests[1]["input"]
        if item.get("type") == "function_call_output"
    ]
    statuses = [item.get("status") for item in outputs[1:]]
    assert statuses.count("completed") == agents.LIVE_SEARCH_BUDGET
    assert statuses[-1] == "refused" and "Search budget reached" in outputs[-1]["message"]


async def test_live_tools_are_research_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for role in Role:
        state = RunState(role, CASE_ID, "initial", [])
        state.literature = LiteratureClient()
        names = {tool["name"] for tool in agents._tools(state)}
        assert bool(names & set(literature.TOOL_SPECS)) == (role == Role.RESEARCH)
        await state.literature.aclose()
    _live_mock(monkeypatch, lambda request: httpx2.Response(200, json=_europepmc(PAPER)))
    _mock_azure(monkeypatch, [_calls(("search_europepmc", EPMC_ARGS))])
    with pytest.raises(AgentRuntimeError, match="not allowlisted"):
        await _run(Role.ONCOLOGY, mode="azure")


async def test_search_rounds_earn_bounded_extra_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    _live_mock(monkeypatch, lambda request: httpx2.Response(200, json=_europepmc(PAPER)))
    curated = get_case(CASE_ID).role_evidence(Role.RESEARCH)[0].id
    rounds = [
        _calls((agents.CORE_TOOLS[Role.RESEARCH], {}), ("search_europepmc", EPMC_ARGS)),
        *(
            _calls(("search_europepmc", {**EPMC_ARGS, "query": f"liver topic {index}"}))
            for index in "abcdefgh"
        ),
    ]
    for index, response in enumerate(rounds):
        for item in response["output"]:
            item["call_id"] = f"round-{index}-{item['call_id']}"

    def respond(body: dict[str, Any]) -> dict[str, Any]:
        if "text" in body:
            return _completion(content=_position([curated]))
        return rounds.pop(0)

    requests, _ = _mock_azure(monkeypatch, respond)
    await _run(Role.RESEARCH, mode="azure")
    assert len(requests) <= agents.MAX_MODEL_STEPS + agents.LIVE_EXTRA_MODEL_STEPS
    assert requests[-1]["text"]["format"]["type"] == "json_schema"


def test_evidence_without_provenance_serializes_as_before() -> None:
    item = get_case(CASE_ID).evidence[0]
    dumped = item.model_dump(mode="json")
    assert not {"retrieved_at", "identifiers", "source_tier", "query"} & set(dumped)
    assert Evidence.model_validate(dumped) == item
