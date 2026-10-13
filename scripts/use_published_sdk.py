"""After SDK publication, replace editable sources and resolve real PyPI artifacts."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    example = root / "examples/fastapi-openai-server"
    project = example / "pyproject.toml"
    content = project.read_text()
    for package in ("caesura-io-core", "caesura-io-openai"):
        content, count = re.subn(rf'"{package}==[^"\n]+"', f'"{package}==3.0.0"', content)
        if count != 1:
            raise SystemExit(f"Expected one version pin for {package}")
        content = re.sub(rf"^{package} = .*\n?", "", content, flags=re.MULTILINE)
    content = content.replace("[tool.uv.sources]\n", "").rstrip() + "\n"
    # Never invent registry URLs/checksums or write a half-resolved transition.
    # If 3.0.0 is unavailable, uv fails and the repository stays unchanged.
    with tempfile.TemporaryDirectory(prefix="caesura-published-examples-") as directory:
        staging = Path(directory)
        (staging / "pyproject.toml").write_text(content)
        (staging / "README.md").write_text((example / "README.md").read_text())
        (staging / "uv.lock").write_text((example / "uv.lock").read_text())
        subprocess.run(
            ["uv", "lock", "--directory", directory, "--no-sources", "--default-index", "https://pypi.org/simple"],
            check=True,
        )
        lock = (staging / "uv.lock").read_text()
        for package in ("caesura-io-core", "caesura-io-openai"):
            if not re.search(
                rf'name = "{package}"\nversion = "3.0.0"\nsource = {{ registry = "https://pypi.org/simple" }}', lock
            ):
                raise SystemExit(f"Expected published 3.0.0 registry metadata for {package}")
        if "editable =" in lock or "../../../sdk-py" in lock:
            raise SystemExit("Lockfile still contains editable SDK dependencies")
        project.write_text(content)
        (example / "uv.lock").write_text(lock)
    readme = root / "README.md"
    text = readme.read_text()
    start = text.index("Use Python 3.10+")
    end = text.index("\nLicensed", start)
    readme.write_text(
        text[:start] + "Use Python 3.10+ and uv. Dependencies are pinned to published SDK 3.0.0 packages;\n"
        "no sibling checkout is required.\n" + text[end:]
    )
    readme = example / "README.md"
    text = readme.read_text()
    start = text.index("Requires Python 3.10+")
    end = text.index("\n```sh", start)
    readme.write_text(
        text[:start] + "Requires Python 3.10+ and uv. Install the published SDK 3.0.0 packages using the\n"
        "committed lockfile; no sibling checkout is required.\n" + text[end:]
    )
    print("Updated published SDK pins, registry lockfile, and installation docs. Run checks before committing.")


if __name__ == "__main__":
    main()
