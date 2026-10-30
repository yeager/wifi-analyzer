import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

from wifi_analyzer.app import (
    GLib,
    band_for_frequency,
    channel_status,
    channel_width_mhz,
    channel_recommendation_text,
    freq_to_channel,
    network_matches_query,
    parse_regulatory_ranges,
    recommend_channels,
    connected_security_advice,
    save_history_snapshot,
    clear_history,
    compare_scans,
    parse_iw_channel_width,
    parse_iw_wifi_standard,
    connected_radio_standard,
    connected_radio_width,
    select_wifi_device,
    _find_wifi_device,
    anonymize_network,
    interference_contributors,
    parse_connection_diagnostics,
    load_signal_history,
    signal_history_summary,
    set_signal_history_accessibility,
    format_signal_history_time,
    format_signal_history_measurements,
    wifi_problem,
    WifiAnalyzerWindow,
    _security_string,
    _read_last_scan,
    wait_for_scan_completion,
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


def test_security_labels_distinguish_owe_and_wpa3_enterprise():
    assert _security_string(0, 0, 0x0800) == "Enhanced Open (OWE)"
    assert _security_string(0, 0, 0x1000) == "Enhanced Open (OWE)"
    assert _security_string(0, 0, 0x0200) == "Enterprise (802.1X)"
    assert _security_string(0, 0, 0x2200) == "WPA2/WPA3 Enterprise"
    assert _security_string(0, 0, 0x0100) == "WPA2"
    assert _security_string(0, 0, 0x0400) == "WPA3"


def test_security_labels_show_advertised_transition_modes():
    assert _security_string(0, 0, 0x0500) == "WPA2/WPA3 Personal"
    assert _security_string(0, 0, 0x2000) == "WPA3 Enterprise"
    assert _security_string(0, 0, 0x2200) == "WPA2/WPA3 Enterprise"
    assert _security_string(0, 0x0100, 0x0100) == "WPA1/WPA2"


def test_frequency_helpers_cover_all_supported_bands():
    assert (freq_to_channel(2412), band_for_frequency(2412)) == (1, "2.4 GHz")
    assert (freq_to_channel(5180), band_for_frequency(5180)) == (36, "5 GHz")
    assert (freq_to_channel(5955), band_for_frequency(5955)) == (1, "6 GHz")
    assert channel_width_mhz(5180) == 20
    assert channel_width_mhz(0) == 0
    assert freq_to_channel(2484) == 14
    assert freq_to_channel(7125) == 0


def test_read_last_scan_unwraps_the_dbus_variant():
    proxy = Mock()
    proxy.call_sync.return_value.unpack.return_value = (GLib.Variant("x", 1234),)

    assert _read_last_scan(proxy) == 1234
    proxy.call_sync.assert_called_once()


def test_wait_for_scan_completion_waits_until_networkmanager_finishes(monkeypatch):
    from wifi_analyzer import app as app_module

    readings = iter([100, 100, 101])
    clock = iter([0.0, 0.0, 0.25])
    monkeypatch.setattr(app_module, "_read_last_scan", lambda _proxy: next(readings))
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(clock))
    sleep = Mock()
    monkeypatch.setattr(app_module.time, "sleep", sleep)

    assert wait_for_scan_completion(Mock(), 100, timeout=5)
    assert sleep.call_count == 2
    assert all(call.args == (0.25,) for call in sleep.call_args_list)


def test_wait_for_scan_completion_times_out_when_lastscan_does_not_change(monkeypatch):
    from wifi_analyzer import app as app_module

    clock = iter([0.0, 2.0])
    monkeypatch.setattr(app_module, "_read_last_scan", lambda _proxy: 100)
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(clock))
    sleep = Mock()
    monkeypatch.setattr(app_module.time, "sleep", sleep)

    assert not wait_for_scan_completion(Mock(), 100, timeout=2)
    sleep.assert_not_called()


