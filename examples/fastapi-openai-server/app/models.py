"""Pydantic models for request validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Responses API models
# ---------------------------------------------------------------------------


class ResponsesRequest(BaseModel):
    """Request body for ``POST /v1/responses`` and ``POST /v1/responses/stream``."""

    input: str
    conversation_id: str = Field(default="demo", alias="conversationId")
    model: str = "gpt-5.4-mini"


# ---------------------------------------------------------------------------
# Chat Completions API models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in the Chat Completions format."""

    role: str
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    """Request body for ``POST /v1/chat/completions``.

    The ``user`` field doubles as the Caesura ``conversationId``, matching
    the convention used in the JS example.
    """

    model: str = "gpt-5.4-mini"
    messages: list[ChatMessage]
    stream: bool = False
    user: str | None = None
