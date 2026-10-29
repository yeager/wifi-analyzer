# Flathub submission

The manifest intended for Flathub is
[`flatpak/io.github.yeager.wifi-analyzer.json`](flatpak/io.github.yeager.wifi-analyzer.json).
It pins a public upstream release tag and commit so builds are reproducible.

## Before a human submission

Flathub's current policy says manifests must not contain AI-generated or
AI-assisted material, and AI agents must not create or automate submission
pull requests or write their messages. The manifest in this repository has
AI-assisted changes, so it is suitable for reproducible upstream builds but
must not be copied into a Flathub submission. A human maintainer must create
and review a compliant manifest independently.

The current public [submission guide](https://docs.flathub.org/docs/for-app-authors/submission)
asks maintainers to build and run the app, run the Flathub linter, then create
the submission pull request through GitHub's web interface against the `new-pr`
branch. The guide does not list a video as a submission requirement. An earlier
project note mentions a Linux video and checklist; confirm whether a separate
Flathub request applies before treating that as a current requirement.

Before a human maintainer submits, they should confirm the release and commit,
build and run the Flatpak, run `flatpak-builder-lint`, and explain each
permission in the pull request. Flathub's [requirements](https://docs.flathub.org/docs/for-app-authors/requirements)
also require complete English localization and apply its AI-content policy to
submission material.

The sandbox only asks for display access, GPU rendering, and the NetworkManager
system D-Bus name needed to scan nearby access points. It does not request
network or home-directory access.
