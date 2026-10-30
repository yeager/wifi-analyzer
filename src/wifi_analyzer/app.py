"""WiFi Analyzer — WiFi Network Analysis Tool."""
import gettext
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from wifi_analyzer import __version__
    from wifi_analyzer.accessibility import AccessibilityManager
    from wifi_analyzer.export_helper import export_csv, export_html_report, export_json
else:
    from . import __version__
    from .accessibility import AccessibilityManager
    from .export_helper import export_csv, export_html_report, export_json

APP_ID = "io.github.yeager.wifi-analyzer"
GETTEXT_DOMAIN = "wifi-analyzer"
_locale_dir = os.environ.get("WIFI_ANALYZER_LOCALE_DIR")
if not _locale_dir or not os.path.isdir(_locale_dir):
    _package_locale_dir = Path(__file__).resolve().parent / "locale"
    if _package_locale_dir.is_dir():
        _locale_dir = str(_package_locale_dir)
    elif os.path.isdir("/app/share/locale"):
        _locale_dir = "/app/share/locale"
    else:
        _locale_dir = "/usr/share/locale"
gettext.bindtextdomain(GETTEXT_DOMAIN, _locale_dir)
gettext.textdomain(GETTEXT_DOMAIN)
_ = gettext.gettext

# 2.4 GHz channel center frequencies
CHANNEL_FREQ_24 = {1: 2412, 2: 2417, 3: 2422, 4: 2427, 5: 2432, 6: 2437,
                   7: 2442, 8: 2447, 9: 2452, 10: 2457, 11: 2462, 12: 2467, 13: 2472}
# 5 GHz common channels
CHANNEL_FREQ_5 = {36: 5180, 40: 5200, 44: 5220, 48: 5240, 52: 5260, 56: 5280,
                  60: 5300, 64: 5320, 100: 5500, 104: 5520, 108: 5540, 112: 5560,
                  116: 5580, 120: 5600, 124: 5620, 128: 5640, 132: 5660, 136: 5680,
                  140: 5700, 144: 5720, 149: 5745, 153: 5765, 157: 5785, 161: 5805, 165: 5825}

def freq_to_channel(freq):
    if freq == 2484:
        return 14
    for ch, f in {**CHANNEL_FREQ_24, **CHANNEL_FREQ_5}.items():
        if f == freq:
            return ch
    if 2412 <= freq <= 2484:
        return (freq - 2407) // 5
    if 5955 <= freq <= 7115:
        return (freq - 5950) // 5
    if 5925 <= freq <= 7125:
        return 0
    if freq >= 5000:
        return (freq - 5000) // 5
    return 0


def band_for_frequency(freq):
    """Return the Wi-Fi band containing *freq*, in MHz."""
    if 2400 <= freq < 2500:
        return "2.4 GHz"
    if 5955 <= freq <= 7115:
        return "6 GHz"
    if 5000 <= freq < 5925:
        return "5 GHz"
    return ""


def channel_width_mhz(freq):
    """Return a conservative fallback when NetworkManager reports no width.

    The AccessPoint D-Bus interface exposes the bandwidth announced by the AP.
    This helper is only used when that value is unavailable, so use the
    20 MHz primary-channel width rather than guessing a wider channel. Keep
    the source alongside the value so the UI does not present an estimate as
    a measurement.
    """
    return 20 if band_for_frequency(freq) else 0


def parse_iw_channel_width(output):
    """Read the connected radio's actual width from ``iw dev`` output."""
    match = re.search(r"width:\s*(\d+)\s*MHz", output, re.IGNORECASE)
    return int(match.group(1)) if match else None


def connected_radio_width(interface=None):
    command = ["iw", "dev"]
    if interface:
        command.extend([interface, "info"])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return parse_iw_channel_width(result.stdout) if result.returncode == 0 else None


def parse_iw_wifi_standard(output, frequency=0):
    """Identify an active link's PHY generation from kernel ``iw`` output.

    This is intentionally limited to an active link. Beacon data supplied by
    NetworkManager does not uniquely identify a remote AP's PHY generation.
    """
    bitrate_lines = "\n".join(
        line for line in output.splitlines()
        if re.match(r"^\s*(?:RX|TX)\s+BITRATE\s*:", line, re.IGNORECASE)
    )
    upper = bitrate_lines.upper()
    for marker, standard in (("EHT", "Wi-Fi 7 (802.11be)"),
                             ("HE", "Wi-Fi 6/6E (802.11ax)"),
                             ("VHT", "Wi-Fi 5 (802.11ac)"),
                             ("HT", "Wi-Fi 4 (802.11n)")):
        if re.search(rf"\b{marker}-MCS\b", upper):
            return standard
    if bitrate_lines:
        return "802.11a/g/b (legacy)" if frequency else "Legacy Wi-Fi"
    return ""


def connected_radio_standard(interface=None):
    """Return a measured PHY label for the connected interface, when known."""
    if interface:
        interfaces = [interface]
    else:
        try:
            device = subprocess.run(["iw", "dev"], capture_output=True, text=True, timeout=2, check=False)
        except (FileNotFoundError, subprocess.SubprocessError):
            return ""
        if device.returncode:
            return ""
        interfaces = re.findall(r"^\s*Interface\s+(\S+)", device.stdout, re.MULTILINE)
    for name in interfaces:
        try:
            link = subprocess.run(["iw", "dev", name, "link"], capture_output=True,
                                  text=True, timeout=2, check=False)
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
        if link.returncode == 0:
            standard = parse_iw_wifi_standard(link.stdout)
            if standard:
                return standard
    return ""


def parse_regulatory_ranges(output):
    """Parse usable frequency ranges from ``iw reg get`` output."""
    ranges = []
    for line in output.splitlines():
        match = re.search(r"\((\d+)\s*-\s*(\d+)\s*@\s*\d+\).*?(?:,\s*(.*))?$", line)
        if match:
            start, end, flags = match.groups()
            ranges.append((int(start), int(end), flags or ""))
    return ranges


