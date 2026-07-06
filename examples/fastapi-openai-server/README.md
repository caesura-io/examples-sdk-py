# FastAPI Server with `caesura-io-openai`

A minimal FastAPI backend exposing standard OpenAI-compatible HTTP endpoints.

**What this shows:** A server-side integration wrapping the official OpenAI Python SDK, logging injected recommendations and credit usage to the console. It uses `gpt-5.4-mini` via the new Responses API and the older Chat Completions API.

**When to use it:** Use the `caesura-io-openai` package when you are building a headless service, backend worker, or an application that already uses the official `openai` package directly.

## Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- An OpenAI API key
- A Caesura API key

## Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Fill in your `OPENAI_API_KEY` and `CAESURA_API_KEY` in `.env`.
3. Install dependencies:
   ```bash
   uv sync
   ```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`.

## Endpoints

### Responses API

```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello, I need help with my account", "conversationId": "demo-session-1"}'
```

### Streaming Responses API

```bash
curl -N -X POST http://localhost:8000/v1/responses/stream \
  -H "Content-Type: application/json" \
  -d '{"input": "Can you explain your pricing?", "conversationId": "demo-session-1"}'
```

### Chat Completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Hello, I need help with my account"}],
    "user": "demo-session-2"
  }'
```

### Streaming Chat Completions

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Can you explain your pricing?"}],
    "stream": true,
    "user": "demo-session-2"
  }'
```

## What you'll see

You can use the included `requests.http` file to ping the server.
In your console, you will see FastAPI/uvicorn startup logs alongside detailed Caesura lifecycle events:
- The requests sent to Caesura's backend for analysis
- The resulting recommendations
- When a recommendation is injected into your OpenAI request

## Async vs Sync Observation Mode

Caesura's `mode` setting (`"async"` or `"sync"`) controls whether recommendation generation **blocks the model call**. It is independent of whether you use Python's sync `OpenAI` or async `AsyncOpenAI` client.

| Mode | Behavior | Trade-off |
|------|----------|-----------|
| `async` (default) | Observation runs in the background via `asyncio.create_task`. Recommendations appear on the **next** turn. | No added latency to the LLM call; one-turn lag before recommendations are injected. |
| `sync` | Observation runs inline before the LLM call. Recommendations are injected into the **current** turn. | Adds Caesura's analysis latency to every model call. |

This example uses `sync` mode by default, meaning recommendations are injected immediately on the current turn. To switch to the non-blocking mode, set `CAESURA_MODE=async` in your `.env` file.

> **Naming collision note:** Python's `AsyncOpenAI` refers to the *async HTTP client* from the `openai` package. Caesura's `mode="async"` refers to the *observation mode* — whether the analysis call blocks the LLM request. These are completely independent concepts.

## Data Flow

Because Caesura operates as a middleware/proxy, it is important to understand where your data goes:
- **Provider API Key (OpenAI):** Sent *only* to OpenAI. It is never sent to the Caesura backend.
- **Conversation Content:** Sent to the Caesura backend for analysis, and to the provider for language model generation.
- **Caesura API Key:** Sent *only* to the Caesura backend.
