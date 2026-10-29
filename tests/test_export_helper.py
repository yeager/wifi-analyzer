import csv

from wifi_analyzer.export_helper import export_csv


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
