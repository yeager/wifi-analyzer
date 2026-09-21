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

## Installation

### Debian/Ubuntu
```bash
sudo apt install wifi-analyzer
```

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
