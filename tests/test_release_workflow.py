import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_every_checkout_uses_the_selected_release_tag_when_dispatching():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")

    checkout_count = workflow.count("- uses: actions/checkout@v7")
    selected_ref_count = workflow.count("ref: ${{ inputs.release_tag || github.ref }}")

    assert checkout_count == 5
    assert selected_ref_count == checkout_count


def test_flatpak_job_skips_tag_releases_and_manual_tag_dispatches():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")

    assert "github.ref_type != 'tag' &&" in workflow
    assert "github.event_name != 'workflow_dispatch' || inputs.release_tag == ''" in workflow


def test_release_workflow_checks_the_selected_version_tag_before_uploading():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    assert "python3 scripts/check-release-tag.py \"$RELEASE_TAG\"" in workflow
    assert workflow.index("Verify release tag matches package metadata") < workflow.index(
        "actions/download-artifact@v7",
        workflow.index("  release:"),
    )


def test_release_workflow_updates_assets_when_the_release_already_exists():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    assert 'gh release view "$RELEASE_TAG"' in workflow
    assert 'gh release upload "$RELEASE_TAG" "${assets[@]}" --clobber' in workflow
    assert 'gh release create "$RELEASE_TAG"' in workflow


def run_release_tag_check(tag):
    env = dict(os.environ, RELEASE_TAG=tag)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-release-tag.py")],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_tag_checker_accepts_matching_version():
    result = run_release_tag_check("v0.1.28")
    assert result.returncode == 0, result.stderr
    assert "matches package version 0.1.28" in result.stdout


def test_release_tag_checker_rejects_a_different_or_malformed_version():
    for tag in ("v0.1.27", "0.1.28", "v0.1.28-rc1"):
        result = run_release_tag_check(tag)
        assert result.returncode != 0, tag
