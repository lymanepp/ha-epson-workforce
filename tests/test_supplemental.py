"""Tests for supplemental-page parsing and the new sensor keys."""

import os
from unittest.mock import MagicMock, patch
import urllib.error

from custom_components.epson_workforce.api import EpsonWorkForceAPI, _parse_wifi_speed
from custom_components.epson_workforce.parser import EpsonHTMLParser

HERE = os.path.dirname(__file__)
FIXTURES_DIR = os.path.join(HERE, "fixtures")


def _fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# parse_dt_dd_page — unit tests against the three real fixture files
# ---------------------------------------------------------------------------


class TestParseDtDdPage:
    """parse_dt_dd_page must extract every key/value pair from the dt/dd markup."""

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
        assert data["B&W Scan"] == "5"
        assert data["Color Scan"] == "0"
        assert data["B&W Copy"] == "5"
        assert data["Color Copy"] == "0"

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
        assert data["IP Address"] == "10.0.1.116"
        assert data["MAC Address"] == "58:05:D9:0C:85:BF"

    def test_nwinfo_wfd_tab_also_parsed(self):
        # The Wi-Fi Direct tab lives in the same page; Connection Method must appear.
        data = EpsonHTMLParser.parse_dt_dd_page(
            _fixture("PRESENTATION-ADVANCED-INFO_NWINFO-TOP.html")
        )
        assert data["Connection Method"] == "Not Set"

    def test_behaviorinfo_hardware_status(self):
        data = EpsonHTMLParser.parse_dt_dd_page(
            _fixture("PRESENTATION-ADVANCED-INFO_BEHAVIORINFO-TOP.html")
        )
        assert data["Scanner"] == "Working normally."
        assert data["Wi-Fi"] == "Working normally."
        assert data["Fax"] == "Working normally."

    def test_empty_html_returns_empty_dict(self):
        assert EpsonHTMLParser.parse_dt_dd_page("<html><body></body></html>") == {}

    def test_no_dt_key_class_ignored(self):
        # A <dt> without class="key" must be silently ignored.
        # A <dt class="key"> without a child <span class="key"> falls back to the dt text.
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
# _parse_wifi_speed helper
# ---------------------------------------------------------------------------


class TestParseWifiSpeed:
    def test_standard_format(self):
        assert _parse_wifi_speed("Wi-Fi-433Mbps") == "433 Mbps"

    def test_with_space(self):
        assert _parse_wifi_speed("Wi-Fi 72 Mbps") == "72 Mbps"

    def test_no_speed_returns_input(self):
        assert _parse_wifi_speed("Not connected") == "Not connected"

    def test_empty_string_returns_none(self):
        assert _parse_wifi_speed("") is None


# ---------------------------------------------------------------------------
# get_sensor_value — new keys, injecting supplemental data directly
# ---------------------------------------------------------------------------


def _api_with_supplemental(mentinfo=None, nwinfo=None, behaviorinfo=None):
    """Return an EpsonWorkForceAPI whose _supplemental is pre-populated."""
    with patch("urllib.request.urlopen", side_effect=Exception("offline")):
        api = EpsonWorkForceAPI("127.0.0.1", "/test")
    api._data = {}  # online enough for get_sensor_value to proceed
    api._supplemental = {}
    if mentinfo is not None:
        api._supplemental["mentinfo"] = mentinfo
    if nwinfo is not None:
        api._supplemental["nwinfo"] = nwinfo
    if behaviorinfo is not None:
        api._supplemental["behaviorinfo"] = behaviorinfo
    return api


