from wifi_analyzer.app import (
    band_for_frequency,
    channel_status,
    channel_width_mhz,
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
    assert recommend_channels([], "5 GHz")
    assert recommend_channels([], "6 GHz")


def test_history_is_bounded_and_can_be_cleared(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    save_history_snapshot([{"ssid": "Office", "bssid": "aa:bb", "band": "5 GHz", "channel": 36,
                            "signal_pct": 50, "dbm": -75, "security": "WPA3"}], now="2026-09-21T15:00:00")
    history = tmp_path / "wifi-analyzer" / "history.json"
    assert "Office" in history.read_text()
    assert history.stat().st_mode & 0o777 == 0o600
    clear_history()
    assert not history.exists()


def test_scan_comparison_width_parsing_and_anonymization():
    assert parse_iw_channel_width("channel 36 (5180 MHz), width: 80 MHz") == 80
    changes = compare_scans([{"bssid": "old", "channel": 1, "signal_pct": 30}],
                            [{"bssid": "old", "channel": 6, "signal_pct": 30}, {"bssid": "new"}])
    assert changes == {"new": ["new"], "gone": [], "changed": ["old"]}
    assert anonymize_network({"ssid": "Private", "bssid": "aa:bb"})["ssid"] == "hidden"
    assert parse_iw_wifi_standard("rx bitrate: 1200 MBit/s HE-MCS 11") == "Wi-Fi 6/6E (802.11ax)"
    assert parse_iw_wifi_standard("tx bitrate: 2882 MBit/s EHT-MCS 13") == "Wi-Fi 7 (802.11be)"
    assert parse_iw_wifi_standard("tx bitrate: 866.7 MBit/s VHT-MCS 9") == "Wi-Fi 5 (802.11ac)"


def test_interference_diagnostics_and_connection_parsing(tmp_path, monkeypatch):
    target = {"ssid": "Target", "bssid": "a", "band": "5 GHz", "channel": 36, "width_mhz": 20}
    other = {"ssid": "Neighbour", "bssid": "b", "band": "5 GHz", "channel": 36, "width_mhz": 20, "signal_pct": 70}
    assert interference_contributors(target, [target, other])[0][0] == "Neighbour"
    assert parse_connection_diagnostics("default via 192.0.2.1 dev wlan0", "Link 2: 1.1.1.1 2001:db8::1") == {
        "gateway": "192.0.2.1", "dns_servers": ["1.1.1.1", "2001:db8::1"]}
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    save_history_snapshot([{"ssid": "AP", "bssid": "a", "signal_pct": 42, "channel": 6}], now="now", profile="Home")
    assert load_signal_history("a", "Home") == [{"scanned_at": "now", "signal_pct": 42, "channel": 6}]


def test_wifi_problem_includes_a_remedy():
    code, title, remedy = wifi_problem([{"ssid": "Office", "connected": True, "signal_pct": 20}])
    assert code == "weak-signal"
    assert "weak" in title.lower()
    assert "closer" in remedy.lower()
    assert wifi_problem([{"ssid": "Office", "connected": True, "signal_pct": 70}]) is None
