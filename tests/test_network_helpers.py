from wifi_analyzer.app import (
    band_for_frequency,
    channel_status,
    channel_width_mhz,
    freq_to_channel,
    network_matches_query,
    parse_regulatory_ranges,
)


def test_frequency_helpers_cover_all_supported_bands():
    assert (freq_to_channel(2412), band_for_frequency(2412)) == (1, "2.4 GHz")
    assert (freq_to_channel(5180), band_for_frequency(5180)) == (36, "5 GHz")
    assert (freq_to_channel(5955), band_for_frequency(5955)) == (1, "6 GHz")
    assert channel_width_mhz(5180) == 20
    assert channel_width_mhz(0) == 0


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
