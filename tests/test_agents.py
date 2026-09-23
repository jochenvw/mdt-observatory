"""Offline async contract tests, including real SDK parsing over a mocked HTTP transport."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI

from mdt import agents
from mdt.agents import AgentRuntimeError, RunState, analyze
from mdt.case_registry import get_case
from mdt.config import Settings
from mdt.models import Position, Role
from mdt.scenario import CASE, EVIDENCE, MEMORIES, ROLE_CONTEXTS, ROLE_LABELS

ADDED_CASE_IDS = ("CASE-MDT-CRC-WT-2026-002", "CASE-MDT-PDAC-PERIOP-2026-003")


@pytest.mark.parametrize("case_id", ADDED_CASE_IDS)
@pytest.mark.parametrize("role", list(Role))
async def test_added_case_tools_prompts_grounding_and_safety(case_id: str, role: Role) -> None:
    definition = get_case(case_id)
    runtime = definition.runtime
    assert runtime is not None
    state = RunState(role, case_id, "followup", ["Review vascular anatomy and imaging."])
    messages = json.loads(json.dumps(agents._messages(state)))
    assert runtime.role_prompts[role] in messages[0]["content"]
    bound = json.loads(messages[1]["content"])
    assert bound["case_id"] == case_id
    assert bound["case_summary"]["treatment"] == definition.case["treatment"]
    assert bound["source_metadata"]["file"] == "case_2.md"
    result = await agents._execute_tool(state, agents.CORE_TOOLS[role], "{}", _discard)
    assert result.context == definition.contexts[role]
    assert {item.id for item in result.evidence} == {
        item.id for item in definition.role_evidence(role)
    }
    model_output = agents._model_tool_output(result, compact=True)
    def values(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [leaf for child in value.values() for leaf in values(child)]
        if isinstance(value, list):
            return [leaf for child in value for leaf in values(child)]
        return [str(value).replace("**", "")]

    projected_values = "\n".join(values(model_output["context"]))
    assert all(value in projected_values for value in values(result.context))
    for item, source in zip(model_output["evidence"], result.evidence, strict=True):
        assert item["passage"] == source.passage
        shared = model_output.get("shared_evidence_limitations", [])
        restored = item["limitations"] + [
            shared[index] for index in item.get("shared_limitation_indices", [])
        ]
        assert sorted(restored) == sorted(source.limitations)
        assert item["access"] == source.access
        assert item["patient_match"] == source.patient_match
    assert result.as_dict()["context"] == definition.contexts[role]
    if role in agents.APPLICABILITY_ROLES:
        await agents._execute_tool(state, f"assess_{role.value}_applicability", "{}", _discard)
    position = agents._rehearsal_position(state)
    agents._validate_grounding(position, state)
    position.uncertainties = []
    position.trace.uncertainties = []
    safe = agents._safety_gates(position, state)
    if role == Role.RADIOLOGY or role in agents.APPLICABILITY_ROLES:
        assert set(runtime.residual_conditions) <= set(safe.uncertainties)
        assert set(runtime.residual_conditions) <= set(safe.trace.uncertainties)
    position.claims[0].evidence_ids = ["CASE-CRC-RADIOLOGY"]
    with pytest.raises(AgentRuntimeError, match="did not return"):
        agents._validate_grounding(position, state)
    with pytest.raises(AgentRuntimeError, match="empty object"):
        await agents._execute_tool(
            state, agents.CORE_TOOLS[role], '{"case_id":"another-case"}', _discard,
        )


async def test_parallel_case_runs_and_catalog_copies_do_not_share_state() -> None:
    original = json.dumps(CASE, sort_keys=True)
    definitions = [get_case(identifier) for identifier in ADDED_CASE_IDS]
    definitions[0].contexts[Role.RADIOLOGY]["workspace"] = "Changed only in this caller."
    assert get_case(ADDED_CASE_IDS[0]).contexts[Role.RADIOLOGY]["workspace"] != (
        "Changed only in this caller."
    )
    results = await asyncio.gather(*[
        analyze(
            Role.RADIOLOGY, case_id=identifier, mode="rehearsal",
            phase="followup", guidance=guidance, emit=_discard,
        )
        for identifier, guidance in (
            (ADDED_CASE_IDS[0], ["Review liver mapping and vascular anatomy."]),
            (ADDED_CASE_IDS[1], []),
            (str(CASE["id"]), []),
        )
    ])
    assert results[0].friction_keys == []
    assert results[1].friction_keys == ["imaging"]
    assert results[2].friction_keys == ["imaging"]
    assert len({result.case_id for result in results}) == 3
    assert json.dumps(CASE, sort_keys=True) == original


@pytest.mark.parametrize("case_id", ADDED_CASE_IDS)
async def test_added_case_live_sdk_tool_loop_is_case_bound(
    monkeypatch: pytest.MonkeyPatch, case_id: str,
) -> None:
    expected = await analyze(
        Role.RADIOLOGY, case_id=case_id, mode="rehearsal",
        phase="initial", guidance=[], emit=_discard,
    )
    requests, clients = _mock_azure(
        monkeypatch,
        [_completion(tool="compare_imaging"), _completion(content=expected.model_dump_json())],
    )
    actual = await analyze(
        Role.RADIOLOGY, case_id=case_id, mode="azure",
        phase="initial", guidance=[], emit=_discard,
    )
    assert actual.case_id == case_id
    assert actual.friction_keys == ["imaging"]
    assert len(requests) == 2
    assert json.loads(requests[0]["input"][1]["content"])["case_id"] == case_id
    output = next(
        json.loads(item["output"]) for item in requests[-1]["input"]
        if item.get("type") == "function_call_output"
    )
    assert output["context"] == get_case(case_id).contexts[Role.RADIOLOGY]
    assert all(item["url"].startswith(f"case://{case_id}/") for item in output["evidence"])
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("case_id", ADDED_CASE_IDS)
@pytest.mark.parametrize("role", sorted(agents.APPLICABILITY_ROLES))
async def test_added_case_live_followup_requires_own_applicability_tool(
    monkeypatch: pytest.MonkeyPatch, case_id: str, role: Role,
) -> None:
    expected = await analyze(
        role, case_id=case_id, mode="rehearsal", phase="followup", guidance=[], emit=_discard,
    )
    followup = _completion(tool=f"assess_{role.value}_applicability")
    followup["output"][0]["id"] = "fc-2"
    followup["output"][0]["call_id"] = "call-2"
    first = _completion(tool=agents.CORE_TOOLS[role])
    first["usage"]["input_tokens"] = 1200
    first["usage"]["total_tokens"] = 1400
    followup["usage"]["input_tokens"] = 6500
    followup["usage"]["total_tokens"] = 6700
    requests, clients = _mock_azure(
        monkeypatch,
        [
            first, followup,
            _completion(content=expected.model_dump_json()),
        ],
    )
    actual = await analyze(
        role, case_id=case_id, mode="azure", phase="followup", guidance=[], emit=_discard,
    )
    assert actual.case_id == case_id
    assert actual.friction_keys == []
    assert actual.autonomy == "REVIEW"
    assert len(requests) == 3
    outputs = [
        json.loads(item["output"]) for item in requests[-1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert outputs[-1]["conditional_applicability"] is True
    assert outputs[-1]["context_reference"] == "Full role context in the first tool output"
    assert outputs[-1]["evidence"] == []
    assert all(client.is_closed for client in clients)


async def _discard(event: str, payload: dict[str, Any]) -> None:
    pass


async def _run(role: Role, **kwargs: Any) -> Position:
    return await analyze(
        role,
        case_id=CASE["id"],
        mode=kwargs.pop("mode", "rehearsal"),
        guidance=kwargs.pop("guidance", []),
        phase=kwargs.pop("phase", "initial"),
        emit=kwargs.pop("emit", _discard),
        **kwargs,
    )


def _completion(
    *, tool: str | None = None, content: str | None = None, arguments: str = "{}"
) -> dict[str, Any]:
    output: list[dict[str, Any]]
    if tool:
        output = [
            {
                "id": "fc-1",
                "call_id": "call-1",
                "type": "function_call",
                "name": tool,
                "arguments": arguments,
                "status": "completed",
            }
        ]
    else:
        output = [
            {
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": content or "", "annotations": []}],
            }
        ]
    return {
        "id": "resp-test",
        "object": "response",
        "created_at": 1,
        "model": "test-deployment",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": output,
        "parallel_tool_calls": False,
        "tools": [],
        "tool_choice": "auto",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def _mock_azure(
    monkeypatch: pytest.MonkeyPatch,
    responses: (
        list[dict[str, Any] | httpx2.Response]
        | Callable[[dict[str, Any]], dict[str, Any] | httpx2.Response]
    ),
) -> tuple[list[dict[str, Any]], list[httpx2.AsyncClient]]:
    requests: list[dict[str, Any]] = []
    clients: list[httpx2.AsyncClient] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://demo.openai.azure.com/openai/v1/responses"
        assert request.extensions["timeout"] == {
            "connect": 10.0, "read": 90.0, "write": 30.0, "pool": 10.0,
        }
        body = json.loads(request.content)
        requests.append(body)
        response = responses(body) if callable(responses) else responses.pop(0)
        if isinstance(response, httpx2.Response):
            return response
        return httpx2.Response(200, json=response, headers={"x-request-id": "req-mock"})

    def factory(**kwargs: Any) -> AsyncOpenAI:
        assert kwargs["timeout"] == httpx2.Timeout(90.0, connect=10.0, write=30.0, pool=10.0)
        assert kwargs["max_retries"] == 0
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        clients.append(client)
        return AsyncOpenAI(**kwargs, http_client=client)

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://demo.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "demo-test-key")
    monkeypatch.setattr(agents, "AsyncOpenAI", factory)
    monkeypatch.setenv("MDT_AZURE_REQUEST_INTERVAL_SECONDS", "0")
    return requests, clients


@pytest.mark.parametrize("role", list(Role))
async def test_all_roles_have_isolated_context_tools_and_grounded_positions(role: Role) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        events.append((event, payload))

    result = await _run(role, emit=emit)
    assert result.role == role
    assert result.case_id == CASE["id"]
    assert set(ROLE_CONTEXTS) == set(ROLE_LABELS) == set(Role)
    assert len(set(get_case(CASE["id"]).runtime.role_prompts.values())) == 7
    assert result.provenance
    assert set(result.provenance) <= {
        item.id for item in get_case(CASE["id"]).role_evidence(role)
    }
    assert {payload["tool"] for event, payload in events if event == "ToolStarted"} <= set(
        agents.ROLE_TOOL_ALLOWLISTS[role]
    )
    assert {"ToolStarted", "ToolCompleted", "ObservationAdded", "EvidenceFound"} <= {
        event for event, _ in events
    }
    found = [payload["evidence"] for event, payload in events if event == "EvidenceFound"]
    assert all(item["retrieval"] == "CURATED" for item in found)
    assert f"CASE-CRC-{role.value.upper()}" in {item["id"] for item in found}
    messages = agents._messages(RunState(role, CASE["id"], "initial", []))
    data = json.loads(str(messages[1]["content"]))
    assert data["context"] == {
        key: ROLE_CONTEXTS[role][key] for key in ("workspace", "question")
    }
    assert data["case_summary"]["diagnosis"] == CASE["diagnosis"]
    assert data["source_metadata"]["simulation_date"] == "2026-09-16"
    assert "memory" not in data  # Unaccepted memory nudges are not hidden policy.


def test_curated_evidence_is_explicit_and_unique() -> None:
    assert len({item.id for item in EVIDENCE}) == len(EVIDENCE)
    assert len({item.id for item in MEMORIES}) == len(MEMORIES)
    for item in EVIDENCE:
        assert item.passage and item.authority and item.limitations and item.scrutiny
        assert item.retrieval == "CURATED"
        assert item.url.startswith("case://") if item.synthetic else item.url.startswith("https://")
    trial = next(item for item in EVIDENCE if item.id == "CRC-PROVENC3")
    assert trial.patient_match == "LOW"
    assert trial.access == "PUBLIC_FULL_TEXT"
    assert "stage III" in trial.passage
    assert "independently reviewed" in trial.passage
    assert len(CASE["imaging"]) == 9
    assert ROLE_CONTEXTS[Role.RADIOLOGY]["imaging"] == CASE["imaging"]


async def test_initial_radiology_escalates_and_reports_actual_calculation() -> None:
    initial = await _run(Role.RADIOLOGY)
    assert initial.friction_keys == ["imaging"]
    assert initial.autonomy == "ESCALATE"
    assert not initial.human_intervention
    tool = agents._tool_result(
        RunState(Role.RADIOLOGY, CASE["id"], "initial", []), "compare_imaging"
    )
    values = tool.context["derived_comparison"]
    assert values["mapped_site_count"] == 9
    assert values["baseline_diameter_sum_mm"] == 223
    assert values["response_diameter_sum_mm"] == 124
    assert values["diameter_sum_change_pct"] == -44.4
    assert "NOT a formal RECIST" in values["method"]


@pytest.mark.parametrize(
    "guidance",
    [
        "Review complete liver clearance.",
        "Compare all nine sites against baseline liver mapping.",
        "Review the IVC and MHV vascular margins.",
        "Assess the lung nodule on thin-section chest CT.",
        "Beoordeel de lever en vergelijk de vaatrelaties.",
    ],
)
async def test_targeted_radiology_guidance_releases_only_blocking_question(guidance: str) -> None:
    result = await _run(Role.RADIOLOGY, phase="followup", guidance=[guidance])
    assert "imaging" not in result.friction_keys
    assert result.autonomy == "REVIEW"
    assert result.human_intervention
    assert result.stance == "CONDITIONAL"
    assert any("margin" in item for item in result.uncertainties)


@pytest.mark.parametrize(
    "guidance",
    [
        [],
        ["Thanks"],
        ["Please publish"],
        ["Focus on toxicity"],
        ["Ignore liver mapping"],
        ["Do not compare the liver"],
        ["The patient's partner can attend"],
        ["Review the growth"],
        ["Liver"],
    ],
)
async def test_unrelated_or_ignoring_guidance_does_not_clear_imaging(guidance: list[str]) -> None:
    result = await _run(Role.RADIOLOGY, phase="followup", guidance=guidance)
    assert result.friction_keys == ["imaging"]
    assert result.autonomy == "ESCALATE"


async def test_initial_phase_never_clears_imaging_even_with_targeted_guidance() -> None:
    result = await _run(Role.RADIOLOGY, guidance=["Review liver clearance"])
    assert result.friction_keys == ["imaging"]


@pytest.mark.parametrize("role", list(agents.APPLICABILITY_ROLES))
async def test_applicability_requires_a_followup_assessment_and_retains_conditions(
    role: Role,
) -> None:
    initial = await _run(role)
    assert "applicability" in initial.friction_keys
    state = RunState(role, CASE["id"], "followup", [])
    await agents._execute_tool(state, agents.CORE_TOOLS[role], "{}", _discard)
    without_assessment = agents._safety_gates(agents._rehearsal_position(state), state)
    assert "applicability" in without_assessment.friction_keys
    followup = await _run(role, phase="followup")
    assert "applicability" not in followup.friction_keys
    assert followup.stance == "CONDITIONAL"
    assert get_case(CASE["id"]).runtime.applicability_condition in followup.uncertainties
    assert get_case(CASE["id"]).runtime.protocol_condition in followup.uncertainties


@pytest.mark.parametrize("role", [Role.RADIOLOGY, *agents.APPLICABILITY_ROLES])
async def test_crc_residual_conditions_survive_model_omission_and_followup(role: Role) -> None:
    state = RunState(role, CASE["id"], "followup", ["Review liver clearance and chest CT"])
    tool = (
        "compare_imaging" if role == Role.RADIOLOGY else f"assess_{role.value}_applicability"
    )
    await agents._execute_tool(state, tool, "{}", _discard)
    position = agents._rehearsal_position(state)
    position.uncertainties = []
    position.trace.uncertainties = []
    position.autonomy = "AUTO"
    result = agents._safety_gates(position, state)
    assert result.autonomy == "REVIEW"
    assert result.stance == "CONDITIONAL"
    assert not result.friction_keys
    assert set(get_case(CASE["id"]).runtime.residual_conditions) <= set(result.uncertainties)
    assert set(get_case(CASE["id"]).runtime.residual_conditions) <= set(
        result.trace.uncertainties
    )


@pytest.mark.parametrize("role", list(Role))
async def test_crc_role_outputs_are_grounded_without_old_case_leakage(role: Role) -> None:
    for phase in ("initial", "followup"):
        result = await _run(role, phase=phase, guidance=["Review liver clearance and chest CT"])
        text = result.model_dump_json().lower()
        for obsolete in ("synthetic", "syn-", "noor", "checkmate", "pneumonitis", "pd-l1"):
            assert obsolete not in text
        assert result.case_id == "CASE-MDT-CRC-BRAF-2026-001"
        if role in agents.APPLICABILITY_ROLES:
            assert {"CRC-BREAKWATER", "CRC-CAIRO5", "CRC-PROVENC3"} <= set(result.provenance)


async def test_role_and_argument_tool_scopes_are_enforced() -> None:
    state = RunState(Role.PATHOLOGY, CASE["id"], "initial", [])
    with pytest.raises(AgentRuntimeError, match="allowlisted"):
        await agents._execute_tool(state, "compare_imaging", "{}", _discard)
    for arguments in ('{"case_id":"other"}', "null", "[]", "{broken"):
        with pytest.raises(AgentRuntimeError):
            await agents._execute_tool(state, "inspect_pathology", arguments, _discard)
    assert not state.results


async def test_grounding_rejects_invented_and_other_role_citations() -> None:
    state = RunState(Role.RADIOLOGY, CASE["id"], "initial", [])
    await agents._execute_tool(state, "compare_imaging", "{}", _discard)
    position = agents._rehearsal_position(state)
    for evidence_id in ("FAKE-STUDY", "CASE-CRC-ONCOLOGY"):
        changed = position.model_copy(deep=True)
        changed.claims[0].evidence_ids = [evidence_id]
        with pytest.raises(AgentRuntimeError, match="did not return"):
            agents._validate_grounding(changed, state)
    for claim in (
        "Source https://invented.invalid/study supports treatment.",
        "NCT99999999 supports treatment.",
        "See PMC999999999.",
    ):
        changed = position.model_copy(deep=True)
        changed.claims[0].claim = claim
        with pytest.raises(AgentRuntimeError, match="uncurated"):
            agents._validate_grounding(changed, state)
    for update in ({"role": Role.SURGERY}, {"case_id": "different-case"}):
        with pytest.raises(AgentRuntimeError, match="identity"):
            agents._validate_grounding(position.model_copy(update=update), state)


async def test_concurrent_analysis_does_not_mutate_scenario_or_leak_guidance() -> None:
    before = json.dumps(ROLE_CONTEXTS, sort_keys=True)
    targeted, untouched = await asyncio.gather(
        _run(Role.RADIOLOGY, phase="followup", guidance=["Review liver clearance"]),
        _run(Role.RADIOLOGY, phase="followup"),
    )
    assert targeted.friction_keys == []
    assert untouched.friction_keys == ["imaging"]
    assert json.dumps(ROLE_CONTEXTS, sort_keys=True) == before


async def test_azure_executes_selected_tools_and_real_sdk_strict_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = await _run(Role.RADIOLOGY)
    expected.position = "Model-authored semantic assessment is preserved."
    expected.friction_keys = []
    expected.autonomy = "AUTO"
    requests, clients = _mock_azure(
        monkeypatch,
        [
            _completion(tool="compare_imaging"),
            _completion(content=expected.model_dump_json()),
        ],
    )
    model_events: list[dict[str, Any]] = []
    envelopes: list[dict[str, Any]] = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        if "model" in payload:
            model_events.append(payload["model"])
            envelopes.append(payload)

    actual = await _run(Role.RADIOLOGY, mode="azure", emit=emit)
    assert actual.position == expected.position
    assert actual.friction_keys == ["imaging"]
    assert actual.autonomy == "ESCALATE"
    assert len(requests) == 2
    assert requests[0]["tool_choice"] == "required"
    assert all(request["reasoning"]["effort"] == "low" for request in requests)
    assert all(request["store"] is False for request in requests)
    assert [tool["name"] for tool in requests[0]["tools"]] == ["compare_imaging"]
    assert requests[-1]["text"]["format"]["type"] == "json_schema"
    assert requests[-1]["text"]["format"]["strict"] is True
    assert any(item.get("type") == "function_call_output" for item in requests[-1]["input"])
    tool_output = next(
        json.loads(item["output"]) for item in requests[-1]["input"]
        if item.get("type") == "function_call_output"
    )
    assert "derived_comparison" in tool_output["context"]
    assert tool_output["context"]["acquisition"] == CASE["dossier"]["imaging"]
    initial_context = json.loads(requests[0]["input"][1]["content"])
    assert "acquisition" not in initial_context["context"]
    assert initial_context["source_metadata"]["file"] == "case.md"
    assert len(model_events) == 2
    assert model_events[-1]["request_id"] == "req-mock"
    assert model_events[-1]["analysis_total_tokens"] == 600
    assert envelopes[-1]["deployment"] == "test-deployment"
    assert envelopes[-1]["model_request_id"] == "req-mock"
    assert envelopes[-1]["request_id"] == "req-mock"
    assert envelopes[-1]["token_usage"]["analysis_total_tokens"] == 600
    proof = [item for item in actual.trace.observations if item.startswith("ACTUAL AZURE CALL:")]
    assert len(proof) == 2
    assert all(
        "deployment=test-deployment" in item and "request_id=req-mock" in item for item in proof
    )
    assert actual.provenance == ["CASE-CRC-RADIOLOGY"]
    assert set(model_events[-1]) == {
        "deployment",
        "model",
        "request_id",
        "response_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "analysis_total_tokens",
        "step",
    }
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("tool", ["reconcile_toxicity", "assess_oncology_applicability"])
async def test_azure_applicability_gate_depends_on_executed_tool(
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
) -> None:
    expected = await _run(Role.ONCOLOGY, phase="followup")
    _mock_azure(
        monkeypatch,
        [
            _completion(tool=tool),
            *([_completion(content="Done")] if tool == "reconcile_toxicity" else []),
            _completion(content=expected.model_dump_json()),
        ],
    )
    result = await _run(Role.ONCOLOGY, phase="followup", mode="azure")
    assert ("applicability" not in result.friction_keys) == tool.endswith("_applicability")


@pytest.mark.parametrize(
    "invalid",
    [
        "no_tool",
        "other_role_tool",
        "bad_args",
        "invalid_json",
        "unknown_evidence",
        "wrong_identity",
    ],
)
async def test_azure_failure_is_explicit_without_rehearsal_fallback(
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    expected = await _run(Role.PATHOLOGY)
    if invalid == "unknown_evidence":
        expected.claims[0].evidence_ids = ["INVENTED"]
    if invalid == "wrong_identity":
        expected.case_id = "wrong-case"
    first = _completion(tool="inspect_pathology")
    if invalid == "no_tool":
        first = _completion(content="Trust me.")
    elif invalid == "other_role_tool":
        first = _completion(tool="compare_imaging")
    elif invalid == "bad_args":
        first = _completion(tool="inspect_pathology", arguments='{"case_id":"other"}')
    requests, clients = _mock_azure(
        monkeypatch,
        [
            first,
            _completion(content="{}" if invalid == "invalid_json" else expected.model_dump_json()),
        ],
    )
    events: list[dict[str, Any]] = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        if event == "UncertaintyRaised":
            events.append(payload)

    with pytest.raises(AgentRuntimeError):
        await _run(Role.PATHOLOGY, mode="azure", emit=emit)
    assert requests
    assert all(client.is_closed for client in clients)
    assert any(payload.get("error") for payload in events)


async def test_azure_tool_budget_and_client_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _completion(tool="inspect_pathology")
    response["output"] *= agents.MAX_TOOL_CALLS + 1
    _, clients = _mock_azure(monkeypatch, [response])
    with pytest.raises(AgentRuntimeError, match="hard budget"):
        await _run(Role.PATHOLOGY, mode="azure")
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("role", list(agents.APPLICABILITY_ROLES))
async def test_model_step_budget_forces_final_structured_output(
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    expected = await _run(role, phase="followup")
    calls = 0

    def respond(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if "text" in body:
            return _completion(content=expected.model_dump_json())
        result = _completion(tool=agents.CORE_TOOLS[role])
        result["output"][0]["call_id"] = f"call-{calls}"
        return result

    requests, _ = _mock_azure(monkeypatch, respond)
    await _run(role, phase="followup", mode="azure")
    assert len(requests) == agents.MAX_MODEL_STEPS
    assert requests[-1]["text"]["format"]["type"] == "json_schema"
    outputs = [
        json.loads(item["output"]) for item in requests[-1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert len(outputs) == 3
    assert all(outputs[0]["context"][key] == value for key, value in ROLE_CONTEXTS[role].items())
    assert all("first tool output" in item["context_reference"] for item in outputs[1:])
    assert all(not set(item["context"]) & set(ROLE_CONTEXTS[role]) for item in outputs[1:])
    assert all(item["evidence"] == [] for item in outputs[1:])
    assert all(
        set(item["previously_returned_evidence_ids"])
        == {item.id for item in get_case(CASE["id"]).role_evidence(role)}
        for item in outputs[1:]
    )


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("phase", ["initial", "followup"])
async def test_every_crc_role_phase_reserves_budget_and_receives_complete_role_data(
    monkeypatch: pytest.MonkeyPatch, role: Role, phase: str,
) -> None:
    expected = await _run(role, phase=phase)
    responses = [_completion(tool=agents.CORE_TOOLS[role])]
    if phase == "followup" and role in agents.APPLICABILITY_ROLES:
        assessment = _completion(tool=f"assess_{role.value}_applicability")
        assessment["output"][0]["call_id"] = "call-applicability"
        responses.append(assessment)
    responses.append(_completion(content=expected.model_dump_json()))
    requests, _ = _mock_azure(monkeypatch, responses)
    await _run(role, phase=phase, mode="azure")
    assert len(requests) == (3 if phase == "followup" and role in agents.APPLICABILITY_ROLES else 2)
    first_message = json.loads(requests[0]["input"][1]["content"])
    assert "dossier" not in first_message
    assert "management_alternatives" not in first_message
    assert "management_options" not in first_message
    assert first_message["source_metadata"]["sha256"] == CASE["source_metadata"]["sha256"]
    assert set(first_message["context"]) == {"workspace", "question"}
    output = next(
        json.loads(item["output"]) for item in requests[-1]["input"]
        if item.get("type") == "function_call_output"
    )
    for key, value in ROLE_CONTEXTS[role].items():
        assert output["context"][key] == value
    for request in requests:
        assert request["max_output_tokens"] == 2000
    assert agents.MAX_TOTAL_TOKENS == 48000


async def test_token_budget_prevents_request(monkeypatch: pytest.MonkeyPatch) -> None:
    requests, clients = _mock_azure(monkeypatch, [])
    monkeypatch.setattr(agents, "MAX_TOTAL_TOKENS", 1)
    with pytest.raises(AgentRuntimeError, match="Token budget"):
        await _run(Role.PATHOLOGY, mode="azure")
    assert not requests
    assert all(client.is_closed for client in clients)


async def test_timeout_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(state: RunState, emit: agents.Emit) -> Position:
        await asyncio.sleep(1)
        raise AssertionError("Should have timed out")

    monkeypatch.setattr(agents, "_azure_position", slow)
    monkeypatch.setattr(agents, "MAX_SECONDS", 0.001)
    with pytest.raises(AgentRuntimeError, match="TimeoutError"):
        await _run(Role.PATHOLOGY, mode="azure")


@pytest.mark.parametrize("failure", [httpx2.ReadTimeout, httpx2.ConnectError])
@pytest.mark.parametrize("failed_stage", ["tool", "position"])
@pytest.mark.parametrize("failures", [1, 2])
async def test_transport_retry_is_bounded_without_repeating_tools_or_falling_back(
    monkeypatch: pytest.MonkeyPatch,
    failure: type[httpx2.TransportError],
    failed_stage: str,
    failures: int,
) -> None:
    expected = await _run(Role.ONCOLOGY)
    attempts = {"tool": 0, "position": 0}
    events: list[tuple[str, dict[str, Any]]] = []

    def respond(body: dict[str, Any]) -> dict[str, Any]:
        stage = "position" if "text" in body else "tool"
        attempts[stage] += 1
        if stage == failed_stage and attempts[stage] <= failures:
            raise failure("Demonstration transport interruption")
        return (
            _completion(content=expected.model_dump_json())
            if stage == "position"
            else _completion(tool=agents.CORE_TOOLS[Role.ONCOLOGY])
        )

    def no_fallback(state: RunState) -> Position:
        raise AssertionError("A transport failure must never run rehearsal.")

    async def emit(event: str, payload: dict[str, Any]) -> None:
        events.append((event, payload))

    requests, clients = _mock_azure(monkeypatch, respond)
    monkeypatch.setattr(agents, "TRANSPORT_RETRY_DELAY_SECONDS", 0.001)
    monkeypatch.setattr(agents, "_rehearsal_position", no_fallback)
    if failures == 1:
        result = await _run(Role.ONCOLOGY, mode="azure", emit=emit)
        assert result.role == Role.ONCOLOGY
        assert "applicability" in result.friction_keys
        assert len(requests) == 3
    else:
        with pytest.raises(AgentRuntimeError, match="API(?:Timeout|Connection)Error"):
            await _run(Role.ONCOLOGY, mode="azure", emit=emit)
        assert attempts[failed_stage] == agents.MAX_TRANSPORT_RETRIES + 1
        assert any(payload.get("error") for _, payload in events)
    retries = [payload for event, payload in events if event == "ReviewRetryScheduled"]
    assert len(retries) == 1
    assert retries[0]["error_type"] in {"APITimeoutError", "APIConnectionError"}
    assert "no new conclusion" in retries[0]["summary"]
    tool_starts = [payload for event, payload in events if event == "ToolStarted"]
    assert len(tool_starts) == (0 if failures == 2 and failed_stage == "tool" else 1)
    assert all(client.is_closed for client in clients)


async def test_transport_retry_respects_pacing_and_overall_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times: list[float] = []

    async def request() -> agents.Response:
        times.append(asyncio.get_running_loop().time())
        if len(times) == 1:
            raise agents.APIConnectionError(
                request=httpx2.Request("POST", "https://demo.openai.azure.com")
            )
        return agents.Response.model_construct()

    monkeypatch.setattr(agents, "TRANSPORT_RETRY_DELAY_SECONDS", 0.001)
    await agents._azure_request(request, _discard, interval_seconds=0.03)
    assert times[1] - times[0] >= 0.03
    times.clear()
    agents._AZURE_NEXT_REQUEST[asyncio.get_running_loop()] = 0
    monkeypatch.setattr(agents, "TRANSPORT_RETRY_DELAY_SECONDS", 1)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.02):
            await agents._azure_request(request, _discard, interval_seconds=0)
    assert len(times) == 1


async def test_transport_and_rate_limit_retries_have_separate_finite_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = await _run(Role.PATHOLOGY)
    calls = 0

    def respond(body: dict[str, Any]) -> dict[str, Any] | httpx2.Response:
        nonlocal calls
        calls += 1
        if calls in (1, 3):
            return httpx2.Response(429, headers={"retry-after": "0.001"}, json={
                "error": {"message": "Demonstration rate limit", "type": "rate_limit_error"}
            })
        if calls == 2:
            raise httpx2.ReadTimeout("Demonstration timeout")
        if "text" in body:
            return _completion(content=expected.model_dump_json())
        return _completion(tool="inspect_pathology")

    _mock_azure(monkeypatch, respond)
    monkeypatch.setattr(agents, "TRANSPORT_RETRY_DELAY_SECONDS", 0.001)
    result = await _run(Role.PATHOLOGY, mode="azure")
    assert calls == 5
    assert result.case_id == CASE["id"]


@pytest.mark.parametrize("status", [400, 401, 403, 503])
async def test_transport_retry_does_not_retry_other_service_errors(
    monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    requests, clients = _mock_azure(monkeypatch, [
        httpx2.Response(status, json={"error": {"message": "Demonstration service failure"}})
    ])
    with pytest.raises(AgentRuntimeError):
        await _run(Role.PATHOLOGY, mode="azure")
    assert len(requests) == 1
    assert all(client.is_closed for client in clients)


async def test_missing_azure_config_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with pytest.raises(AgentRuntimeError, match="Azure requires"):
        await _run(Role.PATHOLOGY, mode="azure")


async def test_comparison_of_guidelines_does_not_resolve_imaging() -> None:
    result = await _run(
        Role.RADIOLOGY, phase="followup", guidance=["Compare the Dutch and EU guidelines"]
    )
    assert result.friction_keys == ["imaging"]


async def test_azure_credential_provider_and_clients_are_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = await _run(Role.PATHOLOGY)
    _, clients = _mock_azure(
        monkeypatch,
        [
            _completion(tool="inspect_pathology"),
            _completion(content=expected.model_dump_json()),
        ],
    )
    monkeypatch.delenv("AZURE_OPENAI_API_KEY")
    closed: list[bool] = []
    token_requests: list[str] = []

    class Credential:
        def __enter__(self) -> "Credential":
            return self

        def __exit__(self, *args: object) -> None:
            closed.append(True)

    def provider(credential: Credential, scope: str) -> Callable[..., Any]:
        assert isinstance(credential, Credential)
        assert scope == "https://ai.azure.com/.default"

        def token() -> str:
            token_requests.append(scope)
            return "demo-test-token"

        return token

    monkeypatch.setattr(agents, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(agents, "get_bearer_token_provider", provider)
    await _run(Role.PATHOLOGY, mode="azure")
    assert token_requests
    assert closed == [True]
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("failure", ["usage", "refusal", "truncation", "duplicate_call"])
async def test_azure_response_failures_remain_visible(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    response = _completion(tool="inspect_pathology")
    if failure == "usage":
        response.pop("usage")
    elif failure == "refusal":
        response = _completion(content="")
        response["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot respond."}]
    elif failure == "truncation":
        response["status"] = "incomplete"
        response["incomplete_details"] = {"reason": "max_output_tokens"}
    else:
        response["output"] *= 2
    _, clients = _mock_azure(monkeypatch, [response])
    with pytest.raises(AgentRuntimeError):
        await _run(Role.PATHOLOGY, mode="azure")
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("fail_one", [False, True])
@pytest.mark.parametrize("concurrency", [1, 3, 7])
async def test_live_semaphore_bounds_complete_role_loops_and_releases_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    fail_one: bool,
    concurrency: int,
) -> None:
    active = 0
    peak = 0
    queued = 0

    async def fake_live(state: RunState, emit: agents.Emit) -> Position:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await agents._execute_tool(state, agents.CORE_TOOLS[state.role], "{}", emit)
            await asyncio.sleep(0.01)
            if fail_one and state.role == Role.RADIOLOGY:
                raise AgentRuntimeError("Deliberate test failure")
            return agents._rehearsal_position(state)
        finally:
            active -= 1

    async def emit(event: str, payload: dict[str, Any]) -> None:
        nonlocal queued
        if payload.get("status") == "QUEUED":
            queued += 1

    monkeypatch.setattr(agents, "_azure_position", fake_live)
    settings = Settings(azure_max_concurrent_roles=concurrency)
    results = await asyncio.gather(
        *(_run(role, mode="azure", emit=emit, settings=settings) for role in Role),
        return_exceptions=True,
    )
    assert peak == concurrency
    assert active == 0
    assert queued == 7 - concurrency
    assert sum(isinstance(result, AgentRuntimeError) for result in results) == int(fail_one)
    assert sum(isinstance(result, Position) for result in results) == 7 - int(fail_one)


async def test_live_queue_timeout_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.get_running_loop()
    agents._AZURE_SEMAPHORES[loop] = asyncio.Semaphore(0)
    monkeypatch.setattr(agents, "MAX_QUEUE_SECONDS", 0.001)
    with pytest.raises(AgentRuntimeError, match="TimeoutError"):
        await _run(Role.PATHOLOGY, mode="azure")


async def test_queue_wait_does_not_consume_active_role_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_live(state: RunState, emit: agents.Emit) -> Position:
        await agents._execute_tool(state, agents.CORE_TOOLS[state.role], "{}", emit)
        return agents._rehearsal_position(state)

    monkeypatch.setattr(agents, "_azure_position", fake_live)
    monkeypatch.setattr(agents, "MAX_SECONDS", 0.2)
    monkeypatch.setattr(agents, "MAX_QUEUE_SECONDS", 3)
    semaphore = asyncio.Semaphore(0)
    agents._AZURE_SEMAPHORES[asyncio.get_running_loop()] = semaphore
    task = asyncio.create_task(_run(Role.PATHOLOGY, mode="azure"))
    await asyncio.sleep(0.3)
    assert not task.done()
    semaphore.release()
    assert (await task).role == Role.PATHOLOGY


@pytest.mark.parametrize("rate_limits", [2, 3])
async def test_429_retry_is_bounded_and_preserves_client_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    rate_limits: int,
) -> None:
    expected = await _run(Role.PATHOLOGY)
    calls = 0

    def respond(body: dict[str, Any]) -> dict[str, Any] | httpx2.Response:
        nonlocal calls
        calls += 1
        if calls <= rate_limits:
            return httpx2.Response(
                429,
                headers={"retry-after": "0.001"},
                json={"error": {"message": "Synthetic rate limit", "type": "rate_limit_error"}},
            )
        if calls == rate_limits + 1:
            return _completion(tool="inspect_pathology")
        if "text" in body:
            return _completion(content=expected.model_dump_json())
        return _completion(content="Ready")

    requests, clients = _mock_azure(monkeypatch, respond)
    if rate_limits > agents.MAX_RATE_LIMIT_RETRIES:
        with pytest.raises(AgentRuntimeError, match="RateLimitError"):
            await _run(Role.PATHOLOGY, mode="azure")
        assert len(requests) == agents.MAX_RATE_LIMIT_RETRIES + 1
    else:
        result = await _run(Role.PATHOLOGY, mode="azure")
        assert result.role == Role.PATHOLOGY
        assert len(requests) == rate_limits + 2
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"retry-after": "60"}, 60.0),
        ({"retry-after-ms": "1500"}, 1.5),
        ({"retry-after": "Thu, 01 Jan 1970 00:00:00 GMT"}, 0.0),
        ({}, 2.0),
    ],
)
def test_retry_after_supports_seconds_milliseconds_and_http_dates(
    headers: dict[str, str],
    expected: float,
) -> None:
    response = httpx2.Response(
        429, headers=headers, request=httpx2.Request("POST", "https://demo.openai.azure.com")
    )
    error = agents.RateLimitError("Synthetic rate limit", response=response, body=None)
    assert agents._retry_after(error, 0) == expected


@pytest.mark.parametrize("value", ["61", "NaN", "infinity", "invalid"])
def test_invalid_or_excessive_retry_after_never_causes_early_retry(value: str) -> None:
    response = httpx2.Response(
        429,
        headers={"retry-after": value},
        request=httpx2.Request("POST", "https://demo.openai.azure.com"),
    )
    error = agents.RateLimitError("Synthetic rate limit", response=response, body=None)
    with pytest.raises(AgentRuntimeError):
        agents._retry_after(error, 0)


async def test_live_retry_waits_at_least_retry_after_and_emits_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = await _run(Role.PATHOLOGY)
    timestamps: list[float] = []
    cooldowns: list[dict[str, Any]] = []

    def respond(body: dict[str, Any]) -> dict[str, Any] | httpx2.Response:
        timestamps.append(asyncio.get_running_loop().time())
        if len(timestamps) == 1:
            return httpx2.Response(
                429,
                headers={"retry-after": "0.02"},
                json={"error": {"message": "Synthetic rate limit", "type": "rate_limit_error"}},
            )
        if "text" in body:
            return _completion(content=expected.model_dump_json())
        return _completion(tool="inspect_pathology")

    async def emit(event: str, payload: dict[str, Any]) -> None:
        if payload.get("status") == "RATE_LIMITED":
            cooldowns.append(payload)

    _mock_azure(monkeypatch, respond)
    await _run(Role.PATHOLOGY, mode="azure", emit=emit)
    assert len(timestamps) == 3
    assert timestamps[1] - timestamps[0] >= 0.02
    assert len(cooldowns) == 1
    assert cooldowns[0]["retry_after_seconds"] == 0.02


async def test_exhausted_retries_preserve_cooldown_for_next_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def respond(body: dict[str, Any]) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(
            429,
            headers={"retry-after": "60" if calls == 3 else "0.001"},
            json={"error": {"message": "Synthetic rate limit", "type": "rate_limit_error"}},
        )

    _mock_azure(monkeypatch, respond)
    with pytest.raises(AgentRuntimeError, match="RateLimitError"):
        await _run(Role.PATHOLOGY, mode="azure")
    loop = asyncio.get_running_loop()
    assert calls == 3
    assert agents._AZURE_NEXT_REQUEST[loop] - loop.time() > 59


async def test_request_pacing_is_shared_across_complete_role_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamps: list[float] = []

    async def request() -> agents.Response:
        timestamps.append(asyncio.get_running_loop().time())
        return agents.Response.model_construct()

    async def fake_live(state: RunState, emit: agents.Emit) -> Position:
        await agents._azure_request(request, emit)
        await agents._execute_tool(state, agents.CORE_TOOLS[state.role], "{}", emit)
        await agents._azure_request(request, emit)
        return agents._rehearsal_position(state)

    monkeypatch.setattr(agents, "_azure_position", fake_live)
    monkeypatch.setenv("MDT_AZURE_REQUEST_INTERVAL_SECONDS", "0.02")
    await asyncio.gather(*(_run(role, mode="azure") for role in Role))
    assert len(timestamps) == 14
    assert all(
        later - earlier >= 0.02 for earlier, later in zip(timestamps, timestamps[1:], strict=False)
    )


@pytest.mark.parametrize("concurrency", [0, 8, 1.5, "invalid"])
def test_invalid_live_concurrency_is_rejected(concurrency: Any) -> None:
    with pytest.raises(agents.ValidationError):
        Settings(azure_max_concurrent_roles=concurrency)


@pytest.mark.parametrize("interval", [-1, 61, float("nan"), float("inf")])
def test_invalid_request_pacing_is_rejected(interval: float) -> None:
    with pytest.raises(agents.ValidationError):
        Settings(azure_request_interval_seconds=interval)


async def test_explicit_application_settings_control_model_request_pacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = await _run(Role.PATHOLOGY)
    intervals: list[float | None] = []
    original = agents._azure_request

    def respond(body: dict[str, Any]) -> dict[str, Any]:
        if "text" in body:
            return _completion(content=expected.model_dump_json())
        return _completion(tool="inspect_pathology")

    async def record_interval(
        request: Callable[[], Awaitable[agents.Response]],
        emit: agents.Emit,
        *,
        interval_seconds: float | None = None,
    ) -> agents.Response:
        intervals.append(interval_seconds)
        return await original(request, emit, interval_seconds=interval_seconds)

    requests, _ = _mock_azure(monkeypatch, respond)
    monkeypatch.setattr(agents, "_azure_request", record_interval)
    settings = Settings(azure_request_interval_seconds=0.02)
    await _run(Role.PATHOLOGY, mode="azure", settings=settings)
    assert len(requests) == 2
    assert intervals == [0.02, 0.02]


async def test_rate_limit_cooldown_is_shared_with_concurrent_requests() -> None:
    timestamps: list[float] = []
    attempts = 0

    async def limited_request() -> agents.Response:
        nonlocal attempts
        timestamps.append(asyncio.get_running_loop().time())
        attempts += 1
        if attempts == 1:
            response = httpx2.Response(
                429,
                headers={"retry-after": "0.04"},
                request=httpx2.Request("POST", "https://demo.openai.azure.com"),
            )
            raise agents.RateLimitError("Synthetic rate limit", response=response, body=None)
        return agents.Response.model_construct()

    async def other_request() -> agents.Response:
        timestamps.append(asyncio.get_running_loop().time())
        return agents.Response.model_construct()

    await asyncio.gather(
        agents._azure_request(limited_request, _discard, interval_seconds=0),
        agents._azure_request(other_request, _discard, interval_seconds=0),
    )
    assert len(timestamps) == 3
    assert all(timestamp - timestamps[0] >= 0.04 for timestamp in timestamps[1:])


async def test_rehearsal_shows_all_autonomy_modes_without_automatic_treatment() -> None:
    positions = await asyncio.gather(*(_run(role) for role in Role))
    assert {position.autonomy for position in positions} == {"AUTO", "REVIEW", "ESCALATE"}
    pathology = next(position for position in positions if position.role == Role.PATHOLOGY)
    assert pathology.autonomy == "AUTO"
    assert pathology.stance == "CONDITIONAL"
    assert "before any treatment decision" in pathology.recommendation
    assert pathology.provenance == ["CASE-CRC-PATHOLOGY"]
    assert not any(
        "ACTUAL AZURE CALL" in observation
        for position in positions
        for observation in position.trace.observations
    )


async def test_api_error_reports_safe_identifiers_without_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, clients = _mock_azure(
        monkeypatch,
        [
            httpx2.Response(
                400,
                headers={"x-request-id": "req-safe-test"},
                json={
                    "error": {
                        "message": "DO-NOT-LOG demo prompt/body secret",
                        "type": "invalid_request_error",
                        "code": "invalid_parameter",
                    }
                },
            )
        ],
    )
    errors: list[dict[str, Any]] = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        if payload.get("error"):
            errors.append(payload)

    with pytest.raises(AgentRuntimeError) as captured:
        await _run(Role.PATHOLOGY, mode="azure", emit=emit)
    assert errors[-1]["status_code"] == 400
    assert errors[-1]["request_id"] == "req-safe-test"
    assert errors[-1]["error_code"] == "invalid_parameter"
    assert "status_code=400" in str(captured.value)
    assert "req-safe-test" in str(captured.value)
    assert "DO-NOT-LOG" not in json.dumps(errors)
    assert "DO-NOT-LOG" not in str(captured.value)
    assert captured.value.__suppress_context__
    assert all(client.is_closed for client in clients)