def test_network_scan_waits_for_networkmanager_before_reading_access_points(monkeypatch):
    from wifi_analyzer import app as app_module

    events = []
    manager_proxy = Mock()
    wireless_proxy = Mock()
    wireless_proxy.call_sync.side_effect = [
        Mock(),
        Mock(unpack=Mock(side_effect=lambda: (events.append("read-access-points") or [],))),
    ]
    proxies = iter([manager_proxy, wireless_proxy])
    monkeypatch.setattr(app_module.Gio.DBusProxy, "new_for_bus_sync", lambda *_args: next(proxies))
    monkeypatch.setattr(app_module, "_find_wifi_device", lambda _proxy: ("/wifi/0", "wlan0", "/"))
    monkeypatch.setattr(app_module, "connected_radio_width", lambda _interface: 0)
    monkeypatch.setattr(app_module, "connected_radio_standard", lambda _interface: "")
    monkeypatch.setattr(app_module, "_read_last_scan", lambda _proxy: 10)

    def wait(_proxy, previous_scan):
        events.append(("wait", previous_scan))
        return True

    monkeypatch.setattr(app_module, "wait_for_scan_completion", wait)

    assert app_module.scan_networks_dbus(regulatory_ranges=[]) == []
    assert events == [("wait", 10), "read-access-points"]
    assert [call.args[0] for call in wireless_proxy.call_sync.call_args_list] == [
        "RequestScan", "GetAllAccessPoints",
    ]


def test_dfs_channels_are_identified_without_claiming_a_ban():
    assert "DFS" in channel_status(5260, 52)
    assert channel_status(5180, 36) == ""


def test_regulatory_ranges_mark_dfs_and_unavailable_channels():
    ranges = parse_regulatory_ranges("\t(5250 - 5350 @ 80), (N/A, 26), (0 ms), DFS\n")
    assert "radar" in channel_status(5260, 52, ranges)
    assert "Unavailable" in channel_status(5180, 36, ranges)


def test_regulatory_parser_preserves_transmit_restriction_flags():
    ranges = parse_regulatory_ranges(
        "\t(5180 - 5200 @ 80), (N/A, 20), (N/A), NO-IR\n"
    )

    assert len(ranges) == 1
    assert "NO-IR" in ranges[0][2]


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


def test_channel_recommendation_accounts_for_both_channel_widths():
    network_20 = [{"band": "2.4 GHz", "channel": 6, "signal_pct": 90, "width_mhz": 20}]
    network_40 = [{"band": "2.4 GHz", "channel": 6, "signal_pct": 90, "width_mhz": 40}]

    scores_20 = dict(recommend_channels(network_20, "2.4 GHz"))
    scores_40 = dict(recommend_channels(network_40, "2.4 GHz"))

    assert scores_20[1] == 0
    assert scores_40[1] > 0
    assert scores_40[1] == scores_40[11]


def test_channel_recommendation_explains_the_limits_of_the_scan_score():
    summary, explanation = channel_recommendation_text([(6, 0.0)])

    assert summary == "Lowest estimated overlap in this scan: channel 6 (score 0.0)"
    assert "Lower scores mean less estimated overlap" in explanation
    assert "Only access points found in this scan count" in explanation
    assert "client traffic and hidden networks are not measured" in explanation


def test_connected_security_advice_covers_open_owe_and_legacy_modes_cautiously():
    assert "reports no Wi-Fi security" in connected_security_advice([{
        "connected": True, "security": "",
    }])
    assert "does not authenticate the access point" in connected_security_advice([{
        "connected": True, "security": "Enhanced Open (OWE)",
    }])
    legacy = connected_security_advice([{"connected": True, "security": "WPA1/WPA2"}])
    assert "use WPA2 with AES or WPA3" in legacy
    assert "cannot tell which cipher" in legacy


def test_connected_security_advice_does_not_warn_about_other_or_modern_networks():
    assert connected_security_advice([{"connected": False, "security": "WEP"}]) == ""
    assert connected_security_advice([{"connected": True, "security": "WPA3"}]) == ""


