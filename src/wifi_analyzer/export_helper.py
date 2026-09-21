"""Safe local export helpers for CSV, JSON, and HTML reports."""
import csv
import json
import time
from html import escape


def export_csv(data, headers, filepath):
    """Export data as CSV."""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(headers)
        writer.writerows(data)
    return filepath


def export_json(data, headers, filepath):
    """Export data as JSON."""
    if headers:
        records = [dict(zip(headers, row)) for row in data]
    else:
        records = data
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return filepath


def export_html_report(networks, recommendations, filepath):
    """Write a self-contained, local diagnostic report."""
    rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(net.get(field, '')))}</td>" for field in
                            ("ssid", "bssid", "band", "channel", "signal_pct", "security", "channel_status")) + "</tr>"
        for net in networks
    )
    advice = "<br>".join(f"{escape(band)}: channel {channel} (score {score})"
                         for band, (channel, score) in recommendations.items() if channel is not None)
    document = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>WiFi Analyzer report</title>
<style>body{{font-family:sans-serif;margin:2rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4rem;text-align:left}}</style>
</head><body><h1>WiFi Analyzer report</h1><p>Generated {escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>
<h2>Channel recommendations</h2><p>{advice or 'No recommendation available'}</p>
<table><thead><tr><th>SSID</th><th>BSSID</th><th>Band</th><th>Channel</th><th>Signal %</th><th>Security</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write(document)
    return filepath
