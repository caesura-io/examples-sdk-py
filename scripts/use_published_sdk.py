"""After SDK publication, pin an explicit release and resolve real PyPI artifacts."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def use_published_sdk(version: str, root: Path) -> None:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Supply an exact stable SDK version, for example 4.0.0")
    example = root / "examples/fastapi-openai-server"
    project = example / "pyproject.toml"
    lockfile = example / "uv.lock"
    content = project.read_text()
    for package in ("caesura-io-core", "caesura-io-openai"):
        content, count = re.subn(rf'"{package}==[^"\n]+"', f'"{package}=={version}"', content)
        if count != 1:
            raise ValueError(f"Expected one version pin for {package}")
        content = re.sub(rf"^{package} = .*\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"\[tool\.uv\.sources\]\s*(?=\[|\Z)", "", content).rstrip() + "\n"
    # Resolve in a temporary directory before changing any committed file.
    with tempfile.TemporaryDirectory(prefix="caesura-published-examples-") as directory:
        staging = Path(directory)
        (staging / "pyproject.toml").write_text(content)
        (staging / "README.md").write_text((example / "README.md").read_text())
        (staging / "uv.lock").write_text(lockfile.read_text())
        subprocess.run(
            ["uv", "lock", "--directory", directory, "--no-sources", "--default-index", "https://pypi.org/simple"],
            check=True,
        )
        lock = (staging / "uv.lock").read_text()
        for package in ("caesura-io-core", "caesura-io-openai"):
            if not re.search(
                rf'name = "{package}"\nversion = "{re.escape(version)}"\n'
                r'source = { registry = "https://pypi.org/simple" }',
                lock,
            ):
                raise ValueError(f"Expected published {version} registry metadata for {package}")
        if "editable =" in lock or "../../../sdk-py" in lock:
            raise ValueError("Lockfile still contains editable SDK dependencies")
        prepared = {project: content, lockfile: lock}
        readme = root / "README.md"
        text = readme.read_text()
        start = text.index("Use Python 3.10+")
        end = text.index("\nLicensed", start)
        prepared[readme] = (
            text[:start] + f"Use Python 3.10+ and uv. Dependencies are pinned to published SDK {version} packages;\n"
            "no sibling checkout is required.\n" + text[end:]
        )
        readme = example / "README.md"
        text = readme.read_text()
        start = text.index("Requires Python 3.10+")
        end = text.index("\n```sh", start)
        prepared[readme] = (
            text[:start] + f"Requires Python 3.10+ and uv. Install the published SDK {version} packages using the\n"
            "committed lockfile; no sibling checkout is required.\n" + text[end:]
        )
        backups = {path: path.read_bytes() for path in prepared}
        try:
            for path, value in prepared.items():
                path.write_text(value)
        except OSError:
            for path, original in backups.items():
                path.write_bytes(original)
            raise
    print(f"Updated SDK {version} pins, registry lockfile, and installation docs. Run checks before committing.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Exact SDK version already published to PyPI")
    args = parser.parse_args()
    use_published_sdk(args.version, Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
