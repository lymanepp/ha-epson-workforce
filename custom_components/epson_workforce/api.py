"""Epson WorkForce API."""

from __future__ import annotations

import ssl
from typing import Any
import urllib.request

from .parser import EpsonHTMLParser


class EpsonWorkForceAPI:
    def __init__(self, ip: str, path: str):
        self._resource = "http://" + ip + path
        self.available: bool = True

        # Internal
        self._parser: EpsonHTMLParser | None = None
        self._data: dict[str, Any] | None = None  # parsed dict cache

        # Defaults
        self._model: str | None = None
        self._mac: str | None = None

        self.update()

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
            with urllib.request.urlopen(self._resource, context=context) as response:
                data_bytes = response.read()
            html_text = data_bytes.decode("utf-8", errors="ignore")
            self._parser = EpsonHTMLParser(html_text, source=self._resource)
            self.available = True
            self._data = None  # invalidate cache
        except Exception:
            self.available = False
            self._parser = None
            self._data = None

    def get_sensor_value(self, sensor: str) -> int | str | None:
        """Retrieves the value of a specified sensor from the parsed printer data."""
        self._ensure_parsed()
        data = self._data or {}

        s = (sensor or "").strip().lower()
        if s == "printer_status":
            return data.get("printer_status") or "Unknown"

        if s == "clean":
            return data.get("maintenance_box")

        label_map = {
            "black": "BK",
            "cyan": "C",
            "magenta": "M",
            "yellow": "Y",
            "photoblack": "PB",
            "lightcyan": "LC",
            "lightmagenta": "LM",
            "gray": "GY",
        }
        if s in label_map:
            inks: dict[str, int] = data.get("inks") or {}
            return inks.get(label_map[s])

        return None

    def _ensure_parsed(self) -> None:
        if self._data is not None:
            return
        if not self._parser:
            return
        try:
            self._data = self._parser.parse()
        except Exception:
            # Leave _data as None to keep Unknown/None behavior
            self._data = {}
