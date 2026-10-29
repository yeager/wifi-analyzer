import json
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_flatpak_manifest import validate


def test_flatpak_manifest_matches_the_current_release():
    app_id, version, errors = validate(ROOT)

    assert app_id == "io.github.yeager.wifi-analyzer"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert version == project["project"]["version"]
    assert errors == []


def test_flatpak_manifest_rejects_a_stale_source_tag(tmp_path):
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
    manifest["modules"][0]["sources"][0]["tag"] = "v0.1.22"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _app_id, _version, errors = validate(tmp_path)

    assert any("manifest source tag" in error for error in errors)
