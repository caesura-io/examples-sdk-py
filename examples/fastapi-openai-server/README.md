# CaesuraO + FastAPI

Create a CaesuraO conversation, then reuse its ID with OpenAI Responses or Chat
Completions. New customer turns receive private guidance; tool continuations do not
trigger another analysis.

## Run

Requires Python 3.10+ and uv. Install the published SDK 3.0.0 packages using the
committed lockfile; no sibling checkout is required.

```sh
cp .env.example .env
# Set OPENAI_API_KEY and CAESURA_API_KEY.
uv sync --locked
uv run uvicorn app.main:app --reload --port 8000
```

Open `requests.http` for a create-and-reuse flow. API credentials stay on the server.
The example has no caller authentication; add application authentication and
conversation ownership checks before deploying it publicly.

| Route | Request |
|---|---|
| `POST /caesura/conversations` | Optional `name`, `calendarId`, `eventId`; returns `{ "id": "..." }` |
| `GET /caesura/conversations/{id}` | Retrieve saved analysis rows |
| `POST /v1/responses` | `input`, `conversationId`, optional `model` |
| `POST /v1/responses/stream` | Same input, SSE output |
| `POST /v1/chat/completions` | `messages`, `conversationId`, optional `model`, `stream` |

Both model APIs require `conversationId`, including when `CAESURA_PERSIST=false`.
Create once and save the returned ID; starting a new conversation requires explicit
creation. An ID does not load previous messages. Supply growing dialogue history
with ordinary OpenAI `user`/`assistant` roles and append generated replies yourself.

`CAESURA_MODE=sync` waits for guidance for the current model call; `async` makes it
available to later calls. This setting is independent of using AsyncOpenAI.
`CAESURA_PERSIST=true` saves analyzed customer messages and analyses, not a complete
transcript. Use the SDK's `persist_transcript` hook for an application-owned archive.
The conversation belongs to the user associated with `CAESURA_API_KEY`. On the
Conversations page, API-created conversations use the API source
type. Empty conversations are hidden by default until a saved analysis updates
their duration; creating an ID alone or using `CAESURA_PERSIST=false` does not
make a populated conversation appear there.

This minimal server uses the SDK's history-based customer detection. For retries,
truncated histories, or RAG supplied as user messages, pass stable `CustomerTurn`
IDs through `caesura_context` as shown in the
[customer-turn guide](https://github.com/caesura-io/sdk-py/blob/main/docs/application-integration.md#select-genuine-customer-turns).
Distinct messages with identical text need
distinct IDs; tool continuations reuse an ID or explicitly select no customer turn.

Analysis errors are logged and model calls continue by default. Applications requiring
guidance should set `failure_policy="raise"` with `mode="sync"`.

## Checks

```sh
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy .
```

Tests mock both services. The optional command below creates real conversations and
consumes API credits. It verifies four customer analyses with assistant background,
using Responses, Chat, or both; it does not claim that HTTP persistence saves replies.

```sh
uv run python -m scripts.check_conversations --api all
```
