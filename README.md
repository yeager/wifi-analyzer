<p align="center">
  <img src="assets/wifi-analyzer-logo.png" width="220" alt="WiFi Analyzer logo">
</p>

# WiFi Analyzer

Wi-Fi signal analyzer, channel planner and local connection diagnostics tool.

Built with GTK4/Adwaita. Part of the [Danne L10n Suite](https://github.com/yeager/debian-repo).

## Features

- Scan access points through NetworkManager D-Bus; no privileged shell command is required.
- Filter results by network name, BSSID, channel or security type.
- Inspect 2.4, 5 and 6 GHz bands with a channel-overlap graph.
- Show NetworkManager's announced AP bandwidth when available, with a clearly
  marked estimate as a fallback.
- Mark 5 GHz DFS channels. Their availability depends on the local regulatory domain.
- Recommend less congested channels from observed signal overlap.
- Sort results by signal, channel, or security and group repeated SSIDs by access-point count.
- Export visible, filtered results as CSV, JSON, anonymized JSON or an HTML
  diagnostic report, with a user-selected file name and destination.
- Keep up to 100 local scan summaries for future history views. Scan data never leaves the device and can be cleared from the menu.
- Mark the active access point and use the actual channel width reported by `iw` for that radio when available.
- Identify Wi-Fi 4, 5, 6/6E and 7 for the active link from `iw` PHY markers.
  A generation is never guessed for an unconnected AP.
- Compare consecutive scans to identify new, missing, or materially changed access points.
- Create a self-contained HTML diagnostic report or an anonymized JSON export for safe sharing.
- Select an access point to identify the strongest overlapping neighbours.
- Show the active connection's gateway and DNS servers from local system diagnostics.
- Use optional 60-second monitoring and location profiles for private local scan history.

## Installation

### Debian/Ubuntu
```bash
sudo apt install wifi-analyzer
```

Source packages follow Debian policy and can be built with:

```bash
dpkg-buildpackage -us -uc -b
```

### Fedora/RPM distributions

Build the source RPM with:

```bash
rpmbuild -ba packaging/rpm/wifi-analyzer.spec
```

GitHub Actions builds both `.deb` and `.rpm` artifacts for releases and pull
requests.

## Translations

The user interface uses gettext catalogues for 20 languages. Swedish is
translated and reviewed; the remaining catalogues are ready for translation.
See [`po/README.md`](po/README.md) to contribute or validate a translation.
The Swedish manual page is installed as `wifi-analyzer(1)` and is maintained in
[`docs/man/sv`](docs/man/sv).

### Flatpak

Flatpak-paketet byggs från
[`build-aux/io.github.yeager.WifiAnalyzer.json`](build-aux/io.github.yeager.WifiAnalyzer.json).
Det kan installeras med Flatpak Builder tills paketet har publicerats på Flathub.

```bash
flatpak-builder --user --install --force-clean build-dir \
  build-aux/io.github.yeager.WifiAnalyzer.json
```

## License

GPL-3.0

## Author

Daniel Nylander — [danielnylander.se](https://danielnylander.se)
