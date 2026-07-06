"""FastAPI application exposing OpenAI-compatible endpoints with Caesura.

Endpoints mirror the JS Fastify example so the two servers are
interchangeable from a client's perspective:

  POST /v1/responses          — Responses API (non-streaming)
  POST /v1/responses/stream   — Responses API (streaming SSE)
  POST /v1/chat/completions   — Chat Completions (non-streaming + streaming)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.caesura_client import openai
from app.models import ChatCompletionRequest, ResponsesRequest

app = FastAPI(
    title="Caesura + OpenAI Example",
    description="Minimal FastAPI server demonstrating caesura-io-openai integration.",
)


# ---------------------------------------------------------------------------
# Responses API
# ---------------------------------------------------------------------------


@app.post("/v1/responses")
async def create_response(body: ResponsesRequest) -> Any:
    """Responses API — non-streaming.

    The Caesura wrapper intercepts this call to:
      1. Observe the user input and send it to the Caesura backend for analysis.
      2. Inject any buffered recommendations into the ``instructions`` field.

    In sync mode (default in this example), step 1 pauses the request until
    the analysis finishes, ensuring recommendations appear immediately on the
    current turn. If switched to async mode, it fires in the background.
    """
    response = await openai.responses.create(
        model=body.model,
        input=body.input,
        caesura_conversation_id=body.conversation_id,
    )
    return response


@app.post("/v1/responses/stream")
async def create_response_stream(body: ResponsesRequest) -> StreamingResponse:
    """Responses API — streaming via Server-Sent Events."""
    stream = await openai.responses.create(
        model=body.model,
        input=body.input,
        stream=True,
        caesura_conversation_id=body.conversation_id,
    )

    async def event_generator() -> AsyncIterator[str]:
        async for event in stream:
            yield f"data: {json.dumps(event.model_dump() if hasattr(event, 'model_dump') else event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Chat Completions API
# ---------------------------------------------------------------------------


@app.post("/v1/chat/completions")
async def create_chat_completion(body: ChatCompletionRequest) -> Any:
    """Classic OpenAI Chat Completions API.

    The ``user`` field from the request body is used as the Caesura
    ``conversationId``, matching the convention in the JS example.  This
    lets you track multi-turn conversations across requests.

    The Caesura wrapper:
      1. Collects user/assistant messages and sends them for analysis.
      2. Injects any buffered recommendations into the messages array
         (placement depends on ``InjectConfig``; default is after the
         last analyzed message).

    In sync mode (default in this example), the analysis is awaited inline
    so recommendations can be injected immediately. If switched to async mode,
    the analysis fires in the background and gets injected on the next turn.
    """
    conversation_id = body.user or "demo"
    messages = [m.model_dump(exclude_none=True) for m in body.messages]

    if body.stream:
        stream = await openai.chat.completions.create(
            model=body.model,
            messages=messages,
            stream=True,
            caesura_conversation_id=conversation_id,
        )

        async def event_generator() -> AsyncIterator[str]:
            async for event in stream:
                yield f"data: {json.dumps(event.model_dump() if hasattr(event, 'model_dump') else event)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    response = await openai.chat.completions.create(
        model=body.model,
        messages=messages,
        caesura_conversation_id=conversation_id,
    )
    return response
