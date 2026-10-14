"""Release preparation must not leave examples half-upgraded."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


@pytest.fixture
def release_script() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts/use_published_sdk.py"
    spec = importlib.util.spec_from_file_location("sdk_release", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("outcome", ["success", "missing release", "wrong version", "local source", "bad docs"])
def test_release_preparation(release_script: ModuleType, tmp_path: Path, outcome: str) -> None:
    example = tmp_path / "examples/fastapi-openai-server"
    example.mkdir(parents=True)
    files = {
        example / "pyproject.toml": 'dependencies = ["caesura-io-core==3.0.0", "caesura-io-openai==3.0.0"]\n',
        example / "uv.lock": "# previous lock\n",
        tmp_path / "README.md": "# Examples\n\nUse Python 3.10+ with old packages.\nLicensed under Apache.\n",
        example / "README.md": "# Server\n\nRequires Python 3.10+ with old packages.\n```sh\nuv sync\n```\n",
    }
    if outcome == "bad docs":
        files[tmp_path / "README.md"] = "Changed documentation layout\n"
    for path, text in files.items():
        path.write_text(text)

    def resolve(args: list[str], *, check: bool) -> None:
        assert check
        assert args[-1] == "https://pypi.org/simple"
        if outcome == "missing release":
            raise subprocess.CalledProcessError(1, args)
        staging = Path(args[args.index("--directory") + 1])
        assert '"caesura-io-core==3.1.0"' in (staging / "pyproject.toml").read_text()
        version = "3.0.0" if outcome == "wrong version" else "3.1.0"
        lock = "\n".join(
            f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            for name in ("caesura-io-core", "caesura-io-openai")
        )
        if outcome == "local source":
            lock += '\nsource = { editable = "../../../sdk-py" }\n'
        (staging / "uv.lock").write_text(lock)

    with patch.object(release_script.subprocess, "run", side_effect=resolve):
        if outcome == "success":
            release_script.use_published_sdk("3.1.0", tmp_path)
            for path in files:
                assert "3.1.0" in path.read_text()
                assert "3.0.0" not in path.read_text()
        else:
            with pytest.raises((ValueError, subprocess.CalledProcessError)):
                release_script.use_published_sdk("3.1.0", tmp_path)
            assert {path: path.read_text() for path in files} == files


@pytest.mark.parametrize("version", ["latest", "3.1", "3.1.0rc1", "3.01.0", "3.1.0; echo unsafe"])
def test_rejects_unpinned_versions(release_script: ModuleType, tmp_path: Path, version: str) -> None:
    with patch.object(release_script.subprocess, "run") as run:
        with pytest.raises(ValueError, match="exact stable"):
            release_script.use_published_sdk(version, tmp_path)
        run.assert_not_called()
