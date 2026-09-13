"""Data coordinator for Epson WorkForce integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import re
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
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

HTTP_OK = 200
HTTP_NOT_FOUND = 404
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_PROTOCOLS = ("http", "https")

# Web Config serves its pages in the printer's configured language, but the
# supplemental pages are parsed by their English labels, so on a non-English
# printer every lookup misses and the sensors are never created. This cookie is
# what Web Config's own language selector sets; most models honour it and return
# English regardless of the printer's own setting.
#
# It is sent only for the supplemental pages. The main page contains user-facing
# printer/scanner status strings that should stay in the language the owner
# configured. Any fields on that page that are keyed by English display labels
# can fall back to the forced-English supplemental network page.
#
# Two things this has to work around, both measured on an XP-4200:
#  * These printers answer HTTP with a 307 to HTTPS, and aiohttp drops the Cookie
#    header across that redirect. Protocol discovery therefore follows the main-
#    page redirect once, remembers the final scheme, and supplemental pages are
#    then requested directly over that scheme. HTTP-only models remain on HTTP.
#  * aiohttp lets a cookie jar override an explicit Cookie header, so these
#    requests use a session with no jar. Otherwise a stray EPSON_COOKIE_LANG in
#    Home Assistant's shared jar would silently undo this.
_ENGLISH_LANG_COOKIE = {"Cookie": "EPSON_COOKIE_LANG=lang_b&1/lang_a&1"}

_MENTINFO_ENGLISH_KEYS = frozenset(
    {
        "Total Number of Pages",
        "Total Number of B&W Pages",
        "Total Number of Color Pages",
        "B&W Copy",
        "Color Copy",
        "B&W Scan",
        "Color Scan",
        "First Printing Date",
    }
)


def _looks_like_main_page(raw: dict[str, Any]) -> bool:
    """Return whether parsed data is recognizable as an Epson status page."""
    return bool(
        raw.get("printer_status")
        or raw.get("scanner_status")
        or raw.get("inks")
        or raw.get("maintenance_box") is not None
        or raw.get("network")
        or raw.get("wifi_direct")
    )


async def async_probe_printer(
    session: aiohttp.ClientSession,
    host: str,
    *,
    schemes: tuple[str, ...] = _PROTOCOLS,
    timeout: aiohttp.ClientTimeout = _TIMEOUT,
) -> tuple[str, dict[str, Any]] | None:
    """Find a working Epson endpoint and return its base URL + parsed main data.

    Redirects are followed so an HTTP endpoint that upgrades to HTTPS is detected
    as HTTPS. A successful HTTP status alone is not enough: the response must also
    parse as an Epson main status page, which prevents a generic/default HTTPS
    page from being cached as the printer endpoint.
    """
    for scheme in schemes:
        url = f"{scheme}://{host}{_PATH_MAIN}"
        try:
            async with session.get(
                url, timeout=timeout, ssl=False, allow_redirects=True
            ) as resp:
                if resp.status != HTTP_OK:
                    _LOGGER.debug("GET %s → HTTP %d", url, resp.status)
                    continue

                html = await resp.text(encoding="utf-8", errors="ignore")
                final_scheme = resp.url.scheme
                if final_scheme not in _PROTOCOLS:
                    _LOGGER.debug(
                        "GET %s → unsupported final scheme %s", url, final_scheme
                    )
                    continue
                base_url = f"{final_scheme}://{host}"

                raw = EpsonHTMLParser(html, source=base_url + _PATH_MAIN).parse()
                if not _looks_like_main_page(raw):
                    _LOGGER.debug(
                        "GET %s → %d (%d bytes), but response is not an Epson "
                        "status page",
                        url,
                        resp.status,
                        len(html),
                    )
                    continue

                _LOGGER.debug(
                    "GET %s → %d (%d bytes); working endpoint is %s",
                    url,
                    resp.status,
                    len(html),
                    base_url,
                )
                return base_url, raw
        except TimeoutError:
            _LOGGER.debug("GET %s → timed out after %ss", url, timeout.total)
        except aiohttp.ClientError as exc:
            _LOGGER.debug("GET %s → request error: %s", url, exc)

    return None


class EpsonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch all data from the Epson printer and expose it as a flat dict."""

    def __init__(self, hass: HomeAssistant, host: str) -> None:
        self.host = host
        # Start with HTTP; _fetch_main validates it, follows redirects, and falls
        # back to HTTPS when needed. The working scheme is then cached so
        # supplemental requests can use it directly without losing the explicit
        # language cookie across a redirect.
        self._base_url = f"http://{host}"
        self._supplemental_404: set[str] = set()
        self._language_warned = False
        self._web_config_session: aiohttp.ClientSession | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"Epson {host}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        # Fetch the main page — failure is fatal for this cycle.
        _LOGGER.debug("Fetching main status page from %s", self._base_url)
        raw = await self._fetch_main()
        if raw is None:
            raise UpdateFailed(  # noqa: TRY003
                f"Cannot reach printer at {self.host} over HTTP or HTTPS"
            )
        _LOGGER.debug(
            "Main page parsed: model=%s status=%s inks=%s",
            raw.get("model"),
            raw.get("printer_status"),
            list(raw.get("inks", {}).keys()),
        )

        # Fetch supplemental pages concurrently; 404s are permanently skipped,
        # other errors are transient and retried next cycle.
        pending = [
            (key, path, page_parser)
            for key, path, page_parser in _SUPPLEMENTAL
            if path not in self._supplemental_404
        ]
        if pending:
            _LOGGER.debug(
                "Fetching %d supplemental page(s): %s",
                len(pending),
                [path for _, path, _ in pending],
            )
        sup_results = await asyncio.gather(
            *[
                self._fetch_supplemental(key, path, page_parser)
                for key, path, page_parser in pending
            ],
            return_exceptions=False,
        )
        sup: dict[str, dict] = {}
        for item in sup_results:
            if item is not None:
                sup[item[0]] = item[1]

        _LOGGER.debug(
            "Supplemental pages received: %s  |  permanently skipped (404): %s",
            list(sup.keys()),
            [p.split("/")[-1] for p in self._supplemental_404],
        )

        data = _build_data(raw, sup)
        self._warn_if_not_english(sup)
        _LOGGER.debug(
            "Built %d sensor value(s): %s",
            len([k for k in data if not k.startswith("_")]),
            [k for k in data if not k.startswith("_")],
        )
        return data

    def _warn_if_not_english(self, sup: dict[str, dict]) -> None:
        """Warn once when the usage page has no recognized English labels.

        A localized page is the usual cause, although a model with a different
        page schema can look the same. Without this the sensors are simply absent
        with nothing in the log to explain why.
        """
        if self._language_warned:
            return
        mentinfo = sup.get("mentinfo")
        if not mentinfo or _MENTINFO_ENGLISH_KEYS.intersection(mentinfo):
            return
        self._language_warned = True
        _LOGGER.warning(
            "Printer at %s returned the usage page with %d entries, but none of"
            " the expected English labels were found, so the usage counters"
            " cannot be read. The printer may be ignoring the language cookie or"
            " using a different page schema. If Web Config is not already set to"
            " English, setting it to English may enable these sensors. Labels"
            " seen: %s",
            self.host,
            len(mentinfo),
            ", ".join(sorted(mentinfo)[:5]),
        )

    def _session(self) -> aiohttp.ClientSession:
        """Return the dedicated Web Config session, creating it on first use.

        It deliberately keeps no cookie jar: aiohttp lets a jar override an
        explicit Cookie header. Using the same isolated session for the main page
        also prevents a stale shared-session language cookie from changing the
        localized status strings we intentionally preserve.
        """
        if self._web_config_session is None:
            self._web_config_session = async_create_clientsession(
                self.hass, cookie_jar=aiohttp.DummyCookieJar()
            )
        return self._web_config_session

    async def _fetch_main(self) -> dict[str, Any] | None:
        """Fetch and parse the main page, caching the working scheme."""
        cached_scheme = self._base_url.split(":", 1)[0]
        alternate = "https" if cached_scheme == "http" else "http"
        schemes = (cached_scheme, alternate)

        result = await async_probe_printer(
            self._session(), self.host, schemes=schemes, timeout=_TIMEOUT
        )
        if result is None:
            return None

        base_url, raw = result
        if self._base_url != base_url:
            _LOGGER.debug("Using Epson Web Config at %s", base_url)
        self._base_url = base_url
        return raw

    async def _fetch_supplemental(
        self,
        key: str,
        path: str,
        page_parser: Any,
    ) -> tuple[str, dict] | None:
        # The main-page fetch has already discovered and cached a working scheme,
        # so supplemental requests can use it directly without probing a known-
        # dead HTTPS endpoint on every update.
        url = self._base_url + path
        try:
            async with self._session().get(
                url, timeout=_TIMEOUT, ssl=False, headers=_ENGLISH_LANG_COOKIE
            ) as resp:
                if resp.status == HTTP_NOT_FOUND:
                    _LOGGER.debug(
                        "GET %s → 404; this page is not available on this printer"
                        " and will not be requested again",
                        url,
                    )
                    self._supplemental_404.add(path)
                    return None
                resp.raise_for_status()
                html = await resp.text(encoding="utf-8", errors="ignore")
                _LOGGER.debug("GET %s → %d (%d bytes)", url, resp.status, len(html))
            return (key, page_parser(html))
        except aiohttp.ClientResponseError as exc:
            _LOGGER.debug(
                "GET %s → HTTP %d (transient, will retry)", url, exc.status
            )
            return None
        except aiohttp.ClientConnectionError as exc:
            _LOGGER.debug("GET %s → connection error (transient): %s", url, exc)
            return None
        except TimeoutError:
            _LOGGER.debug(
                "GET %s → timed out after %ss (transient, will retry)",
                url,
                _TIMEOUT.total,
            )
            return None
        except Exception as exc:
            _LOGGER.debug("GET %s → unexpected error (transient): %s", url, exc)
            return None


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
        "signal_strength": network.get("Signal Strength")
        or nwinfo.get("Signal Strength")
        or None,
        "ssid": network.get("SSID") or nwinfo.get("SSID") or None,
        "wifi_direct_connection_method": wifi_direct.get("Connection Method")
        or nwinfo.get("Connection Method")
        or None,
        # Page counters
        "total_pages": _to_int(mentinfo.get("Total Number of Pages")),
        "bw_pages": _to_int(mentinfo.get("Total Number of B&W Pages")),
        "color_pages": _to_int(mentinfo.get("Total Number of Color Pages")),
        "bw_copies": _to_int(mentinfo.get("B&W Copy")),
        "color_copies": _to_int(mentinfo.get("Color Copy")),
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
