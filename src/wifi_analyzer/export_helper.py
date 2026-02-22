"""Extended export: CSV, JSON, ODS, PDF."""
import csv
import json
import os
import time


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
    ext = {'csv': '.csv', 'json': '.json', 'ods': '.ods', 'pdf': '.pdf'}.get(fmt, '.txt')
    return os.path.join(output_dir, f"{title}_{timestamp}{ext}")