def local_regulatory_ranges():
    """Read the kernel regulatory database when the host provides ``iw``."""
    try:
        result = subprocess.run(
            ["iw", "reg", "get"], capture_output=True, text=True,
            timeout=2, check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    return parse_regulatory_ranges(result.stdout) if result.returncode == 0 else []


def channel_status(freq, channel, regulatory_ranges=()):
    """Return a concise regulatory hint for a channel.

    DFS channels are usable, but their availability can change while a radio
    performs radar detection.  Exact availability remains country dependent,
    so this intentionally does not claim that a channel is forbidden.
    """
    matching_ranges = [flags for start, end, flags in regulatory_ranges if start <= freq <= end]
    if regulatory_ranges and not matching_ranges:
        return _("Unavailable in the detected regulatory domain")
    if any("DFS" in flags for flags in matching_ranges):
        return _("DFS — radar detection may interrupt this channel")
    if band_for_frequency(freq) == "5 GHz" and (52 <= channel <= 64 or 100 <= channel <= 144):
        return _("DFS — availability depends on local regulations")
    return ""


def network_matches_query(network, query):
    """Match a user search against the fields shown in the network list."""
    query = query.casefold().strip()
    if not query:
        return True
    haystack = " ".join(str(network.get(field, "")) for field in (
        "ssid", "bssid", "band", "channel", "security", "width_mhz", "channel_status"
    )).casefold()
    return query in haystack


def recommend_channels(networks, band, regulatory_ranges=()):
    """Rank channels by observed overlap, excluding out-of-range channels.

    Do not manufacture a recommendation when this scan failed or contains no
    access points in the selected band: there is no evidence to rank against.
    """
    if not networks or any(net.get("error_code") for net in networks):
        return []
    observed = [
        net for net in networks
        if net.get("band") == band and net.get("channel", 0) > 0
    ]
    if not observed:
        return []

    candidates_by_band = {
        # When the regulatory domain is known, consider every permitted
        # 2.4 GHz primary channel. Without it, stay with the common 1/6/11 set.
        "2.4 GHz": list(CHANNEL_FREQ_24) if regulatory_ranges else [1, 6, 11],
        "5 GHz": sorted(CHANNEL_FREQ_5),
        # 20 MHz 6 GHz primary channels.  Regulatory status remains a host
        # responsibility and is shown separately in the UI.
        "6 GHz": list(range(1, 234, 4)),
    }
    candidates = candidates_by_band.get(band, [])
    scored = []
    for candidate in candidates:
        if regulatory_ranges:
            if band == "2.4 GHz":
                frequency = CHANNEL_FREQ_24.get(candidate)
            elif band == "5 GHz":
                frequency = CHANNEL_FREQ_5.get(candidate)
            else:
                frequency = 5950 + candidate * 5
            if frequency is None or not any(
                start <= frequency <= end
                and not any(
                    restricted in flags.upper()
                    for restricted in ("NO-IR", "PASSIVE-SCAN", "NO-BEACON")
                )
                for start, end, flags in regulatory_ranges
            ):
                continue
        score = 0.0
        for net in observed:
            distance = abs(candidate - net["channel"])
            # Compare observed APs against a 20 MHz candidate channel. Center
            # channel overlap ends when the channels' half-widths no longer meet.
            span = max((net.get("width_mhz", 20) + 20) / 10, 1)
            if distance < span:
                score += net.get("signal_pct", 0) * (1 - distance / span)
        scored.append((candidate, round(score, 1)))
    return sorted(scored, key=lambda item: (item[1], item[0]))


def channel_recommendation_text(recommendations, no_result_reason="no-observations"):
    """Explain the scan-based estimate without implying measured airtime."""
    if not recommendations:
        if no_result_reason == "scan-failed":
            return (
                _("No channel recommendation available"),
                _("The scan did not complete, so nearby access points could not be compared."),
            )
        if no_result_reason == "no-eligible-channels":
            return (
                _("No channel recommendation available"),
                _("Nearby access points were found, but the detected regulatory information lists no candidate channel that can initiate transmission. Check the router’s country and channel settings."),
            )
        return (
            _("No channel recommendation available"),
            _("Scan this band to compare nearby access points."),
        )
    channel, score = recommendations[0]
    return (
        _("Lowest estimated overlap in this scan: channel {channel} (score {score})").format(
            channel=channel, score=score,
        ),
        _("Lower scores mean less estimated overlap. The candidate is estimated at 20 MHz; reported access point widths are used when available. Only access points found in this scan count; client traffic and hidden networks are not measured."),
    )


def connected_security_advice(networks):
    """Give cautious security guidance for the connected access point only."""
    connected = next(
        (network for network in networks if network.get("connected")), None,
    )
    if connected is None:
        return ""
    security = connected.get("security")
    if not isinstance(security, str):
        security = ""

    if security in {"WEP", "WPA1", "WPA1/WPA2", "WPA Enterprise"}:
        return _(
            "Security advice: The connected access point advertises an older "
            "Wi-Fi security mode. If you manage it, use WPA2 with AES or WPA3 "
            "and disable WEP/WPA1. The scan cannot tell which cipher your "
            "connection uses."
        )
    if security == "Enhanced Open (OWE)":
        return _(
            "Security advice: Enhanced Open encrypts Wi-Fi traffic but does "
            "not authenticate the access point. Check the network name with "
            "the venue or network owner before using it."
        )
    if not security:
        return _(
            "Security advice: The connected access point reports no Wi-Fi "
            "security. Avoid sensitive activity on this network until you "
            "have checked what protection it provides. HTTPS protects only "
            "connections to sites that use it."
        )
    return ""


def interference_contributors(network, networks):
    """Explain which observed APs overlap the selected AP most."""
    contributors = []
    for other in networks:
        if other is network or other.get("band") != network.get("band"):
            continue
        distance = abs(other.get("channel", 0) - network.get("channel", 0))
        span = max((network.get("width_mhz", 20) + other.get("width_mhz", 20)) / 10, 1)
        if distance < span:
            impact = round(other.get("signal_pct", 0) * (1 - distance / span), 1)
            contributors.append((other.get("ssid", "<Hidden>"), other.get("bssid", ""), impact))
    return sorted(contributors, key=lambda item: item[2], reverse=True)


def parse_connection_diagnostics(route_output, dns_output, address_output="", link_output=""):
    """Extract gateway and DNS servers without retaining unrelated system data."""
    gateway = ""
    for line in route_output.splitlines():
        fields = line.split()
        if not fields or fields[0] != "default" or "via" not in fields:
            continue
        via_index = fields.index("via")
        if via_index + 1 >= len(fields):
            continue
        candidate = fields[via_index + 1]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        gateway = candidate
        break
    servers = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{3,}", dns_output)
    addresses = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?|[0-9a-fA-F:]{3,}(?:/\d{1,3})?", address_output)
    rates = re.findall(r"(?:tx|rx) bitrate:\s*([^\n]+)", link_output, re.IGNORECASE)
    return {"gateway": gateway, "dns_servers": list(dict.fromkeys(servers)),
            "ip_addresses": list(dict.fromkeys(addresses)), "link_rates": rates}


def connection_diagnostics():
    try:
        route = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=2, check=False).stdout
        route6 = subprocess.run(["ip", "-6", "route"], capture_output=True, text=True, timeout=2, check=False).stdout
        dns = subprocess.run(["resolvectl", "dns"], capture_output=True, text=True, timeout=2, check=False).stdout
        addresses = subprocess.run(["ip", "-brief", "address"], capture_output=True, text=True, timeout=2, check=False).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"gateway": "", "dns_servers": [], "ip_addresses": [], "link_rates": []}

    # Match link-rate diagnostics to the active NetworkManager radio when
    # several adapters are present. An inactive first radio may have no link.
    try:
        nm_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            NM_BUS_NAME, NM_OBJ_PATH, NM_IFACE, None,
        )
        wifi_device = _find_wifi_device(nm_proxy)
        interface = wifi_device[1] if wifi_device else None
    except Exception:  # Keep gateway, DNS and IP details useful without D-Bus.
        interface = None

    link = ""
    if interface:
        try:
            link = subprocess.run(
                ["iw", "dev", interface, "link"], capture_output=True,
                text=True, timeout=2, check=False,
            ).stdout
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
    return parse_connection_diagnostics(f"{route}\n{route6}", dns, addresses, link)


def wifi_problem(networks, previous=()):
    """Return one actionable problem code and remedy, or ``None``."""
    if any(net.get("error_code") == "scan-failed" for net in networks):
        return (
            "scan-failed",
            _("Wi-Fi scan failed"),
            _(
                "Check that NetworkManager is running and your Wi-Fi adapter is enabled. "
                "For Flatpak, make sure the app can access NetworkManager."
            ),
        )
    if any(net.get("error_code") == "no-device" for net in networks):
        return ("no-device", _("No Wi-Fi device found"),
                _("Enable Wi-Fi in system settings, disable airplane mode, and check the adapter driver."))
    if not networks:
        return (
            "no-access-points",
            _("No access points found"),
            _(
                "No nearby access points were found in this scan. Check that Wi-Fi is enabled, "
                "airplane mode is off, and move closer to the router before scanning again. "
                "Hidden networks may not appear."
            ),
        )
    connected = next((net for net in networks if net.get("connected")), None)
    if connected and connected.get("signal_pct", 0) < 25:
        return ("weak-signal", _("Wi-Fi signal is weak"),
                _("Move closer to the access point, reduce obstructions, or select a less congested channel."))
    old_connected = next((net for net in previous if net.get("connected")), None)
    if old_connected and not connected:
        return ("connection-lost", _("Wi-Fi connection was lost"),
                _("Check the access point, reconnect from system settings, and inspect the gateway and DNS diagnostics."))
    if old_connected and connected and old_connected.get("bssid") != connected.get("bssid"):
        return ("roamed", _("Wi-Fi access point changed"),
                _("Roaming can be normal. If it causes interruptions, compare signal history and access-point overlap."))
    return None


