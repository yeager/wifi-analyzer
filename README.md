# Wi-Fi Analyzer

Wi-Fi signal analyzer and channel scanner.

Built with GTK4/Adwaita. Part of the [Danne L10n Suite](https://github.com/yeager/debian-repo).

## Features

- Scan access points through NetworkManager D-Bus; no privileged shell command is required.
- Filter results by network name, BSSID, channel or security type.
- Inspect 2.4, 5 and 6 GHz bands with a channel-overlap graph.
- Show the inferred 20 MHz primary-channel width. NetworkManager does not expose
  an access point's negotiated width, so the application labels this value as an estimate.
- Mark 5 GHz DFS channels. Their availability depends on the local regulatory domain.
- Recommend less congested channels from observed signal overlap.
- Sort results by signal, channel, or security and group repeated SSIDs by access-point count.
- Export scan results as CSV or JSON from the application menu.
- Keep up to 100 local scan summaries for future history views. Scan data never leaves the device and can be cleared from the menu.
- Mark the active access point and use the actual channel width reported by `iw` for that radio when available.
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

## Translations

The user interface has gettext catalogues for 20 languages, including Swedish.
See [`po/README.md`](po/README.md) to contribute or validate a translation.

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
