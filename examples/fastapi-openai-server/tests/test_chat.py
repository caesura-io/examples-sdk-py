"""Exercise the HTTP endpoints and inspect both mocked upstream requests."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx
from caesura_openai import CaesuraOpenAIOptions, create_async_caesura
from openai import AsyncOpenAI

# Override shell credentials/config before importing the singleton client.
os.environ["OPENAI_API_KEY"] = "sk-test-openai"
os.environ["CAESURA_API_KEY"] = "caesura_test"
os.environ["CAESURA_MODE"] = "sync"
os.environ["CAESURA_PERSIST"] = "false"

from app import main
from app.caesura_client import credit_meter
from app.config import settings
from app.main import app

CAESURA_URL = "https://api.caesurao.com/api/analyze"
GUIDANCE = "Be friendly and helpful."
ANALYSIS = {"recommendation": GUIDANCE, "observation": "User is asking for help."}

CHAT_RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
    "model": "gpt-5.4-mini",
}
RESPONSES_RESPONSE: dict[str, Any] = {
    "id": "resp-test",
    "object": "response",
    "created_at": 0,
    "status": "completed",
    "model": "gpt-5.4-mini",
    "output": [
        {
            "id": "msg-test",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "Hello!", "annotations": []}],
        }
    ],
}


async def post(path: str, body: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=body)


def mock_openai(api: str, stream: bool = False) -> respx.Route:
    url = "https://api.openai.com/v1/" + ("chat/completions" if api == "chat" else "responses")
    if not stream:
        return respx.post(url).respond(200, json=CHAT_RESPONSE if api == "chat" else RESPONSES_RESPONSE)
    event = (
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gpt-5.4-mini",
            "choices": [{"index": 0, "delta": {"content": "Hello!"}, "finish_reason": None}],
        }
        if api == "chat"
        else {
            "type": "response.output_text.delta",
            "delta": "Hello!",
            "item_id": "msg-test",
            "output_index": 0,
            "content_index": 0,
            "sequence_number": 1,
            "logprobs": [],
        }
    )
    terminal = (
        {**event, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        if api == "chat"
        else {"type": "response.completed", "response": RESPONSES_RESPONSE, "sequence_number": 2}
    )
    return respx.post(url).respond(
        200,
        text=f"data: {json.dumps(event)}\n\ndata: {json.dumps(terminal)}\n\ndata: [DONE]\n\n",
        headers={"content-type": "text/event-stream"},
    )


def request_body(api: str, conversation_id: str) -> dict[str, Any]:
    if api == "chat":
        return {"messages": [{"role": "user", "content": "Hello"}], "conversationId": conversation_id}
    return {"input": "Hello", "conversationId": conversation_id}


def endpoint(api: str) -> str:
    return "/v1/chat/completions" if api == "chat" else "/v1/responses"


@pytest.mark.parametrize("api", ["chat", "responses"])
@pytest.mark.parametrize("stream", [False, True])
@respx.mock
async def test_endpoints_analyze_inject_and_isolate_keys(api: str, stream: bool) -> None:
    caesura = respx.post(CAESURA_URL).respond(200, json=ANALYSIS, headers={"x-credit-usage": "0.25"})
    provider = mock_openai(api, stream)
    conversation_id = uuid4().hex
    body = request_body(api, conversation_id)
    path = endpoint(api)
    if stream:
        if api == "chat":
            body["stream"] = True
        else:
            path += "/stream"
    response = await post(path, body)
    assert response.status_code == 200
    assert caesura.call_count == provider.call_count == 1
    analysis_request = caesura.calls.last.request
    provider_request = provider.calls.last.request
    sent = json.loads(analysis_request.content)
    assert sent["conversationId"] == sent["sessionId"] == conversation_id
    assert sent.get("notifyIntegrations") is not True
    assert sent["persist"] is False
    assert [(m["speakerRole"], m["text"]) for m in sent["messages"]] == [("user", "Hello")]
    assert analysis_request.headers["authorization"] == "Bearer caesura_test"
    assert provider_request.headers["authorization"] == "Bearer sk-test-openai"
    assert analysis_request.headers["x-include-credit-usage"] == "true"
    assert credit_meter.total_by_conversation(conversation_id) == 0.25
    upstream = json.loads(provider_request.content)
    assert GUIDANCE in json.dumps(upstream.get("messages", upstream.get("input")))
    assert "caesura_conversation_id" not in upstream
    if stream:
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "Hello!" in response.text
        assert response.text.endswith("data: [DONE]\n\n")
    else:
        assert response.json()["id"] == ("chatcmpl-test" if api == "chat" else "resp-test")


@pytest.mark.parametrize("api", ["chat", "responses"])
@respx.mock
async def test_missing_conversation_ids_are_rejected(api: str) -> None:
    body = {"messages": [{"role": "user", "content": "Hello"}]} if api == "chat" else {"input": "Hello"}
    assert (await post(endpoint(api), body)).status_code == 422
    assert not respx.calls


@pytest.mark.parametrize("api", ["chat", "responses"])
@pytest.mark.parametrize("analysis", ["plain text", "custom object", "array"])
@respx.mock
async def test_analysis_without_recommendation_field_is_injected(api: str, analysis: str) -> None:
    if analysis == "plain text":
        respx.post(CAESURA_URL).respond(200, text=GUIDANCE, headers={"content-type": "text/plain"})
    else:
        payload = {"guidance": GUIDANCE} if analysis == "custom object" else [GUIDANCE]
        respx.post(CAESURA_URL).respond(200, json=payload)
    provider = mock_openai(api)
    assert (await post(endpoint(api), request_body(api, uuid4().hex))).status_code == 200
    upstream = json.loads(provider.calls.last.request.content)
    assert GUIDANCE in json.dumps(upstream.get("messages", upstream.get("input")))


@respx.mock
async def test_responses_history_excludes_tool_items_from_analysis() -> None:
    caesura = respx.post(CAESURA_URL).respond(200, json=ANALYSIS)
    provider = mock_openai("responses")
    history = [
        {"role": "user", "content": [{"type": "input_text", "text": "Hello"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Let me check."}]},
        {"type": "function_call", "call_id": "call-test", "name": "lookup", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call-test", "output": "tool-only data"},
        {"role": "user", "content": "Thanks"},
    ]
    response = await post("/v1/responses", {"input": history, "conversationId": uuid4().hex})
    assert response.status_code == 200
    assert [m for m in json.loads(provider.calls.last.request.content)["input"] if m in history] == history
    sent = json.loads(caesura.calls.last.request.content)["messages"]
    assert [(m["speakerRole"], m["text"]) for m in sent] == [
        ("user", "Hello"),
        ("user", "Let me check."),
        ("user", "Thanks"),
    ]


@respx.mock
async def test_chat_preserves_tool_call_pair_and_excludes_tool_data_from_analysis() -> None:
    caesura = respx.post(CAESURA_URL).respond(200, json=ANALYSIS)
    provider = mock_openai("chat")
    messages = [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "Let me check.",
            "tool_calls": [{"id": "call-test", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call-test", "content": "tool-only data"},
    ]
    response = await post("/v1/chat/completions", {"messages": messages, "conversationId": uuid4().hex})
    assert response.status_code == 200
    upstream = json.loads(provider.calls.last.request.content)["messages"]
    tool_index = next(i for i, message in enumerate(upstream) if message.get("tool_calls"))
    assert upstream[tool_index : tool_index + 2] == messages[1:]
    assert not caesura.called  # A tool continuation is not a new customer turn.


@pytest.mark.parametrize("path", ["/v1/responses", "/v1/responses/stream", "/v1/chat/completions"])
@respx.mock
async def test_persistence_requires_explicit_backend_id(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "caesura_persist", True)
    body = {"messages": [{"role": "user", "content": "Hello"}]} if "chat" in path else {"input": "Hello"}
    response = await post(path, body)
    assert response.status_code == 422
    assert "existing CaesuraO conversation ID" in response.json()["detail"]
    assert not respx.calls


@respx.mock
async def test_persist_false_retains_authoritative_conversation_id() -> None:
    def analyze(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("persist", True):
            return httpx.Response(400, json={"message": "Invalid conversation ID"})
        assert body["sessionId"] == "known-backend-conversation"
        return httpx.Response(200, json=ANALYSIS)

    respx.post(CAESURA_URL).mock(side_effect=analyze)
    provider = mock_openai("responses")
    response = await post("/v1/responses", {"input": "Hello", "conversationId": "known-backend-conversation"})
    assert response.status_code == 200
    assert GUIDANCE in json.dumps(json.loads(provider.calls.last.request.content)["input"])


@respx.mock
async def test_caesura_auth_failure_is_logged_but_openai_still_responds(capsys: pytest.CaptureFixture[str]) -> None:
    respx.post(CAESURA_URL).respond(401, json={"error": "Expired API key"})
    provider = mock_openai("chat")
    response = await post("/v1/chat/completions", request_body("chat", uuid4().hex))
    assert response.status_code == 200
    assert provider.call_count == 1
    assert "Analysis transport failed" in capsys.readouterr().err


@pytest.fixture
async def persistent_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Use a fresh SDK client so the persisted flow exercises actual SDK HTTP calls."""
    async with AsyncOpenAI(api_key="sk-test-openai") as raw:
        client = create_async_caesura(
            raw,
            CaesuraOpenAIOptions(
                api_key="caesura_test",
                mode="sync",
                persist=True,
            ),
        )
        monkeypatch.setattr(main, "openai", client)
        monkeypatch.setattr(settings, "caesura_persist", True)
        yield


