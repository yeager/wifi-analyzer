import csv
import stat

from wifi_analyzer.export_helper import export_csv, export_html_report, export_json


def test_exports_are_owner_only_and_tighten_existing_file_permissions(tmp_path):
    csv_path = tmp_path / "networks.csv"
    json_path = tmp_path / "networks.json"
    html_path = tmp_path / "report.html"

    export_csv([["Home Wi-Fi", "00:11:22:33:44:55"]], ["SSID", "BSSID"], csv_path)
    export_json([["Home Wi-Fi", "00:11:22:33:44:55"]], ["SSID", "BSSID"], json_path)
    export_html_report(
        [{"ssid": "Home Wi-Fi", "bssid": "00:11:22:33:44:55"}], {}, html_path,
    )

    existing_path = tmp_path / "existing.csv"
    existing_path.write_text("old contents\n", encoding="utf-8")
    existing_path.chmod(0o644)
    export_csv([["Private network"]], ["SSID"], existing_path)

    for path in (csv_path, json_path, html_path, existing_path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_csv_export_treats_formula_like_text_as_plain_text(tmp_path):
    path = tmp_path / "networks.csv"
    values = [
        "=1+1",
        "+1+1",
        "-1+1",
        "@SUM(A1:A2)",
        "  =HYPERLINK(\"https://example.invalid\")",
        "\t=1+1",
        "\v=1+1",
        "\f=1+1",
        "\u00a0=1+1",
        "\ufeff=1+1",
        " \ufeff\u00a0=1+1",
        -67,
    ]

    headers = ["=header", *(["SSID"] * 10), "dBm"]
    export_csv([values], headers, path)

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[0][0] == "'=header"
    assert rows[0][-1] == "dBm"
    assert rows[1] == [
        "'=1+1",
        "'+1+1",
        "'-1+1",
        "'@SUM(A1:A2)",
        "'  =HYPERLINK(\"https://example.invalid\")",
        "'\t=1+1",
        "'\v=1+1",
        "'\f=1+1",
        "'\u00a0=1+1",
        "'\ufeff=1+1",
        "' \ufeff\u00a0=1+1",
        "-67",
    ]


def test_csv_export_preserves_safe_text_and_numbers(tmp_path):
    path = tmp_path / "networks.csv"
    export_csv([["Guest network", "WPA2", 36, -67, ""]], [], path)

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows == [["Guest network", "WPA2", "36", "-67", ""]]


def test_html_report_escapes_network_fields_and_recommendation_values(tmp_path):
    report_path = tmp_path / "report.html"
    networks = [{
        "ssid": '<img src=x onerror="alert(1)">',
        "bssid": "<script>alert(2)</script>",
        "band": "5 GHz",
        "channel": 36,
        "signal_pct": 80,
        "security": "WPA2",
        "channel_status": "preferred",
    }]
    recommendations = {
        "<script>alert(3)</script>": ("<img src=x>", "<svg onload=alert(4)>")
    }

    export_html_report(networks, recommendations, report_path)

    html = report_path.read_text(encoding="utf-8")
    assert "<img src=x onerror=\"alert(1)\">" not in html
    assert "<script>alert(2)</script>" not in html
    assert "<script>alert(3)</script>" not in html
    assert "<img src=x>" not in html
    assert "<svg onload=alert(4)>" not in html
    assert "&lt;script&gt;alert(3)&lt;/script&gt;" in html
    assert "&lt;img src=x&gt;" in html
    assert "&lt;svg onload=alert(4)&gt;" in html
