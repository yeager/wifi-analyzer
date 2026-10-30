import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_every_checkout_uses_the_selected_release_tag_when_dispatching():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")

    checkout_count = workflow.count("- uses: actions/checkout@v7")
    selected_ref_count = workflow.count("ref: ${{ inputs.release_tag || github.ref }}")

    assert checkout_count == 5
    assert selected_ref_count == checkout_count


def test_flatpak_job_builds_exact_release_tags_and_includes_them_in_releases():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")

    assert "scripts/prepare_flatpak_release_manifest.py \"$release_tag\"" in workflow
    assert "mv flatpak/release-manifest.json flatpak/release/io.github.yeager.wifi-analyzer.json" in workflow
    assert "check_flatpak_manifest.py --manifest flatpak/release/io.github.yeager.wifi-analyzer.json" in workflow
    assert "needs: [screenshot, flatpak, debian, rpm]" in workflow
    assert "name: wifi-analyzer-flatpak" in workflow
    assert "-name '*.flatpak'" in workflow


def test_release_workflow_checks_the_selected_version_tag_before_uploading():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    assert "python3 scripts/check-release-tag.py \"$RELEASE_TAG\"" in workflow
    assert "python3 scripts/check-release-commit.py \"$RELEASE_TAG\"" in workflow
    assert workflow.index("Verify release tag matches package metadata") < workflow.index(
        "actions/download-artifact@v7",
        workflow.index("  release:"),
    )


def test_pypi_release_checks_tag_version_and_main_ancestry_before_publish():
    workflow = (ROOT / ".github/workflows/pypi-publish.yml").read_text(encoding="utf-8")
    assert workflow.count("python3 scripts/check-release-tag.py \"$RELEASE_TAG\"") == 2
    assert workflow.count("python3 scripts/check-release-commit.py \"$RELEASE_TAG\"") == 2
    assert workflow.count("fetch-depth: 0") == 2
    assert workflow.count("ref: ${{ inputs.release_tag || github.ref }}") == 2
    assert workflow.count("Mark the checkout as safe for Git") == 2
    assert workflow.count("inputs.release_tag != ''") == 2


def test_release_commit_checker_rejects_a_non_semver_tag_without_git_access():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-release-commit.py"), "not-a-tag"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "vMAJOR.MINOR.PATCH" in result.stdout