@pytest.mark.parametrize("api", ["chat", "responses"])
@pytest.mark.usefixtures("persistent_client")
@respx.mock
async def test_create_conversation_once_and_reuse_for_persisted_turns(api: str) -> None:
    creation = respx.post("https://api.caesurao.com/api/conversation").respond(
        200,
        json={"success": True, "id": "backend-conversation"},
    )
    analysis = respx.post(CAESURA_URL).respond(200, json=ANALYSIS)
    provider = mock_openai(api)
    metadata = {"name": "SDK example", "calendarId": "calendar-1", "eventId": "event-1"}

    created = await post("/caesura/conversations", metadata)
    assert created.status_code == 201
    assert created.json() == {"id": "backend-conversation"}
    assert not analysis.called and not provider.called
    assert json.loads(creation.calls.last.request.content) == metadata
    assert creation.calls.last.request.headers["authorization"] == "Bearer caesura_test"

    for turn in range(2):
        body = request_body(api, created.json()["id"])
        if api == "chat":
            body["messages"][0]["content"] = f"Hello {turn}"
        else:
            body["input"] = f"Hello {turn}"
        response = await post(endpoint(api), body)
        assert response.status_code == 200
    assert creation.call_count == 1
    assert analysis.call_count == provider.call_count == 2
    for call in analysis.calls:
        body = json.loads(call.request.content)
        assert body["sessionId"] == body["conversationId"] == "backend-conversation"
        assert body["persist"] is True
    for call in provider.calls:
        assert call.request.headers["authorization"] == "Bearer sk-test-openai"
        upstream = json.loads(call.request.content)
        assert GUIDANCE in json.dumps(upstream.get("messages", upstream.get("input")))