def test_missing_channel_recommendation_suggests_a_scan():
    summary, explanation = channel_recommendation_text([])

    assert summary == "No channel recommendation available"
    assert explanation == "Scan this band to compare nearby access points."


def test_channel_recommendation_explains_when_regulations_leave_no_candidate():
    summary, explanation = channel_recommendation_text(
        [], "no-eligible-channels",
    )

    assert summary == "No channel recommendation available"
    assert "detected regulatory information" in explanation
    assert "no candidate channel that can initiate transmission" in explanation
    assert "router’s country and channel settings" in explanation


def test_failed_channel_scan_does_not_ask_user_to_scan_again():
    summary, explanation = channel_recommendation_text([], "scan-failed")

    assert summary == "No channel recommendation available"
    assert "scan did not complete" in explanation
    assert "could not be compared" in explanation


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


def test_24ghz_recommendations_use_all_channels_allowed_by_known_domain():
    network = {"band": "2.4 GHz", "channel": 6, "signal_pct": 90, "width_mhz": 20}
    ranges = [(2412, 2472, "")]

    recommendations = recommend_channels([network], "2.4 GHz", ranges)

    assert {channel for channel, _score in recommendations} == set(range(1, 14))
    assert recommendations[0][0] in {1, 11, 13}


def test_24ghz_recommendations_exclude_channels_restricted_from_beaconing():
    network = {"band": "2.4 GHz", "channel": 6, "signal_pct": 90, "width_mhz": 20}
    ranges = [(2412, 2467, ""), (2472, 2472, "NO-IR")]

    recommendations = recommend_channels([network], "2.4 GHz", ranges)

    assert 13 not in {channel for channel, _score in recommendations}


def test_channel_recommendations_skip_channels_that_cannot_initiate_transmission():
    network = {"band": "5 GHz", "channel": 36, "signal_pct": 70, "width_mhz": 20}
    ranges = [
        (5180, 5200, "NO-IR, DFS"),
        (5220, 5240, ""),
    ]

    recommendations = recommend_channels([network], "5 GHz", ranges)

    assert recommendations
    assert all(channel not in {36, 40} for channel, _score in recommendations)


def test_main_view_channel_recommendations_use_latest_scan_regulatory_ranges(monkeypatch):
    from wifi_analyzer import app as app_module

    networks = [{
        "ssid": "Example", "bssid": "aa:bb", "band": "5 GHz", "channel": 36,
        "dbm": -50, "signal_pct": 100, "security": "WPA3",
    }]
    ranges = [(5180, 5200, "")]
    recommend = Mock(return_value=[(36, 0.0)])
    monkeypatch.setattr(app_module, "recommend_channels", recommend)

    window = app_module.WifiAnalyzerWindow.__new__(app_module.WifiAnalyzerWindow)
    window.networks = networks
    window.regulatory_ranges = ranges
    window.selected_channel = None
    window._get_band = lambda: "5 GHz"
    window.listbox = Mock()
    window.listbox.get_first_child.return_value = None
    window.security_filter = Mock()
    window.security_filter.get_selected_item.return_value.get_string.return_value = "All security"
    window.signal_threshold = Mock()
    window.signal_threshold.get_value_as_int.return_value = -100
    window.hidden_filter = Mock()
    window.hidden_filter.get_active.return_value = False
    window.search_entry = Mock()
    window.search_entry.get_text.return_value = ""
    window.sort_filter = Mock()
    window.sort_filter.get_selected_item.return_value.get_string.return_value = "Signal"
    window.channel_chart = Mock()
    window.recommendation = Mock()
    window.recommendation_detail = Mock()
    window.security_advice = Mock()

    window._update_ui()

    recommend.assert_called_once_with(networks, "5 GHz", ranges)

    recommend.return_value = []
    window.regulatory_ranges = [(5180, 5200, "NO-IR")]
    window._update_ui()

    assert "detected regulatory information" in window.recommendation_detail.set_label.call_args.args[0]