def _history_path():
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    directory = os.path.join(base, "wifi-analyzer")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "history.json")


MAX_HISTORY_PROFILE_LENGTH = 64


def _load_history_records(path):
    """Load structurally valid local history records, ignoring malformed data."""
    try:
        with open(path, encoding="utf-8") as handle:
            history = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(history, list):
        return []
    return [
        scan for scan in history
        if isinstance(scan, dict)
        and isinstance(scan.get("scanned_at"), str)
        and isinstance(scan.get("profile", "Default"), str)
        and isinstance(scan.get("networks"), list)
    ]


def save_history_snapshot(networks, now=None, profile="Default"):
    """Keep local, bounded scan summaries. No scan data leaves the device."""
    now = now or datetime.now().astimezone().isoformat(timespec="seconds")
    profile = profile.strip()[:MAX_HISTORY_PROFILE_LENGTH] if isinstance(profile, str) else "Default"
    profile = profile or "Default"
    descriptor = None
    temporary_path = None
    try:
        path = _history_path()
        history = _load_history_records(path)
        history.append({"scanned_at": now, "profile": profile, "networks": [
            {key: net.get(key) for key in ("ssid", "bssid", "band", "channel", "signal_pct", "dbm", "security")}
            for net in networks if net.get("bssid")
        ]})
        # Network names and BSSIDs are sensitive local data.  A private,
        # atomic replacement avoids both accidental sharing and torn JSON files.
        descriptor, temporary_path = tempfile.mkstemp(
            prefix="history-", dir=os.path.dirname(path),
        )
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = None
        with handle:
            json.dump(history[-100:], handle, ensure_ascii=False, indent=2)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        temporary_path = None
        return True
    except OSError:
        return False
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def clear_history():
    try:
        os.unlink(_history_path())
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def load_signal_history(bssid, profile=None):
    """Return local time-series points for one AP, optionally per location profile."""
    points = []
    for scan in _load_history_records(_history_path()):
        if profile is not None and profile != scan.get("profile", "Default"):
            continue
        for net in scan["networks"]:
            if not isinstance(net, dict) or net.get("bssid") != bssid:
                continue
            signal = net.get("signal_pct")
            channel = net.get("channel")
            if (
                isinstance(signal, bool)
                or not isinstance(signal, (int, float))
                or not math.isfinite(signal)
                or not 0 <= signal <= 100
                or isinstance(channel, bool)
                or not isinstance(channel, int)
                or channel < 0
            ):
                continue
            points.append({
                "scanned_at": scan["scanned_at"],
                "signal_pct": signal,
                "channel": channel,
            })
    return points


def signal_history_summary(points):
    """Summarize valid signal values for sighted and screen-reader users."""
    signals = [
        float(signal)
        for point in points
        if isinstance(point, dict)
        for signal in [point.get("signal_pct")]
        if not isinstance(signal, bool)
        and isinstance(signal, (int, float))
        and math.isfinite(signal)
        and 0 <= signal <= 100
    ]
    if not signals:
        return _("No local signal history yet")
    return _(
        "Signal history: {count} measurements, range {minimum}% to {maximum}%, "
        "latest {latest}%."
    ).format(
        count=len(signals),
        minimum=f"{min(signals):.0f}",
        maximum=f"{max(signals):.0f}",
        latest=f"{signals[-1]:.0f}",
    )


def set_signal_history_accessibility(widget, points):
    """Expose the signal plot's role, name and non-visual summary."""
    widget.set_accessible_role(Gtk.AccessibleRole.IMG)
    widget.update_property(
        [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
        [_("Signal history"), signal_history_summary(points)],
    )


def format_signal_history_time(value):
    """Format stored local scan times, keeping malformed legacy values safe."""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%x %X")
    except (TypeError, ValueError, OverflowError):
        return str(value)[:32]


def format_signal_history_measurements(points):
    """Return localized measurement rows, with the latest scan first."""
    return [
        _("{time}: {signal}%").format(
            time=format_signal_history_time(point.get("scanned_at")),
            signal=f"{float(point['signal_pct']):.0f}",
        )
        for point in reversed(points)
    ]


def compare_scans(previous, current):
    """Return APs that appeared, disappeared, or changed channel/signal."""
    before = {net.get("bssid"): net for net in previous if net.get("bssid")}
    after = {net.get("bssid"): net for net in current if net.get("bssid")}
    return {
        "new": sorted(set(after) - set(before)),
        "gone": sorted(set(before) - set(after)),
        "changed": sorted(bssid for bssid in set(before) & set(after)
                          if before[bssid].get("channel") != after[bssid].get("channel")
                          or abs(before[bssid].get("signal_pct", 0) - after[bssid].get("signal_pct", 0)) >= 15),
    }


def anonymize_network(network):
    """Return only allowlisted radio measurements without connection identifiers."""
    allowed_fields = (
        "band", "freq", "channel", "width_mhz", "signal_pct", "dbm",
        "security", "channel_status",
    )
    record = {field: network[field] for field in allowed_fields if field in network}
    record["ssid"] = "hidden"
    record["bssid"] = "hidden"
    return record

NM_BUS_NAME = "org.freedesktop.NetworkManager"
NM_OBJ_PATH = "/org/freedesktop/NetworkManager"
NM_IFACE = "org.freedesktop.NetworkManager"
NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
NM_WIRELESS_IFACE = "org.freedesktop.NetworkManager.Device.Wireless"
NM_AP_IFACE = "org.freedesktop.NetworkManager.AccessPoint"
NM_DEVICE_TYPE_WIFI = 2
NM_AP_SEC_KEY_MGMT_802_1X = 0x0200
NM_AP_SEC_KEY_MGMT_PSK = 0x0100
NM_AP_SEC_KEY_MGMT_SAE = 0x0400
NM_AP_SEC_KEY_MGMT_OWE = 0x0800
NM_AP_SEC_KEY_MGMT_OWE_TM = 0x1000
NM_AP_SEC_KEY_MGMT_EAP_SUITE_B_192 = 0x2000

def _security_string(flags, wpa_flags, rsn_flags):
    if (rsn_flags & NM_AP_SEC_KEY_MGMT_EAP_SUITE_B_192
            and rsn_flags & NM_AP_SEC_KEY_MGMT_802_1X):
        return "WPA2/WPA3 Enterprise"
    if rsn_flags & NM_AP_SEC_KEY_MGMT_EAP_SUITE_B_192:
        return "WPA3 Enterprise"
    if rsn_flags & NM_AP_SEC_KEY_MGMT_SAE and rsn_flags & NM_AP_SEC_KEY_MGMT_PSK:
        return "WPA2/WPA3 Personal"
    if rsn_flags & NM_AP_SEC_KEY_MGMT_SAE:
        return "WPA3"
    if rsn_flags & (NM_AP_SEC_KEY_MGMT_OWE | NM_AP_SEC_KEY_MGMT_OWE_TM):
        return "Enhanced Open (OWE)"
    if rsn_flags:
        if rsn_flags & NM_AP_SEC_KEY_MGMT_802_1X:
            # RSN with 802.1X does not by itself reveal whether an AP supports
            # WPA2 Enterprise, WPA3 Enterprise, or a transition configuration.
            return "Enterprise (802.1X)"
        return "WPA1/WPA2" if wpa_flags else "WPA2"
    if wpa_flags:
        if wpa_flags & 0x200:
            return "WPA Enterprise"
        return "WPA1"
    if flags & 0x1:
        return "WEP"
    return ""

def _find_wifi_device(nm_proxy):
    devices = nm_proxy.call_sync(
        "GetDevices", None, Gio.DBusCallFlags.NONE, -1, None
    ).unpack()[0]
    candidates = []
    for path in devices:
        dev_props = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            NM_BUS_NAME, path, "org.freedesktop.DBus.Properties", None
        )
        device_type = dev_props.call_sync(
            "Get", GLib.Variant("(ss)", (NM_DEVICE_IFACE, "DeviceType")),
            Gio.DBusCallFlags.NONE, -1, None
        ).unpack()[0]
        if device_type == NM_DEVICE_TYPE_WIFI:
            device_interface = dev_props.call_sync(
                "Get", GLib.Variant("(ss)", (NM_DEVICE_IFACE, "Interface")),
                Gio.DBusCallFlags.NONE, -1, None
            ).unpack()[0]
            wireless_props = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                NM_BUS_NAME, path, "org.freedesktop.DBus.Properties", None
            )
            active_ap = wireless_props.call_sync(
                "Get", GLib.Variant("(ss)", (NM_WIRELESS_IFACE, "ActiveAccessPoint")),
                Gio.DBusCallFlags.NONE, -1, None
            ).unpack()[0]
            candidates.append((path, device_interface, active_ap))
    return select_wifi_device(candidates)


