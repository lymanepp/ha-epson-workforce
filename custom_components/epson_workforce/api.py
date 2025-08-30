"""Epson WorkForce API"""

import ssl
import urllib.request

from bs4 import BeautifulSoup

# Maximum status length before truncating trailing period
MAX_STATUS_LENGTH = 30

LEVEL_SENSOR_TO_DIV = {
    "black": ("clrname", "BK"),
    "photoblack": ("clrname", "PB"),
    "magenta": ("clrname", "M"),
    "cyan": ("clrname", "C"),
    "yellow": ("clrname", "Y"),
    "lightcyan": ("clrname", "LC"),
    "lightmagenta": ("clrname", "LM"),
    "clean": ("mbicn", "Waste"),
}


class EpsonWorkForceAPI:
    def __init__(self, ip: str, path: str):
        """Initialize the link to the printer status page."""
        self._resource = "http://" + ip + path
        self.available = True
        self.soup = None
        self._model = None
        self._mac_address = None
        self.update()

    def get_sensor_value(self, sensor: str) -> int | str | None:
        """To make it the user easier to configure the cartridge type."""
        if not self.soup:
            return None

        # Handle printer status sensor separately
        if sensor == "printer_status":
            return self._get_printer_status()

        # Handle ink level sensors
        sensor_info = LEVEL_SENSOR_TO_DIV.get(sensor)
        if not sensor_info:
            return None

        div_name, div_text = sensor_info
        try:
            for li in self.soup.find_all("li", class_="tank"):
                div = li.find("div", class_=div_name)

                if div and div_text in (div.contents[0], "Waste"):
                    return int(li.find("div", class_="tank").findChild()["height"]) * 2
        except Exception:
            pass

        return None

    @property
    def model(self):
        """Return the printer model if available."""
        return self._model or "WorkForce Printer"

    @property
    def mac_address(self):
        """Return the printer MAC address if available."""
        return self._mac_address

    def _extract_device_info(self):
        """Extract device information from the HTML page."""
        if not self.soup:
            return

        # Try to find model information
        try:
            # Look for model in title or other common locations
            title = self.soup.find("title")
            if title and title.text:
                title_text = title.text.strip()
                # Extract model from title (e.g., "ET-8500 Series")
                if title_text and title_text != "":
                    self._model = f"Epson {title_text}"
        except Exception:
            pass

        try:
            # Look for MAC address in the text content
            all_text = self.soup.get_text()
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]

            for line in lines:
                if 'MAC Address' in line and ':' in line:
                    # Extract MAC address
                    mac_part = line.split('MAC Address')[1].strip()
                    if mac_part.startswith(':'):
                        mac_part = mac_part[1:].strip()
                    self._mac_address = mac_part
                    break
        except Exception:
            pass

    def _clean_status(self, status: str | None) -> str | None:
        """Clean up status text by removing trailing periods from short statuses."""
        if not status:
            return None
        if len(status) < MAX_STATUS_LENGTH and status.endswith('.'):
            status = status[:-1]
        return status

    def _get_fieldset_status(self) -> str | None:
        """Get status from fieldset structure: <fieldset id="PRT_STATUS">
        <ul>...</ul></fieldset>"""
        if not self.soup:
            return None

        fieldset = self.soup.find("fieldset", id="PRT_STATUS")
        if not fieldset:
            return None

        ul = fieldset.find("ul")
        if not ul:
            return None

        status = ul.get_text(strip=True)
        return self._clean_status(status)

    def _get_information_div_status(self):
        """Get status from information div structure: <div class="information">
        <p class="clearfix"><span>Available.</span></p></div>"""
        info_div = self.soup.find("div", class_="information")
        if not info_div:
            return None

        # Prefer a <span> inside <p.clearfix>, else any <span> within .information
        p = info_div.find("p", class_="clearfix")
        span = (p.find("span") if p else None) or info_div.find("span")
        if not span:
            return None

        status = span.get_text(strip=True)
        return self._clean_status(status)

    def _get_printer_status(self) -> str:
        """Get printer status using multiple parsing strategies."""
        try:
            # Try fieldset structure first: <fieldset id="PRT_STATUS">
            # <ul>...</ul></fieldset>
            status = self._get_fieldset_status()
            if status:
                return status

            # Information div structure: <div class="information"><p class="clearfix">
            # <span>Available.</span></p></div>
            status = self._get_information_div_status()
            if status:
                return status
        except Exception:
            return "Unknown"
        else:
            return "Unknown"

    def update(self):
        """Fetch the HTML page."""
        try:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(self._resource, context=context) as response:
                data = response.read()
                response.close()

            self.soup = BeautifulSoup(data, "html.parser")
            self.available = True
            self._extract_device_info()
        except Exception:
            self.available = False