def test_main_view_adds_connected_network_security_advice(monkeypatch):
    from wifi_analyzer import app as app_module

    networks = [{
        "ssid": "Office", "bssid": "aa:bb", "band": "5 GHz", "channel": 36,
        "dbm": -50, "signal_pct": 100, "security": "WEP", "connected": True,
    }]
    monkeypatch.setattr(app_module, "recommend_channels", lambda *_args: [(36, 0.0)])
    window = app_module.WifiAnalyzerWindow.__new__(app_module.WifiAnalyzerWindow)
    window.networks = networks
    window.regulatory_ranges = []
    window.selected_channel = None
    window._get_band = lambda: "5 GHz"
    window.listbox = Mock()
    window.listbox.get_first_child.return_value = None
    window.security_filter = Mock()
    window.security_filter.get_selected_item.return_value.get_string.return_value = "All security"
    window.signal_threshold = Mock()
    window.signal_threshold.get_value_as_int.return_value = -100
    window.hidden_filter = Mock()
    window.hidden_filter.get_active.return_value = False
    window.search_entry = Mock()
    window.search_entry.get_text.return_value = ""
    window.sort_filter = Mock()
    window.sort_filter.get_selected_item.return_value.get_string.return_value = "Signal"
    window.channel_chart = Mock()
    window.recommendation = Mock()
    window.recommendation_detail = Mock()
    window.security_advice = Mock()

    window._update_ui()

    advice = window.security_advice.set_label.call_args.args[0]
    assert "Security advice:" in advice
    assert "disable WEP/WPA1" in advice
    window.security_advice.set_visible.assert_called_once_with(True)