def select_wifi_device(candidates):
    """Prefer the NetworkManager Wi-Fi device with an active access point."""
    candidates = list(candidates)
    if not candidates:
        return None
    return next(
        (candidate for candidate in candidates if candidate[2] not in (None, "", "/")),
        candidates[0],
    )


def scan_networks_dbus(regulatory_ranges=None):
    """Scan WiFi networks via NetworkManager D-Bus"""
    networks = []
    if regulatory_ranges is None:
        regulatory_ranges = local_regulatory_ranges()
    try:
        nm_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            NM_BUS_NAME, NM_OBJ_PATH, NM_IFACE, None
        )
        wifi_device = _find_wifi_device(nm_proxy)
        if not wifi_device:
            networks.append({"ssid": _("Error: no WiFi device found"), "bssid": "", "freq": 0,
                             "channel": 0, "signal_pct": 0, "dbm": -100, "security": "", "band": "",
                             "error_code": "no-device", "error_message": _("No Wi-Fi device found")})
            return networks
        wifi_path, wifi_interface, active_ap = wifi_device

        actual_width = connected_radio_width(wifi_interface)
        active_standard = connected_radio_standard(wifi_interface)

        wireless_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            NM_BUS_NAME, wifi_path, NM_WIRELESS_IFACE, None
        )

        wireless_proxy.call_sync(
            "RequestScan", GLib.Variant("(a{sv})", ({},)),
            Gio.DBusCallFlags.NONE, 5000, None
        )

        ap_paths = wireless_proxy.call_sync(
            "GetAllAccessPoints", None, Gio.DBusCallFlags.NONE, -1, None
        ).unpack()[0]

        for ap_path in ap_paths:
            ap_props_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                NM_BUS_NAME, ap_path, "org.freedesktop.DBus.Properties", None
            )
            props = ap_props_proxy.call_sync(
                "GetAll", GLib.Variant("(s)", (NM_AP_IFACE,)),
                Gio.DBusCallFlags.NONE, -1, None
            ).unpack()[0]

            ssid_bytes = bytes(props.get("Ssid", []))
            ssid = ssid_bytes.decode("utf-8", errors="replace") or _("<Hidden>")
            bssid = props.get("HwAddress", "")
            freq = props.get("Frequency", 0)
            signal_pct = props.get("Strength", 0)
            flags = props.get("Flags", 0)
            wpa_flags = props.get("WpaFlags", 0)
            rsn_flags = props.get("RsnFlags", 0)
            last_seen = props.get("LastSeen", -1)
            security = _security_string(flags, wpa_flags, rsn_flags)
            channel = freq_to_channel(freq)
            band = band_for_frequency(freq)
            connected = ap_path == active_ap
            announced_width = props.get("Bandwidth", 0)
            width_mhz = actual_width if connected and actual_width else announced_width or channel_width_mhz(freq)
            # Convert signal % to approximate dBm
            dbm = int(signal_pct / 2 - 100) if signal_pct else -100

            networks.append({
                "ssid": ssid, "bssid": bssid, "freq": freq, "channel": channel,
                "signal_pct": signal_pct, "dbm": dbm, "security": security,
                "band": band, "width_mhz": width_mhz,
                "channel_status": channel_status(freq, channel, regulatory_ranges),
                "last_seen": last_seen,
                "connected": connected,
                "width_source": "measured" if connected and actual_width else "estimated",
                "wifi_standard": active_standard if connected else "",
            })
    except (GLib.Error, TypeError, ValueError) as error:
        networks.append({"ssid": f"Error: {error}", "bssid": "", "freq": 0, "channel": 0,
                         "signal_pct": 0, "dbm": -100, "security": "", "band": "",
                         "error_code": "scan-failed", "error_message": str(error)})
    return networks



def _wlc_settings_path():
    import os
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(xdg, "wifi-analyzer")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "welcome.json")

def _load_wlc_settings():
    import os, json
    p = _wlc_settings_path()
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"welcome_shown": False}

def _save_wlc_settings(s):
    import json
    with open(_wlc_settings_path(), "w") as f:
        json.dump(s, f, indent=2)

