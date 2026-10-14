# Updating published SDK dependencies

The examples use `caesura-io-core==4.0.0` and `caesura-io-openai==4.0.0` from PyPI.

After both new versions are published, run this from the repository root:

```sh
python scripts/use_published_sdk.py --version <published-version>
```

The script updates both pins, resolves the registry lockfile, and refreshes the
installation docs. Review the [SDK migration guide](https://github.com/caesura-io/sdk-py/blob/main/docs/migration.md)
and run checks from `examples/fastapi-openai-server`:

```sh
uv sync --locked --no-sources
uv run --no-sync ruff format --check . ../../scripts
uv run --no-sync ruff check . ../../scripts
uv run --no-sync mypy . ../../scripts
uv run --no-sync pytest
```

Standalone CI checks Python 3.10/3.13 with OpenAI 2/3. Commit the manifest and
lockfile together; exclude `.env`, local databases, and logs.

## Testing local SDK changes

With `sdk-py` beside this repository, run from `examples/fastapi-openai-server`:

```sh
uv sync --locked
uv pip install --no-deps -e ../../../sdk-py/packages/caesura-core -e ../../../sdk-py/packages/caesura-openai
uv run --no-sync pytest
```

Use `uv run --no-sync` when running the application with local SDK packages.
Run `uv sync --locked --no-sources` to restore published packages.
