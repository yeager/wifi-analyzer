#!/usr/bin/env python3
"""Compile every validated PO catalogue into a gettext locale tree."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def validate_project_id(catalogue: Path) -> None:
    text = catalogue.read_text(encoding="utf-8")
    match = re.search(r'^"Project-Id-Version: ([^"]*)\\n"$', text, re.MULTILINE)
    if not match or match.group(1).strip().casefold() in {"", "package version"}:
        raise ValueError(
            f"{catalogue.name} has an empty or default Project-Id-Version header"
        )


def validate_swedish_catalogue(catalogue: Path) -> None:
    statistics = subprocess.run(
        ["msgfmt", "--check", "--check-format", "--statistics", "-o", "/dev/null", str(catalogue)],
        check=True,
        capture_output=True,
        text=True,
    ).stderr
    if re.search(
        r"\b[1-9]\d* (?:fuzzy translations?|untranslated messages?)\b",
        statistics,
    ):
        raise ValueError(
            "Swedish catalogue contains fuzzy or untranslated messages: "
            + statistics.strip()
        )
    try:
        subprocess.run(
            ["msgcmp", str(catalogue), str(ROOT / "po" / "wifi-analyzer.pot")],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            "Swedish catalogue does not match po/wifi-analyzer.pot: "
            + error.stderr.strip()
        ) from error


def compile_catalogues() -> None:
    for catalogue in sorted((ROOT / "po").glob("*.po")):
        language = catalogue.stem
        validate_project_id(catalogue)
        if language == "sv":
            validate_swedish_catalogue(catalogue)
        targets = (
            ROOT / "locale" / language / "LC_MESSAGES" / "wifi-analyzer.mo",
            ROOT / "src" / "wifi_analyzer" / "locale" / language / "LC_MESSAGES" / "wifi-analyzer.mo",
        )
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["msgfmt", "--check", "--check-format", "-o", str(target), str(catalogue)],
                check=True,
            )


if __name__ == "__main__":
    compile_catalogues()