def test_history_is_bounded_and_can_be_cleared(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert save_history_snapshot([{"ssid": "Office", "bssid": "aa:bb", "band": "5 GHz", "channel": 36,
                                  "signal_pct": 50, "dbm": -75, "security": "WPA3"}], now="2026-09-21T15:00:00")
    history = tmp_path / "wifi-analyzer" / "history.json"
    assert "Office" in history.read_text()
    assert history.stat().st_mode & 0o777 == 0o600
    clear_history()
    assert not history.exists()


def test_history_storage_errors_are_reported_without_raising(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        "wifi_analyzer.app.tempfile.mkstemp",
        Mock(side_effect=OSError("read-only filesystem")),
    )

    assert not save_history_snapshot([
        {"ssid": "Office", "bssid": "aa:bb", "signal_pct": 50, "channel": 36},
    ])


def test_clearing_history_reports_storage_errors(monkeypatch):
    monkeypatch.setattr("wifi_analyzer.app._history_path", lambda: "/unused/history.json")
    monkeypatch.setattr(
        "wifi_analyzer.app.os.unlink",
        Mock(side_effect=PermissionError("read-only filesystem")),
    )

    assert not clear_history()


def test_scan_results_remain_visible_when_local_history_cannot_be_saved(monkeypatch):
    from wifi_analyzer import app as app_module

    window = WifiAnalyzerWindow.__new__(WifiAnalyzerWindow)
    window.networks = []
    window.regulatory_ranges = []
    window._last_problem_code = None
    window.profile_entry = Mock()
    window.profile_entry.get_text.return_value = "Home"
    window._update_ui = Mock()
    window._set_status = Mock()
    networks = [{
        "ssid": "Office", "bssid": "aa:bb", "band": "5 GHz", "channel": 36,
        "signal_pct": 70, "dbm": -60, "security": "WPA2",
    }]
    monkeypatch.setattr(app_module, "save_history_snapshot", lambda *_args, **_kwargs: False)

    window._on_scan_done(networks)

    window._update_ui.assert_called_once_with()
    window._set_status.assert_called_once()
    assert window.networks[0]["ssid"] == "Office"
    assert "Local scan history could not be saved" in window._set_status.call_args.args[0]


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


def test_history_recovers_from_invalid_utf8(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    history = tmp_path / "wifi-analyzer" / "history.json"
    history.parent.mkdir(parents=True)
    history.write_bytes(b"\xff\xfe")

    save_history_snapshot(
        [{"ssid": "Office", "bssid": "aa:bb", "signal_pct": 75, "channel": 36}],
        now="2026-10-29T12:00:00",
        profile="Office",
    )

    assert load_signal_history("aa:bb", "Office") == [
        {"scanned_at": "2026-10-29T12:00:00", "signal_pct": 75, "channel": 36},
    ]


def test_history_profile_names_are_trimmed_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    profile = "  " + "Office" * 30 + "  "

    save_history_snapshot(
        [{"ssid": "Office", "bssid": "aa:bb", "signal_pct": 75, "channel": 36}],
        now="2026-10-30T12:00:00",
        profile=profile,
    )

    history = json.loads((tmp_path / "wifi-analyzer" / "history.json").read_text(encoding="utf-8"))
    assert history[0]["profile"] == ("Office" * 30)[:64]


def test_empty_or_non_text_history_profile_uses_default(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    save_history_snapshot([], now="first", profile="  ")
    save_history_snapshot([], now="second", profile=None)

    history = json.loads((tmp_path / "wifi-analyzer" / "history.json").read_text(encoding="utf-8"))
    assert [record["profile"] for record in history] == ["Default", "Default"]


def test_signal_history_accessibility_summary_covers_valid_values_and_ignores_bad_data():
    points = [
        {"signal_pct": 42},
        {"signal_pct": 81.5},
        {"signal_pct": True},
        {"signal_pct": float("nan")},
        {"signal_pct": 101},
        {"signal_pct": "90"},
        None,
    ]

    assert signal_history_summary(points) == (
        "Signal history: 2 measurements, range 42% to 82%, latest 82%."
    )
    assert signal_history_summary([]) == "No local signal history yet"


def test_signal_history_chart_exposes_accessible_name_and_summary():
    from gi.repository import Gtk

    widget = Mock()
    points = [{"signal_pct": 60}, {"signal_pct": 75}]

    set_signal_history_accessibility(widget, points)

    widget.set_accessible_role.assert_called_once_with(Gtk.AccessibleRole.IMG)
    properties, values = widget.update_property.call_args.args
    assert properties == [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION]
    assert values == [
        "Signal history",
        "Signal history: 2 measurements, range 60% to 75%, latest 75%.",
    ]


def test_signal_history_time_formats_iso_values_and_keeps_bad_legacy_values_safe():
    assert format_signal_history_time("not-a-time") == "not-a-time"
    assert format_signal_history_time(None) == "None"


def test_signal_history_measurements_are_formatted_newest_first():
    assert format_signal_history_measurements([
        {"scanned_at": "old", "signal_pct": 40},
        {"scanned_at": "new", "signal_pct": 75},
    ]) == ["new: 75%", "old: 40%"]


def test_scan_comparison_width_parsing_and_anonymization():
    assert parse_iw_channel_width("channel 36 (5180 MHz), width: 80 MHz") == 80
    changes = compare_scans([{"bssid": "old", "channel": 1, "signal_pct": 30}],
                            [{"bssid": "old", "channel": 6, "signal_pct": 30}, {"bssid": "new"}])
    assert changes == {"new": ["new"], "gone": [], "changed": ["old"]}
    assert anonymize_network({"ssid": "Private", "bssid": "aa:bb"})["ssid"] == "hidden"
    assert parse_iw_wifi_standard("rx bitrate: 1200 MBit/s HE-MCS 11") == "Wi-Fi 6/6E (802.11ax)"
    assert parse_iw_wifi_standard("tx bitrate: 2882 MBit/s EHT-MCS 13") == "Wi-Fi 7 (802.11be)"
    assert parse_iw_wifi_standard("tx bitrate: 866.7 MBit/s VHT-MCS 9") == "Wi-Fi 5 (802.11ac)"


def test_wifi_device_selection_prefers_the_connected_adapter():
    devices = [
        ("/org/freedesktop/NetworkManager/Devices/1", "wlan0", "/"),
        ("/org/freedesktop/NetworkManager/Devices/2", "wlan1", "/org/freedesktop/NetworkManager/AccessPoint/4"),
    ]

    assert select_wifi_device(devices) == devices[1]
    assert select_wifi_device(devices[:1]) == devices[0]
    assert select_wifi_device([]) is None


def test_network_manager_lookup_returns_the_connected_adapter(monkeypatch):
    from wifi_analyzer import app as app_module

    class FakeVariant:
        def __init__(self, value):
            self.value = value

        def unpack(self):
            return (self.value,)

    class FakeProperties:
        def __init__(self, path):
            self.path = path

        def call_sync(self, _method, parameters, *_args):
            interface, name = parameters.unpack()
            if name == "DeviceType":
                return FakeVariant(app_module.NM_DEVICE_TYPE_WIFI)
            if name == "Interface":
                return FakeVariant("wlan0" if self.path.endswith("/1") else "wlan1")
            if interface == app_module.NM_WIRELESS_IFACE and name == "ActiveAccessPoint":
                return FakeVariant("/" if self.path.endswith("/1") else "/ap/2")
            raise AssertionError((interface, name))

    network_manager = Mock()
    network_manager.call_sync.return_value.unpack.return_value = (
        (
            "/org/freedesktop/NetworkManager/Devices/1",
            "/org/freedesktop/NetworkManager/Devices/2",
        ),
    )
    fake_gio = Mock()
    fake_gio.DBusProxy.new_for_bus_sync.side_effect = (
        lambda _bus, _flags, _info, _name, path, _interface, _cancellable: FakeProperties(path)
    )
    monkeypatch.setattr(app_module, "Gio", fake_gio)

    assert _find_wifi_device(network_manager) == (
        "/org/freedesktop/NetworkManager/Devices/2", "wlan1", "/ap/2",
    )


def test_connected_radio_width_and_standard_use_the_selected_interface(monkeypatch):
    from wifi_analyzer import app as app_module

    calls = []
    outputs = {
        ("iw", "dev", "wlan1", "info"): "Interface wlan1\n\tchannel 36 (5180 MHz), width: 160 MHz\n",
        ("iw", "dev", "wlan1", "link"): "Connected to 00:11:22:33:44:55 (on wlan1)\nrx bitrate: 2882 MBit/s EHT-MCS 13\n",
    }

    def run(command, **_kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command)], "")

    monkeypatch.setattr(app_module.subprocess, "run", run)

    assert connected_radio_width("wlan1") == 160
    assert connected_radio_standard("wlan1") == "Wi-Fi 7 (802.11be)"
    assert calls == [
        ("iw", "dev", "wlan1", "info"),
        ("iw", "dev", "wlan1", "link"),
    ]


def test_connected_radio_standard_skips_unconnected_interfaces(monkeypatch):
    from wifi_analyzer import app as app_module

    outputs = iter([
        "phy#0\n\tInterface wlan0\nphy#1\n\tInterface wlan1\n",
        "Not connected.\n",
        "Connected to 00:11:22:33:44:55 (on wlan1)\ntx bitrate: 1200 MBit/s HE-MCS 11\n",
    ])
    monkeypatch.setattr(
        app_module.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, next(outputs), ""),
    )

    assert connected_radio_standard() == "Wi-Fi 6/6E (802.11ax)"


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


