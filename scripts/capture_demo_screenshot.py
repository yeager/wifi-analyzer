#!/usr/bin/env python3
"""Capture the running GTK app with fictional access points for documentation."""
import json
import os
import subprocess
import sys
import time
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


def run_demo_app():
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = config_root / "wifi-analyzer"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "welcome.json").write_text(
        json.dumps({"welcome_shown": True}), encoding="utf-8"
    )
    # The demo must never issue a real scan; populate the UI after its window
    # has been presented so GTK has a mapped surface before the screenshot.
    app.WifiAnalyzerWindow._scan = lambda _window: None

    class DemoApp(app.WifiAnalyzerApp):
        def do_activate(self):
            window = self.get_active_window()
            if not window:
                window = app.WifiAnalyzerWindow(self)
            self._wlc_settings = {"welcome_shown": True}
            window.present()
            GLib.idle_add(self._populate_demo_networks, window)

        @staticmethod
        def _populate_demo_networks(window):
            window.networks = [dict(network) for network in DEMO_NETWORKS]
            window._update_ui()
            if len(window.visible_networks) != len(DEMO_NETWORKS):
                print(
                    f"Expected 3 visible demo networks, found {len(window.visible_networks)}",
                    file=sys.stderr,
                    flush=True,
                )
                window.get_application().quit()
                return GLib.SOURCE_REMOVE
            window._set_status("Found 3 networks")
            ready = Path(os.environ["WIFI_ANALYZER_DEMO_READY"])
            ready.write_text(json.dumps({
                "visible_networks": len(window.visible_networks),
                "status": window.statusbar.get_label(),
            }), encoding="utf-8")
            return GLib.SOURCE_REMOVE

    application = DemoApp()
    application.run()
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        return run_demo_app()

    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    ready = Path(os.environ["WIFI_ANALYZER_DEMO_READY"])
    ready.unlink(missing_ok=True)
    server = subprocess.Popen([sys.executable, __file__, "--serve"])
    try:
        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError("Demo app exited before its screenshot was captured")
            if ready.is_file():
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Demo app did not display the fictional networks in time")
        state = json.loads(ready.read_text(encoding="utf-8"))
        if (
            state.get("visible_networks") != len(DEMO_NETWORKS)
            or "Found 3 networks" not in state.get("status", "")
        ):
            raise RuntimeError(f"Demo app reported unexpected UI state: {state}")
        time.sleep(1)
        result = subprocess.run(["scrot", "-u", str(target)], check=False, timeout=5)
        if result.returncode or not target.is_file() or target.stat().st_size < 10_000:
            raise RuntimeError("Screenshot did not contain the rendered Wi-Fi Analyzer window")
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
