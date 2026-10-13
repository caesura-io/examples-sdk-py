"""Deterministic four-turn checks: both upstream APIs are mocked."""

from __future__ import annotations

import copy
import json
from typing import Any

import httpx
import pytest
import respx
from caesura_core import CaesuraEvent, MemoryCaesuraStore
from caesura_openai import CaesuraOpenAIOptions, create_async_caesura
from openai import AsyncOpenAI

from scripts.check_conversations import SCENARIOS, TEXT, run_scenario, verify_saved_conversation

# This module sets fake credentials before the example app is imported.
from tests.test_chat import mock_openai

CONVERSATION_URL = "https://api.caesurao.com/api/conversation"
ANALYZE_URL = "https://api.caesurao.com/api/analyze"


def saved_row(turn: int) -> dict[str, Any]:
    return {
        "id": turn + 1,
        "text": TEXT,
        "speakerName": "Customer",
        "speakerIndex": 1,
        "analysisJsonOpenai": {"guidance": "Keep it brief."} if turn == 0 else {"isSame": True},
    }


@pytest.mark.parametrize("scenario", list(SCENARIOS))
@respx.mock
async def test_four_turns_save_dialogue_but_buffer_only_one_guidance(scenario: str) -> None:
    rows: list[dict[str, Any]] = []
    conversation_id = "created-conversation"
    creation = respx.post(CONVERSATION_URL).respond(200, json={"id": conversation_id})

    def analyze(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["persist"] is True
        assert body["sessionId"] == body["conversationId"] == conversation_id
        assert body["calculateSimilarities"] is True
        assert body["similarityThreshold"] == 0.5
        assert body.get("notifyIntegrations") is not True
        assert request.headers["authorization"] == "Bearer caesura_test"
        turn = len(rows)
        messages = body["messages"]
        dialogue = [message for message in messages if message["speakerRole"] == "user"]
        context = [message for message in messages if message["speakerRole"] == "assistant"]
        assert len(dialogue) == turn * 2 + 1
        assert len(context) == (0 if turn == 0 else 1)
        assert [(m["text"], m["speakerName"], m["speakerIndex"]) for m in dialogue] == [
            (TEXT, "Customer" if index % 2 == 0 else "Agent", 1 if index % 2 == 0 else 0)
            for index in range(turn * 2 + 1)
        ]
        last = messages[-1]
        # Emulate the backend's persistence of the LAST message, exposing misplaced analysis context.
        row = saved_row(turn)
        row.update(text=last["text"], speakerName=last.get("speakerName"), speakerIndex=last.get("speakerIndex", 0))
        rows.append(row)
        return httpx.Response(200, json=row["analysisJsonOpenai"])

    analysis = respx.post(ANALYZE_URL).mock(side_effect=analyze)
    fetched = respx.get(CONVERSATION_URL, params={"conversationId": conversation_id}).mock(
        side_effect=lambda _: httpx.Response(200, json={"conversation": {"id": conversation_id, "analyses": rows}}),
    )
    providers = [mock_openai(api) for api in sorted(set(SCENARIOS[scenario]))]
    store = MemoryCaesuraStore()
    events: list[CaesuraEvent] = []
    errors: list[Any] = []
    async with AsyncOpenAI(api_key="sk-test-openai") as raw:
        client = create_async_caesura(
            raw,
            CaesuraOpenAIOptions(
                api_key="caesura_test",
                mode="sync",
                persist=True,
                calculate_similarities=True,
                similarity_threshold=0.5,
                store=store,
                on_event=events.append,
                on_error=errors.append,
            ),
        )
        summary = await run_scenario(scenario, client, store, events, errors)
    assert creation.call_count == fetched.call_count == 1
    assert creation.calls.last.request.headers["authorization"] == "Bearer caesura_test"
    assert fetched.calls.last.request.headers["authorization"] == "Bearer caesura_test"
    assert analysis.call_count == sum(route.call_count for route in providers) == 4
    assert summary["saved_rows"] == 4
    assert summary["duplicate_responses"] == 3
    assert summary["buffered_guidance"] == 1
    assert [turn["is_same"] for turn in summary["turns"]] == [None, True, True, True]
    assert [turn["injected_guidance"] for turn in summary["turns"]] == [1, 1, 1, 1]
    assert len(store.get(conversation_id).recommendations) == 1
    for route in providers:
        for call in route.calls:
            assert call.request.headers["authorization"] == "Bearer sk-test-openai"
            body = json.loads(call.request.content)
            supplied = body.get("input", body.get("messages"))
            original = [message for message in supplied if message.get("content") == TEXT]
            assert [message["role"] for message in original] == [
                "user" if i % 2 == 0 else "assistant" for i in range(len(original))
            ]


@pytest.mark.parametrize("corruption", ["text", "name", "index", "analysis", "duplicate-id"])
def test_saved_row_validation_rejects_content_regressions(corruption: str) -> None:
    rows = [saved_row(index) for index in range(4)]
    broken = copy.deepcopy(rows)
    if corruption == "text":
        broken[-1]["text"] = '{"guidance":"not dialogue"}'
    elif corruption == "name":
        broken[-1]["speakerName"] = "Agent"
    elif corruption == "index":
        broken[-1]["speakerIndex"] = 0
    elif corruption == "analysis":
        del broken[-1]["analysisJsonOpenai"]
    else:
        broken[-1]["id"] = broken[0]["id"]
    with pytest.raises(AssertionError):
        verify_saved_conversation({"conversation": {"id": "c1", "analyses": broken}}, "c1")


@respx.mock
async def test_fetch_endpoint_returns_saved_rows_and_uses_only_caesura_key() -> None:
    payload = {"conversation": {"id": "c1", "analyses": [saved_row(index) for index in range(4)]}}
    route = respx.get(CONVERSATION_URL, params={"conversationId": "c1"}).respond(200, json=payload)
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/caesura/conversations/c1")
    assert response.status_code == 200
    assert response.json() == payload
    assert route.calls.last.request.headers["authorization"] == "Bearer caesura_test"
    verify_saved_conversation(response.json(), "c1")


@pytest.mark.parametrize("status", [401, 404, 500])
@respx.mock
async def test_fetch_endpoint_reports_upstream_failure(status: int) -> None:
    respx.get(CONVERSATION_URL).respond(status, json={"error": "upstream failure"})
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/caesura/conversations/c1")
    assert response.status_code == (status if status < 500 else 502)
