"""Epson WorkForce API"""

import ssl
import urllib.request

from bs4 import BeautifulSoup

SENSOR_TO_DIV = {
    "black": ("clrname", "BK"),
    "photoblack": ("clrname", "PB"),
    "magenta": ("clrname", "M"),
    "cyan": ("clrname", "C"),
    "yellow": ("clrname", "Y"),
    "lightcyan": ("clrname", "LC"),
    "lightmagenta": ("clrname", "LM"),
    "clean": ("mbicn", "Waste"),
    "printer_status": ("fieldset", "PRT_STATUS"),
}


class EpsonWorkForceAPI:
    def __init__(self, ip, path):
        """Initialize the link to the printer status page."""
        self._resource = "http://" + ip + path
        self.available = True
        self.soup = None
        self._model = None
        self._serial = None
        self.update()

    def get_sensor_value(self, sensor):
        """To make it the user easier to configure the cartridge type."""
        if sensor not in SENSOR_TO_DIV:
            return 0

        div_name, div_text = SENSOR_TO_DIV.get(sensor)

        # Handle printer status sensor differently
        if sensor == "printer_status":
            try:
                fieldset = self.soup.find("fieldset", id=div_text)
                if fieldset:
                    ul = fieldset.find("ul")
                    if ul:
                        return ul.get_text(strip=True)
                return "Unknown"
            except Exception:
                return "Unknown"

        # Handle ink level sensors
        try:
            for li in self.soup.find_all("li", class_="tank"):
                div = li.find("div", class_=div_name)

                if div and div_text in (div.contents[0], "Waste"):
                    return int(li.find("div", class_="tank").findChild()["height"]) * 2
        except Exception:
            return 0

    @property
    def model(self):
        """Return the printer model if available."""
        return self._model or "WorkForce Printer"

    @property
    def serial_number(self):
        """Return the printer serial number if available."""
        return self._serial

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

        # Try to find serial number or MAC address
        try:
            # Look for MAC address in the text content
            all_text = self.soup.get_text()
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]

            for line in lines:
                if 'MAC Address' in line and ':' in line:
                    # Extract MAC address as serial identifier
                    mac_part = line.split('MAC Address')[1].strip()
                    if mac_part.startswith(':'):
                        mac_part = mac_part[1:].strip()
                    self._serial = mac_part
                    break
        except Exception:
            pass

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