@pytest.mark.usefixtures("persistent_client")
@pytest.mark.parametrize("failure", ["unauthorized", "missing-id", "timeout"])
@respx.mock
async def test_conversation_creation_failure_does_not_return_an_id(failure: str) -> None:
    creation = respx.post("https://api.caesurao.com/api/conversation")
    if failure == "timeout":
        creation.mock(side_effect=httpx.ReadTimeout("Timed out"))
    else:
        creation.respond(401 if failure == "unauthorized" else 200, json={})
    response = await post("/caesura/conversations", {})
    assert response.status_code == 502
    assert "id" not in response.json()
    assert len(respx.calls) == 1
    assert json.loads(creation.calls.last.request.content) == {}


@pytest.mark.usefixtures("persistent_client")
@respx.mock
async def test_fastapi_mixed_apis_share_guidance_and_persist_customer_turns() -> None:
    from scripts.check_conversations import TEXT, verify_saved_conversation

    rows: list[dict[str, Any]] = []
    creation = respx.post("https://api.caesurao.com/api/conversation").respond(200, json={"id": "mixed-id"})

    def analyze(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["sessionId"] == "mixed-id"
        assert body.get("notifyIntegrations") is not True
        context = [message for message in body["messages"] if message["speakerRole"] == "assistant"]
        assert len(context) == (1 if rows else 0)
        last = body["messages"][-1]
        payload = {"guidance": GUIDANCE} if not rows else {"isSame": True}
        rows.append(
            {
                "id": len(rows) + 1,
                "text": last["text"],
                "speakerName": last.get("speakerName"),
                "speakerIndex": last.get("speakerIndex", 0),
                "analysisJsonOpenai": payload,
            }
        )
        return httpx.Response(200, json=payload)

    respx.post(CAESURA_URL).mock(side_effect=analyze)
    respx.get("https://api.caesurao.com/api/conversation", params={"conversationId": "mixed-id"}).mock(
        side_effect=lambda _: httpx.Response(200, json={"conversation": {"id": "mixed-id", "analyses": rows}}),
    )
    providers = [mock_openai("responses"), mock_openai("chat")]
    created = await post("/caesura/conversations", {"name": "Mixed API check"})
    assert created.status_code == 201
    history: list[dict[str, Any]] = []
    for api in ["responses", "chat", "responses", "chat"]:
        if history:
            history.append({"role": "assistant", "content": TEXT})
        history.append({"role": "user", "content": TEXT})
        body = (
            {"input": history, "conversationId": created.json()["id"]}
            if api == "responses"
            else {
                "messages": history,
                "conversationId": created.json()["id"],
            }
        )
        assert (await post(endpoint(api), body)).status_code == 200
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        fetched = await client.get("/caesura/conversations/mixed-id")
    assert fetched.status_code == 200
    verify_saved_conversation(fetched.json(), "mixed-id")
    assert creation.call_count == 1
    assert [provider.call_count for provider in providers] == [2, 2]
    for provider in providers:
        for call in provider.calls:
            body = json.loads(call.request.content)
            assert GUIDANCE in json.dumps(body.get("messages", body.get("input")))
