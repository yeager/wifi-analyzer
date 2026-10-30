# Flathub submission

The upstream Flatpak manifest used for local builds and CI is
[`flatpak/io.github.yeager.wifi-analyzer.json`](flatpak/io.github.yeager.wifi-analyzer.json).
It pins a public upstream release tag and commit so builds are reproducible. It
is not a Flathub submission manifest.

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
branch. It does not require a video; older issue comments that mention one are
out of date.

Before a human maintainer submits, they should confirm the release and commit,
build and run the Flatpak, run `flatpak-builder-lint`, and explain each
permission in the pull request. The human submitter must audit the app and
packaging for AI-generated code, documentation or other included material and
disclose affected parts and their approximate extent. Reviewers decide whether
disclosed material is acceptable. The manifest itself must contain no
AI-generated or AI-assisted content, and AI tools must not create the submission
pull request or its text. See Flathub's [requirements and generative AI policy](https://docs.flathub.org/docs/for-app-authors/requirements#generative-ai-policy)
for the current rules; the general [requirements](https://docs.flathub.org/docs/for-app-authors/requirements)
also require complete English localization.

The sandbox only asks for display access, GPU rendering, and the NetworkManager
system D-Bus name needed to scan nearby access points. It does not request
network or home-directory access.
