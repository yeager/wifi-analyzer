"""Safe local export helpers for CSV, JSON, and HTML reports."""
from contextlib import contextmanager
import csv
import json
import os
import time
import unicodedata
from html import escape


@contextmanager
def _private_text_file(filepath, newline=None):
    """Open an export as owner-only, tightening permissions before truncation."""
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(filepath, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.ftruncate(descriptor, 0)
        handle = os.fdopen(descriptor, "w", encoding="utf-8", newline=newline)
        descriptor = None
        with handle:
            yield handle
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _safe_csv_cell(value):
    """Keep untrusted text from becoming a spreadsheet formula."""
    if not isinstance(value, str):
        return value
    trimmed = value.lstrip()
    while trimmed.startswith("\ufeff"):
        trimmed = trimmed[1:].lstrip()
    if value and (
        unicodedata.category(value[0]) == "Cc"
        or (trimmed and trimmed[0] in "=+-@")
    ):
        return "'" + value
    return value


def export_csv(data, headers, filepath):
    """Export private CSV, escaping formula-like untrusted text cells."""
    with _private_text_file(filepath, newline="") as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(_safe_csv_cell(value) for value in headers)
        writer.writerows((_safe_csv_cell(value) for value in row) for row in data)
    return filepath


def export_json(data, headers, filepath):
    """Export JSON with owner-only file permissions."""
    if headers:
        records = [dict(zip(headers, row)) for row in data]
    else:
        records = data
    with _private_text_file(filepath) as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return filepath


def export_html_report(networks, recommendations, filepath):
    """Write a self-contained, owner-only local diagnostic report."""
    rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(net.get(field, '')))}</td>" for field in
                            ("ssid", "bssid", "band", "channel", "signal_pct", "security", "channel_status")) + "</tr>"
        for net in networks
    )
    advice = "<br>".join(
        f"{escape(str(band))}: channel {escape(str(channel))} (score {escape(str(score))})"
        for band, (channel, score) in recommendations.items()
        if channel is not None
    )
    document = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>WiFi Analyzer report</title>
<style>body{{font-family:sans-serif;margin:2rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4rem;text-align:left}}</style>
</head><body><h1>WiFi Analyzer report</h1><p>Generated {escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>
<h2>Channel recommendations</h2><p>{advice or 'No recommendation available'}</p>
<table><thead><tr><th>SSID</th><th>BSSID</th><th>Band</th><th>Channel</th><th>Signal %</th><th>Security</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    with _private_text_file(filepath) as handle:
        handle.write(document)
    return filepath
