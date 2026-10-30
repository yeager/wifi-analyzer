#!/usr/bin/env python3
"""Create a temporary Flatpak manifest pinned to one exact release commit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "flatpak/io.github.yeager.wifi-analyzer.json"


def prepare(root: Path, tag: str, commit: str) -> Path:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"invalid release tag {tag!r}; expected vMAJOR.MINOR.PATCH")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("release commit must be a full lowercase Git hash")

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if tag != f"v{version}":
        raise ValueError(f"release tag {tag} does not match project version {version}")

    manifest_path = root / "flatpak/io.github.yeager.wifi-analyzer.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = [
        source
        for module in manifest.get("modules", [])
        for source in module.get("sources", [])
        if source.get("type") == "git"
    ]
    repository = project.get("project", {}).get("urls", {}).get("Repository", "")
    if len(sources) != 1 or sources[0].get("url", "").removesuffix(".git") != repository.removesuffix(".git"):
        raise ValueError("Flatpak manifest must contain one Git source for the project repository")

    sources[0]["tag"] = tag
    sources[0]["commit"] = commit
    output = root / "flatpak/release/io.github.yeager.wifi-analyzer.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, such as v1.2.3")
    args = parser.parse_args()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", f"{args.tag}^{{commit}}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        output = prepare(ROOT, args.tag, commit)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))
    print(f"Prepared release Flatpak manifest {output.relative_to(ROOT)} for {args.tag} at {commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