class ChannelDrawingArea(Gtk.DrawingArea):
    """Custom drawing area for channel overlap visualization."""
    def __init__(self):
        super().__init__()
        self.networks = []
        self.band_filter = "2.4 GHz"
        self.zoom = 1.0
        self.on_channel_selected = None
        self.selectable_channels = []
        self.focused_channel = None
        self.set_draw_func(self._draw)
        self.set_content_height(220)
        self.set_focusable(True)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        instructions = _("Focus the chart and use the Left and Right Arrow keys to choose a channel. Press Home or End to jump to the first or last channel. Press Enter or Space to filter the network list. Scroll to zoom.")
        self.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [_("Channel overlap chart"), instructions],
        )
        keys = Gtk.EventControllerKey.new()
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)
        click = Gtk.GestureClick.new()
        click.connect("pressed", self._on_click)
        self.add_controller(click)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)
        self.set_tooltip_text(instructions)

    def set_networks(self, networks, band="2.4 GHz", selectable_channels=None):
        self.networks = networks
        self.band_filter = band
        if selectable_channels is None:
            selectable_channels = [
                net["channel"] for net in networks
                if net["band"] == band and net["channel"] > 0
            ]
        self.selectable_channels = sorted(set(selectable_channels))
        if self.focused_channel not in self.selectable_channels:
            self.focused_channel = None
        self.queue_draw()

    def _announce(self, message):
        Gtk.Accessible.announce(
            self, message, Gtk.AccessibleAnnouncementPriority.MEDIUM,
        )

    def _on_key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Home, Gdk.KEY_End):
            if not self.selectable_channels:
                return False
            if keyval == Gdk.KEY_Home:
                index = 0
            elif keyval == Gdk.KEY_End:
                index = len(self.selectable_channels) - 1
            else:
                direction = 1 if keyval == Gdk.KEY_Right else -1
                if self.focused_channel in self.selectable_channels:
                    index = self.selectable_channels.index(self.focused_channel)
                else:
                    index = -1 if direction > 0 else 0
                index = (index + direction) % len(self.selectable_channels)
            self.focused_channel = self.selectable_channels[index]
            self.queue_draw()
            self._announce(_("Channel {channel}. Press Enter to filter the network list.").format(
                channel=self.focused_channel,
            ))
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            if self.focused_channel is None or self.on_channel_selected is None:
                return False
            selected = self.on_channel_selected(self.focused_channel)
            if selected is False:
                message = _("Channel filter cleared.")
            else:
                message = _("Filtering access points by channel {channel}.").format(
                    channel=self.focused_channel,
                )
            self._announce(message)
            return True

        return False

    def _channel_bounds(self):
        filtered = [n for n in self.networks if n["band"] == self.band_filter and n["channel"] > 0]
        if self.band_filter == "2.4 GHz":
            low, high = 0, 14
        else:
            channels = sorted(
                {n["channel"] for n in filtered}
                | set(self.selectable_channels)
            )
            low, high = (min(channels) - 4, max(channels) + 4) if channels else (0, 1)
        center = (low + high) / 2
        half_span = (high - low) / (2 * self.zoom)
        return center - half_span, center + half_span

    def _on_scroll(self, _controller, _dx, dy):
        self.zoom = max(1.0, min(8.0, self.zoom * (1.25 if dy < 0 else 0.8)))
        self.queue_draw()
        return True

    def _on_click(self, _gesture, _presses, x, y):
        width = self.get_allocated_width()
        plot_left, plot_right = 50, width - 20
        if not plot_left <= x <= plot_right or not 20 <= y <= self.get_allocated_height() - 40:
            return
        ch_min, ch_max = self._channel_bounds()
        channel = round(ch_min + (x - 50) / max(width - 70, 1) * (ch_max - ch_min))
        visible_channels = {
            n["channel"] for n in self.networks
            if n["band"] == self.band_filter and n["channel"] > 0
        }
        if self.on_channel_selected and visible_channels and channel > 0:
            channel = min(visible_channels, key=lambda candidate: abs(candidate - channel))
            self.focused_channel = channel
            self.grab_focus()
            self.queue_draw()
            self.on_channel_selected(channel)

    def _font_scale(self):
        """Follow the desktop text scale for Cairo-drawn chart labels."""
        settings = Gtk.Settings.get_default()
        dpi = settings.get_property("gtk-xft-dpi") if settings else -1
        return dpi / (96 * 1024) if dpi > 0 else 1.0

    def _draw(self, area, cr, width, height):
        font_scale = self._font_scale()
        # Background
        cr.set_source_rgb(0.15, 0.15, 0.18)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        filtered = [n for n in self.networks if n["band"] == self.band_filter and n["channel"] > 0]
        if not filtered:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(14 * font_scale)
            cr.move_to(width / 2 - 60, height / 2)
            cr.show_text(_("No networks found"))
            return

        margin_left, margin_right, margin_top, margin_bottom = 50, 20, 20, 40
        plot_w = width - margin_left - margin_right
        plot_h = height - margin_top - margin_bottom

        ch_min, ch_max = self._channel_bounds()

        dbm_min, dbm_max = -100, -20

        def ch_to_x(ch):
            return margin_left + (ch - ch_min) / max(ch_max - ch_min, 1) * plot_w

        def dbm_to_y(dbm):
            return margin_top + plot_h - (dbm - dbm_min) / (dbm_max - dbm_min) * plot_h

        # Grid
        cr.set_source_rgba(0.4, 0.4, 0.4, 0.3)
        cr.set_line_width(0.5)
        for dbm in range(-100, -10, 10):
            y = dbm_to_y(dbm)
            cr.move_to(margin_left, y); cr.line_to(width - margin_right, y)
            cr.stroke()
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(10 * font_scale)
            cr.move_to(5, y + 4)
            cr.show_text(f"{dbm}")
            cr.set_source_rgba(0.4, 0.4, 0.4, 0.3)

        if self.band_filter == "2.4 GHz":
            ch_range = range(1, 14)
        else:
            ch_range = sorted(set(n["channel"] for n in filtered))
        for ch in ch_range:
            x = ch_to_x(ch)
            cr.set_source_rgba(0.4, 0.4, 0.4, 0.3)
            cr.move_to(x, margin_top); cr.line_to(x, height - margin_bottom)
            cr.stroke()
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(10 * font_scale)
            cr.move_to(x - 5, height - margin_bottom + 15)
            cr.show_text(str(ch))

        # Draw networks as bell curves
        colors = [
            (0.2, 0.6, 1.0), (1.0, 0.4, 0.3), (0.3, 0.9, 0.4), (1.0, 0.8, 0.2),
            (0.8, 0.3, 0.9), (0.2, 0.9, 0.9), (1.0, 0.5, 0.0), (0.6, 0.6, 1.0),
        ]
        for i, net in enumerate(filtered):
            color = colors[i % len(colors)]
            cr.set_source_rgba(*color, 0.3)
            cr.set_line_width(2)

            center = net["channel"]
            # Channels are 5 MHz apart. The curve reaches its baseline at
            # approximately the advertised channel width.
            bw = max(net.get("width_mhz", 20) / 10, 1)
            peak_y = dbm_to_y(net["dbm"])
            base_y = dbm_to_y(-100)

            steps = 60
            points = []
            for s in range(steps + 1):
                ch = center - bw * 2 + (bw * 4) * s / steps
                x = ch_to_x(ch)
                dist = (ch - center) / bw
                amp = math.exp(-dist * dist * 2)
                y = base_y + (peak_y - base_y) * amp
                points.append((x, y))

            # Fill
            cr.move_to(points[0][0], base_y)
            for x, y in points:
                cr.line_to(x, y)
            cr.line_to(points[-1][0], base_y)
            cr.close_path()
            cr.fill()

            # Outline
            cr.set_source_rgba(*color, 0.9)
            cr.move_to(*points[0])
            for x, y in points:
                cr.line_to(x, y)
            cr.stroke()

            # Label
            cr.set_source_rgb(*color)
            cr.set_font_size(9 * font_scale)
            label = net["ssid"][:18]
            tx = ch_to_x(center)
            cr.move_to(tx - len(label) * 2.5, peak_y - 6)
            cr.show_text(label)

        if self.focused_channel is not None:
            x = ch_to_x(self.focused_channel)
            if margin_left <= x <= width - margin_right:
                cr.set_source_rgb(1.0, 0.85, 0.1)
                cr.set_line_width(3 * font_scale)
                cr.set_dash([5 * font_scale, 3 * font_scale])
                cr.move_to(x, margin_top)
                cr.line_to(x, height - margin_bottom)
                cr.stroke()
                cr.set_dash([])


class NetworkRow(Gtk.ListBoxRow):
    def __init__(self, net):
        super().__init__()
        self.net = net
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(6); box.set_margin_bottom(6)

        # Signal strength icon
        if net["signal_pct"] > 75:
            icon = "network-wireless-signal-excellent-symbolic"
        elif net["signal_pct"] > 50:
            icon = "network-wireless-signal-good-symbolic"
        elif net["signal_pct"] > 25:
            icon = "network-wireless-signal-ok-symbolic"
        else:
            icon = "network-wireless-signal-weak-symbolic"
        img = Gtk.Image.new_from_icon_name(icon)
        box.append(img)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)
        ssid_label = Gtk.Label(label=net["ssid"], xalign=0)
        ssid_label.add_css_class("heading")
        ssid_label.set_tooltip_text(net.get("bssid", ""))
        vbox.append(ssid_label)
        width = net.get("width_mhz", 0)
        width_source = _("measured") if net.get("width_source") == "measured" else _("estimated")
        width_detail = f" · {width} MHz {width_source}" if width else ""
        standard_detail = f" · {net['wifi_standard']}" if net.get("wifi_standard") else ""
        active_detail = _(" · Connected") if net.get("connected") else ""
        detail = (_("Ch {channel} · {frequency} MHz{width}{active} · {dbm} dBm · {security} · {bssid}").format(
            channel=net["channel"], frequency=net.get("freq", 0), width=width_detail,
            active=active_detail + standard_detail, dbm=net["dbm"], security=net["security"] or _("Open"),
            bssid=net.get("bssid", "")))
        sub = Gtk.Label(label=detail, xalign=0)
        sub.add_css_class("dim-label")
        vbox.append(sub)
        if net.get("channel_status"):
            status = Gtk.Label(label=net["channel_status"], xalign=0)
            status.add_css_class("warning")
            status.set_wrap(True)
            vbox.append(status)
        box.append(vbox)

        # Signal bar
        pct_label = Gtk.Label(label=f"{net['signal_pct']}%")
        pct_label.add_css_class("numeric")
        box.append(pct_label)

        self.set_child(box)


