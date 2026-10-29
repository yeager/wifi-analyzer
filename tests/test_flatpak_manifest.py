import json
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_flatpak_manifest import validate


def test_flatpak_manifest_pins_a_released_source_not_newer_than_the_project():
    app_id, version, errors = validate(ROOT)

    assert app_id == "io.github.yeager.wifi-analyzer"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert tuple(map(int, version.split("."))) <= tuple(
        map(int, project["project"]["version"].split("."))
    )
    assert errors == []


def test_flatpak_manifest_rejects_a_source_tag_newer_than_the_project(tmp_path):
    for relative_path in (
        "pyproject.toml",
        "flatpak/io.github.yeager.wifi-analyzer.json",
        "data/io.github.yeager.wifi-analyzer.desktop",
        "data/io.github.yeager.wifi-analyzer.metainfo.xml",
    ):
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, destination)

    manifest_path = tmp_path / "flatpak/io.github.yeager.wifi-analyzer.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["modules"][0]["sources"][0]["tag"] = "v0.1.25"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _app_id, _version, errors = validate(tmp_path)

    assert any("source version" in error for error in errors)


def test_flatpak_manifest_rejects_a_non_semantic_project_version(tmp_path):
    for relative_path in (
        "pyproject.toml",
        "flatpak/io.github.yeager.wifi-analyzer.json",
        "data/io.github.yeager.wifi-analyzer.desktop",
        "data/io.github.yeager.wifi-analyzer.metainfo.xml",
    ):
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, destination)

    project_path = tmp_path / "pyproject.toml"
    project = project_path.read_text(encoding="utf-8").replace(
        'version = "0.1.24"', 'version = "0.1.24+local"'
    )
    project_path.write_text(project, encoding="utf-8")

    _app_id, _version, errors = validate(tmp_path)

    assert any("project version" in error for error in errors)
