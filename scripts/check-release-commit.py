#!/usr/bin/env python3
"""Verify that a version tag identifies a commit contained in origin/main."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+\Z")


def validate_release_commit(tag: str, root: Path = ROOT) -> tuple[bool, str]:
    if not TAG_PATTERN.fullmatch(tag):
        return False, f"Release tag must use vMAJOR.MINOR.PATCH format; got {tag!r}"
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if resolved.returncode != 0:
        event_ref = os.environ.get("GITHUB_REF", "")
        event_sha = os.environ.get("GITHUB_SHA", "")
        checked_out = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if event_ref != f"refs/tags/{tag}" or checked_out.returncode != 0:
            detail = resolved.stderr.strip()
            return False, f"Could not resolve release tag {tag!r} to a commit: {detail}"
        checked_out_sha = checked_out.stdout.strip()
        if not event_sha or checked_out_sha != event_sha:
            return False, f"Checkout does not match GitHub's commit for release tag {tag!r}"
        resolved_sha = checked_out_sha
    else:
        resolved_sha = resolved.stdout.strip()
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", "main"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if fetched.returncode != 0:
        return False, f"Could not fetch origin/main: {fetched.stderr.strip()}"
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved_sha, "FETCH_HEAD"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if ancestry.returncode != 0:
        return False, f"Release tag {tag} does not point to a commit contained in origin/main"
    return True, f"Release tag {tag} points to a commit contained in origin/main"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: check-release-commit.py vMAJOR.MINOR.PATCH", file=sys.stderr)
        return 2
    valid, message = validate_release_commit(sys.argv[1])
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
