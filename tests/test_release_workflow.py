from pathlib import Path


def test_every_checkout_uses_the_selected_release_tag_when_dispatching():
    workflow = (Path(__file__).parents[1] / ".github/workflows/packages.yml").read_text(
        encoding="utf-8",
    )

    checkout_count = workflow.count("- uses: actions/checkout@v7")
    selected_ref_count = workflow.count("ref: ${{ inputs.release_tag || github.ref }}")

    assert checkout_count == 5
    assert selected_ref_count == checkout_count


def test_flatpak_job_skips_tag_releases_and_manual_tag_dispatches():
    workflow = (Path(__file__).parents[1] / ".github/workflows/packages.yml").read_text(
        encoding="utf-8",
    )

    assert "github.ref_type != 'tag' &&" in workflow
    assert "github.event_name != 'workflow_dispatch' || inputs.release_tag == ''" in workflow
