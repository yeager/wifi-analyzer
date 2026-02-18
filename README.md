# WiFi Analyzer

WiFi network analysis tool built with GTK4/Adwaita.

![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)

## Features

- Scan and list available WiFi networks
- Display channel, signal strength (dBm), security type
- Channel overlap visualization with bell curves
- 2.4 GHz and 5 GHz band filtering
- Signal strength percentage and icons
- Dark/light theme toggle
- Uses `nmcli` as backend

## Installation

```bash
pip install -e .
wifi-analyzer
```

## Requirements

- Python 3.10+
- GTK4, libadwaita
- PyGObject
- NetworkManager (`nmcli`)

## License

GPL-3.0-or-later — Daniel Nylander
