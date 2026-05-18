"""Epson WorkForce API."""

from __future__ import annotations

import re
import ssl
from typing import Any
import urllib.error
import urllib.request

from .parser import EpsonHTMLParser

# Supplemental advanced-UI pages (optional — not all printers expose them)
_PATH_MENTINFO = "/PRESENTATION/ADVANCED/INFO_MENTINFO/TOP"  # page counters
_PATH_NWINFO = "/PRESENTATION/ADVANCED/INFO_NWINFO/TOP"  # extended network
_PATH_BEHAVIORINFO = "/PRESENTATION/ADVANCED/INFO_BEHAVIORINFO/TOP"  # hw status

_SUPPLEMENTAL_PAGES = (
    ("mentinfo", _PATH_MENTINFO),
    ("nwinfo", _PATH_NWINFO),
    ("behaviorinfo", _PATH_BEHAVIORINFO),
)

HTTP_NOT_FOUND = 404


class EpsonWorkForceAPI:
    def __init__(self, ip: str, path: str, timeout: float = 5.0):
        self._resource = "http://" + ip + path
        self._base_url = "http://" + ip
        self._ip = ip  # Store IP address for diagnostic sensor
        self.available: bool = True
        self._timeout = timeout

        # Internal
        self._parser: EpsonHTMLParser | None = None
        self._data: dict[str, Any] | None = None  # parsed dict cache
        self._supplemental: dict[str, Any] = {}  # data from extra pages
        self._supplemental_404: set[str] = (
            set()
        )  # paths permanently absent on this printer

        # Defaults
        self._model: str | None = None
        self._mac: str | None = None

        self.update()

    @property
    def name(self) -> str | None:
        """Returns the name of the printer."""
        self._ensure_parsed()
        return (self._data or {}).get("name")

    @property
    def model(self) -> str:
        """Returns the model name of the printer."""
        self._ensure_parsed()
        return (self._data or {}).get("model") or "WorkForce Printer"

    @property
    def mac_address(self) -> str | None:
        """Returns the MAC address of the device if available."""
        self._ensure_parsed()
        return (self._data or {}).get("mac_address")

    def update(self) -> None:
        """
        Fetch and parse the HTML page from the device (rebuilds parser + resets cache).
        """
        context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(
                self._resource, context=context, timeout=self._timeout
            ) as response:
                data_bytes = response.read()

            html_text = data_bytes.decode("utf-8", errors="ignore")
            self._parser = EpsonHTMLParser(html_text, source=self._resource)
            self.available = True
            self._data = None  # invalidate cache
        except Exception:
            self.available = False
            self._parser = None
            self._data = None
            self._supplemental = {}
            return

        # Fetch supplemental pages. A 404 means the page doesn't exist on this
        # printer and is permanently skipped. Any other error (timeout, connection
        # reset) is transient — retry next cycle since the main page is reachable.
        self._supplemental = {}
        for key, path in _SUPPLEMENTAL_PAGES:
            if path in self._supplemental_404:
                continue
            try:
                url = self._base_url + path
                with urllib.request.urlopen(
                    url, context=context, timeout=self._timeout
                ) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                self._supplemental[key] = EpsonHTMLParser.parse_dt_dd_page(html)
            except urllib.error.HTTPError as exc:
                if exc.code == HTTP_NOT_FOUND:
                    self._supplemental_404.add(path)  # never try again
            except Exception:
                pass  # transient — will retry next poll

    def get_sensor_value(self, sensor: str) -> int | str | None:
        """Retrieves the value of a specified sensor from the parsed printer data."""
        self._ensure_parsed()
        data = self._data or {}
        sup = self._supplemental

        result: int | str | None = None

        # Handle special sensors
        if sensor == "printer_status":
            result = data.get("printer_status") or "Unknown"
        elif sensor == "scanner_status":
            result = data.get("scanner_status") or "Unknown"
        elif sensor == "clean":
            result = data.get("maintenance_box")
        elif sensor == "ip_address":
            result = self._ip

        # Network diagnostics (original page)
        elif sensor in ("signal_strength", "ssid"):
            network = data.get("network", {})
            network_key = "Signal Strength" if sensor == "signal_strength" else "SSID"
            result = network.get(network_key) or "Unknown"

        # WiFi Direct diagnostics
        elif sensor == "wifi_direct_connection_method":
            wifi_direct = data.get("wifi_direct", {})
            result = wifi_direct.get("Connection Method") or "Unknown"

        # --- NEW: page counters (INFO_MENTINFO) ---
        elif sensor == "total_pages":
            result = _to_int(sup.get("mentinfo", {}).get("Total Number of Pages"))
        elif sensor == "bw_pages":
            result = _to_int(sup.get("mentinfo", {}).get("Total Number of B&W Pages"))
        elif sensor == "color_pages":
            result = _to_int(sup.get("mentinfo", {}).get("Total Number of Color Pages"))
        elif sensor == "bw_scans":
            result = _to_int(sup.get("mentinfo", {}).get("B&W Scan"))
        elif sensor == "color_scans":
            result = _to_int(sup.get("mentinfo", {}).get("Color Scan"))
        elif sensor == "first_print_date":
            result = sup.get("mentinfo", {}).get("First Printing Date")

        # --- NEW: extended network info (INFO_NWINFO) ---
        elif sensor == "wifi_speed":
            result = _parse_wifi_speed(
                sup.get("nwinfo", {}).get("Connection Status", "")
            )
        elif sensor == "wifi_channel":
            result = sup.get("nwinfo", {}).get("Channel")
        elif sensor == "wifi_mode":
            result = sup.get("nwinfo", {}).get("Wi-Fi Mode")
        elif sensor == "wifi_security":
            result = sup.get("nwinfo", {}).get("Security Level")

        # --- NEW: hardware status (INFO_BEHAVIORINFO) ---
        elif sensor == "wifi_hw_status":
            result = sup.get("behaviorinfo", {}).get("Wi-Fi")

        # Default to ink sensors
        else:
            inks: dict[str, int] = data.get("inks") or {}
            result = inks.get(sensor)

        return result

    def _ensure_parsed(self) -> None:
        if self._data is not None:
            return
        if not self._parser:
            return
        try:
            self._data = self._parser.parse()
        except Exception:
            self._data = {}


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def _parse_wifi_speed(connection_status: str) -> str | None:
    """Extract speed from e.g. 'Wi-Fi-72Mbps' → '72 Mbps'."""
    match = re.search(r"(\d+)\s*Mbps", connection_status, re.IGNORECASE)
    if match:
        return f"{match.group(1)} Mbps"
    return connection_status or None
