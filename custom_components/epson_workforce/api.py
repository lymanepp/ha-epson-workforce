"""Epson WorkForce API"""

import urllib.request

from bs4 import BeautifulSoup

SENSOR_TO_DIV = {
    "black": ("clrname", "BK"),
    "photoblack": ("clrname", "PB"),
    "magenta": ("clrname", "M"),
    "cyan": ("clrname", "C"),
    "yellow": ("clrname", "Y"),
    "clean": ("mbicn", "Waste"),
}


class EpsonWorkForceAPI:
    def __init__(self, ip):
        """Initialize the link to the printer status page."""
        self._resource = "http://" + ip + "/PRESENTATION/HTML/TOP/PRTINFO.HTML"
        self.available = True
        self.soup = None
        self.update()

    def getSensorValue(self, sensor):
        """To make it the user easier to configure the cartridge type."""
        if sensor not in SENSOR_TO_DIV:
            return 0

        div_name, div_text = SENSOR_TO_DIV.get(sensor)

        try:
            for li in self.soup.find_all("li", class_="tank"):
                div = li.find("div", class_=div_name)

                if div and div_text in (div.contents[0], "Waste"):
                    return int(li.find("div", class_="tank").findChild()["height"]) * 2
        except Exception:
            return 0

    def update(self):
        try:
            """Just fetch the HTML page."""
            with urllib.request.urlopen(self._resource) as response:
                data = response.read()
                response.close()

            self.soup = BeautifulSoup(data, "html.parser")
            self.available = True
        except Exception:
            self.available = False
