# Flathub submission

The manifest intended for Flathub is
[`flatpak/io.github.yeager.WifiAnalyzer.json`](flatpak/io.github.yeager.WifiAnalyzer.json).
It pins the public upstream release tag and commit so reviewers can reproduce
the build without trusting a moving branch.

Before opening a Flathub pull request:

1. Update the manifest to the newest signed release tag and commit.
2. Build it with Flatpak Builder using the current GNOME SDK.
3. Open a submission pull request to
   <https://github.com/flathub/flathub> with this manifest named
   `io.github.yeager.WifiAnalyzer.json`.
4. Respond to the automated build and AppStream review comments there.

The sandbox only asks for display access, GPU rendering, and the NetworkManager
system D-Bus name needed to scan nearby access points. It does not request
network or home-directory access.
