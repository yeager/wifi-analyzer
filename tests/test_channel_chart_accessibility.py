import time
from unittest.mock import Mock, patch

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from wifi_analyzer.app import ChannelDrawingArea, NetworkRow, SignalHistoryDrawingArea


class TestChannelChartAccessibility:
    @classmethod
    def setup_class(cls):
        Gtk.init()

    def test_gobject_cairo_foreign_binding_is_available(self):
        # Gtk.DrawingArea.set_draw_func passes cairo.Context through PyGObject.
        # python3-cairo alone does not install this GObject converter on Debian.
        gi.require_foreign("cairo")

    def test_drawing_area_callback_receives_cairo_context(self):
        chart = ChannelDrawingArea()
        draw_contexts = []
        chart.set_draw_func(lambda _area, context, _width, _height: draw_contexts.append(context))
        window = Gtk.Window()
        window.set_child(chart)
        window.present()

        main_context = GLib.MainContext.default()
        deadline = time.monotonic() + 2
        while not draw_contexts and time.monotonic() < deadline:
            if main_context.pending():
                main_context.iteration(False)
            else:
                time.sleep(0.01)
        window.destroy()

        assert draw_contexts
        assert isinstance(draw_contexts[0], cairo.Context)

    def test_chart_is_focusable_and_has_an_accessible_role(self):
        chart = ChannelDrawingArea()

        assert chart.get_focusable()
        assert chart.get_accessible_role() == Gtk.AccessibleRole.IMG

    def test_signal_history_chart_has_an_image_accessible_role(self):
        chart = SignalHistoryDrawingArea([
            {"scanned_at": "2026-10-30T12:00:00+02:00", "signal_pct": 75},
        ])

        assert chart.get_accessible_role() == Gtk.AccessibleRole.IMG

    def test_arrow_keys_cycle_all_channels_and_enter_filters_them(self):
        chart = ChannelDrawingArea()
        chart.on_channel_selected = Mock(return_value=True)
        chart._announce = Mock()
        chart.set_networks(
            [{"band": "2.4 GHz", "channel": 6}],
            "2.4 GHz",
            selectable_channels=[1, 6, 11],
        )

        assert chart._on_key_pressed(None, Gdk.KEY_Left, 0, 0)
        assert chart.focused_channel == 11
        assert chart._on_key_pressed(None, Gdk.KEY_Right, 0, 0)
        assert chart.focused_channel == 1
        assert chart._on_key_pressed(None, Gdk.KEY_Right, 0, 0)
        assert chart.focused_channel == 6
        assert chart._on_key_pressed(None, Gdk.KEY_Return, 0, 0)
        chart.on_channel_selected.assert_called_once_with(6)
        chart._announce.assert_called_with("Filtering access points by channel 6.")

    def test_enter_announces_when_the_channel_filter_is_cleared(self):
        chart = ChannelDrawingArea()
        chart.selectable_channels = [1]
        chart.focused_channel = 1
        chart.on_channel_selected = Mock(return_value=False)
        chart._announce = Mock()

        assert chart._on_key_pressed(None, Gdk.KEY_space, 0, 0)
        chart._announce.assert_called_once_with("Channel filter cleared.")

    def test_mouse_selection_becomes_the_keyboard_navigation_origin(self):
        chart = ChannelDrawingArea()
        chart.on_channel_selected = Mock()
        chart.set_networks(
            [
                {"band": "2.4 GHz", "channel": 1},
                {"band": "2.4 GHz", "channel": 6},
                {"band": "2.4 GHz", "channel": 11},
            ],
            "2.4 GHz",
        )

        with (
            patch.object(ChannelDrawingArea, "get_allocated_width", return_value=500),
            patch.object(ChannelDrawingArea, "get_allocated_height", return_value=220),
            patch.object(ChannelDrawingArea, "grab_focus", return_value=True) as grab_focus,
        ):
            chart._on_click(None, 1, 265, 100)

        assert chart.focused_channel == 6
        chart.on_channel_selected.assert_called_once_with(6)
        grab_focus.assert_called_once_with()
        assert chart._on_key_pressed(None, Gdk.KEY_Right, 0, 0)
        assert chart.focused_channel == 11

    def test_home_and_end_jump_to_the_first_and_last_available_channels(self):
        chart = ChannelDrawingArea()
        chart.set_networks([], "5 GHz", selectable_channels=[36, 40, 44, 149])
        chart._announce = Mock()

        assert chart._on_key_pressed(None, Gdk.KEY_Home, 0, 0)
        assert chart.focused_channel == 36
        assert chart._announce.call_args.args[0].startswith("Channel 36.")

        assert chart._on_key_pressed(None, Gdk.KEY_End, 0, 0)
        assert chart.focused_channel == 149
        assert chart._announce.call_args.args[0].startswith("Channel 149.")

    def test_scan_error_row_shows_guidance_without_fake_signal_metrics(self):
        row = NetworkRow({
            "ssid": "Error: no WiFi device found",
            "signal_pct": 0,
            "error_code": "no-device",
        })
        labels = []

        def collect_labels(widget):
            if isinstance(widget, Gtk.Label):
                labels.append(widget.get_text())
            child = widget.get_first_child() if hasattr(widget, "get_first_child") else None
            while child:
                collect_labels(child)
                child = child.get_next_sibling()

        collect_labels(row)

        assert "No Wi-Fi device found" in labels
        assert any("Enable Wi-Fi" in label and "adapter driver" in label for label in labels)
        assert not any("0%" in label or "0 dBm" in label or "Open" == label for label in labels)

