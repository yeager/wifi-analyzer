import json
import shutil
import sys
import tomllib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_flatpak_manifest import validate
from prepare_flatpak_release_manifest import prepare


def _copy_release_manifest_inputs(destination):
    for relative_path in (
        "pyproject.toml",
        "flatpak/io.github.yeager.wifi-analyzer.json",
        "data/io.github.yeager.wifi-analyzer.desktop",
        "data/io.github.yeager.wifi-analyzer.metainfo.xml",
    ):
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, target)


def test_flatpak_manifest_pins_the_current_project_release():
    app_id, version, errors = validate(ROOT)

    assert app_id == "io.github.yeager.wifi-analyzer"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert version == project["project"]["version"]
    assert errors == []


@pytest.mark.parametrize("tag_offset", [-1, 1])
def test_flatpak_manifest_rejects_a_source_tag_that_does_not_match_the_project(
    tmp_path, tag_offset
):
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
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    major, minor, patch = map(int, project["project"]["version"].split("."))
    manifest["modules"][0]["sources"][0]["tag"] = (
        f"v{major}.{minor}.{patch + tag_offset}"
    )
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
    project_text = project_path.read_text(encoding="utf-8")
    version = tomllib.loads(project_text)["project"]["version"]
    project = project_text.replace(
        f'version = "{version}"', f'version = "{version}+local"'
    )
    project_path.write_text(project, encoding="utf-8")

    _app_id, _version, errors = validate(tmp_path)

    assert any("project version" in error for error in errors)


def test_flatpak_manifest_rejects_unreviewed_host_filesystem_access(tmp_path):
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
    manifest["finish-args"].append("--filesystem=host")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _app_id, _version, errors = validate(tmp_path)

    assert any("unreviewed Flatpak permission: --filesystem=host" in error for error in errors)


def test_release_manifest_pins_the_exact_version_tag_and_commit(tmp_path):
    _copy_release_manifest_inputs(tmp_path)
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    tag = f"v{project['project']['version']}"
    commit = "a" * 40
    original_manifest = (tmp_path / "flatpak/io.github.yeager.wifi-analyzer.json").read_text(encoding="utf-8")

    output = prepare(tmp_path, tag, commit)

    assert output.name == "io.github.yeager.wifi-analyzer.json"
    assert output.parent.name == "release"
    manifest = json.loads(output.read_text(encoding="utf-8"))
    source = manifest["modules"][0]["sources"][0]
    assert source["tag"] == tag
    assert source["commit"] == commit
    assert (tmp_path / "flatpak/io.github.yeager.wifi-analyzer.json").read_text(encoding="utf-8") == original_manifest
    _app_id, _version, errors = validate(tmp_path, output)
    assert errors == []


def test_release_manifest_rejects_a_tag_that_does_not_match_project_version(tmp_path):
    _copy_release_manifest_inputs(tmp_path)

    with pytest.raises(ValueError, match="does not match project version"):
        prepare(tmp_path, "v9.9.9", "a" * 40)


def test_release_manifest_rejects_an_unpinned_commit(tmp_path):
    _copy_release_manifest_inputs(tmp_path)
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    tag = f"v{project['project']['version']}"

    with pytest.raises(ValueError, match="full lowercase Git hash"):
        prepare(tmp_path, tag, "not-a-commit")
