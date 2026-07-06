# Caesura SDK Examples

This repository contains runnable example projects demonstrating the consumer-facing Caesura Python SDKs. These examples are designed to show developers exactly how to integrate Caesura into their applications.

Caesura operates as a background observer to your application's conversational flow. It analyzes the ongoing dialogue to detect psychological patterns and communication dynamics, then injects actionable recommendations back into the context for the agent's next turn. You can choose whether this observation cycle runs asynchronously (non-blocking) or synchronously.

## Examples

### 1. [FastAPI Server with `caesura-io-openai`](./examples/fastapi-openai-server)
A minimal FastAPI backend exposing standard OpenAI-compatible HTTP endpoints.
- **What this shows:** A server-side integration wrapping the official OpenAI Python SDK, logging injected recommendations and credit usage to the console. It uses `gpt-5.4-mini` via the new Responses API and the older Chat Completions API.
- **When to use it:** Use the `caesura-io-openai` package when you are building a headless service, backend worker, or an application that already uses the official `openai` package directly.

## Prerequisites

To run these examples, you will need:
- **Python**: 3.10 or higher
- **uv**: The fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **API Keys**:
  - A Caesura API key (`caesura_...`)
  - An OpenAI API key

## Data Flow Disclosure

Because Caesura operates as a middleware/proxy, it is important to understand where your data goes:
- **Provider API Key (e.g., OpenAI):** Sent *only* to the provider. It is never sent to the Caesura backend. In frontend apps, this key remains securely on the server.
- **Conversation Content:** Sent to the Caesura backend for analysis, and to the provider for language model generation.
- **Caesura API Key:** Sent *only* to the Caesura backend.

## Environment Variables

Each example contains a `.env.example` file. You should copy it to `.env` and fill in your keys. By default, keys are loaded from the environment so you never have to hardcode them in your source.

```bash
cp .env.example .env
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](./LICENSE) file for details.
