"""Wiring the Caesura-wrapped AsyncOpenAI client.

This module creates the singleton ``openai`` client that the rest of the
application imports.  It demonstrates the key integration pattern:

  1. Create a standard ``AsyncOpenAI`` client (its API key goes ONLY to OpenAI).
  2. Wrap it with ``create_async_caesura`` — this adds the Caesura observe/inject
     cycle *around* every ``chat.completions.create`` and ``responses.create`` call.
  3. The ``CaesuraOpenAIOptions`` carries the Caesura API key and config — these
     go ONLY to the Caesura backend, never to OpenAI.

IMPORTANT — naming collision:
  • ``AsyncOpenAI`` = the *async HTTP transport* from the ``openai`` package.
  • ``mode="async"`` = the Caesura *observation mode* (fire-and-forget analysis).
  These are independent concepts.  You can use ``AsyncOpenAI`` with either
  Caesura mode.
"""

from __future__ import annotations

from caesura_openai import (
    CaesuraOpenAIOptions,
    create_async_caesura,
    create_credit_meter,
    create_debug_logger,
)
from openai import AsyncOpenAI

from app.config import settings

# ── Credit meter ──────────────────────────────────────────────────────────
# Accumulates per-conversation credit usage.  Pass ``meter.record`` as the
# ``on_credit_usage`` callback so costs are tracked automatically.
credit_meter = create_credit_meter()

# ── Caesura-wrapped OpenAI client ─────────────────────────────────────────
#
# Step 1: Create the raw OpenAI client.
#   → ``api_key`` is sent ONLY to OpenAI via its own HTTPS connection.
#
# Step 2: Wrap it with ``create_async_caesura``.
#   → ``CaesuraOpenAIOptions.api_key`` is sent ONLY to the Caesura backend.
#   → The Caesura wrapper intercepts ``.chat.completions.create()`` and
#     ``.responses.create()`` calls to inject recommendations.
#   → In ``mode="sync"`` (default in this example), the SDK awaits the analysis
#     before forwarding to the LLM, so recommendations appear on the *current* turn
#     (higher latency).
#   → In ``mode="async"``, observation is non-blocking: the analysis
#     request fires in the background via ``asyncio.create_task``.  The LLM
#     call proceeds immediately, and any resulting recommendation is buffered
#     for injection on the *next* turn (one-turn lag).
#
openai = create_async_caesura(
    AsyncOpenAI(api_key=settings.openai_api_key),
    CaesuraOpenAIOptions(
        base_url=settings.caesura_base_url,
        api_key=settings.caesura_api_key,
        mode=settings.caesura_mode,
        on_credit_usage=credit_meter.record,
        on_event=create_debug_logger(),  # Logs Caesura activity to the console
    ),
)
