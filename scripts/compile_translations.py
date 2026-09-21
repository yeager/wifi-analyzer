#!/usr/bin/env python3
"""Compile every validated PO catalogue into a gettext locale tree."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
for catalogue in sorted((ROOT / "po").glob("*.po")):
    language = catalogue.stem
    target = ROOT / "locale" / language / "LC_MESSAGES" / "wifi-analyzer.mo"
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["msgfmt", "--check", "-o", str(target), str(catalogue)], check=True)
