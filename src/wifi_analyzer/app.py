"""WiFi Analyzer — WiFi Network Analysis Tool."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, Pango
import subprocess, threading, re, gettext, math, cairo
from datetime import datetime

APP_ID = "io.github.yeager.WifiAnalyzer"
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
    for ch, f in {**CHANNEL_FREQ_24, **CHANNEL_FREQ_5}.items():
        if f == freq:
            return ch
    if 2412 <= freq <= 2484:
        return (freq - 2407) // 5
    if 5925 <= freq <= 7125:
        return (freq - 5950) // 5
    if freq >= 5000:
        return (freq - 5000) // 5
    return 0


def band_for_frequency(freq):
    """Return the Wi-Fi band containing *freq*, in MHz."""
    if 2400 <= freq < 2500:
        return "2.4 GHz"
    if 5925 <= freq <= 7125:
        return "6 GHz"
    if 5000 <= freq < 5925:
        return "5 GHz"
    return ""


def channel_width_mhz(freq):
    """Return the width that can safely be inferred from NetworkManager data.

    NetworkManager's AccessPoint D-Bus interface exposes a centre frequency but
    no channel-width property.  A 20 MHz primary channel is therefore the only
    non-speculative value we can display.  Keep the source alongside the value
    so the UI does not present an estimate as a measurement.
    """
    return 20 if band_for_frequency(freq) else 0


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

NM_BUS_NAME = "org.freedesktop.NetworkManager"
NM_OBJ_PATH = "/org/freedesktop/NetworkManager"
NM_IFACE = "org.freedesktop.NetworkManager"
NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
NM_WIRELESS_IFACE = "org.freedesktop.NetworkManager.Device.Wireless"
NM_AP_IFACE = "org.freedesktop.NetworkManager.AccessPoint"
NM_DEVICE_TYPE_WIFI = 2

def _security_string(flags, wpa_flags, rsn_flags):
    if rsn_flags & 0x400:
        return "WPA3"
    if rsn_flags:
        if rsn_flags & 0x200:
            return "WPA2 Enterprise"
        return "WPA2"
    if wpa_flags:
        if wpa_flags & 0x200:
            return "WPA Enterprise"
        return "WPA1"
    if flags & 0x1:
        return "WEP"
    return ""

def _find_wifi_device_path(nm_proxy):
    devices = nm_proxy.call_sync(
        "GetDevices", None, Gio.DBusCallFlags.NONE, -1, None
    ).unpack()[0]
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
            return path
    return None


def scan_networks_dbus():
    """Scan WiFi networks via NetworkManager D-Bus"""
    networks = []
    regulatory_ranges = local_regulatory_ranges()
    try:
        nm_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            NM_BUS_NAME, NM_OBJ_PATH, NM_IFACE, None
        )
        wifi_path = _find_wifi_device_path(nm_proxy)
        if not wifi_path:
            networks.append({"ssid": _("Error: no WiFi device found"), "bssid": "", "freq": 0,
                             "channel": 0, "signal_pct": 0, "dbm": -100, "security": "", "band": ""})
            return networks

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
            security = _security_string(flags, wpa_flags, rsn_flags)
            channel = freq_to_channel(freq)
            band = band_for_frequency(freq)
            width_mhz = channel_width_mhz(freq)
            # Convert signal % to approximate dBm
            dbm = int(signal_pct / 2 - 100) if signal_pct else -100

            networks.append({
                "ssid": ssid, "bssid": bssid, "freq": freq, "channel": channel,
                "signal_pct": signal_pct, "dbm": dbm, "security": security,
                "band": band, "width_mhz": width_mhz,
                "channel_status": channel_status(freq, channel, regulatory_ranges),
            })
    except GLib.Error as e:
        networks.append({"ssid": f"Error: {e}", "bssid": "", "freq": 0, "channel": 0,
                         "signal_pct": 0, "dbm": -100, "security": "", "band": ""})
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
        self.set_draw_func(self._draw)
        self.set_content_height(220)

    def set_networks(self, networks, band="2.4 GHz"):
        self.networks = networks
        self.band_filter = band
        self.queue_draw()

    def _draw(self, area, cr, width, height):
        # Background
        cr.set_source_rgb(0.15, 0.15, 0.18)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        filtered = [n for n in self.networks if n["band"] == self.band_filter and n["channel"] > 0]
        if not filtered:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(14)
            cr.move_to(width / 2 - 60, height / 2)
            cr.show_text(_("No networks found"))
            return

        margin_left, margin_right, margin_top, margin_bottom = 50, 20, 20, 40
        plot_w = width - margin_left - margin_right
        plot_h = height - margin_top - margin_bottom

        if self.band_filter == "2.4 GHz":
            ch_min, ch_max = 0, 14
        else:
            channels = sorted(set(n["channel"] for n in filtered))
            ch_min = min(channels) - 4 if channels else 30
            ch_max = max(channels) + 4 if channels else 170

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
            cr.set_font_size(10)
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
            cr.set_font_size(10)
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
            cr.set_font_size(9)
            label = net["ssid"][:18]
            tx = ch_to_x(center)
            cr.move_to(tx - len(label) * 2.5, peak_y - 6)
            cr.show_text(label)


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
        vbox.append(ssid_label)
        width = net.get("width_mhz", 0)
        width_detail = f" · {width} MHz estimated" if width else ""
        dfs_detail = f" · {net['channel_status']}" if net.get("channel_status") else ""
        detail = (f"Ch {net['channel']} · {net['band']}{width_detail} · "
                  f"{net['dbm']} dBm · {net['security'] or 'Open'}{dfs_detail}")
        sub = Gtk.Label(label=detail, xalign=0)
        sub.add_css_class("dim-label")
        vbox.append(sub)
        box.append(vbox)

        # Signal bar
        pct_label = Gtk.Label(label=f"{net['signal_pct']}%")
        pct_label.add_css_class("numeric")
        box.append(pct_label)

        self.set_child(box)


class WifiAnalyzerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="WiFi Analyzer", default_width=950, default_height=750)
        self.networks = []
        self.dark_mode = False

        header = Adw.HeaderBar()
        # Theme toggle
        theme_btn = Gtk.Button(icon_name="display-brightness-symbolic", tooltip_text=_("Toggle theme"))
        theme_btn.connect("clicked", self._toggle_theme)
        header.pack_end(theme_btn)
        # Menu
        menu = Gio.Menu()
        menu.append(_("About"), "win.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)
        # Refresh
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Scan"))
        refresh_btn.connect("clicked", lambda b: self._scan())
        header.pack_end(refresh_btn)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._show_about)
        self.add_action(about_action)

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
        self.signal_threshold.set_value(-100)
        self.signal_threshold.set_tooltip_text(_("Only show access points at or above this estimated dBm value"))
        self.signal_threshold.connect("value-changed", self._on_filter_changed)
        filter_box.append(self.signal_threshold)

        security_label = Gtk.Label(label=_("Security"))
        filter_box.append(security_label)
        self.security_filter = Gtk.DropDown.new_from_strings([
            _("All security"), "Open", "WEP", "WPA1", "WPA2", "WPA2 Enterprise", "WPA3",
        ])
        self.security_filter.connect("notify::selected", self._on_filter_changed)
        filter_box.append(self.security_filter)

        self.hidden_filter = Gtk.CheckButton(label=_("Hidden SSIDs only"))
        self.hidden_filter.connect("toggled", self._on_filter_changed)
        filter_box.append(self.hidden_filter)
        main_box.append(filter_box)

        # Channel overlap visualization
        frame = Gtk.Frame()
        frame.set_margin_start(12); frame.set_margin_end(12); frame.set_margin_top(8)
        self.channel_chart = ChannelDrawingArea()
        frame.set_child(self.channel_chart)
        main_box.append(frame)

        # Network list
        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.set_margin_start(12); sw.set_margin_end(12); sw.set_margin_top(8); sw.set_margin_bottom(4)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        sw.set_child(self.listbox)
        main_box.append(sw)

        # Status bar
        self.statusbar = Gtk.Label(label=_("Ready — click Scan"), xalign=0)
        self.statusbar.set_margin_start(12); self.statusbar.set_margin_end(12)
        self.statusbar.set_margin_top(4); self.statusbar.set_margin_bottom(4)
        self.statusbar.add_css_class("dim-label")
        main_box.append(self.statusbar)

        self.set_content(main_box)
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

    def _scan(self):
        self._set_status(_("Scanning..."))
        def worker():
            nets = scan_networks_dbus()
            GLib.idle_add(self._on_scan_done, nets)
        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, nets):
        self.networks = sorted(nets, key=lambda n: n["signal_pct"], reverse=True)
        self._update_ui()
        self._set_status(f"Found {len(self.networks)} networks")

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
                    and n["dbm"] >= self.signal_threshold.get_value_as_int()
                    and (selected_security == _("All security") or n["security"] == selected_security)
                    and (not self.hidden_filter.get_active() or n["ssid"] == _("<Hidden>"))
                    and network_matches_query(n, self.search_entry.get_text())]
        for net in filtered:
            self.listbox.append(NetworkRow(net))
        # Update chart
        self.channel_chart.set_networks(filtered, band)

    def _show_about(self, *args):
        about = Adw.AboutDialog(
            application_name="WiFi Analyzer",
            application_icon=APP_ID,
            version="0.1.5",
            developer_name="Daniel Nylander",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/yeager/wifi-analyzer",
            issue_url="https://github.com/yeager/wifi-analyzer/issues",
            translator_credits="https://www.transifex.com/danielnylander/wifi-analyzer/",
            developers=["Daniel Nylander"],
            copyright="© 2026 Daniel Nylander",
            comments=_("WiFi Network Analysis Tool"),
        )
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
