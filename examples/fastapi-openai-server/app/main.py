"""FastAPI application exposing OpenAI-compatible endpoints with CaesuraO.

Create a CaesuraO conversation, then reuse its ID on the model endpoints:

  POST /caesura/conversations — Explicit CaesuraO conversation creation
  POST /v1/responses          — Responses API (non-streaming)
  POST /v1/responses/stream   — Responses API (streaming SSE)
  POST /v1/chat/completions   — Chat Completions (non-streaming + streaming)
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.backend import fetch_conversation
from app.caesura_client import openai
from app.models import ChatCompletionRequest, ConversationCreateRequest, ResponsesRequest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await openai.close()


app = FastAPI(
    lifespan=lifespan,
    title="CaesuraO + OpenAI Example",
    description="Minimal FastAPI server demonstrating caesura-io-openai integration.",
)


def resolve_conversation_id(conversation_id: str | None) -> str:
    if conversation_id and conversation_id.strip():
        return conversation_id
    raise HTTPException(
        status_code=422,
        detail="An existing CaesuraO conversation ID is required in conversationId.",
    )


@app.post("/caesura/conversations", status_code=201)
async def create_conversation(body: ConversationCreateRequest) -> dict[str, str]:
    """Create once through the CaesuraO SDK and return the ID to reuse on later turns."""
    try:
        conversation_id = await openai.create_conversation(
            name=body.name,
            calendar_id=body.calendar_id,
            event_id=body.event_id,
        )
    except Exception as exc:
        logger.exception("CaesuraO conversation creation failed")
        raise HTTPException(
            status_code=502, detail="CaesuraO conversation creation failed. Check server logs."
        ) from exc
    return {"id": conversation_id}


@app.get("/caesura/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, Any]:
    """Fetch saved dialogue and analysis rows using the server's CaesuraO key."""
    try:
        return await fetch_conversation(conversation_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise HTTPException(
            status_code=status if 400 <= status < 500 else 502, detail="Could not fetch the CaesuraO conversation."
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not fetch the CaesuraO conversation.") from exc


# ---------------------------------------------------------------------------
# Responses API
# ---------------------------------------------------------------------------


@app.post("/v1/responses")
async def create_response(body: ResponsesRequest) -> Any:
    """Responses API — non-streaming.

    The CaesuraO wrapper intercepts this call to:
      1. Observe the user input and send it to the CaesuraO backend for analysis.
      2. Inject eligible guidance into ``input``; add the skill prompt to ``instructions``.

    In sync mode (default in this example), step 1 pauses the request until
    the analysis finishes, ensuring recommendations appear immediately on the
    current turn. If switched to async mode, it fires in the background.
    """
    response = await openai.responses.create(
        model=body.model,
        input=body.input,
        caesura_conversation_id=resolve_conversation_id(body.conversation_id),
    )
    return response


@app.post("/v1/responses/stream")
async def create_response_stream(body: ResponsesRequest) -> StreamingResponse:
    """Responses API — streaming via Server-Sent Events."""
    stream = await openai.responses.create(
        model=body.model,
        input=body.input,
        stream=True,
        caesura_conversation_id=resolve_conversation_id(body.conversation_id),
    )

    async def event_generator() -> AsyncIterator[str]:
        async with stream:
            async for event in stream:
                yield f"data: {json.dumps(event.model_dump() if hasattr(event, 'model_dump') else event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Chat Completions API
# ---------------------------------------------------------------------------


@app.post("/v1/chat/completions")
async def create_chat_completion(body: ChatCompletionRequest) -> Any:
    """Chat Completions using the same conversationId as Responses."""
    conversation_id = resolve_conversation_id(body.conversation_id)
    messages = [m.model_dump(exclude_none=True, by_alias=True) for m in body.messages]

    if body.stream:
        stream = await openai.chat.completions.create(
            model=body.model,
            messages=messages,
            stream=True,
            caesura_conversation_id=conversation_id,
        )

        async def event_generator() -> AsyncIterator[str]:
            async with stream:
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
