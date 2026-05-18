"""Data coordinator for Epson WorkForce integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import re
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .parser import EpsonHTMLParser

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

_PATH_MAIN = "/PRESENTATION/HTML/TOP/PRTINFO.HTML"
_PATH_MENTINFO = "/PRESENTATION/ADVANCED/INFO_MENTINFO/TOP"
_PATH_NWINFO = "/PRESENTATION/ADVANCED/INFO_NWINFO/TOP"
_PATH_BEHAVIORINFO = "/PRESENTATION/ADVANCED/INFO_BEHAVIORINFO/TOP"

_SUPPLEMENTAL = (
    ("mentinfo", _PATH_MENTINFO, EpsonHTMLParser.parse_dt_dd_page),
    ("nwinfo", _PATH_NWINFO, EpsonHTMLParser.parse_dt_dd_page),
    ("behaviorinfo", _PATH_BEHAVIORINFO, EpsonHTMLParser.parse_behaviorinfo_page),
)

HTTP_NOT_FOUND = 404
_TIMEOUT = aiohttp.ClientTimeout(total=10)


class EpsonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch all data from the Epson printer and expose it as a flat dict."""

    def __init__(self, hass: HomeAssistant, host: str) -> None:
        self.host = host
        self._base_url = f"http://{host}"
        self._supplemental_404: set[str] = set()
        super().__init__(
            hass,
            _LOGGER,
            name=f"Epson {host}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)

        # Fetch the main page — failure is fatal for this cycle.
        main_html = await self._fetch(session, _PATH_MAIN)
        if main_html is None:
            raise UpdateFailed(f"Cannot reach printer at {self._base_url}")  # noqa: TRY003

        parser = EpsonHTMLParser(main_html, source=self._base_url + _PATH_MAIN)
        raw = parser.parse()

        # Fetch supplemental pages concurrently; 404s are permanently skipped,
        # other errors are transient and retried next cycle.
        sup_results = await asyncio.gather(
            *[
                self._fetch_supplemental(session, key, path, page_parser)
                for key, path, page_parser in _SUPPLEMENTAL
                if path not in self._supplemental_404
            ],
            return_exceptions=False,
        )
        sup: dict[str, dict] = {}
        for item in sup_results:
            if item is not None:
                sup[item[0]] = item[1]

        return _build_data(raw, sup)

    async def _fetch(self, session: aiohttp.ClientSession, path: str) -> str | None:
        try:
            async with session.get(
                self._base_url + path, timeout=_TIMEOUT, ssl=False
            ) as resp:
                resp.raise_for_status()
                return await resp.text(encoding="utf-8", errors="ignore")
        except aiohttp.ClientResponseError as exc:
            if exc.status == HTTP_NOT_FOUND:
                _LOGGER.debug("404 on main page %s", path)
            return None
        except Exception as exc:
            _LOGGER.debug("Failed to fetch %s: %s", path, exc)
            return None

    async def _fetch_supplemental(
        self,
        session: aiohttp.ClientSession,
        key: str,
        path: str,
        page_parser: Any,
    ) -> tuple[str, dict] | None:
        try:
            async with session.get(
                self._base_url + path, timeout=_TIMEOUT, ssl=False
            ) as resp:
                if resp.status == HTTP_NOT_FOUND:
                    self._supplemental_404.add(path)
                    return None
                resp.raise_for_status()
                html = await resp.text(encoding="utf-8", errors="ignore")
            return (key, page_parser(html))
        except aiohttp.ClientResponseError as exc:
            if exc.status == HTTP_NOT_FOUND:
                self._supplemental_404.add(path)
            return None
        except Exception:
            return None  # transient — retry next poll


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def _parse_wifi_speed(connection_status: str) -> str | None:
    match = re.search(r"(\d+)\s*Mbps", connection_status, re.IGNORECASE)
    if match:
        return f"{match.group(1)} Mbps"
    return connection_status or None


def _build_data(raw: dict[str, Any], sup: dict[str, dict]) -> dict[str, Any]:
    """
    Flatten raw parser output and supplemental pages into a single sensor-keyed dict.
    """
    inks: dict[str, int] = raw.get("inks") or {}
    network: dict[str, str] = raw.get("network") or {}
    wifi_direct: dict[str, str] = raw.get("wifi_direct") or {}
    mentinfo: dict[str, str] = sup.get("mentinfo") or {}
    nwinfo: dict[str, str] = sup.get("nwinfo") or {}
    behaviorinfo: dict[str, str | None] = sup.get("behaviorinfo") or {}

    data: dict[str, Any] = {
        # Device identity (used by DeviceInfo, not sensors)
        "_model": raw.get("model"),
        "_mac": raw.get("mac_address"),
        "_name": raw.get("name"),
        # Ink levels — keyed by colour code
        **{f"ink_{k.lower()}": v for k, v in inks.items()},
        # Maintenance box
        "clean": raw.get("maintenance_box"),
        # Status
        "printer_status": raw.get("printer_status"),
        "scanner_status": raw.get("scanner_status") or behaviorinfo.get("Scanner"),
        "fax_status": behaviorinfo.get("Fax"),
        # Network (main page)
        "ip_address": raw.get("ip_address"),
        "signal_strength": network.get("Signal Strength") or None,
        "ssid": network.get("SSID") or None,
        "wifi_direct_connection_method": wifi_direct.get("Connection Method") or None,
        # Page counters
        "total_pages": _to_int(mentinfo.get("Total Number of Pages")),
        "bw_pages": _to_int(mentinfo.get("Total Number of B&W Pages")),
        "color_pages": _to_int(mentinfo.get("Total Number of Color Pages")),
        "bw_scans": _to_int(mentinfo.get("B&W Scan")),
        "color_scans": _to_int(mentinfo.get("Color Scan")),
        "first_print_date": mentinfo.get("First Printing Date") or None,
        # Extended network (supplemental)
        "wifi_speed": _parse_wifi_speed(nwinfo.get("Connection Status", "")),
        "wifi_channel": nwinfo.get("Channel") or None,
        "wifi_mode": nwinfo.get("Wi-Fi Mode") or None,
        "wifi_security": nwinfo.get("Security Level") or None,
        # Hardware status
        "wifi_hw_status": behaviorinfo.get("Wi-Fi"),
    }

    # Remove keys whose value is None — absent keys mean sensor not created
    return {k: v for k, v in data.items() if v is not None}
