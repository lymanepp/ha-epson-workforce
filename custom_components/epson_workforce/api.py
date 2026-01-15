"""Epson WorkForce API."""

from __future__ import annotations

import ssl
from typing import Any
import urllib.request
import re

from .parser import EpsonHTMLParser


class EpsonWorkForceAPI:
    def __init__(self, ip: str, path: str, timeout: float = 5.0):
        self._resource = "http://" + ip + path
        self._ip = ip  # Store IP address for diagnostic sensor
        self.available: bool = True
        self._timeout = timeout

        # Internal
        self._parser: EpsonHTMLParser | None = None
        self._data: dict[str, Any] | None = None  # parsed dict cache
        self._usage_data: dict[str, Any] = {}

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
        try:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(
                self._resource, context=context, timeout=self._timeout
            ) as response:
                data_bytes = response.read()

            html_text = data_bytes.decode("utf-8", errors="ignore")
            self._parser = EpsonHTMLParser(html_text, source=self._resource)
            self.available = True
            self._data = None  # invalidate cache
            
            # Fetch additional usage stats
            self._fetch_usage_data(context)
            
        except Exception:
            self.available = False
            self._parser = None
            self._data = None

    def _fetch_usage_data(self, context: ssl.SSLContext) -> None:
        """Fetch data from additional usage pages."""
        possible_paths = [
            "/PRESENTATION/ADVANCED/COMMON/TOP",
            "/PRESENTATION/ADVANCED/INFO_MENTINFO/TOP"
        ]
        
        patterns = {
            "total_pages": r"Total Number of Pages.*?>(\d+)</div>",
            "bw_pages": r"Total Number of B(?:&amp;|W) Pages.*?>(\d+)</div>",
            "color_pages": r"Total Number of Color Pages.*?>(\d+)</div>",
            "bw_scans": r"B(?:&amp;|W) Scan.*?>(\d+)</div>",
            "color_scans": r"Color Scan.*?>(\d+)</div>",
            "first_print_date": r"First Printing Date.*?>([\d-]+)</div>",
        }

        for path in possible_paths:
            try:
                url = f"http://{self._ip}{path}"
                with urllib.request.urlopen(url, context=context, timeout=self._timeout) as response:
                    html = response.read().decode("utf-8", errors="ignore")
                    
                    # Debug: logging can be added here if needed
                    found_on_this_page = False
                    for key, pattern in patterns.items():
                        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                        if match:
                            self._usage_data[key] = match.group(1).strip()
                            found_on_this_page = True
                    
                    if found_on_this_page:
                        break
            except Exception:
                continue

    def get_sensor_value(self, sensor: str) -> int | str | None:
        """Retrieves the value of a specified sensor from the parsed printer data."""
        self._ensure_parsed()
        data = self._data or {}

        # Handle usage sensors
        if sensor in self._usage_data:
            return self._usage_data[sensor]

        # Handle special sensors
        if sensor == "printer_status":
            return data.get("printer_status") or "Unknown"
        if sensor == "clean":
            return data.get("maintenance_box")
        if sensor == "ip_address":
            return self._ip

        # Network diagnostics
        if sensor in ("signal_strength", "ssid"):
            network = data.get("network", {})
            network_key = "Signal Strength" if sensor == "signal_strength" else "SSID"
            return network.get(network_key) or "Unknown"

        # WiFi Direct diagnostics
        if sensor == "wifi_direct_connection_method":
            wifi_direct = data.get("wifi_direct", {})
            return wifi_direct.get("Connection Method") or "Unknown"

        # Default to ink sensors
        inks: dict[str, int] = data.get("inks") or {}
        return inks.get(sensor)

    def _ensure_parsed(self) -> None:
        if self._data is not None:
            return
        if not self._parser:
            return
        try:
            self._data = self._parser.parse()
        except Exception:
            self._data = {}
