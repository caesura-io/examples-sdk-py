"""Endpoint tests for the FastAPI + Caesura example server.

These tests use ``httpx.AsyncClient`` as the FastAPI test client and
``respx`` to mock both the OpenAI and Caesura HTTP backends, so no real
API calls are made.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
import respx
from httpx import ASGITransport

# Set test environment variables BEFORE importing the app, because
# ``config.py`` instantiates ``Settings()`` at module level.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-openai")
os.environ.setdefault("CAESURA_API_KEY", "caesura_test")
os.environ.setdefault("CAESURA_BASE_URL", "http://caesura.test")
os.environ.setdefault("CAESURA_MODE", "sync")

from app.main import app

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

OPENAI_CHAT_RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello! How can I help?"},
            "finish_reason": "stop",
        }
    ],
    "model": "gpt-5.4-mini",
    "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
}

CAESURA_ANALYZE_RESPONSE: dict[str, Any] = {
    "recommendation": "Be friendly and helpful.",
    "observation": "User is asking for help.",
    "sentiment": "neutral",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatCompletions:
    @pytest.mark.asyncio
    @respx.mock
    async def test_chat_completions_returns_response(self) -> None:
        """POST /v1/chat/completions returns a valid chat completion."""
        respx.post("http://caesura.test/api/analyze").mock(
            return_value=httpx.Response(200, json=CAESURA_ANALYZE_RESPONSE)
        )
        respx.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-5.4-mini",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "user": "test-session",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data or "id" in data


class TestResponses:
    @pytest.mark.asyncio
    @respx.mock
    async def test_responses_returns_response(self) -> None:
        """POST /v1/responses returns a valid response."""
        respx.post("http://caesura.test/api/analyze").mock(
            return_value=httpx.Response(200, json=CAESURA_ANALYZE_RESPONSE)
        )
        respx.post(url__regex=r".*/responses").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "resp-test",
                    "output": [{"type": "message", "content": [{"type": "text", "text": "Hi there!"}]}],
                },
            )
        )

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/responses",
                json={
                    "input": "Hello, I need help",
                    "conversationId": "test-session",
                },
            )

        assert resp.status_code == 200


class TestKeyIsolation:
    """Verify that API keys are never sent to the wrong backend.

    This is a critical security property: the OpenAI key must only go to
    OpenAI, and the Caesura key must only go to the Caesura backend.
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_keys_are_isolated(self) -> None:
        """OpenAI key -> OpenAI only; Caesura key -> Caesura only."""
        caesura_route = respx.post("http://caesura.test/api/analyze").mock(
            return_value=httpx.Response(200, json=CAESURA_ANALYZE_RESPONSE)
        )
        openai_route = respx.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-5.4-mini",
                    "messages": [{"role": "user", "content": "test"}],
                    "user": "isolation-test",
                },
            )

        # Check Caesura request — should have Caesura key, NOT OpenAI key
        if caesura_route.calls:
            caesura_req = caesura_route.calls.last.request
            caesura_auth = caesura_req.headers.get("authorization", "")
            assert "caesura_test" in caesura_auth
            assert "sk-test-openai" not in caesura_auth

        # Check OpenAI request — should have OpenAI key, NOT Caesura key
        if openai_route.calls:
            openai_req = openai_route.calls.last.request
            openai_auth = openai_req.headers.get("authorization", "")
            assert "sk-test-openai" in openai_auth
            assert "caesura_test" not in openai_auth
