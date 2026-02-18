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
    if freq >= 5000:
        return (freq - 5000) // 5
    return 0

def parse_nmcli():
    """Parse nmcli dev wifi list output."""
    networks = []
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,BSSID,FREQ,SIGNAL,SECURITY,CHAN,BARS,MODE", "dev", "wifi", "list", "--rescan", "yes"],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # nmcli -t uses : as separator but BSSID contains colons
            # Format: SSID:BSSID:FREQ:SIGNAL:SECURITY:CHAN:BARS:MODE
            # BSSID is like AA\:BB\:CC\:DD\:EE\:FF (escaped)
            parts = line.replace("\\:", "§").split(":")
            parts = [p.replace("§", ":") for p in parts]
            if len(parts) >= 6:
                ssid = parts[0] or _("<Hidden>")
                bssid = parts[1]
                try:
                    freq = int(parts[2].strip().split()[0])
                except (ValueError, IndexError):
                    freq = 0
                try:
                    signal_pct = int(parts[3])
                except ValueError:
                    signal_pct = 0
                security = parts[4] if len(parts) > 4 else ""
                try:
                    channel = int(parts[5])
                except (ValueError, IndexError):
                    channel = freq_to_channel(freq)
                # Convert signal % to approximate dBm
                dbm = int(signal_pct / 2 - 100) if signal_pct else -100
                networks.append({
                    "ssid": ssid, "bssid": bssid, "freq": freq, "channel": channel,
                    "signal_pct": signal_pct, "dbm": dbm, "security": security,
                    "band": "5 GHz" if freq >= 5000 else "2.4 GHz"
                })
    except Exception as e:
        networks.append({"ssid": f"Error: {e}", "bssid": "", "freq": 0, "channel": 0,
                         "signal_pct": 0, "dbm": -100, "security": "", "band": ""})
    return networks


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
        bw = 2.5 if self.band_filter == "2.4 GHz" else 2.0  # channel bandwidth

        for i, net in enumerate(filtered):
            color = colors[i % len(colors)]
            cr.set_source_rgba(*color, 0.3)
            cr.set_line_width(2)

            center = net["channel"]
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
        detail = f"Ch {net['channel']} · {net['band']} · {net['dbm']} dBm · {net['security'] or 'Open'}"
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

        # Band selector
        band_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        band_box.set_margin_start(12); band_box.set_margin_end(12); band_box.set_margin_top(8)
        self.band_24_btn = Gtk.ToggleButton(label="2.4 GHz", active=True)
        self.band_5_btn = Gtk.ToggleButton(label="5 GHz", group=self.band_24_btn)
        self.band_24_btn.connect("toggled", self._on_band_toggle)
        self.band_5_btn.connect("toggled", self._on_band_toggle)
        band_box.append(self.band_24_btn)
        band_box.append(self.band_5_btn)
        main_box.append(band_box)

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
        return "2.4 GHz" if self.band_24_btn.get_active() else "5 GHz"

    def _on_band_toggle(self, btn):
        self._update_ui()

    def _scan(self):
        self._set_status(_("Scanning..."))
        def worker():
            nets = parse_nmcli()
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
        filtered = [n for n in self.networks if n["band"] == band]
        for net in filtered:
            self.listbox.append(NetworkRow(net))
        # Update chart
        self.channel_chart.set_networks(self.networks, band)

    def _show_about(self, *args):
        about = Adw.AboutDialog(
            application_name="WiFi Analyzer",
            application_icon=APP_ID,
            version="0.1.0",
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

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = WifiAnalyzerWindow(self)
        win.present()

    def do_startup(self):
        Adw.Application.do_startup(self)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *a: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])


def main():
    app = WifiAnalyzerApp()
    app.run()

if __name__ == "__main__":
    main()
