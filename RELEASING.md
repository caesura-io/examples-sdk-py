# Updating published SDK dependencies

The examples use `caesura-io-core==4.0.0` and `caesura-io-openai==4.0.0` from
PyPI. The committed lockfile contains registry URLs and hashes; no sibling SDK
checkout is required.

For future updates, wait until both SDK distributions are published, update their
exact pins together, and regenerate `uv.lock`. Commit the manifest and lockfile
together. Never replace registry hashes with guessed values or use an unpinned
remote SDK checkout.

From `examples/fastapi-openai-server`:

```sh
uv sync --locked --no-sources
uv run --no-sync ruff format --check . ../../scripts
uv run --no-sync ruff check . ../../scripts
uv run --no-sync mypy . ../../scripts
uv run --no-sync pytest
```

Standalone CI checks Python 3.10/3.13 with OpenAI 2/3. Review the changes before
committing; exclude `.env`, local databases, and logs. From the repository root,
run `python scripts/use_published_sdk.py --version <published-version>` to update
both pins, resolve the lockfile from PyPI, and refresh the installation docs. The
script validates the resolved release before changing any files.

See the SDK [migration guide](https://github.com/caesura-io/sdk-py/blob/main/docs/migration.md).
Successful creation returns the authoritative conversation ID. Reuse it across
Chat/Responses; IDs do not fetch history. The SDK saves customer messages, completed
agent replies, and explicit greetings. The example uses strict failure handling;
creation errors stop the request.

## Testing unreleased SDK changes

From `examples/fastapi-openai-server`, with `sdk-py` beside this repository:

```sh
uv sync --locked
uv pip install --no-deps -e ../../../sdk-py/packages/caesura-core -e ../../../sdk-py/packages/caesura-openai
CAESURA_BASE_URL=http://localhost:4000 uv run --no-sync uvicorn app.main:app --reload --port 8000
uv run --no-sync pytest
```

Use a local API with the matching persistence changes. `uv sync` restores the
pinned releases. Deploy the API changes before releasing SDKs that rely on them.
