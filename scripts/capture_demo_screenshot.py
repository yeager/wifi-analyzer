#!/usr/bin/env python3
"""Capture the running GTK app with fictional access points for documentation."""
import json
import os
import subprocess
import sys
from pathlib import Path

from wifi_analyzer import app
from gi.repository import GLib


DEMO_NETWORKS = [
    {
        "ssid": "Example Home", "bssid": "02:00:00:00:00:01",
        "freq": 2412, "channel": 1, "signal_pct": 86, "dbm": -57,
        "security": "WPA3", "band": "2.4 GHz", "width_mhz": 20,
        "channel_status": "", "last_seen": 0, "connected": True,
        "width_source": "measured", "wifi_standard": "Wi-Fi 6",
    },
    {
        "ssid": "Example Guest", "bssid": "02:00:00:00:00:02",
        "freq": 2437, "channel": 6, "signal_pct": 62, "dbm": -69,
        "security": "WPA2", "band": "2.4 GHz", "width_mhz": 20,
        "channel_status": "", "last_seen": 0, "connected": False,
        "width_source": "estimated", "wifi_standard": "",
    },
    {
        "ssid": "Example Neighbour", "bssid": "02:00:00:00:00:03",
        "freq": 2462, "channel": 11, "signal_pct": 43, "dbm": -78,
        "security": "WPA2", "band": "2.4 GHz", "width_mhz": 20,
        "channel_status": "", "last_seen": 0, "connected": False,
        "width_source": "estimated", "wifi_standard": "",
    },
]


def capture_and_quit(_app):
    window = _app.get_active_window()
    if not window or len(window.visible_networks) != len(DEMO_NETWORKS):
        count = len(window.visible_networks) if window else 0
        raise RuntimeError(f"Expected 3 visible demo networks, found {count}")
    window_ids = subprocess.check_output(
        ["xdotool", "search", "--onlyvisible", "--name", "WiFi Analyzer"],
        text=True,
    ).splitlines()
    if not window_ids:
        raise RuntimeError("Could not find the visible WiFi Analyzer X11 window")
    subprocess.run(["xdotool", "windowfocus", "--sync", window_ids[0]], check=True)
    focused_window = subprocess.check_output(["xdotool", "getwindowfocus"], text=True).strip()
    if focused_window != window_ids[0]:
        raise RuntimeError("Could not focus the WiFi Analyzer X11 window")
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["scrot", "-u", str(target)], check=False)
    if result.returncode or not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("Could not capture the Wi-Fi Analyzer window")
    _app.quit()
    return GLib.SOURCE_REMOVE


def main():
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = config_root / "wifi-analyzer"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "welcome.json").write_text(
        json.dumps({"welcome_shown": True}), encoding="utf-8"
    )
    app.scan_networks_dbus = lambda: DEMO_NETWORKS
    app.WifiAnalyzerWindow._scan = lambda window: window._on_scan_done(DEMO_NETWORKS)
    application = app.WifiAnalyzerApp()
    result = {"status": 0}

    def capture(_app):
        try:
            capture_and_quit(_app)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            print(f"Screenshot capture failed: {error}", file=sys.stderr)
            result["status"] = 1
            _app.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(4, capture, application)
    application.connect("activate", lambda *_args: None)
    application.run()
    return result["status"]


if __name__ == "__main__":
    raise SystemExit(main())
