"""Extended export: CSV, JSON, ODS, PDF."""
import csv
import json
import os
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


def export_ods(data, headers, filepath):
    """Export data as ODS (simple XML)."""
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">')
    xml.append('<office:body><office:spreadsheet><table:table table:name="Sheet1">')
    if headers:
        xml.append('<table:table-row>')
        for h in headers:
            xml.append(f'<table:table-cell><text:p>{h}</text:p></table:table-cell>')
        xml.append('</table:table-row>')
    for row in data:
        xml.append('<table:table-row>')
        for cell in row:
            xml.append(f'<table:table-cell><text:p>{cell}</text:p></table:table-cell>')
        xml.append('</table:table-row>')
    xml.append('</table:table></office:spreadsheet></office:body></office:document-content>')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml))
    return filepath


def get_export_path(title, fmt, output_dir=None):
    """Generate export file path."""
    if output_dir is None:
        output_dir = os.path.expanduser("~")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    ext = {'csv': '.csv', 'json': '.json', 'ods': '.ods', 'pdf': '.pdf', 'html': '.html'}.get(fmt, '.txt')
    return os.path.join(output_dir, f"{title}_{timestamp}{ext}")