class TestNewSensorValues:
    """get_sensor_value returns correct values for every new sensor key."""

    # Page counters
    def test_total_pages(self):
        api = _api_with_supplemental(mentinfo={"Total Number of Pages": "1250"})
        assert api.get_sensor_value("total_pages") == 1250

    def test_bw_pages(self):
        api = _api_with_supplemental(mentinfo={"Total Number of B&W Pages": "993"})
        assert api.get_sensor_value("bw_pages") == 993

    def test_color_pages(self):
        api = _api_with_supplemental(mentinfo={"Total Number of Color Pages": "257"})
        assert api.get_sensor_value("color_pages") == 257

    def test_bw_scans(self):
        api = _api_with_supplemental(mentinfo={"B&W Scan": "5"})
        assert api.get_sensor_value("bw_scans") == 5

    def test_color_scans(self):
        api = _api_with_supplemental(mentinfo={"Color Scan": "0"})
        assert api.get_sensor_value("color_scans") == 0

    def test_first_print_date(self):
        api = _api_with_supplemental(mentinfo={"First Printing Date": "01-21-2026"})
        assert api.get_sensor_value("first_print_date") == "01-21-2026"

    # Extended network
    def test_wifi_speed(self):
        api = _api_with_supplemental(nwinfo={"Connection Status": "Wi-Fi-433Mbps"})
        assert api.get_sensor_value("wifi_speed") == "433 Mbps"

    def test_wifi_channel(self):
        api = _api_with_supplemental(nwinfo={"Channel": "44"})
        assert api.get_sensor_value("wifi_channel") == "44"

    def test_wifi_mode(self):
        api = _api_with_supplemental(nwinfo={"Wi-Fi Mode": "IEEE 802.11 a/n/ac"})
        assert api.get_sensor_value("wifi_mode") == "IEEE 802.11 a/n/ac"

    def test_wifi_security(self):
        api = _api_with_supplemental(nwinfo={"Security Level": "WPA3-SAE(AES)"})
        assert api.get_sensor_value("wifi_security") == "WPA3-SAE(AES)"

    # Hardware status
    def test_wifi_hw_status(self):
        api = _api_with_supplemental(behaviorinfo={"Wi-Fi": "Working normally."})
        assert api.get_sensor_value("wifi_hw_status") == "Working normally."

    def test_scanner_status_falls_back_to_behaviorinfo(self):
        """When the main page has no SCN_STATUS fieldset, scanner_status must
        fall back to the 'Scanner' key in the BEHAVIORINFO supplemental page."""
        api = _api_with_supplemental(behaviorinfo={"Scanner": "Working normally."})
        api._data = {}  # no scanner_status from main page
        assert api.get_sensor_value("scanner_status") == "Working normally."

    def test_scanner_status_main_page_takes_priority(self):
        """If the main page does supply scanner_status, it wins over supplemental."""
        api = _api_with_supplemental(behaviorinfo={"Scanner": "Working normally."})
        api._data = {"scanner_status": "Available"}
        assert api.get_sensor_value("scanner_status") == "Available"

    def test_scanner_status_none_when_no_data_anywhere(self):
        """No main page value and no supplemental → None (sensor not created)."""
        api = _api_with_supplemental()
        api._data = {}
        assert api.get_sensor_value("scanner_status") is None

    # Missing supplemental data → None (sensor won't be created)
    def test_all_new_keys_return_none_when_no_supplemental(self):
        api = _api_with_supplemental()
        for key in (
            "total_pages",
            "bw_pages",
            "color_pages",
            "bw_scans",
            "color_scans",
            "first_print_date",
            "wifi_speed",
            "wifi_channel",
            "wifi_mode",
            "wifi_security",
            "wifi_hw_status",
        ):
            assert api.get_sensor_value(key) is None, f"Expected None for {key!r}"

    def test_page_count_with_comma_thousands(self):
        # Printers with high page counts may format numbers with commas
        api = _api_with_supplemental(mentinfo={"Total Number of Pages": "12,345"})
        assert api.get_sensor_value("total_pages") == 12345

    def test_page_count_non_numeric_returns_none(self):
        api = _api_with_supplemental(mentinfo={"Total Number of Pages": "N/A"})
        assert api.get_sensor_value("total_pages") is None


# ---------------------------------------------------------------------------
# 404 blacklist behavior
# ---------------------------------------------------------------------------