def test_html_diagnostic_export_warns_about_network_names_and_macs(monkeypatch):
    from wifi_analyzer import app as app_module

    captured = {}

    class FakeDialog:
        def __init__(self, title, _subtitle):
            captured["title"] = title

        def set_body(self, body):
            captured["body"] = body

        def add_response(self, response, label):
            captured.setdefault("responses", {})[response] = label

        def set_default_response(self, response):
            captured["default"] = response

        def set_response_appearance(self, response, appearance):
            captured["appearance"] = (response, appearance)

        def connect(self, signal, callback):
            captured["callback"] = callback

        def present(self, parent):
            captured["parent"] = parent

    monkeypatch.setattr(app_module.Adw.AlertDialog, "new", FakeDialog)
    window = app_module.WifiAnalyzerWindow.__new__(app_module.WifiAnalyzerWindow)
    window._choose_export_path = lambda *args: captured.setdefault("chooser", args)

    window._export_report()

    assert captured["title"] == "Export network details?"
    assert "SSIDs" in captured["body"]
    assert "BSSIDs" in captured["body"]
    assert "location" in captured["body"]
    assert captured["responses"]["cancel"] == "Cancel"
    assert captured["responses"]["export"] == "Continue to export"
    assert captured["default"] == "cancel"
    assert "chooser" not in captured

    captured["callback"](None, "cancel")
    assert "chooser" not in captured

    captured["callback"](None, "export")
    assert captured["chooser"][0] == "Export diagnostic report"


