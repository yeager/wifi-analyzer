#!/usr/bin/env python3
"""Ensure a release tag agrees with the project and package metadata."""
from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    tag = os.environ.get("RELEASE_TAG", "")
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if not match:
        print(f"Invalid release tag: {tag!r}; expected vMAJOR.MINOR.PATCH", file=sys.stderr)
        return 1
    tag_version = match.group(1)

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = project["project"]["version"]
    metainfo = ET.parse(ROOT / "data/io.github.yeager.wifi-analyzer.metainfo.xml").getroot()
    appstream_version = metainfo.find("releases/release").get("version")
    changelog = (ROOT / "debian/changelog").read_text(encoding="utf-8")
    changelog_match = re.match(r"wifi-analyzer \(([^)]+)\)", changelog)
    changelog_version = changelog_match.group(1) if changelog_match else None
    versions = {
        "tag": tag_version,
        "pyproject.toml": project_version,
        "AppStream": appstream_version,
        "debian/changelog": changelog_version,
    }
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={version!r}" for name, version in versions.items())
        print(f"Release version mismatch: {details}", file=sys.stderr)
        return 1
    print(f"Release tag {tag} matches package version {project_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
