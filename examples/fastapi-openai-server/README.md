# CaesuraO + FastAPI

Create a CaesuraO conversation, then reuse its ID with OpenAI Responses or Chat
Completions. New customer turns receive private guidance; tool continuations do not
trigger another analysis.

## Run

Requires Python 3.10+ and uv. Install the published SDK 4.0.0 packages using the
committed lockfile; no sibling checkout is required.

```sh
cp .env.example .env
# Set OPENAI_API_KEY and CAESURA_API_KEY.
uv sync --locked
uv run uvicorn app.main:app --reload --port 8000
```

Run `requests.http` in order with the JetBrains HTTP Client. Response handlers
capture conversation IDs and actual replies for the following requests.
API credentials stay on the server.
The example has no caller authentication; add application authentication and
conversation ownership checks before deploying it publicly.

| Route | Request |
|---|---|
| `POST /caesura/conversations` | Optional `name`, `calendarId`, `eventId`, `greeting`; returns `id` and any supplied greeting |
| `GET /caesura/conversations/{id}` | Retrieve saved messages and analyses |
| `POST /v1/responses` | `input`, `conversationId`, optional `model` |
| `POST /v1/responses/stream` | Same input, SSE output |
| `POST /v1/chat/completions` | `messages`, `conversationId`, optional `model`, `stream` |

Both model APIs require `conversationId`, including when `CAESURA_PERSIST=false`.
Create once and save the returned ID; starting a new conversation requires explicit
creation. An ID does not load previous messages. Supply growing dialogue history
with ordinary OpenAI `user`/`assistant` roles and append generated replies yourself.

`CAESURA_MODE=sync` waits for guidance for the current model call; `async` makes it
available to later calls. This setting is independent of using AsyncOpenAI.
`CAESURA_PERSIST=true` saves completed customer messages, agent replies, and analyses
by default.
The conversation belongs to the user associated with `CAESURA_API_KEY`. On the
Conversations page, API-created conversations use the API source
filter. Empty conversations are hidden by default; creating an ID alone or using
`CAESURA_PERSIST=false` does not populate the conversation.

This minimal server uses the SDK's history-based customer detection. For retries,
truncated histories, or RAG supplied as user messages, pass stable `CustomerTurn`
IDs through `caesura_context` as shown in the
[customer-turn guide](https://github.com/caesura-io/sdk-py/blob/main/docs/application-integration.md#select-genuine-customer-turns).
Distinct messages with identical text need
distinct IDs; tool continuations reuse an ID or explicitly select no customer turn.

This example uses `failure_policy="raise"` with `mode="sync"` by default.
Analysis or customer-message storage failures prevent model generation. If saving
a completed reply fails, the request reports the error after generation.

## Checks

```sh
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy .
```

Tests mock both services. The optional command below creates real conversations and
consumes API credits. It verifies four customer analyses with assistant background,
using Responses, Chat, or both, including the actual generated agent replies.

```sh
uv run python -m scripts.check_conversations --api all
```

With `CAESURA_PERSIST=true` (default), completed customer and agent messages are
saved automatically. Optional `greeting` on conversation creation records an
application greeting without analysis. Partial or interrupted replies are not saved
as completed messages. A persistence failure fails the request instead of being hidden.