class TestSupplementalFetch404:
    """A 404 on a supplemental path must permanently skip that path."""

    def _make_api_with_responses(self, main_html, supplemental_responses):
        """
        Build an API where the main page succeeds and each supplemental URL
        returns what supplemental_responses dict says (an Exception subclass
        or a string of HTML).
        """
        main_resp = MagicMock()
        main_resp.read.return_value = main_html.encode("utf-8")

        from custom_components.epson_workforce.api import (
            _PATH_BEHAVIORINFO,
            _PATH_MENTINFO,
            _PATH_NWINFO,
        )

        path_map = {
            _PATH_MENTINFO: supplemental_responses.get(
                "mentinfo", Exception("timeout")
            ),
            _PATH_NWINFO: supplemental_responses.get("nwinfo", Exception("timeout")),
            _PATH_BEHAVIORINFO: supplemental_responses.get(
                "behaviorinfo", Exception("timeout")
            ),
        }

        call_count = {"n": 0}

        def fake_urlopen(url, **kwargs):
            # First call is always the main page
            if call_count["n"] == 0:
                call_count["n"] += 1
                ctx = MagicMock()
                ctx.__enter__ = lambda s: main_resp
                ctx.__exit__ = MagicMock(return_value=False)
                return ctx
            call_count["n"] += 1
            for path, result in path_map.items():
                if url.endswith(path):
                    if isinstance(result, BaseException):
                        raise result
                    if isinstance(result, type) and issubclass(result, BaseException):
                        raise result()
                    resp = MagicMock()
                    resp.read.return_value = result.encode("utf-8")
                    ctx = MagicMock()
                    ctx.__enter__ = lambda s: resp
                    ctx.__exit__ = MagicMock(return_value=False)
                    return ctx
            raise Exception("unexpected url")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            api = EpsonWorkForceAPI("127.0.0.1", "/test")
        return api

    def test_404_path_added_to_blacklist(self):
        from custom_components.epson_workforce.api import _PATH_MENTINFO

        err = urllib.error.HTTPError(_PATH_MENTINFO, 404, "Not Found", {}, None)
        api = self._make_api_with_responses(
            "<html><body></body></html>",
            {"mentinfo": err},
        )
        assert _PATH_MENTINFO in api._supplemental_404

    def test_non_404_http_error_not_blacklisted(self):
        from custom_components.epson_workforce.api import _PATH_MENTINFO

        err = urllib.error.HTTPError(_PATH_MENTINFO, 500, "Server Error", {}, None)
        api = self._make_api_with_responses(
            "<html><body></body></html>",
            {"mentinfo": err},
        )
        assert _PATH_MENTINFO not in api._supplemental_404

    def test_timeout_not_blacklisted(self):

        from custom_components.epson_workforce.api import _PATH_MENTINFO

        api = self._make_api_with_responses(
            "<html><body></body></html>",
            {"mentinfo": TimeoutError("timed out")},
        )
        assert _PATH_MENTINFO not in api._supplemental_404

    def test_blacklisted_path_skipped_on_next_update(self):
        from custom_components.epson_workforce.api import _PATH_MENTINFO

        err = urllib.error.HTTPError(_PATH_MENTINFO, 404, "Not Found", {}, None)
        api = self._make_api_with_responses(
            "<html><body></body></html>",
            {"mentinfo": err},
        )
        assert _PATH_MENTINFO in api._supplemental_404

        # On the next update the blacklisted path must not be attempted.
        # We verify by making urlopen raise AssertionError for that path —
        # if it's called, the test fails.
        original_urlopen = __builtins__  # keep reference for main page

        main_resp = MagicMock()
        main_resp.read.return_value = b"<html><body></body></html>"
        call_count = {"n": 0}

        def strict_urlopen(url, **kwargs):
            if call_count["n"] == 0:
                call_count["n"] += 1
                ctx = MagicMock()
                ctx.__enter__ = lambda s: main_resp
                ctx.__exit__ = MagicMock(return_value=False)
                return ctx
            if url.endswith(_PATH_MENTINFO):
                raise AssertionError("blacklisted path was fetched again")
            raise Exception("other supplemental also missing")

        with patch("urllib.request.urlopen", side_effect=strict_urlopen):
            api.update()  # must not raise
