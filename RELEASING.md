# Updating published SDK dependencies

The examples use `caesura-io-core==3.0.0` and `caesura-io-openai==3.0.0` from
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
committing; exclude `.env`, local databases, and logs. The completed 3.0.0 migration
can be reproduced with `python scripts/use_published_sdk.py` from the repository
root; this script is specific to that release.

See the SDK [migration guide](https://github.com/caesura-io/sdk-py/blob/main/docs/migration.md).
Creation returns the authoritative conversation ID. Reuse it across Chat/Responses;
IDs do not fetch history. Default HTTP persistence saves analyzed customer messages
and analyses, not greetings, replies, or a full transcript.
