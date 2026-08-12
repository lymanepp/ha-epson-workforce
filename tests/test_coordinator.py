"""Tests for EpsonCoordinator and _build_data."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.epson_workforce.coordinator import (
    EpsonCoordinator,
    _build_data,
    _parse_wifi_speed,
    _to_int,
)

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

    def _mock_session(self, responses: dict[str, tuple[int, str]]):
        """Return a mock aiohttp session where each path maps to (status, html)."""

        def fake_get(url, **kwargs):
            for path, (status, html) in responses.items():
                if url.endswith(path):
                    resp = MagicMock()
                    resp.status = status
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
            raise Exception(f"Unexpected URL: {url}")

        session = MagicMock()
        session.get = MagicMock(side_effect=fake_get)
        return session

    @pytest.mark.asyncio
    async def test_404_supplemental_blacklisted(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _PATH_MAIN,
            _PATH_MENTINFO,
        )

        main_html = (
            "<html><head><title>ET-4950 Series</title></head><body>"
            "<fieldset id='PRT_STATUS'><ul><li>Available.</li></ul></fieldset>"
            "</body></html>"
        )

        responses = {
            _PATH_MAIN: (200, main_html),
            _PATH_MENTINFO: (404, ""),
        }

        with patch(
            "custom_components.epson_workforce.coordinator.async_create_clientsession",
            return_value=self._mock_session(responses),
        ):
            coordinator = _make_coordinator(hass)
            await coordinator._async_update_data()

        assert _PATH_MENTINFO in coordinator._supplemental_404

    @pytest.mark.asyncio
    async def test_main_page_failure_raises(self, hass):
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.epson_workforce.coordinator import _PATH_MAIN

        responses = {_PATH_MAIN: (503, "")}

        with (
            patch(
                "custom_components.epson_workforce.coordinator.async_create_clientsession",
                return_value=self._mock_session(responses),
            ),
            pytest.raises(UpdateFailed),
        ):
            coordinator = _make_coordinator(hass)
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_status_request_forces_english_cookie(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _EPSON_ENGLISH_COOKIE,
            _PATH_MAIN,
            _TIMEOUT,
        )

        session = self._mock_session({_PATH_MAIN: (200, "")})

        with patch(
            "custom_components.epson_workforce.coordinator.async_create_clientsession",
            return_value=session,
        ):
            coordinator = _make_coordinator(hass)

        coordinator._status_request(_PATH_MAIN)

        session.get.assert_called_once_with(
            f"https://10.0.1.116{_PATH_MAIN}",
            timeout=_TIMEOUT,
            ssl=False,
            headers={"Cookie": _EPSON_ENGLISH_COOKIE},
        )

    @pytest.mark.asyncio
    async def test_https_failure_falls_back_to_http(self, hass):
        from custom_components.epson_workforce.coordinator import (
            _EPSON_ENGLISH_COOKIE,
            _PATH_MAIN,
            _TIMEOUT,
        )

        main_html = (
            "<html><head><title>ET-4950 Series</title></head><body>"
            "<fieldset id='PRT_STATUS'><ul><li>Available.</li></ul></fieldset>"
            "</body></html>"
        )

        def fake_get(url, **kwargs):
            if url.startswith("https://"):
                raise aiohttp.ClientConnectionError("HTTPS unavailable")
            if url == f"http://10.0.1.116{_PATH_MAIN}":
                resp = MagicMock()
                resp.status = 200
                resp.raise_for_status = MagicMock()
                resp.text = AsyncMock(return_value=main_html)
                cm = MagicMock()
                cm.__aenter__ = AsyncMock(return_value=resp)
                cm.__aexit__ = AsyncMock(return_value=False)
                return cm
            raise Exception(f"Unexpected URL: {url}")

        session = MagicMock()
        session.get = MagicMock(side_effect=fake_get)

        with patch(
            "custom_components.epson_workforce.coordinator.async_create_clientsession",
            return_value=session,
        ):
            coordinator = _make_coordinator(hass)
            html = await coordinator._fetch(_PATH_MAIN)

        assert html == main_html
        assert coordinator._base_url == "http://10.0.1.116"
        assert session.get.call_count == 2
        session.get.assert_any_call(
            f"https://10.0.1.116{_PATH_MAIN}",
            timeout=_TIMEOUT,
            ssl=False,
            headers={"Cookie": _EPSON_ENGLISH_COOKIE},
        )
        session.get.assert_any_call(
            f"http://10.0.1.116{_PATH_MAIN}",
            timeout=_TIMEOUT,
            ssl=False,
            headers={"Cookie": _EPSON_ENGLISH_COOKIE},
        )
