"""Pydantic models for request validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """Optional metadata for a new CaesuraO backend conversation."""

    name: str | None = None
    calendar_id: str | None = Field(default=None, alias="calendarId")
    event_id: str | None = Field(default=None, alias="eventId")


# ---------------------------------------------------------------------------
# Responses API models
# ---------------------------------------------------------------------------


class ResponsesRequest(BaseModel):
    """Request body for ``POST /v1/responses`` and ``POST /v1/responses/stream``."""

    input: str | list[dict[str, Any]]
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1)
    model: str = "gpt-5.4-mini"


# ---------------------------------------------------------------------------
# Chat Completions API models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in the Chat Completions format."""

    role: str
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    speaker_index: int | None = Field(default=None, alias="speakerIndex")


class ChatCompletionRequest(BaseModel):
    """Chat input with an explicit CaesuraO conversationId."""

    model: str = "gpt-5.4-mini"
    messages: list[ChatMessage]
    stream: bool = False
    conversation_id: str | None = Field(default=None, alias="conversationId", min_length=1)