def test_release_commit_checker_accepts_main_and_rejects_unmerged_tag(tmp_path):
    work = tmp_path / "work"
    remote = tmp_path / "origin.git"
    work.mkdir()

    def git(*arguments):
        return subprocess.run(
            ["git", *arguments], cwd=work, capture_output=True, text=True, check=True,
        ).stdout.strip()

    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (work / "state").write_text("main\n", encoding="utf-8")
    git("add", "state")
    git("commit", "-m", "main")
    git("remote", "add", "origin", str(remote))
    git("push", "-u", "origin", "main")
    git("tag", "v1.2.3")
    git("push", "origin", "v1.2.3")
    main_sha = git("rev-parse", "HEAD")

    checker = ROOT / "scripts/check-release-commit.py"
    (work / "scripts").mkdir()
    shutil.copyfile(checker, work / "scripts/check-release-commit.py")
    checker = work / "scripts/check-release-commit.py"
    accepted = subprocess.run(
        [sys.executable, str(checker), "v1.2.3"], cwd=work,
        check=False, capture_output=True, text=True,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    git("tag", "-d", "v1.2.3")
    event_environment = dict(
        os.environ,
        GITHUB_REF="refs/tags/v1.2.3",
        GITHUB_SHA=main_sha,
    )
    accepted_without_local_tag = subprocess.run(
        [sys.executable, str(checker), "v1.2.3"], cwd=work,
        env=event_environment, check=False, capture_output=True, text=True,
    )
    assert accepted_without_local_tag.returncode == 0, (
        accepted_without_local_tag.stdout + accepted_without_local_tag.stderr
    )

    git("checkout", "-b", "unmerged")
    (work / "unmerged").write_text("unmerged\n", encoding="utf-8")
    git("add", "unmerged")
    git("commit", "-m", "unmerged")
    git("tag", "v1.2.4")
    rejected = subprocess.run(
        [sys.executable, str(checker), "v1.2.4"], cwd=work,
        check=False, capture_output=True, text=True,
    )
    assert rejected.returncode != 0
    assert "not point to a commit contained in origin/main" in rejected.stdout


def test_release_workflow_updates_assets_when_the_release_already_exists():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    assert 'scripts/publish-release-assets.sh "${assets[@]}"' in workflow


def test_debian_smoke_test_requires_launcher_metadata_icons_and_translations():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    for path in (
        "usr/share/applications/io.github.yeager.wifi-analyzer.desktop",
        "usr/share/metainfo/io.github.yeager.wifi-analyzer.metainfo.xml",
        "usr/share/icons/hicolor/256x256/apps/io.github.yeager.wifi-analyzer.png",
        "usr/share/icons/hicolor/512x512/apps/io.github.yeager.wifi-analyzer.png",
        "usr/share/locale/sv/LC_MESSAGES/wifi-analyzer.mo",
        "usr/share/man/man1/wifi-analyzer.1.gz",
        "usr/share/man/sv/man1/wifi-analyzer.1.gz",
    ):
        assert path in workflow


def test_rpm_build_checks_launcher_metadata_icons_and_translations():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    rpm_job = workflow.split("  rpm:\n", 1)[1].split("  release:\n", 1)[0]
    assert "rpm -qpl \"$package\"" in rpm_job
    for path in (
        "/usr/share/applications/io.github.yeager.wifi-analyzer.desktop",
        "/usr/share/metainfo/io.github.yeager.wifi-analyzer.metainfo.xml",
        "/usr/share/icons/hicolor/256x256/apps/io.github.yeager.wifi-analyzer.png",
        "/usr/share/icons/hicolor/512x512/apps/io.github.yeager.wifi-analyzer.png",
        "/usr/share/locale/sv/LC_MESSAGES/wifi-analyzer.mo",
        "/usr/share/man/man1/wifi-analyzer.1.gz",
        "/usr/share/man/sv/man1/wifi-analyzer.1.gz",
    ):
        assert path in rpm_job


def test_rpm_build_pins_fedora_and_installs_pyproject_build_backend():
    workflow = (ROOT / ".github/workflows/packages.yml").read_text(encoding="utf-8")
    rpm_job = workflow.split("  rpm:\n", 1)[1].split("  release:\n", 1)[0]
    spec = (ROOT / "packaging/rpm/wifi-analyzer.spec").read_text(encoding="utf-8")
    build_system = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["build-system"]
    assert "container: fedora:44" in rpm_job
    assert "python3-setuptools_scm" in rpm_job
    assert "python3dist(setuptools-scm)" in spec
    assert any("setuptools-scm" in requirement for requirement in build_system["requires"])


def test_iw_is_optional_for_rpm_and_recommended_for_extra_radio_details():
    spec = (ROOT / "packaging/rpm/wifi-analyzer.spec").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Recommends:      iw" in spec
    assert "Requires:        iw" not in spec
    assert "does not require `iw`" in readme


def test_apt_repository_instructions_include_the_primary_key_fingerprint_check():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "C7982569D1DCC5468A072D94D7B45ED27B9EBB63" in readme
    assert "gpg --show-keys --with-fingerprint /tmp/yeager-repo-key.asc" in readme
    assert "https://yeager.github.io/debian-repo stable main" in readme


def run_release_publisher(tmp_path, release_exists):
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    calls_path = tmp_path / "gh-calls"
    fake_gh = bin_directory / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\0' \"$@\" >> \"$GH_CALLS\"\n"
        "printf '\\0' >> \"$GH_CALLS\"\n"
        "if [[ \"$1 $2\" == 'release view' ]]; then\n"
        "  [[ \"$FAKE_RELEASE_EXISTS\" == 1 ]]\n"
        "elif [[ \"$1 $2\" == 'release upload' || \"$1 $2\" == 'release create' ]]; then\n"
        "  exit 0\n"
        "else\n"
        "  exit 90\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    environment = dict(
        os.environ,
        PATH=f"{bin_directory}{os.pathsep}{os.environ['PATH']}",
        RELEASE_TAG="v0.1.28",
        GH_CALLS=str(calls_path),
        FAKE_RELEASE_EXISTS="1" if release_exists else "0",
    )
    assets = ["wifi-analyzer_0.1.28_all.deb", "wifi-analyzer-0.1.28-1.noarch.rpm"]
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/publish-release-assets.sh"), *assets],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    calls = []
    for invocation in calls_path.read_bytes().split(b"\0\0"):
        if invocation:
            calls.append([os.fsdecode(argument) for argument in invocation.split(b"\0")])
    return result, calls, assets


def test_release_publisher_uploads_and_replaces_assets_for_existing_release(tmp_path):
    result, calls, assets = run_release_publisher(tmp_path, release_exists=True)
    assert result.returncode == 0, result.stderr
    assert calls == [
        ["release", "view", "v0.1.28"],
        ["release", "upload", "v0.1.28", *assets, "--clobber"],
    ]


def test_release_publisher_creates_a_new_release_with_verified_tag(tmp_path):
    result, calls, assets = run_release_publisher(tmp_path, release_exists=False)
    assert result.returncode == 0, result.stderr
    assert calls == [
        ["release", "view", "v0.1.28"],
        [
            "release", "create", "v0.1.28", "--verify-tag", "--generate-notes",
            "--title", "WiFi Analyzer v0.1.28", *assets,
        ],
    ]


def test_release_publisher_requires_a_tag_and_assets(tmp_path):
    script = ROOT / "scripts/publish-release-assets.sh"
    without_tag = subprocess.run(
        ["bash", str(script), "asset.deb"], cwd=ROOT,
        env=dict(os.environ, RELEASE_TAG=""), capture_output=True, text=True,
    )
    assert without_tag.returncode == 2
    without_assets = subprocess.run(
        ["bash", str(script)], cwd=ROOT,
        env=dict(os.environ, RELEASE_TAG="v0.1.28"), capture_output=True, text=True,
    )
    assert without_assets.returncode == 2


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
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    result = run_release_tag_check(f"v{version}")
    assert result.returncode == 0, result.stderr
    assert f"matches package version {version}" in result.stdout


def test_release_tag_checker_rejects_a_different_or_malformed_version():
    for tag in ("v0.0.0", "0.1.30", "v0.1.30-rc1"):
        result = run_release_tag_check(tag)
        assert result.returncode != 0, tag