class SignalHistoryDrawingArea(Gtk.DrawingArea):
    """Render locally stored signal points for one selected access point."""
    def __init__(self, points):
        super().__init__()
        self.points = points
        self.set_content_height(220)
        set_signal_history_accessibility(self, points)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width, height):
        cr.set_source_rgb(0.15, 0.15, 0.18)
        cr.paint()
        if not self.points:
            cr.set_source_rgb(0.7, 0.7, 0.7)
            cr.set_font_size(14)
            cr.move_to(20, height / 2)
            cr.show_text(_("No local signal history yet"))
            return
        left, right, top, bottom = 42, 18, 18, 30
        plot_w, plot_h = width - left - right, height - top - bottom
        def point(index, signal):
            x = left + index / max(len(self.points) - 1, 1) * plot_w
            y = top + plot_h - max(0, min(100, signal or 0)) / 100 * plot_h
            return x, y
        cr.set_source_rgba(0.55, 0.55, 0.55, 0.35)
        for signal in range(0, 101, 25):
            y = top + plot_h - signal / 100 * plot_h
            cr.move_to(left, y); cr.line_to(width - right, y); cr.stroke()
            cr.set_source_rgb(0.7, 0.7, 0.7); cr.move_to(4, y + 4); cr.show_text(f"{signal}%")
            cr.set_source_rgba(0.55, 0.55, 0.55, 0.35)
        cr.set_source_rgb(0.25, 0.65, 1.0); cr.set_line_width(2)
        for index, item in enumerate(self.points):
            x, y = point(index, item.get("signal_pct"))
            if index: cr.line_to(x, y)
            else: cr.move_to(x, y)
        cr.stroke()


class WifiAnalyzerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("WiFi Analyzer"), default_width=950, default_height=750)
        self.networks = []
        self.regulatory_ranges = []
        self.dark_mode = False
        self._last_problem_code = None
        self._scanning = False
        self.selected_channel = None

        header = Adw.HeaderBar()
        # Theme toggle
        theme_btn = Gtk.Button(icon_name="display-brightness-symbolic", tooltip_text=_("Toggle theme"))
        theme_btn.connect("clicked", self._toggle_theme)
        header.pack_end(theme_btn)
        # Menu
        menu = Gio.Menu()
        menu.append(_("Export CSV"), "win.export-csv")
        menu.append(_("Export JSON"), "win.export-json")
        menu.append(_("Export anonymized JSON"), "win.export-anonymous-json")
        menu.append(_("Export diagnostic report"), "win.export-report")
        menu.append(_("Connection diagnostics"), "win.connection-diagnostics")
        menu.append(_("Clear local history"), "win.clear-history")
        menu.append(_("About"), "win.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)
        # Refresh
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Scan"))
        refresh_btn.connect("clicked", lambda b: self._scan())
        header.pack_end(refresh_btn)
        self.monitor_button = Gtk.ToggleButton(label=_("Monitor"), tooltip_text=_("Scan every 60 seconds and notify about changes"))
        self.monitor_button.connect("toggled", self._toggle_monitor)
        header.pack_start(self.monitor_button)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._show_about)
        self.add_action(about_action)
        for action_name, callback in (("export-csv", self._export_csv),
                                      ("export-json", self._export_json),
                                      ("export-anonymous-json", self._export_anonymous_json),
                                      ("export-report", self._export_report),
                                      ("connection-diagnostics", self._show_connection_diagnostics),
                                      ("clear-history", self._clear_history)):
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", callback)
            self.add_action(action)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)

        # Band selector. Adw.ToggleGroup keeps the choice mutually exclusive
        # and exposes an accessible active-name for keyboard and assistive use.
        band_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        band_box.set_margin_start(12); band_box.set_margin_end(12); band_box.set_margin_top(8)
        self.band_selector = Adw.ToggleGroup()
        for name, label in (("2.4 GHz", "2.4 GHz"), ("5 GHz", "5 GHz"), ("6 GHz", "6 GHz")):
            toggle = Adw.Toggle.new()
            toggle.set_name(name)
            toggle.set_label(label)
            self.band_selector.add(toggle)
        self.band_selector.set_active_name("2.4 GHz")
        self.band_selector.connect("notify::active-name", self._on_band_changed)
        band_box.append(self.band_selector)
        main_box.append(band_box)

        self.search_entry = Gtk.SearchEntry(placeholder_text=_("Filter by name, BSSID, channel or security"))
        self.search_entry.set_margin_start(12); self.search_entry.set_margin_end(12)
        self.search_entry.set_margin_top(8)
        self.search_entry.connect("search-changed", self._on_search_changed)
        main_box.append(self.search_entry)

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.set_margin_start(12); filter_box.set_margin_end(12)
        filter_box.set_margin_top(6)
        signal_label = Gtk.Label(label=_("Minimum signal"))
        filter_box.append(signal_label)
        self.signal_threshold = Gtk.SpinButton.new_with_range(-100, 0, 5)
        self.signal_threshold.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Minimum signal")],
        )
        self.signal_threshold.set_value(-100)
        self.signal_threshold.set_tooltip_text(_("Only show access points at or above this estimated dBm value"))
        self.signal_threshold.connect("value-changed", self._on_filter_changed)
        filter_box.append(self.signal_threshold)

        security_label = Gtk.Label(label=_("Security"))
        filter_box.append(security_label)
        self.security_filter = Gtk.DropDown.new_from_strings([
            _("All security"), _("Open"), "WEP", "WPA1", "WPA2", "WPA1/WPA2",
            "Enterprise (802.1X)", "WPA2/WPA3 Personal", "WPA2/WPA3 Enterprise",
            "WPA3", "WPA3 Enterprise", "Enhanced Open (OWE)",
        ])
        self.security_filter.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Security")],
        )
        self.security_filter.connect("notify::selected", self._on_filter_changed)
        filter_box.append(self.security_filter)

        self.hidden_filter = Gtk.CheckButton(label=_("Hidden SSIDs only"))
        self.hidden_filter.connect("toggled", self._on_filter_changed)
        filter_box.append(self.hidden_filter)

        sort_label = Gtk.Label(label=_("Sort"))
        filter_box.append(sort_label)
        self.sort_filter = Gtk.DropDown.new_from_strings([_("Signal"), _("Channel"), _("Security")])
        self.sort_filter.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Sort")],
        )
        self.sort_filter.connect("notify::selected", self._on_filter_changed)
        filter_box.append(self.sort_filter)
        profile_label = Gtk.Label(label=_("Profile"))
        filter_box.append(profile_label)
        self.profile_entry = Gtk.Entry(text="Default", width_chars=10)
        self.profile_entry.set_max_length(MAX_HISTORY_PROFILE_LENGTH)
        self.profile_entry.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Profile")],
        )
        self.profile_entry.set_tooltip_text(_("Keep local scan history separate for this location"))
        filter_box.append(self.profile_entry)
        main_box.append(filter_box)

        recommendation_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        recommendation_box.set_margin_start(12); recommendation_box.set_margin_end(12)
        recommendation_box.set_margin_top(6)
        self.recommendation = Gtk.Label(xalign=0)
        self.recommendation.add_css_class("dim-label")
        self.recommendation_detail = Gtk.Label(xalign=0, wrap=True)
        self.recommendation_detail.add_css_class("dim-label")
        self.security_advice = Gtk.Label(xalign=0, wrap=True)
        self.security_advice.set_margin_top(4)
        recommendation_box.append(self.recommendation)
        recommendation_box.append(self.recommendation_detail)
        recommendation_box.append(self.security_advice)
        main_box.append(recommendation_box)

        # Channel overlap visualization
        frame = Gtk.Frame()
        frame.set_margin_start(12); frame.set_margin_end(12); frame.set_margin_top(8)
        self.channel_chart = ChannelDrawingArea()
        self.channel_chart.on_channel_selected = self._select_channel
        frame.set_child(self.channel_chart)
        main_box.append(frame)

        # Network list
        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.set_margin_start(12); sw.set_margin_end(12); sw.set_margin_top(8); sw.set_margin_bottom(4)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self._on_network_selected)
        self.listbox.add_css_class("boxed-list")
        sw.set_child(self.listbox)
        main_box.append(sw)

        # Status bar
        self.statusbar = Gtk.Label(label=_("Ready — click Scan"), xalign=0)
        self.statusbar.set_margin_start(12); self.statusbar.set_margin_end(12)
        self.statusbar.set_margin_top(4); self.statusbar.set_margin_bottom(4)
        self.statusbar.add_css_class("dim-label")
        self.statusbar.set_wrap(True)
        main_box.append(self.statusbar)

        self.set_content(main_box)
        self.accessibility = AccessibilityManager(self, app)
        self._scan()

    def _set_status(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.statusbar.set_label(f"[{ts}] {msg}")

    def _toggle_theme(self, btn):
        mgr = Adw.StyleManager.get_default()
        self.dark_mode = not self.dark_mode
        mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.dark_mode else Adw.ColorScheme.FORCE_LIGHT)

    def _get_band(self):
        return self.band_selector.get_active_name() or "2.4 GHz"

    def _on_band_changed(self, selector, _param):
        self._update_ui()

    def _on_search_changed(self, entry):
        self._update_ui()

    def _on_filter_changed(self, *_args):
        self._update_ui()

    def _select_channel(self, channel):
        """Filter visible APs by a clicked channel; click it again to clear."""
        self.selected_channel = None if self.selected_channel == channel else channel
        self._update_ui()
        return self.selected_channel == channel

    def _on_network_selected(self, _listbox, row):
        if not row:
            return
        self._show_signal_history(row.net)
        contributors = interference_contributors(row.net, self.networks)
        if contributors:
            names = ", ".join(f"{ssid} ({impact})" for ssid, _bssid, impact in contributors[:3])
            self._set_status(_("Main overlapping access points: {names}").format(names=names))
        else:
            self._set_status(_("No overlapping access points detected"))

    def _show_signal_history(self, network):
        """Show the selected AP's private, profile-scoped local signal graph."""
        profile = self.profile_entry.get_text().strip() or "Default"
        points = load_signal_history(network.get("bssid", ""), profile)
        dialog = Adw.Dialog()
        dialog.set_title(_("Signal history"))
        dialog.set_content_width(600)
        page = Adw.StatusPage()
        page.set_title(network.get("ssid") or _("<Hidden>"))
        page.set_description(_("Local history for profile: {profile}").format(profile=profile))
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.append(SignalHistoryDrawingArea(points))
        if points:
            history_label = Gtk.Label(label=_("Recent measurements"), xalign=0)
            history_label.add_css_class("heading")
            content.append(history_label)
            history_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            history_list.add_css_class("boxed-list")
            for label in format_signal_history_measurements(points):
                measurement = Gtk.Label(
                    label=label,
                    xalign=0,
                )
                measurement.set_margin_start(12)
                measurement.set_margin_end(12)
                measurement.set_margin_top(6)
                measurement.set_margin_bottom(6)
                history_list.append(measurement)
            history_scroll = Gtk.ScrolledWindow(
                vexpand=True, min_content_height=100,
            )
            history_scroll.set_child(history_list)
            content.append(history_scroll)
        page.set_child(content)
        dialog.set_child(page)
        dialog.present(self)

    def _scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._set_status(_("Scanning..."))
        def worker():
            try:
                regulatory_ranges = local_regulatory_ranges()
                nets = scan_networks_dbus(regulatory_ranges=regulatory_ranges)
            except Exception as error:  # Preserve a usable UI for unforeseen D-Bus failures.
                regulatory_ranges = []
                nets = [{"ssid": f"Error: {error}", "bssid": "", "freq": 0,
                         "channel": 0, "signal_pct": 0, "dbm": -100, "security": "", "band": "",
                         "error_code": "scan-failed", "error_message": str(error)}]
            GLib.idle_add(self._on_scan_done, nets, regulatory_ranges)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_monitor(self, button):
        if button.get_active():
            self._monitor_source = GLib.timeout_add_seconds(60, self._monitor_scan)
            self._set_status(_("Monitoring enabled; scanning every 60 seconds"))
        elif getattr(self, "_monitor_source", None):
            GLib.source_remove(self._monitor_source)
            self._monitor_source = None
            self._set_status(_("Monitoring disabled"))

    def _monitor_scan(self):
        self._scan()
        return True

    def _on_scan_done(self, nets, regulatory_ranges=()):
        self._scanning = False
        self.regulatory_ranges = regulatory_ranges
        previous = self.networks
        counts = {}
        for net in nets:
            if net.get("ssid"):
                counts[net["ssid"]] = counts.get(net["ssid"], 0) + 1
        for net in nets:
            net["access_point_count"] = counts.get(net.get("ssid"), 1)
        self.networks = sorted(nets, key=lambda n: n["signal_pct"], reverse=True)
        scan_error = next((net for net in self.networks if net.get("error_code") == "scan-failed"), None)
        problem = wifi_problem(self.networks, previous)
        history_saved = None
        if any(net.get("bssid") for net in self.networks):
            history_saved = save_history_snapshot(
                self.networks,
                profile=self.profile_entry.get_text().strip() or "Default",
            )
        self._update_ui()
        changes = compare_scans(previous, self.networks) if previous else None
        suffix = _(" · {new} new, {gone} gone").format(
            new=len(changes["new"]), gone=len(changes["gone"]),
        ) if changes else ""
        if scan_error:
            self._set_status(_("Scan failed: {error}").format(error=scan_error["error_message"]))
        else:
            message = _("Found {count} networks{suffix}").format(
                count=len(self.networks), suffix=suffix,
            )
            if problem and problem[0] == "no-access-points":
                message += " · " + problem[2]
            if history_saved is False:
                message += " · " + _("Local scan history could not be saved")
            self._set_status(message)
        if changes and (changes["new"] or changes["gone"] or changes["changed"]):
            notification = Gio.Notification.new(_("WiFi scan changed"))
            notification.set_body(_("{new} new, {gone} gone, {changed} changed access points").format(
                new=len(changes["new"]), gone=len(changes["gone"]), changed=len(changes["changed"])))
            self.get_application().send_notification("wifi-scan-change", notification)
        if problem:
            code, title, remedy = problem
            if code != self._last_problem_code:
                notification = Gio.Notification.new(title)
                notification.set_body(remedy)
                notification.set_priority(Gio.NotificationPriority.URGENT)
                self.get_application().send_notification("wifi-problem", notification)
            self._last_problem_code = code
        else:
            self._last_problem_code = None

    def _update_ui(self):
        band = self._get_band()
        # Update list
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        selected_security = self.security_filter.get_selected_item().get_string()
        filtered = [n for n in self.networks
                    if n["band"] == band
                    and (self.selected_channel is None or n["channel"] == self.selected_channel)
                    and n["dbm"] >= self.signal_threshold.get_value_as_int()
                    and (selected_security == _("All security")
                         or (selected_security == _("Open") and not n["security"])
                         or n["security"] == selected_security)
                    and (not self.hidden_filter.get_active() or n["ssid"] == _("<Hidden>"))
                    and network_matches_query(n, self.search_entry.get_text())]
        sort_name = self.sort_filter.get_selected_item().get_string()
        if sort_name == _("Channel"):
            filtered.sort(key=lambda net: (net.get("channel", 0), -net.get("signal_pct", 0)))
        elif sort_name == _("Security"):
            filtered.sort(key=lambda net: (net.get("security", ""), -net.get("signal_pct", 0)))
        else:
            filtered.sort(key=lambda net: net.get("signal_pct", 0), reverse=True)
        for net in filtered:
            self.listbox.append(NetworkRow(net))
        self.visible_networks = filtered
        # Update chart
        selectable_channels = [
            net["channel"] for net in self.networks
            if net["band"] == band and net["channel"] > 0
        ]
        self.channel_chart.set_networks(filtered, band, selectable_channels)
        recommendations = recommend_channels(
            self.networks, band, getattr(self, "regulatory_ranges", ()),
        )
        if any(net.get("error_code") for net in self.networks):
            no_result_reason = "scan-failed"
        elif any(
            net.get("band") == band and net.get("channel", 0) > 0
            for net in self.networks
        ) and getattr(self, "regulatory_ranges", ()):
            no_result_reason = "no-eligible-channels"
        else:
            no_result_reason = "no-observations"
        recommendation, explanation = channel_recommendation_text(
            recommendations, no_result_reason,
        )
        security_advice = connected_security_advice(self.networks)
        self.recommendation.set_label(recommendation)
        self.recommendation_detail.set_label(explanation)
        self.security_advice.set_label(security_advice)
        self.security_advice.set_visible(bool(security_advice))

    def _export_rows(self):
        fields = ("ssid", "bssid", "band", "freq", "channel", "width_mhz", "signal_pct", "dbm", "security", "channel_status", "last_seen")
        return [[net.get(field, "") for field in fields] for net in getattr(self, "visible_networks", self.networks) if net.get("bssid")]

    def _choose_export_path(self, title, filename, callback):
        """Let the user choose an export location before writing any data."""
        dialog = Gtk.FileChooserNative.new(
            title, self, Gtk.FileChooserAction.SAVE, _("Export"), _("Cancel"),
        )
        dialog.set_current_name(filename)

        def on_response(chooser, response):
            if response == Gtk.ResponseType.ACCEPT:
                selected = chooser.get_file()
                path = selected.get_path() if selected else None
                if path:
                    try:
                        callback(path)
                    except OSError as error:
                        self._set_status(_("Export failed: {error}").format(error=error))
            chooser.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _export_csv(self, *_args):
        headers = ["SSID", "BSSID", "Band", "Frequency MHz", "Channel", "Width MHz", "Signal %", "Estimated dBm", "Security", "Channel status", "Last seen s"]
        def write(path):
            export_csv(self._export_rows(), headers, path)
            self._set_status(_("Exported CSV to {path}").format(path=path))
        self._confirm_identifiable_export(_("Export CSV"), "wifi-analyzer.csv", write)

    def _export_json(self, *_args):
        headers = ["ssid", "bssid", "band", "frequency_mhz", "channel", "width_mhz", "signal_percent", "estimated_dbm", "security", "channel_status", "last_seen_seconds"]
        def write(path):
            export_json(self._export_rows(), headers, path)
            self._set_status(_("Exported JSON to {path}").format(path=path))
        self._confirm_identifiable_export(_("Export JSON"), "wifi-analyzer.json", write)

    def _export_anonymous_json(self, *_args):
        dialog = Adw.AlertDialog.new(_("Export anonymized JSON"), None)
        dialog.set_body(_("This export hides network names (SSIDs), access point MAC addresses (BSSIDs) and connection-specific details. It keeps band, frequency, channel, signal, width and security or regulatory details. Those details may still identify a location, so review the file before sharing it."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("export", _("Continue to export"))
        dialog.set_response_appearance("export", Adw.ResponseAppearance.SUGGESTED)

        def write(path):
            records = [anonymize_network(net) for net in getattr(self, "visible_networks", self.networks)
                       if net.get("bssid")]
            export_json(records, None, path)
            self._set_status(_("Exported anonymized JSON to {path}").format(path=path))

        def on_response(_dialog, response):
            if response == "export":
                self._choose_export_path(_("Export anonymized JSON"), "wifi-analyzer-anonymous.json", write)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _confirm_identifiable_export(self, title, filename, write):
        """Warn before exporting scan data that identifies nearby networks."""
        dialog = Adw.AlertDialog.new(_("Export network details?"), None)
        dialog.set_body(_("This export includes visible network names (SSIDs) and access point MAC addresses (BSSIDs). Save it locally and review it before sharing; these details can reveal nearby networks and your location."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("export", _("Continue to export"))
        dialog.set_default_response("cancel")
        dialog.set_response_appearance("export", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_dialog, response):
            if response == "export":
                self._choose_export_path(title, filename, write)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _export_report(self, *_args):
        def write(path):
            regulatory_ranges = getattr(self, "regulatory_ranges", ())
            report_networks = [
                net for net in getattr(self, "visible_networks", self.networks)
                if net.get("bssid")
            ]
            recommendations = {}
            for band in ("2.4 GHz", "5 GHz", "6 GHz"):
                ranked = recommend_channels(report_networks, band, regulatory_ranges)
                recommendations[band] = ranked[0] if ranked else (None, None)
            export_html_report(report_networks, recommendations, path)
            self._set_status(_("Exported diagnostic report to {path}").format(path=path))
        self._confirm_identifiable_export(_("Export diagnostic report"), "wifi-analyzer-report.html", write)

    def _show_connection_diagnostics(self, *_args):
        info = connection_diagnostics()
        dns = ", ".join(info["dns_servers"]) or _("unavailable")
        addresses = ", ".join(info["ip_addresses"]) or _("unavailable")
        rates = "; ".join(info["link_rates"]) or _("unavailable")
        dialog = Adw.AlertDialog.new(_("Connection diagnostics"), None)
        dialog.set_body(_("Gateway: {gateway}\nDNS: {dns}\nIP addresses: {addresses}\nLink rate: {rates}").format(
            gateway=info["gateway"] or _("unavailable"), dns=dns, addresses=addresses, rates=rates))
        dialog.add_response("close", _("Close"))
        dialog.present(self)

    def _clear_history(self, *_args):
        if clear_history():
            self._set_status(_("Cleared local scan history"))
        else:
            self._set_status(_("Could not clear local scan history"))

    def _show_about(self, *args):
        about = Adw.AboutDialog(
            application_name="WiFi Analyzer",
            application_icon=APP_ID,
            version=__version__,
            developer_name="Daniel Nylander",
            license_type=Gtk.License.GPL_3_0,
            website="https://www.danielnylander.se",
            issue_url="https://github.com/yeager/wifi-analyzer/issues",
            translator_credits="https://www.transifex.com/danielnylander/wifi-analyzer/",
            developers=["Daniel Nylander"],
            copyright="© 2026 Daniel Nylander",
            comments=_("WiFi Network Analysis Tool"),
        )
        about.add_credit_section(_("Created by"), ["Daniel Nylander"])
        about.add_credit_section(_("With thanks to"), [
            "GTK", "libadwaita", "NetworkManager", "Flatpak", "GNU gettext",
        ])
        about.add_link(_("Project on GitHub"), "https://github.com/yeager/wifi-analyzer")
        about.present(self)


class WifiAnalyzerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        GLib.set_application_name(_("WiFi Analyzer"))
        self._wlc_settings = {}

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = WifiAnalyzerWindow(self)
        win.present()
        # Welcome dialog
        self._wlc_settings = _load_wlc_settings()
        if not self._wlc_settings.get("welcome_shown"):
            self._show_welcome(self.props.active_window or self)


    def do_startup(self):
        Adw.Application.do_startup(self)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *a: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("win.export-csv", ["<Control><Shift>e"])
        self.set_accels_for_action("win.connection-diagnostics", ["<Control>d"])

    def _show_welcome(self, win):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)
        page = Adw.StatusPage()
        page.set_icon_name("network-wireless-symbolic")
        page.set_title(_("Welcome to WiFi Analyzer"))
        page.set_description(_("Analyze WiFi networks.\n\n✓ Scan nearby networks\n✓ Signal strength monitoring\n✓ Channel overlap detection"))
        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)
        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.set_child(box)
        dialog.present(win)

    def _on_welcome_close(self, btn, dialog):
        self._wlc_settings["welcome_shown"] = True
        _save_wlc_settings(self._wlc_settings)
        dialog.close()


def main():
    app = WifiAnalyzerApp()
    app.run()

if __name__ == "__main__":
    main()
