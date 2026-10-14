"""Published SDK usage across client types, analysis modes, APIs, and streams."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, Literal

import httpx
import pytest
import respx
from caesura_core import AnalysisContext, AnalyzeMessage, CaesuraEvent, CustomerTurn, MemoryCaesuraStore
from caesura_openai import CaesuraOpenAIOptions, SpeakerNames, create_async_caesura, create_caesura
from openai import AsyncOpenAI, OpenAI

from tests.test_chat import CAESURA_URL, GUIDANCE, endpoint, mock_openai, post


@pytest.mark.parametrize("client_type", ["sync", "async"])
@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("api", ["chat", "responses"])
@pytest.mark.parametrize("stream", [False, True])
@respx.mock
async def test_clients_modes_and_streams(
    client_type: str, mode: Literal["sync", "async"], api: str, stream: bool
) -> None:
    analysis_value = {"next-step": GUIDANCE, "Exact Key": False, "zero": 0}
    analysis = respx.post(CAESURA_URL).respond(200, json=analysis_value)
    provider = mock_openai(api, stream)
    store = MemoryCaesuraStore()
    errors: list[Any] = []
    options = CaesuraOpenAIOptions(
        api_key="caesura_test",
        mode=mode,
        persist=False,
        store=store,
        speaker_names=SpeakerNames(agent="Support", customer="Customer"),
        on_error=errors.append,
    )
    client: Any = (
        create_caesura(OpenAI(api_key="sk-test-openai", max_retries=0), options)
        if client_type == "sync"
        else create_async_caesura(AsyncOpenAI(api_key="sk-test-openai", max_retries=0), options)
    )
    history = [{"role": "user", "content": "Help me prepare for a meeting."}]
    original = copy.deepcopy(history)
    kwargs = {"model": "gpt-5.4-mini", "stream": stream, "caesura_conversation_id": "isolated-check"}
    kwargs["messages" if api == "chat" else "input"] = history
    create = client.chat.completions.create if api == "chat" else client.responses.create

    def call_sync() -> list[Any]:
        result = create(**kwargs)
        return list(result) if stream else [result]

    async def wait_for_analysis(turn: int) -> None:
        while store.get("isolated-check").in_flight or len(store.get("isolated-check").recommendations) < turn:
            assert not errors
            await asyncio.sleep(0.01)

    try:
        for turn in (1, 2):
            kwargs["caesura_context"] = AnalysisContext(
                turn=CustomerTurn(str(turn), AnalyzeMessage("user", original[0]["content"]))
            )
            if client_type == "sync":
                output = await asyncio.to_thread(call_sync)
            else:
                result = await create(**kwargs)
                output = [event async for event in result] if stream else [result]
            assert "Hello!" in json.dumps([item.model_dump() for item in output])
            await asyncio.wait_for(wait_for_analysis(turn), timeout=5)
        assert not errors
        assert history == original  # Injected guidance never becomes application dialogue.
        assert analysis.call_count == provider.call_count == 2
        assert store.get("isolated-check").recommendations[0].analysis == analysis_value
        upstream = json.loads(provider.calls.last.request.content)
        assert GUIDANCE in json.dumps(upstream.get("messages", upstream.get("input")))
        for call in analysis.calls:
            body = json.loads(call.request.content)
            assert body["currentUser"] == "Support"
            assert body["persist"] is False
            assert body.get("notifyIntegrations") is not True
            assert "kind" not in body and "callType" not in body
            dialogue = [m for m in body["messages"] if m["speakerRole"] == "user"]
            assert [(m["speakerName"], m["speakerIndex"], m["text"]) for m in dialogue] == [
                ("Customer", 1, original[0]["content"])
            ]
            assert all(m["speakerIndex"] == -1 for m in body["messages"] if m["speakerRole"] == "assistant")
    finally:
        if client_type == "sync":
            client.close()
        else:
            await client.close()


@pytest.mark.parametrize("api", ["chat", "responses"])
@respx.mock
async def test_routes_preserve_explicit_speaker_indices(api: str) -> None:
    analysis = respx.post(CAESURA_URL).respond(200, json={"next step": GUIDANCE})
    mock_openai(api)
    history = [
        {"role": "assistant", "content": "Synthetic agent turn", "speakerIndex": 7},
        {"role": "user", "content": "Synthetic customer turn", "speakerIndex": 0},
    ]
    body = (
        {"messages": history, "conversationId": f"explicit-indices-{api}"}
        if api == "chat"
        else {"input": history, "conversationId": f"explicit-indices-{api}"}
    )
    assert (await post(endpoint(api), body)).status_code == 200
    messages = json.loads(analysis.calls.last.request.content)["messages"]
    assert [(m["speakerRole"], m["speakerIndex"]) for m in messages] == [("user", 7), ("user", 0)]


@pytest.mark.parametrize("value", [0, False, None, ["text", 1], {"next step": "Proceed", "Exact.Key": 0}])
@respx.mock
def test_analysis_values_keep_their_shape(value: Any) -> None:
    respx.post(CAESURA_URL).respond(200, content=json.dumps(value), headers={"content-type": "application/json"})
    mock_openai("responses")
    store = MemoryCaesuraStore()
    events: list[CaesuraEvent] = []
    with create_caesura(
        OpenAI(api_key="sk-test-openai"),
        CaesuraOpenAIOptions(api_key="caesura_test", mode="sync", persist=False, store=store, on_event=events.append),
    ) as client:
        client.responses.create(model="gpt-5.4-mini", input="Synthetic dialogue", caesura_conversation_id="values")
    recommendations = store.get("values").recommendations
    responses = [event for event in events if event.type == "response"]
    assert len(responses) == 1
    assert responses[0].analysis == value
    assert type(responses[0].analysis) is type(value)
    if value is None:
        assert not recommendations  # Null is a valid response but carries no guidance to buffer.
        return
    assert len(recommendations) == 1
    assert recommendations[0].analysis == value
    assert type(recommendations[0].analysis) is type(value)


@respx.mock
def test_explicit_creation_and_reuse_across_apis() -> None:
    respx.get("https://api.caesurao.com/api/conversation/messages").mock(
        side_effect=lambda request: httpx.Response(
            200, json={"success": True, "conversationId": request.url.params["conversationId"], "nextMessageId": 1}
        )
    )
    respx.post("https://api.caesurao.com/api/conversation/messages").mock(
        side_effect=lambda request: httpx.Response(200, json={"success": True, **json.loads(request.content)})
    )
    creation = respx.post("https://api.caesurao.com/api/conversation").respond(200, json={"id": "backend-id"})
    analysis = respx.post(CAESURA_URL).respond(200, json={"guidance": GUIDANCE})
    mock_openai("chat")
    mock_openai("responses")
    store = MemoryCaesuraStore()
    with create_caesura(
        OpenAI(api_key="sk-test-openai"),
        CaesuraOpenAIOptions(api_key="caesura_test", mode="sync", store=store),
    ) as client:
        conversation_id = client.create_conversation()
        assert conversation_id is not None
        client.responses.create(model="gpt-5.4-mini", input="Hello", caesura_conversation_id=conversation_id)
        client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[{"role": "assistant", "content": "Hello"}],
            caesura_conversation_id=conversation_id,
        )
        store.clear(conversation_id)
        client.responses.create(model="gpt-5.4-mini", input="Next", caesura_conversation_id=conversation_id)
    assert creation.call_count == 1
    assert analysis.call_count == 2
    assert all(json.loads(call.request.content)["sessionId"] == conversation_id for call in analysis.calls)


@respx.mock
def test_missing_id_rejected_without_provider_or_analysis_calls() -> None:
    with (
        create_caesura(
            OpenAI(api_key="sk-test-openai"),
            CaesuraOpenAIOptions(api_key="caesura_test", mode="sync", persist=False),
        ) as client,
        pytest.raises(ValueError, match="conversation"),
    ):
        client.responses.create(model="gpt-5.4-mini", input="Hello")
    assert not respx.calls