def test_all_identifiable_exports_require_confirmation(monkeypatch):
    from wifi_analyzer import app as app_module

    captured = []
    window = app_module.WifiAnalyzerWindow.__new__(app_module.WifiAnalyzerWindow)
    window._confirm_identifiable_export = lambda *args: captured.append(args)

    window._export_csv()
    window._export_json()
    window._export_report()

    assert [(title, filename) for title, filename, _write in captured] == [
        ("Export CSV", "wifi-analyzer.csv"),
        ("Export JSON", "wifi-analyzer.json"),
        ("Export diagnostic report", "wifi-analyzer-report.html"),
    ]


def test_diagnostic_export_reuses_regulatory_ranges_from_the_latest_scan(monkeypatch):
    from wifi_analyzer import app as app_module

    captured = {}
    network = {
        "ssid": "Example", "bssid": "00:11:22:33:44:55", "band": "5 GHz",
        "channel": 36, "signal_pct": 70, "width_mhz": 20,
    }
    hidden_by_band_filter = {
        "ssid": "Other band", "bssid": "00:11:22:33:44:66", "band": "2.4 GHz",
        "channel": 6, "signal_pct": 70, "width_mhz": 20,
    }
    window = WifiAnalyzerWindow.__new__(WifiAnalyzerWindow)
    window.networks = [network, hidden_by_band_filter]
    window.visible_networks = [network]
    window.regulatory_ranges = [(2412, 2412, ""), (5180, 5180, "")]
    window._confirm_identifiable_export = (
        lambda _title, _filename, write: write("report.html")
    )
    window._set_status = Mock()

    def export_report(networks, recommendations, path):
        captured.update(networks=networks, recommendations=recommendations, path=path)

    monkeypatch.setattr(
        app_module, "local_regulatory_ranges",
        Mock(side_effect=AssertionError("must use scan cache")),
    )
    monkeypatch.setattr(app_module, "export_html_report", export_report)

    window._export_report()

    assert captured["path"] == "report.html"
    assert captured["networks"] == [network]
    assert captured["recommendations"]["5 GHz"][0] == 36
    assert captured["recommendations"]["2.4 GHz"] == (None, None)


def test_interference_diagnostics_and_connection_parsing(tmp_path, monkeypatch):
    target = {"ssid": "Target", "bssid": "a", "band": "5 GHz", "channel": 36, "width_mhz": 20}
    other = {"ssid": "Neighbour", "bssid": "b", "band": "5 GHz", "channel": 36, "width_mhz": 20, "signal_pct": 70}
    assert interference_contributors(target, [target, other])[0][0] == "Neighbour"
    wide_target = {**target, "width_mhz": 40}
    near_other = {**other, "channel": 41}
    assert interference_contributors(wide_target, [wide_target, near_other])
    assert parse_connection_diagnostics("default via 192.0.2.1 dev wlan0", "Link 2: 1.1.1.1 2001:db8::1",
                                        "wlan0 UP 192.0.2.10/24 2001:db8::2/64",
                                        "rx bitrate: 866.7 MBit/s") == {
        "gateway": "192.0.2.1", "dns_servers": ["1.1.1.1", "2001:db8::1"],
        "ip_addresses": ["192.0.2.10/24", "2001:db8::2/64"], "link_rates": ["866.7 MBit/s"]}
    assert parse_connection_diagnostics(
        "default dev ppp0\ndefault via fe80::1 dev wlan0 proto ra", "",
    )["gateway"] == "fe80::1"
    assert parse_connection_diagnostics("default via not-an-ip dev wlan0", "")["gateway"] == ""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    save_history_snapshot([{"ssid": "AP", "bssid": "a", "signal_pct": 42, "channel": 6}], now="now", profile="Home")
    assert load_signal_history("a", "Home") == [{"scanned_at": "now", "signal_pct": 42, "channel": 6}]


