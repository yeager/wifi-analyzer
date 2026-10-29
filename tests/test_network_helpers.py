import json
import subprocess
import sys
from pathlib import Path

from wifi_analyzer.app import (
    band_for_frequency,
    channel_status,
    channel_width_mhz,
    channel_recommendation_text,
    freq_to_channel,
    network_matches_query,
    parse_regulatory_ranges,
    recommend_channels,
    save_history_snapshot,
    clear_history,
    compare_scans,
    parse_iw_channel_width,
    parse_iw_wifi_standard,
    anonymize_network,
    interference_contributors,
    parse_connection_diagnostics,
    load_signal_history,
    wifi_problem,
)


def test_app_module_loads_when_executed_as_a_script():
    app = Path(__file__).parents[1] / "src" / "wifi_analyzer" / "app.py"
    result = subprocess.run(
        [sys.executable, "-c", f"import runpy; runpy.run_path({str(app)!r}, run_name='direct_app')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_frequency_helpers_cover_all_supported_bands():
    assert (freq_to_channel(2412), band_for_frequency(2412)) == (1, "2.4 GHz")
    assert (freq_to_channel(5180), band_for_frequency(5180)) == (36, "5 GHz")
    assert (freq_to_channel(5955), band_for_frequency(5955)) == (1, "6 GHz")
    assert channel_width_mhz(5180) == 20
    assert channel_width_mhz(0) == 0
    assert freq_to_channel(2484) == 14
    assert freq_to_channel(7125) == 0


def test_dfs_channels_are_identified_without_claiming_a_ban():
    assert "DFS" in channel_status(5260, 52)
    assert channel_status(5180, 36) == ""


def test_regulatory_ranges_mark_dfs_and_unavailable_channels():
    ranges = parse_regulatory_ranges("\t(5250 - 5350 @ 80), (N/A, 26), (0 ms), DFS\n")
    assert "radar" in channel_status(5260, 52, ranges)
    assert "Unavailable" in channel_status(5180, 36, ranges)


def test_network_search_matches_displayed_fields_case_insensitively():
    network = {
        "ssid": "Office WiFi",
        "bssid": "AA:BB:CC:DD:EE:FF",
        "band": "5 GHz",
        "channel": 52,
        "security": "WPA3",
        "width_mhz": 20,
        "channel_status": "DFS",
    }
    assert network_matches_query(network, "office")
    assert network_matches_query(network, "aa:bb")
    assert network_matches_query(network, "wpa3")
    assert network_matches_query(network, "52")
    assert not network_matches_query(network, "guest")


def test_channel_recommendation_avoids_the_strongest_overlap():
    networks = [{"band": "2.4 GHz", "channel": 1, "signal_pct": 90, "width_mhz": 20}]
    assert recommend_channels(networks, "2.4 GHz")[0][0] in (6, 11)
    assert recommend_channels([], "2.4 GHz") == []
    assert recommend_channels([], "5 GHz") == []
    assert recommend_channels([], "6 GHz") == []


def test_channel_recommendation_explains_the_limits_of_the_scan_score():
    summary, explanation = channel_recommendation_text([(6, 0.0)])

    assert summary == "Lowest estimated overlap in this scan: channel 6 (score 0.0)"
    assert "Lower scores mean less estimated overlap" in explanation
    assert "Only access points found in this scan count" in explanation
    assert "client traffic and hidden networks are not measured" in explanation


def test_missing_channel_recommendation_suggests_a_scan():
    summary, explanation = channel_recommendation_text([])

    assert summary == "No channel recommendation available"
    assert explanation == "Scan this band to compare nearby access points."


def test_channel_recommendations_require_a_complete_scan_with_band_observations():
    network = {"band": "5 GHz", "channel": 36, "signal_pct": 75, "width_mhz": 20}
    assert recommend_channels([network], "2.4 GHz") == []
    assert recommend_channels([network, {"error_code": "scan-failed"}], "5 GHz") == []
    assert recommend_channels([network, {"error_code": "no-device"}], "5 GHz") == []
    assert recommend_channels([network], "5 GHz")


def test_channel_recommendations_respect_detected_regulatory_ranges():
    ranges = [
        (2437, 2437, ""),  # 2.4 GHz channel 6
        (5180, 5200, ""),  # 5 GHz channels 36 and 40
        (5955, 5975, ""),  # 6 GHz channels 1 and 5
    ]

    networks = [
        {"band": "2.4 GHz", "channel": 6, "signal_pct": 30, "width_mhz": 20},
        {"band": "5 GHz", "channel": 36, "signal_pct": 30, "width_mhz": 20},
        {"band": "6 GHz", "channel": 1, "signal_pct": 30, "width_mhz": 20},
    ]
    assert {channel for channel, _score in recommend_channels(networks, "2.4 GHz", ranges)} == {6}
    assert {channel for channel, _score in recommend_channels(networks, "5 GHz", ranges)} == {36, 40}
    assert {channel for channel, _score in recommend_channels(networks, "6 GHz", ranges)} == {1, 5}


def test_history_is_bounded_and_can_be_cleared(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    save_history_snapshot([{"ssid": "Office", "bssid": "aa:bb", "band": "5 GHz", "channel": 36,
                            "signal_pct": 50, "dbm": -75, "security": "WPA3"}], now="2026-09-21T15:00:00")
    history = tmp_path / "wifi-analyzer" / "history.json"
    assert "Office" in history.read_text()
    assert history.stat().st_mode & 0o777 == 0o600
    clear_history()
    assert not history.exists()


def test_history_recovers_from_wrong_json_shape_and_ignores_bad_records(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    history = tmp_path / "wifi-analyzer" / "history.json"
    history.parent.mkdir(parents=True)
    history.write_text('{"not": "a list"}', encoding="utf-8")

    save_history_snapshot(
        [{"ssid": "Office", "bssid": "aa:bb", "signal_pct": 75, "channel": 36}],
        now="2026-10-29T12:00:00",
        profile="Office",
    )
    assert load_signal_history("aa:bb", "Office") == [
        {"scanned_at": "2026-10-29T12:00:00", "signal_pct": 75, "channel": 36},
    ]

    history.write_text(json.dumps([
        {"scanned_at": [], "profile": "Office", "networks": []},
        {"scanned_at": "broken", "profile": "Office", "networks": [
            None,
            {"bssid": "aa:bb", "signal_pct": "bad", "channel": 36},
        ]},
        {"scanned_at": "valid", "profile": "Office", "networks": [
            {"bssid": "aa:bb", "signal_pct": 60, "channel": 40},
        ]},
    ]), encoding="utf-8")

    assert load_signal_history("aa:bb", "Office") == [
        {"scanned_at": "valid", "signal_pct": 60, "channel": 40},
    ]


def test_scan_comparison_width_parsing_and_anonymization():
    assert parse_iw_channel_width("channel 36 (5180 MHz), width: 80 MHz") == 80
    changes = compare_scans([{"bssid": "old", "channel": 1, "signal_pct": 30}],
                            [{"bssid": "old", "channel": 6, "signal_pct": 30}, {"bssid": "new"}])
    assert changes == {"new": ["new"], "gone": [], "changed": ["old"]}
    assert anonymize_network({"ssid": "Private", "bssid": "aa:bb"})["ssid"] == "hidden"
    assert parse_iw_wifi_standard("rx bitrate: 1200 MBit/s HE-MCS 11") == "Wi-Fi 6/6E (802.11ax)"
    assert parse_iw_wifi_standard("tx bitrate: 2882 MBit/s EHT-MCS 13") == "Wi-Fi 7 (802.11be)"
    assert parse_iw_wifi_standard("tx bitrate: 866.7 MBit/s VHT-MCS 9") == "Wi-Fi 5 (802.11ac)"


def test_wifi_standard_ignores_network_name_and_non_bitrate_text():
    output = """Connected to 00:11:22:33:44:55 (on wlan0)
SSID: EHT-MCS HE VHT HT Guest
freq: 5180
signal: -45 dBm
rx bitrate: 866.7 MBit/s VHT-MCS 9 80MHz
tx bitrate: 780.0 MBit/s VHT-MCS 8 80MHz
"""

    assert parse_iw_wifi_standard(output) == "Wi-Fi 5 (802.11ac)"


def test_wifi_standard_requires_a_phy_marker_on_a_bitrate_line():
    output = """SSID: EHT-MCS Guest
freq: 5180
rx bitrate: 866.7 MBit/s
"""

    assert parse_iw_wifi_standard(output, 5180) == "802.11a/g/b (legacy)"


def test_anonymized_network_keeps_radio_measurements_only():
    assert anonymize_network({
        "ssid": "Office WiFi",
        "bssid": "00:11:22:33:44:55",
        "band": "5 GHz",
        "freq": 5180,
        "channel": 36,
        "width_mhz": 80,
        "signal_pct": 75,
        "dbm": -62,
        "security": "WPA2",
        "channel_status": "",
        "connected": True,
        "wifi_standard": "Wi-Fi 6 (802.11ax)",
        "width_source": "measured",
        "last_seen": 42,
        "future_identifier": "should-not-leak",
    }) == {
        "ssid": "hidden",
        "bssid": "hidden",
        "band": "5 GHz",
        "freq": 5180,
        "channel": 36,
        "width_mhz": 80,
        "signal_pct": 75,
        "dbm": -62,
        "security": "WPA2",
        "channel_status": "",
    }


def test_anonymized_export_requires_confirmation_before_file_chooser(monkeypatch):
    from wifi_analyzer import app as app_module

    captured = {}

    class FakeDialog:
        def __init__(self, title, _subtitle):
            captured["title"] = title

        def set_body(self, body):
            captured["body"] = body

        def add_response(self, response, label):
            captured.setdefault("responses", {})[response] = label

        def set_response_appearance(self, response, appearance):
            captured["appearance"] = (response, appearance)

        def connect(self, signal, callback):
            captured["callback"] = callback

        def present(self, parent):
            captured["parent"] = parent

    monkeypatch.setattr(app_module.Adw.AlertDialog, "new", FakeDialog)
    window = app_module.WifiAnalyzerWindow.__new__(app_module.WifiAnalyzerWindow)
    window._choose_export_path = lambda *args: captured.setdefault("chooser", args)

    window._export_anonymous_json()

    assert "SSIDs" in captured["body"]
    assert "BSSIDs" in captured["body"]
    assert "connection-specific details" in captured["body"]
    assert "identify a location" in captured["body"]
    assert captured["responses"]["cancel"] == "Cancel"
    assert captured["responses"]["export"] == "Continue to export"
    assert "chooser" not in captured

    captured["callback"](None, "cancel")
    assert "chooser" not in captured

    captured["callback"](None, "export")
    assert captured["chooser"][0] == "Export anonymized JSON"


def test_interference_diagnostics_and_connection_parsing(tmp_path, monkeypatch):
    target = {"ssid": "Target", "bssid": "a", "band": "5 GHz", "channel": 36, "width_mhz": 20}
    other = {"ssid": "Neighbour", "bssid": "b", "band": "5 GHz", "channel": 36, "width_mhz": 20, "signal_pct": 70}
    assert interference_contributors(target, [target, other])[0][0] == "Neighbour"
    assert parse_connection_diagnostics("default via 192.0.2.1 dev wlan0", "Link 2: 1.1.1.1 2001:db8::1",
                                        "wlan0 UP 192.0.2.10/24 2001:db8::2/64",
                                        "rx bitrate: 866.7 MBit/s") == {
        "gateway": "192.0.2.1", "dns_servers": ["1.1.1.1", "2001:db8::1"],
        "ip_addresses": ["192.0.2.10/24", "2001:db8::2/64"], "link_rates": ["866.7 MBit/s"]}
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    save_history_snapshot([{"ssid": "AP", "bssid": "a", "signal_pct": 42, "channel": 6}], now="now", profile="Home")
    assert load_signal_history("a", "Home") == [{"scanned_at": "now", "signal_pct": 42, "channel": 6}]


def test_wifi_problem_includes_a_remedy():
    code, title, remedy = wifi_problem([{"ssid": "Office", "connected": True, "signal_pct": 20}])
    assert code == "weak-signal"
    assert "weak" in title.lower()
    assert "closer" in remedy.lower()
    assert wifi_problem([{"ssid": "Office", "connected": True, "signal_pct": 70}]) is None


def test_empty_scan_does_not_claim_wifi_device_is_missing():
    assert wifi_problem([]) is None
    no_device = wifi_problem([{"error_code": "no-device"}])
    assert no_device and no_device[0] == "no-device"


def test_failed_scan_has_a_remedy_without_reporting_connection_lost():
    previous = [{"ssid": "Office", "connected": True, "bssid": "aa:bb"}]
    failed_scan = [{"error_code": "scan-failed", "error_message": "D-Bus unavailable"}]

    problem = wifi_problem(failed_scan, previous)
    assert problem and problem[0] == "scan-failed"
    assert "NetworkManager" in problem[2]
    assert problem[0] != "connection-lost"


def test_release_version_is_consistent():
    import re

    root = Path(__file__).parents[1]
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    init = (root / "src" / "wifi_analyzer" / "__init__.py").read_text(encoding="utf-8")
    app = (root / "src" / "wifi_analyzer" / "app.py").read_text(encoding="utf-8")
    project_version = re.search(r'(?m)^version = "([^"]+)"', project).group(1)
    package_version = re.search(r'__version__ = "([^"]+)"', init).group(1)
    assert project_version == package_version
    assert 'version=__version__,' in app


def test_flathub_manifest_has_a_valid_pinned_source():
    import json
    import re

    root = Path(__file__).parents[1]
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'(?m)^version = "([^\"]+)"', project).group(1)
    manifest = json.loads((root / "flatpak" / "io.github.yeager.wifi-analyzer.json").read_text(encoding="utf-8"))
    sources = manifest["modules"][0]["sources"]
    assert len(sources) in (1, 2)
    source = sources[0]

    assert source["tag"].startswith("v")
    assert tuple(map(int, source["tag"][1:].split("."))) <= tuple(map(int, project_version.split(".")))
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    assert source["url"] == "https://github.com/yeager/wifi-analyzer.git"
    app_id = manifest["app-id"]
    assert app_id == "io.github.yeager.wifi-analyzer"
    assert f'APP_ID = "{app_id}"' in (root / "src" / "wifi_analyzer" / "app.py").read_text(encoding="utf-8")
    assert f"<id>{app_id}</id>" in (root / "data" / f"{app_id}.metainfo.xml").read_text(encoding="utf-8")
