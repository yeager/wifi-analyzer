#!/usr/bin/env python3
"""Check that the Flatpak manifest pins a valid released source version."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FINISH_ARGS = {
    "--share=ipc",
    "--socket=fallback-x11",
    "--socket=wayland",
    "--device=dri",
    "--system-talk-name=org.freedesktop.NetworkManager",
}


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
        source_tag = source.get("tag", "")
        tag_match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", source_tag)
        version_match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
        if not version_match:
            errors.append(f"project version {version!r} is not a semantic version")
        elif not tag_match:
            errors.append(
                f"manifest source tag {source_tag!r} is not a semantic version tag"
            )
        elif tuple(map(int, tag_match.groups())) > tuple(map(int, version_match.groups())):
            errors.append(
                f"manifest source version {source_tag!r} is newer than project version {version!r}"
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

    finish_args = manifest.get("finish-args", [])
    if not isinstance(finish_args, list) or any(not isinstance(arg, str) for arg in finish_args):
        errors.append("manifest finish-args must be a list of permission strings")
    else:
        granted = set(finish_args)
        for permission in sorted(granted - REQUIRED_FINISH_ARGS):
            errors.append(f"manifest grants an unreviewed Flatpak permission: {permission}")
        for permission in sorted(REQUIRED_FINISH_ARGS - granted):
            errors.append(f"manifest is missing required Flatpak permission: {permission}")

    return app_id, version, errors


def main() -> int:
    app_id, version, errors = validate(ROOT)
    if errors:
        for error in errors:
            print(f"Flatpak manifest: {error}")
        return 1

    manifest = json.loads((ROOT / "flatpak/io.github.yeager.wifi-analyzer.json").read_text(encoding="utf-8"))
    source = next(
        source for module in manifest["modules"] for source in module["sources"]
        if source.get("type") == "git"
    )
    print(f"Flatpak manifest pins {app_id} to {source['tag']} (project version {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
