#!/usr/bin/env python3
"""Check that the Flatpak manifest describes this project's current release."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def validate(root: Path) -> tuple[str, str, list[str]]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = json.loads(
        (root / "flatpak/io.github.yeager.wifi-analyzer.json").read_text(encoding="utf-8")
    )
    project_data = project["project"]
    app_id = manifest.get("app-id", "")
    version = project_data["version"]
    sources = [
        source
        for module in manifest.get("modules", [])
        for source in module.get("sources", [])
        if source.get("type") == "git"
    ]
    errors: list[str] = []

    if len(sources) != 1:
        errors.append(f"expected one Git source, found {len(sources)}")
    else:
        source = sources[0]
        repository = project_data.get("urls", {}).get("Repository", "").removesuffix(".git")
        manifest_repository = source.get("url", "").removesuffix(".git")
        if not repository or manifest_repository != repository:
            errors.append(f"manifest source URL {source.get('url')!r} does not match {repository!r}")
        expected_tag = f"v{version}"
        if source.get("tag") != expected_tag:
            errors.append(
                f"manifest source tag {source.get('tag')!r} does not match project version {expected_tag!r}"
            )
        if not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", "")):
            errors.append("manifest Git source must pin a full 40-character lowercase commit hash")

    if not app_id:
        errors.append("manifest is missing app-id")
    else:
        command = manifest.get("command")
        if command not in project_data.get("scripts", {}):
            errors.append(f"manifest command {command!r} is not declared in pyproject.toml")
        desktop_file = root / "data" / f"{app_id}.desktop"
        if not desktop_file.is_file():
            errors.append(f"desktop file does not match app-id: {desktop_file.name}")
        metainfo_file = root / "data" / f"{app_id}.metainfo.xml"
        if not metainfo_file.is_file():
            errors.append(f"AppStream file does not match app-id: {metainfo_file.name}")
        else:
            metadata_id = ET.parse(metainfo_file).getroot().findtext("id")
            if metadata_id != app_id:
                errors.append(f"AppStream id {metadata_id!r} does not match manifest app-id {app_id!r}")

    return app_id, version, errors


def main() -> int:
    app_id, version, errors = validate(ROOT)
    if errors:
        for error in errors:
            print(f"Flatpak manifest: {error}")
        return 1

    print(f"Flatpak manifest matches {app_id} {version} (v{version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
