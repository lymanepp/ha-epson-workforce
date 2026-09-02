"""Tests for supplemental-page parsing and entity registry defaults."""

from __future__ import annotations

import os

from custom_components.epson_workforce.parser import EpsonHTMLParser

HERE = os.path.dirname(__file__)
FIXTURES_DIR = os.path.join(HERE, "fixtures")


def _fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# parse_dt_dd_page
# ---------------------------------------------------------------------------


class TestParseDtDdPage:
    def test_mentinfo_printing_totals(self):
        data = EpsonHTMLParser.parse_dt_dd_page(
            _fixture("PRESENTATION-ADVANCED-INFO_MENTINFO-TOP.html")
        )
        assert data["First Printing Date"] == "01-21-2026"
        assert data["Total Number of Pages"] == "1250"
        assert data["Total Number of B&W Pages"] == "993"
        assert data["Total Number of Color Pages"] == "257"

    def test_mentinfo_function_counters(self):
        data = EpsonHTMLParser.parse_dt_dd_page(
            _fixture("PRESENTATION-ADVANCED-INFO_MENTINFO-TOP.html")
        )
        assert data["B&W Copy"] == "5"
        assert data["Color Copy"] == "0"
        assert data["B&W Scan"] == "5"
        assert data["Color Scan"] == "0"

    def test_nwinfo_connection_fields(self):
        data = EpsonHTMLParser.parse_dt_dd_page(
            _fixture("PRESENTATION-ADVANCED-INFO_NWINFO-TOP.html")
        )
        assert data["Connection Status"] == "Wi-Fi-433Mbps"
        assert data["Signal Strength"] == "Excellent"
        assert data["SSID"] == "CHAOS PRIVATE"
        assert data["Channel"] == "44"
        assert data["Security Level"] == "WPA3-SAE(AES)"
        assert data["Wi-Fi Mode"] == "IEEE 802.11 a/n/ac"

    def test_behaviorinfo_raw_has_periods(self):
        """parse_dt_dd_page returns raw values — periods are still present."""
        data = EpsonHTMLParser.parse_dt_dd_page(
            _fixture("PRESENTATION-ADVANCED-INFO_BEHAVIORINFO-TOP.html")
        )
        assert data["Scanner"] == "Working normally."
        assert data["Wi-Fi"] == "Working normally."
        assert data["Fax"] == "Working normally."

    def test_empty_html_returns_empty_dict(self):
        assert EpsonHTMLParser.parse_dt_dd_page("<html><body></body></html>") == {}

    def test_dt_without_key_class_ignored(self):
        html = """
        <dl>
          <dt class="key"><span class="key">Label&nbsp;:</span></dt><dd class="value">val</dd>
          <dt class="other"><span class="key">Skip&nbsp;:</span></dt><dd>ignored</dd>
          <dt class="key">NoSpan&nbsp;:</dt><dd class="value">fallback</dd>
        </dl>
        """
        data = EpsonHTMLParser.parse_dt_dd_page(html)
        assert data["Label"] == "val"
        assert "Skip" not in data
        assert data["NoSpan"] == "fallback"


# ---------------------------------------------------------------------------
# parse_behaviorinfo_page — strips trailing periods
# ---------------------------------------------------------------------------


class TestParseBehaviorinfoPage:
    def test_periods_stripped(self):
        data = EpsonHTMLParser.parse_behaviorinfo_page(
            _fixture("PRESENTATION-ADVANCED-INFO_BEHAVIORINFO-TOP.html")
        )
        assert data["Scanner"] == "Working normally"
        assert data["Wi-Fi"] == "Working normally"
        assert data["Fax"] == "Working normally"

    def test_none_values_handled(self):
        """parse_behaviorinfo_page must not raise if _clean_status returns None."""
        html = "<dl><dt class='key'><span class='key'>Empty&nbsp;:</span></dt><dd class='value'></dd></dl>"
        data = EpsonHTMLParser.parse_behaviorinfo_page(html)
        assert data.get("Empty") is None


# ---------------------------------------------------------------------------
# entity_registry_enabled_default
# ---------------------------------------------------------------------------


class TestEntityRegistryEnabledDefault:
    ENABLED_BY_DEFAULT = {
        "ink_bk",
        "ink_pb",
        "ink_gy",
        "ink_m",
        "ink_c",
        "ink_y",
        "ink_lc",
        "ink_lm",
        "clean",
        "printer_status",
        "scanner_status",
        "fax_status",
        "total_pages",
        "bw_pages",
        "color_pages",
        "bw_copies",
        "color_copies",
        "bw_scans",
        "color_scans",
    }

    DISABLED_BY_DEFAULT = {
        "ip_address",
        "signal_strength",
        "ssid",
        "wifi_direct_connection_method",
        "wifi_speed",
        "wifi_channel",
        "wifi_mode",
        "wifi_security",
        "first_print_date",
        "wifi_hw_status",
    }

    def test_enabled_sensors(self):
        from custom_components.epson_workforce.sensor import SENSOR_TYPES

        for desc in SENSOR_TYPES:
            if desc.key in self.ENABLED_BY_DEFAULT:
                assert (
                    desc.entity_registry_enabled_default is True
                ), f"{desc.key!r} should be enabled by default"

    def test_disabled_sensors(self):
        from custom_components.epson_workforce.sensor import SENSOR_TYPES

        for desc in SENSOR_TYPES:
            if desc.key in self.DISABLED_BY_DEFAULT:
                assert (
                    desc.entity_registry_enabled_default is False
                ), f"{desc.key!r} should be disabled by default"

    def test_all_keys_classified(self):
        from custom_components.epson_workforce.sensor import SENSOR_TYPES

        all_keys = {d.key for d in SENSOR_TYPES}
        classified = self.ENABLED_BY_DEFAULT | self.DISABLED_BY_DEFAULT
        assert not (all_keys - classified), f"Unclassified: {all_keys - classified}"
        assert not (self.ENABLED_BY_DEFAULT & self.DISABLED_BY_DEFAULT)


# ---------------------------------------------------------------------------
# state_class
# ---------------------------------------------------------------------------


class TestSensorStateClass:
    """Percentage sensors need a state class to get long-term statistics."""

    PERCENTAGE_KEYS = {
        "ink_bk",
        "ink_pb",
        "ink_gy",
        "ink_m",
        "ink_c",
        "ink_y",
        "ink_lc",
        "ink_lm",
        "clean",
    }

    def test_percentage_sensors_are_measurements(self):
        from homeassistant.components.sensor import SensorStateClass

        from custom_components.epson_workforce.sensor import SENSOR_TYPES

        for desc in SENSOR_TYPES:
            if desc.key in self.PERCENTAGE_KEYS:
                assert (
                    desc.state_class == SensorStateClass.MEASUREMENT
                ), f"{desc.key!r} should be a measurement"

    def test_percentage_keys_match_sensor_types(self):
        from homeassistant.const import PERCENTAGE

        from custom_components.epson_workforce.sensor import SENSOR_TYPES

        actual = {
            desc.key
            for desc in SENSOR_TYPES
            if desc.native_unit_of_measurement == PERCENTAGE
        }
        assert actual == self.PERCENTAGE_KEYS
