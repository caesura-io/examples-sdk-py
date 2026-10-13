"""Four-customer-turn checks against real APIs. Run: python -m scripts.check_conversations."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from caesura_core import CaesuraEvent, MemoryCaesuraStore
from caesura_openai import AsyncCaesuraOpenAI, CaesuraOpenAIOptions, create_async_caesura
from openai import AsyncOpenAI

from app.backend import fetch_conversation
from app.config import settings

TEXT = "I need help preparing for tomorrow's meeting."
SCENARIOS = {
    "responses": ["responses"] * 4,
    "chat": ["chat"] * 4,
    "mixed": ["responses", "chat", "responses", "chat"],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_saved_conversation(data: dict[str, Any], conversation_id: str) -> list[dict[str, Any]]:
    conversation = data["conversation"]
    require(conversation["id"] == conversation_id, "Fetched a different conversation")
    rows = conversation["analyses"]
    require(isinstance(rows, list) and len(rows) == 4, "Expected four saved dialogue/analysis rows")
    require(all(isinstance(row, dict) and isinstance(row.get("id"), int) for row in rows), "Invalid analysis row IDs")
    ordered: list[dict[str, Any]] = sorted(rows, key=lambda row: row["id"])
    require(len({row["id"] for row in ordered}) == 4, "Expected four distinct analysis rows")
    for turn, row in enumerate(ordered):
        name, index = "Customer", 1
        require(row.get("text") == TEXT, f"Turn {turn + 1}: incorrect saved dialogue text")
        require(row.get("speakerName") == name, f"Turn {turn + 1}: incorrect saved speaker name")
        require(row.get("speakerIndex") == index, f"Turn {turn + 1}: incorrect saved speaker index")
        # A deduped row may have an empty analysis value. Never assume a particular payload shape.
        require("analysisJsonOpenai" in row, f"Turn {turn + 1}: saved analysis field missing")
    return ordered


async def run_scenario(
    scenario: str,
    client: AsyncCaesuraOpenAI,
    store: MemoryCaesuraStore,
    events: list[CaesuraEvent],
    errors: list[Any],
) -> dict[str, Any]:
    conversation_id = await client.create_conversation(name=f"CaesuraO Python four-turn check: {scenario}")
    print(json.dumps({"scenario": scenario, "conversation_id": conversation_id}), flush=True)
    history: list[dict[str, Any]] = []
    turn_results: list[dict[str, Any]] = []
    for turn, api in enumerate(SCENARIOS[scenario]):
        role = "user"
        if history:
            history.append({"role": "assistant", "content": TEXT})
        name, index = ("Customer", 1) if role == "user" else ("Agent", 0)
        # Controlled input dialogue, not the model's generated reply.
        history.append({"role": role, "content": TEXT})
        start, error_start = len(events), len(errors)
        if api == "responses":
            result = await client.responses.create(
                model="gpt-5.4-mini",
                input=list(history),
                max_output_tokens=64,
                caesura_conversation_id=conversation_id,
            )
        else:
            result = await client.chat.completions.create(
                model="gpt-5.4-mini",
                messages=list(history),
                max_completion_tokens=64,
                caesura_conversation_id=conversation_id,
            )
        require(bool(result.id), f"Turn {turn + 1}: missing OpenAI response")
        require(len(errors) == error_start, f"Turn {turn + 1}: CaesuraO analysis failed")
        current = events[start:]
        requests = [event for event in current if event.type == "request"]
        responses = [event for event in current if event.type == "response"]
        require(len(requests) == len(responses) == 1, f"Turn {turn + 1}: missing analysis request/response")
        request_body = requests[0].body
        if request_body is None:
            raise AssertionError(f"Turn {turn + 1}: missing analysis request body")
        body = request_body.to_dict()
        require(body.get("notifyIntegrations") is not True, "Integration notifications must remain disabled")
        require(body.get("persist") is True and body.get("sessionId") == conversation_id, "Wrong persistence settings")
        last = body["messages"][-1]
        require(
            (last.get("text"), last.get("speakerRole"), last.get("speakerName"), last.get("speakerIndex"))
            == (TEXT, "user", name, index),
            f"Turn {turn + 1}: latest dialogue identity was lost or replaced by analysis context",
        )
        injected = [event for event in current if event.type == "injected"]
        turn_results.append(
            {
                "api": api,
                "speaker": name,
                "speaker_index": index,
                "is_same": responses[0].is_same,
                "buffered_guidance": len(store.get(conversation_id).recommendations),
                "injected_guidance": sum(len(event.blocks) for event in injected),
            }
        )
    rows = verify_saved_conversation(await fetch_conversation(conversation_id), conversation_id)
    summary = {
        "scenario": scenario,
        "conversation_id": conversation_id,
        "model_calls": 4,
        "saved_rows": len(rows),
        "buffered_guidance": len(store.get(conversation_id).recommendations),
        "duplicate_responses": sum(turn["is_same"] is True for turn in turn_results),
        "turns": turn_results,
    }
    print(json.dumps(summary), flush=True)
    return summary


async def run(scenarios: list[str], threshold: float | None) -> None:
    events: list[CaesuraEvent] = []
    errors: list[Any] = []
    store = MemoryCaesuraStore()
    async with AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=60) as raw:
        client = create_async_caesura(
            raw,
            CaesuraOpenAIOptions(
                api_key=settings.caesura_api_key,
                mode="sync",
                persist=True,
                calculate_similarities=True,
                similarity_threshold=threshold,
                timeout_ms=45000,
                store=store,
                on_event=events.append,
                on_error=errors.append,
            ),
        )
        for scenario in scenarios:
            await run_scenario(scenario, client, store, events, errors)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create conversations and verify four persisted turns using real APIs."
    )
    parser.add_argument("--api", choices=[*SCENARIOS, "all"], default="all")
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=None,
        help="Optional experimental suppression threshold (for example 0.5).",
    )
    args = parser.parse_args()
    if args.similarity_threshold is not None and not 0 <= args.similarity_threshold <= 1:
        parser.error("--similarity-threshold must be between 0 and 1")
    scenarios = list(SCENARIOS) if args.api == "all" else [args.api]
    try:
        asyncio.run(run(scenarios, args.similarity_threshold))
    except AssertionError as exc:
        raise SystemExit(f"Check failed: {exc}") from None
    except Exception as exc:
        # Provider error bodies can contain credentials or other sensitive context.
        raise SystemExit(
            f"API check failed ({type(exc).__name__}); no credentials or response bodies printed."
        ) from None


if __name__ == "__main__":
    main()
