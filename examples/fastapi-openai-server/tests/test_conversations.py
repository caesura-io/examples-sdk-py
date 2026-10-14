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
        turn = sum(bool(row["analysisJsonOpenai"]) for row in rows)
        messages = body["messages"]
        dialogue = [message for message in messages if message["speakerRole"] == "user"]
        context = [message for message in messages if message["speakerRole"] == "assistant"]
        assert len(dialogue) == turn * 2 + 1
        assert len(context) == (0 if turn == 0 else 1)
        assert [(m["text"], m["speakerName"], m["speakerIndex"]) for m in dialogue] == [
            (
                TEXT if index % 2 == 0 else "Hello!",
                "Customer" if index % 2 == 0 else "Agent",
                1 if index % 2 == 0 else 0,
            )
            for index in range(turn * 2 + 1)
        ]
        row = next(row for row in rows if row["messageId"] == body["transcriptMessageId"])
        row["analysisJsonOpenai"] = {"guidance": "Keep it brief."} if turn == 0 else {"isSame": True}
        return httpx.Response(200, json=row["analysisJsonOpenai"])

    def save(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        for message in body["messages"]:
            if any(row["messageId"] == message["id"] for row in rows):
                continue
            customer = message["role"] == "user"
            rows.append(
                {
                    "id": len(rows) + 1,
                    "messageId": message["id"],
                    "text": message["text"],
                    "speakerName": "Customer" if customer else "Agent",
                    "speakerIndex": 1 if customer else 0,
                    "analysisJsonOpenai": "",
                }
            )
        return httpx.Response(200, json={"success": True, **json.loads(request.content)})

    respx.get(CONVERSATION_URL + "/messages").respond(
        200, json={"success": True, "conversationId": conversation_id, "nextMessageId": 1}
    )
    uploads = respx.post(CONVERSATION_URL + "/messages").mock(side_effect=save)

    analysis = respx.post(ANALYZE_URL).mock(side_effect=analyze)
    fetched = respx.get(CONVERSATION_URL, params={"conversationId": conversation_id}).mock(
        side_effect=lambda _: httpx.Response(200, json={"conversation": {"id": conversation_id, "analyses": rows}}),
    )
    from tests.test_chat import CHAT_RESPONSE, RESPONSES_RESPONSE

    generation = 0

    def provider_response(request: httpx.Request) -> httpx.Response:
        nonlocal generation
        generation += 1
        payload = copy.deepcopy(CHAT_RESPONSE if "chat/completions" in str(request.url) else RESPONSES_RESPONSE)
        payload["id"] = f"generation-{generation}"
        return httpx.Response(200, json=payload)

    providers = [mock_openai(api).mock(side_effect=provider_response) for api in sorted(set(SCENARIOS[scenario]))]
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
    assert summary["saved_rows"] == uploads.call_count == 8
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
            original = [message for message in supplied if message.get("content") in (TEXT, "Hello!")]
            assert [message["role"] for message in original] == [
                "user" if i % 2 == 0 else "assistant" for i in range(len(original))
            ]


@pytest.mark.parametrize("corruption", ["text", "name", "index", "analysis", "duplicate-id"])
def test_saved_row_validation_rejects_content_regressions(corruption: str) -> None:
    rows = [saved_row(index) for index in range(8)]
    for index, row in enumerate(rows):
        if index % 2:
            row.update(text="Hello!", speakerName="Agent", speakerIndex=0)

    broken = copy.deepcopy(rows)
    if corruption == "text":
        broken[-2]["text"] = '{"guidance":"not dialogue"}'
    elif corruption == "name":
        broken[-2]["speakerName"] = "Agent"
    elif corruption == "index":
        broken[-2]["speakerIndex"] = 0
    elif corruption == "analysis":
        del broken[-1]["analysisJsonOpenai"]
    else:
        broken[-2]["id"] = broken[0]["id"]
    with pytest.raises(AssertionError):
        verify_saved_conversation({"conversation": {"id": "c1", "analyses": broken}}, "c1")


@respx.mock
async def test_fetch_endpoint_returns_saved_rows_and_uses_only_caesura_key() -> None:
    payload = {"conversation": {"id": "c1", "analyses": [saved_row(index) for index in range(8)]}}
    route = respx.get(CONVERSATION_URL, params={"conversationId": "c1"}).respond(200, json=payload)
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/caesura/conversations/c1")
    assert response.status_code == 200
    assert response.json() == payload
    assert route.calls.last.request.headers["authorization"] == "Bearer caesura_test"
    assert len(response.json()["conversation"]["analyses"]) == 8


@pytest.mark.parametrize("status", [401, 404, 500])
@respx.mock
async def test_fetch_endpoint_reports_upstream_failure(status: int) -> None:
    respx.get(CONVERSATION_URL).respond(status, json={"error": "upstream failure"})
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/caesura/conversations/c1")
    assert response.status_code == (status if status < 500 else 502)
