"""Tests for EpsonCoordinator and _build_data."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.epson_workforce.coordinator import (
    EpsonCoordinator,
    _build_data,
    _looks_like_main_page,
    _parse_wifi_speed,
    _to_int,
)
from custom_components.epson_workforce.parser import EpsonHTMLParser

# ---------------------------------------------------------------------------
# _to_int
# ---------------------------------------------------------------------------


class TestToInt:
    def test_plain_number(self):
        assert _to_int("1250") == 1250

    def test_comma_thousands(self):
        assert _to_int("12,345") == 12345

    def test_none_returns_none(self):
        assert _to_int(None) is None

    def test_non_numeric_returns_none(self):
        assert _to_int("N/A") is None


# ---------------------------------------------------------------------------
# _parse_wifi_speed
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
# _build_data — the core data transformation
# ---------------------------------------------------------------------------


def _raw(overrides=None):
    base = {
        "model": "Epson ET-4950 Series",
        "name": "EPSON0C85BF",
        "mac_address": "58:05:D9:0C:85:BF",
        "ip_address": "10.0.1.116",
        "printer_status": "Available",
        "scanner_status": None,
        "inks": {"BK": 57, "C": 81, "M": 81, "Y": 81},
        "maintenance_box": 78,
        "network": {
            "Signal Strength": "Excellent",
            "SSID": "CHAOS PRIVATE",
            "Connection Status": "Wi-Fi-433Mbps",
        },
        "wifi_direct": {"Connection Method": "Not Set"},
    }
    if overrides:
        base.update(overrides)
    return base


def _sup(overrides=None):
    base = {
        "mentinfo": {
            "Total Number of Pages": "1250",
            "Total Number of B&W Pages": "993",
            "Total Number of Color Pages": "257",
            "B&W Copy": "5",
            "Color Copy": "0",
            "B&W Scan": "5",
            "Color Scan": "0",
            "First Printing Date": "01-21-2026",
        },
        "nwinfo": {
            "Connection Status": "Wi-Fi-433Mbps",
            "Signal Strength": "Excellent",
            "SSID": "CHAOS PRIVATE",
            "Connection Method": "Not Set",
            "Channel": "44",
            "Wi-Fi Mode": "IEEE 802.11 a/n/ac",
            "Security Level": "WPA3-SAE(AES)",
        },
        "behaviorinfo": {
            "Scanner": "Working normally",
            "Fax": "Working normally",
            "Wi-Fi": "Working normally",
        },
    }
    if overrides:
        base.update(overrides)
    return base


class TestBuildData:
    def test_ink_keys_prefixed(self):
        data = _build_data(_raw(), {})
        assert "ink_bk" in data
        assert "ink_c" in data
        assert "BK" not in data

    def test_ink_values_correct(self):
        data = _build_data(_raw(), {})
        assert data["ink_bk"] == 57
        assert data["ink_c"] == 81

    def test_maintenance_box(self):
        data = _build_data(_raw(), {})
        assert data["clean"] == 78

    def test_printer_status(self):
        data = _build_data(_raw(), {})
        assert data["printer_status"] == "Available"

    def test_scanner_status_from_behaviorinfo(self):
        """When main page has no scanner_status, falls back to behaviorinfo."""
        data = _build_data(_raw({"scanner_status": None}), _sup())
        assert data["scanner_status"] == "Working normally"

    def test_scanner_status_main_page_wins(self):
        raw = _raw({"scanner_status": "Available"})
        data = _build_data(raw, _sup())
        assert data["scanner_status"] == "Available"

    def test_fax_status(self):
        data = _build_data(_raw(), _sup())
        assert data["fax_status"] == "Working normally"

    def test_network_fields(self):
        data = _build_data(_raw(), {})
        assert data["ip_address"] == "10.0.1.116"
        assert data["signal_strength"] == "Excellent"
        assert data["ssid"] == "CHAOS PRIVATE"
        assert data["wifi_direct_connection_method"] == "Not Set"

    def test_network_fields_fall_back_to_english_supplemental_page(self):
        raw = _raw(
            {
                "network": {"Signaalsterkte": "Uitstekend", "SSID": "CHAOS PRIVATE"},
                "wifi_direct": {"Verbindingsmethode": "Niet ingesteld"},
            }
        )
        data = _build_data(raw, _sup())
        assert data["signal_strength"] == "Excellent"
        assert data["ssid"] == "CHAOS PRIVATE"
        assert data["wifi_direct_connection_method"] == "Not Set"

    def test_page_counters(self):
        data = _build_data(_raw(), _sup())
        assert data["total_pages"] == 1250
        assert data["bw_pages"] == 993
        assert data["color_pages"] == 257
        assert data["bw_copies"] == 5
        assert data["color_copies"] == 0
        assert data["bw_scans"] == 5
        assert data["color_scans"] == 0
        assert data["first_print_date"] == "01-21-2026"

    def test_wifi_speed_parsed(self):
        data = _build_data(_raw(), _sup())
        assert data["wifi_speed"] == "433 Mbps"

    def test_wifi_channel(self):
        data = _build_data(_raw(), _sup())
        assert data["wifi_channel"] == "44"

    def test_none_values_excluded(self):
        """Keys with None values must not appear in output — their absence
        is what prevents entity creation for unsupported sensors."""
        data = _build_data(_raw({"scanner_status": None}), {})
        assert "scanner_status" not in data
        assert "fax_status" not in data

    def test_device_identity_keys(self):
        data = _build_data(_raw(), {})
        assert data["_model"] == "Epson ET-4950 Series"
        assert data["_mac"] == "58:05:D9:0C:85:BF"
        assert data["_name"] == "EPSON0C85BF"

    def test_no_supplemental(self):
        """All supplemental sensors absent when sup is empty — no KeyError."""
        data = _build_data(_raw(), {})
        for key in (
            "total_pages",
            "bw_pages",
            "wifi_channel",
            "wifi_speed",
            "fax_status",
            "wifi_hw_status",
        ):
            assert key not in data

    def test_empty_string_network_values_excluded(self):
        """Empty strings from network table must not create sensors."""
        raw = _raw({"network": {"Signal Strength": "", "SSID": "MyNet"}})
        data = _build_data(raw, {})
        assert "signal_strength" not in data
        assert data["ssid"] == "MyNet"


# ---------------------------------------------------------------------------
# Main-page validation
# ---------------------------------------------------------------------------


class TestMainPageValidation:
    @pytest.mark.parametrize(
        "filename",
        [
            "ET-16500.html",
            "ET-4950.HTML",
            "ET-8500.html",
            "L6270.html",
            "WF-2930.html",
            "WF-3540.html",
            "WF-7720.html",
            "WF-7840.html",
            "XP-2205.html",
        ],
    )
    def test_known_main_pages_are_recognized(self, filename):
        html = (Path(__file__).parent / "fixtures" / filename).read_text(
            encoding="utf-8"
        )
        assert _looks_like_main_page(EpsonHTMLParser(html).parse())

    def test_generic_page_is_rejected(self):
        html = "<html><title>Default Page</title><body>Welcome</body></html>"
        assert not _looks_like_main_page(EpsonHTMLParser(html).parse())


# ---------------------------------------------------------------------------
# EpsonCoordinator — fetch behaviour
# ---------------------------------------------------------------------------


def _make_coordinator(hass):
    return EpsonCoordinator(hass, "10.0.1.116")


class TestCoordinatorFetch:
    @pytest.fixture
    def hass(self):
        h = MagicMock()
        h.data = {}
        return h

    def _patch_sessions(self, session):
        """Route the dedicated Web Config session factory to one mock."""
        return patch(
            "custom_components.epson_workforce.coordinator.async_create_clientsession",
            return_value=session,
        )

    def _mock_session(self, responses):
        """Return a mock session with optional per-scheme responses."""
        missing = object()

        def fake_get(url, **kwargs):
            scheme = url.split(":", 1)[0]
            path = "/" + url.split("/", 3)[3]
            response = responses.get((scheme, path), responses.get(path, missing))
            if response is missing:
                raise AssertionError(f"Unexpected URL: {url}")
            if isinstance(response, Exception):
                raise response

            status, html, *final_scheme_override = response
            final_scheme = final_scheme_override[0] if final_scheme_override else scheme
            resp = MagicMock()
            resp.status = status
            resp.url = MagicMock()
            resp.url.scheme = final_scheme
            if status != 200:
                resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
                    MagicMock(), MagicMock(), status=status
                )
            else:
                resp.raise_for_status = MagicMock()
            resp.text = AsyncMock(return_value=html)
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=resp)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        session = MagicMock()
        session.get = MagicMock(side_effect=fake_get)
        return session

    @pytest.mark.asyncio
    async def test_404_supplemental_blacklisted(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _PATH_MAIN,
            _PATH_MENTINFO,
        )

        coordinator = _make_coordinator(hass)

        main_html = (
            "<html><head><title>ET-4950 Series</title></head><body>"
            "<fieldset id='PRT_STATUS'><ul><li>Available.</li></ul></fieldset>"
            "</body></html>"
        )

        responses = {
            _PATH_MAIN: (200, main_html),
            _PATH_MENTINFO: (404, ""),
        }

        with self._patch_sessions(self._mock_session(responses)):
            await coordinator._async_update_data()

        assert _PATH_MENTINFO in coordinator._supplemental_404

    @pytest.mark.asyncio
    async def test_main_page_failure_raises(self, hass):
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.epson_workforce.coordinator import _PATH_MAIN

        coordinator = _make_coordinator(hass)

        responses = {_PATH_MAIN: (503, "")}

        with (
            self._patch_sessions(self._mock_session(responses)),
            pytest.raises(UpdateFailed),
        ):
            await coordinator._async_update_data()

    # --- English-language cookie for the supplemental pages ---

    _NL_MAIN_HTML = (
        "<html><head><title>XP-4200 Series</title></head><body>"
        "<fieldset id='PRT_STATUS'><ul><li>Beschikbaar.</li></ul></fieldset>"
        "</body></html>"
    )

    @pytest.mark.asyncio
    async def test_cookie_sent_for_supplemental_pages_only(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _ENGLISH_LANG_COOKIE,
            _PATH_BEHAVIORINFO,
            _PATH_MAIN,
            _PATH_MENTINFO,
            _PATH_NWINFO,
        )

        coordinator = _make_coordinator(hass)
        session = self._mock_session(
            {
                _PATH_MAIN: (200, self._NL_MAIN_HTML, "https"),
                _PATH_MENTINFO: (200, "<dl></dl>"),
                _PATH_NWINFO: (200, "<dl></dl>"),
                _PATH_BEHAVIORINFO: (200, "<dl></dl>"),
            }
        )

        with self._patch_sessions(session):
            await coordinator._async_update_data()

        calls = {
            call.args[0].split("/PRESENTATION", 1)[-1]: (
                call.args[0],
                call.kwargs.get("headers"),
            )
            for call in session.get.call_args_list
        }
        assert len(calls) == 4
        for path in (_PATH_MENTINFO, _PATH_NWINFO, _PATH_BEHAVIORINFO):
            url, headers = calls[path.split("/PRESENTATION", 1)[-1]]
            assert headers == _ENGLISH_LANG_COOKIE, f"{path} needs the cookie"
            # Requested over HTTPS directly; aiohttp would drop the Cookie
            # header across the printer's HTTP-to-HTTPS redirect.
            assert url.startswith("https://"), f"{path} must not rely on a redirect"
        # The main page keeps the printer's own language for its status strings.
        main_url, main_headers = calls[_PATH_MAIN.split("/PRESENTATION", 1)[-1]]
        assert main_headers is None
        assert main_url.startswith("http://")
        assert coordinator._base_url == "https://10.0.1.116"

    @pytest.mark.asyncio
    async def test_http_is_used_when_https_serves_default_page(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _PATH_BEHAVIORINFO,
            _PATH_MAIN,
            _PATH_MENTINFO,
            _PATH_NWINFO,
        )

        coordinator = _make_coordinator(hass)
        session = self._mock_session(
            {
                ("http", _PATH_MAIN): (200, self._NL_MAIN_HTML),
                ("https", _PATH_MAIN): (
                    200,
                    "<html><title>Default Page</title><body>Welcome</body></html>",
                ),
                _PATH_MENTINFO: (404, ""),
                _PATH_NWINFO: (404, ""),
                _PATH_BEHAVIORINFO: (404, ""),
            }
        )

        with self._patch_sessions(session):
            await coordinator._async_update_data()
            first_poll = [call.args[0] for call in session.get.call_args_list]
            session.get.reset_mock()
            await coordinator._async_update_data()

        assert all(url.startswith("http://") for url in first_poll)
        assert coordinator._base_url == "http://10.0.1.116"
        assert [call.args[0] for call in session.get.call_args_list] == [
            "http://10.0.1.116" + _PATH_MAIN
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "http_response",
        [
            pytest.param(
                aiohttp.ClientConnectionError("HTTP unavailable"),
                id="connection-error",
            ),
            pytest.param((503, ""), id="http-error"),
            pytest.param(
                (
                    200,
                    "<html><title>Default Page</title><body>Welcome</body></html>",
                ),
                id="invalid-page",
            ),
        ],
    )
    async def test_http_probe_failure_falls_back_to_https(self, hass, http_response):
        from custom_components.epson_workforce.coordinator import (
            _PATH_BEHAVIORINFO,
            _PATH_MAIN,
            _PATH_MENTINFO,
            _PATH_NWINFO,
        )

        coordinator = _make_coordinator(hass)
        session = self._mock_session(
            {
                ("http", _PATH_MAIN): http_response,
                ("https", _PATH_MAIN): (200, self._NL_MAIN_HTML),
                _PATH_MENTINFO: (404, ""),
                _PATH_NWINFO: (404, ""),
                _PATH_BEHAVIORINFO: (404, ""),
            }
        )

        with self._patch_sessions(session):
            await coordinator._async_update_data()

        assert [call.args[0] for call in session.get.call_args_list[:2]] == [
            "http://10.0.1.116" + _PATH_MAIN,
            "https://10.0.1.116" + _PATH_MAIN,
        ]
        assert coordinator._base_url == "https://10.0.1.116"

    @pytest.mark.asyncio
    async def test_cached_scheme_failure_falls_back_and_recaches(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _PATH_BEHAVIORINFO,
            _PATH_MAIN,
            _PATH_MENTINFO,
            _PATH_NWINFO,
        )

        coordinator = _make_coordinator(hass)
        coordinator._base_url = "https://10.0.1.116"
        session = self._mock_session(
            {
                ("https", _PATH_MAIN): (
                    200,
                    "<html><title>Default Page</title><body>Welcome</body></html>",
                ),
                ("http", _PATH_MAIN): (200, self._NL_MAIN_HTML),
                _PATH_MENTINFO: (404, ""),
                _PATH_NWINFO: (404, ""),
                _PATH_BEHAVIORINFO: (404, ""),
            }
        )

        with self._patch_sessions(session):
            await coordinator._async_update_data()

        assert [call.args[0] for call in session.get.call_args_list[:2]] == [
            "https://10.0.1.116" + _PATH_MAIN,
            "http://10.0.1.116" + _PATH_MAIN,
        ]
        assert coordinator._base_url == "http://10.0.1.116"

    @pytest.mark.asyncio
    async def test_warns_once_when_pages_are_not_english(self, hass, caplog):
        import logging
        import os

        from custom_components.epson_workforce.coordinator import (
            _PATH_MAIN,
            _PATH_MENTINFO,
        )

        fixture = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "PRESENTATION-ADVANCED-INFO_MENTINFO-TOP-dutch.html",
        )
        with open(fixture, encoding="utf-8") as handle:
            dutch_html = handle.read()

        coordinator = _make_coordinator(hass)
        responses = {
            _PATH_MAIN: (200, self._NL_MAIN_HTML),
            _PATH_MENTINFO: (200, dutch_html),
        }

        with (
            self._patch_sessions(self._mock_session(responses)),
            caplog.at_level(logging.WARNING),
        ):
            first = await coordinator._async_update_data()
            await coordinator._async_update_data()

        # The page parsed fine, but its Dutch labels yield no counters.
        assert first.get("total_pages") is None
        warnings = [
            r for r in caplog.records if "expected English labels" in r.getMessage()
        ]
        assert len(warnings) == 1, "warning must be logged exactly once"

    @pytest.mark.asyncio
    async def test_no_warning_when_counters_are_read(self, hass, caplog):
        import logging

        from custom_components.epson_workforce.coordinator import (
            _PATH_MAIN,
            _PATH_MENTINFO,
        )

        english_html = (
            '<dl class="values">'
            '<dt class="key"><span class="key">Total Number of Pages&nbsp;:</span></dt>'
            '<dd class="value clearfix">'
            '<div class="preserve-white-space">10</div></dd>'
            "</dl>"
        )

        coordinator = _make_coordinator(hass)
        responses = {
            _PATH_MAIN: (200, self._NL_MAIN_HTML),
            _PATH_MENTINFO: (200, english_html),
        }

        with (
            self._patch_sessions(self._mock_session(responses)),
            caplog.at_level(logging.WARNING),
        ):
            data = await coordinator._async_update_data()

        assert data["total_pages"] == 10
        assert not [
            r for r in caplog.records if "expected English labels" in r.getMessage()
        ]

    @pytest.mark.asyncio
    async def test_no_warning_when_any_expected_english_label_is_present(
        self, hass, caplog
    ):
        import logging

        from custom_components.epson_workforce.coordinator import (
            _PATH_MAIN,
            _PATH_MENTINFO,
        )

        # Total Number of Pages is deliberately absent. The old warning predicate
        # treated that as proof that *no* English labels had matched.
        english_html = (
            '<dl class="values">'
            '<dt class="key"><span class="key">B&amp;W Copy&nbsp;:</span></dt>'
            '<dd class="value clearfix">'
            '<div class="preserve-white-space">5</div></dd>'
            "</dl>"
        )
        coordinator = _make_coordinator(hass)
        responses = {
            _PATH_MAIN: (200, self._NL_MAIN_HTML),
            _PATH_MENTINFO: (200, english_html),
        }

        with (
            self._patch_sessions(self._mock_session(responses)),
            caplog.at_level(logging.WARNING),
        ):
            data = await coordinator._async_update_data()

        assert data["bw_copies"] == 5
        assert "total_pages" not in data
        assert not [
            r for r in caplog.records if "expected English labels" in r.getMessage()
        ]
