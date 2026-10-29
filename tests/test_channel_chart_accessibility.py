from unittest.mock import Mock

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

from wifi_analyzer.app import ChannelDrawingArea


class TestChannelChartAccessibility:
    @classmethod
    def setup_class(cls):
        Gtk.init()

    def test_chart_is_focusable_and_has_an_accessible_role(self):
        chart = ChannelDrawingArea()

        assert chart.get_focusable()
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