def test_connection_diagnostics_uses_networkmanager_active_wifi_interface(monkeypatch):
    from wifi_analyzer import app as app_module

    calls = []
    outputs = {
        ("ip", "route"): "default via 192.0.2.1 dev wlan1",
        ("ip", "-6", "route"): "default via fe80::1 dev wlan1 proto ra",
        ("resolvectl", "dns"): "Link 2 (wlan1): 1.1.1.1",
        ("ip", "-brief", "address"): "wlan1 UP 192.0.2.10/24",
        ("iw", "dev", "wlan1", "link"): "Connected to aa:bb:cc:dd:ee:ff (on wlan1)\nrx bitrate: 866.7 MBit/s",
    }

    def run(command, **_kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command)], "")

    fake_gio = Mock()
    monkeypatch.setattr(app_module, "Gio", fake_gio)
    monkeypatch.setattr(app_module, "_find_wifi_device", Mock(return_value=("/device/2", "wlan1", "/ap/2")))
    monkeypatch.setattr(app_module.subprocess, "run", run)

    diagnostics = app_module.connection_diagnostics()

    assert diagnostics["link_rates"] == ["866.7 MBit/s"]
    assert diagnostics["gateway"] == "192.0.2.1"
    assert ("ip", "-6", "route") in calls
    assert ("iw", "dev", "wlan1", "link") in calls
    assert ("iw", "dev") not in calls


def test_wifi_problem_includes_a_remedy():
    code, title, remedy = wifi_problem([{"ssid": "Office", "connected": True, "signal_pct": 20}])
    assert code == "weak-signal"
    assert "weak" in title.lower()
    assert "closer" in remedy.lower()
    assert wifi_problem([{"ssid": "Office", "connected": True, "signal_pct": 70}]) is None


def test_empty_successful_scan_gives_specific_access_point_troubleshooting():
    problem = wifi_problem([])

    assert problem and problem[0] == "no-access-points"
    assert problem[1] == "No access points found"
    assert "Wi-Fi is enabled" in problem[2]
    assert "airplane mode is off" in problem[2]
    assert "move closer" in problem[2]
    assert "Hidden networks may not appear" in problem[2]


def test_empty_scan_shows_remedy_in_status_and_notification(monkeypatch):
    from wifi_analyzer import app as app_module

    fake_gio = Mock()
    monkeypatch.setattr(app_module, "Gio", fake_gio)
    window = WifiAnalyzerWindow.__new__(WifiAnalyzerWindow)
    window.networks = []
    window.regulatory_ranges = []
    window._last_problem_code = None
    window.profile_entry = Mock()
    window.profile_entry.get_text.return_value = "Home"
    window._update_ui = Mock()
    window._set_status = Mock()
    application = Mock()
    window.get_application = Mock(return_value=application)

    window._on_scan_done([])

    status = window._set_status.call_args.args[0]
    assert "Found 0 networks" in status
    assert "airplane mode is off" in status
    application.send_notification.assert_called_once_with("wifi-problem", fake_gio.Notification.new.return_value)
    fake_gio.Notification.new.assert_called_once_with("No access points found")
    fake_gio.Notification.new.return_value.set_body.assert_called_once_with(
        "No nearby access points were found in this scan. Check that Wi-Fi is enabled, "
        "airplane mode is off, and move closer to the router before scanning again. "
        "Hidden networks may not appear."
    )


def test_empty_scan_does_not_claim_wifi_device_is_missing():
    assert wifi_problem([])[0] == "no-access-points"
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
