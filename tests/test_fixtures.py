"""Test the Epson WorkForce API using real HTML fixtures."""

import os
from bs4 import BeautifulSoup
from unittest.mock import patch

from custom_components.epson_workforce.api import EpsonWorkForceAPI

class TestEpsonWorkForceAPIFixtures:
    """Test class for EpsonWorkForceAPI using real HTML fixtures."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock the update method to avoid network calls
        with patch.object(EpsonWorkForceAPI, 'update'):
            self.api = EpsonWorkForceAPI("192.168.1.100", "/PRESENTATION/HTML/TOP/PRTINFO.HTML")

    def load_fixture(self, filename):
        """Load HTML fixture file."""
        fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', filename)
        with open(fixture_path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_et8500(self):
        """Test ET-8500 Series HTML fixture."""
        html = self.load_fixture('ET-8500.html')
        self.api.soup = BeautifulSoup(html, "html.parser")
        self.api._extract_device_info()

        # Test printer status (uses primary structure: fieldset)
        status = self.api.get_sensor_value("printer_status")
        assert status == "Available"

        # Test device information extraction
        assert self.api.model == "Epson ET-8500 Series"
        assert self.api.mac_address == "DC:CD:2F:0C:9E:89"

        # Test ink levels - ET-8500 has BK, PB, C, Y, M, GY
        # Values from HTML: BK=13*2=26, PB=19*2=38, C=20*2=40, Y=23*2=46, M=21*2=42
        assert self.api.get_sensor_value("black") == 26
        assert self.api.get_sensor_value("photoblack") == 38
        assert self.api.get_sensor_value("cyan") == 40
        assert self.api.get_sensor_value("yellow") == 46
        assert self.api.get_sensor_value("magenta") == 42

        # Test waste tank level - ET-8500 waste: height='18' * 2 = 36
        assert self.api.get_sensor_value("clean") == 36

        # Verify HTML structure - should use primary status structure (fieldset)
        fieldset = self.api.soup.find("fieldset", id="PRT_STATUS")
        assert fieldset is not None
        assert "Available" in fieldset.get_text()

        # Verify ink structure - should have 7 tank elements (6 colors + 1 waste)
        tanks = self.api.soup.find_all("li", class_="tank")
        assert len(tanks) == 7

        # Verify color names in order
        color_names = [tank.find("div", class_="clrname") for tank in tanks]
        color_texts = [cn.get_text() if cn else None for cn in color_names]
        expected_colors = ["BK", "PB", "C", "Y", "M", "GY", None]  # Last one is waste tank
        assert color_texts == expected_colors

        # Verify waste tank detection
        waste_tanks = self.api.soup.find_all("div", class_="mbicn")
        assert len(waste_tanks) == 1

    def test_wf3540(self):
        """Test WF-3540 Series HTML fixture."""
        html = self.load_fixture('WF-3540.html')
        self.api.soup = BeautifulSoup(html, "html.parser")
        self.api._extract_device_info()

        # Test printer status (uses fallback structure: div.information)
        status = self.api.get_sensor_value("printer_status")
        assert status == "Available"

        # Test device information extraction
        assert self.api.model == "Epson WF-3540 Series"
        assert self.api.mac_address == "B0:E8:92:05:3D:87"

        # Test ink levels - WF-3540 has BK, M, Y, C
        # Values from HTML: BK=13*2=26, M=36*2=72, Y=20*2=40, C=50*2=100
        assert self.api.get_sensor_value("black") == 26
        assert self.api.get_sensor_value("magenta") == 72
        assert self.api.get_sensor_value("yellow") == 40
        assert self.api.get_sensor_value("cyan") == 100
        assert self.api.get_sensor_value("photoblack") is None
        assert self.api.get_sensor_value("lightcyan") is None
        assert self.api.get_sensor_value("lightmagenta") is None

        # Test waste tank level - WF-3540 waste: height='21' * 2 = 42
        assert self.api.get_sensor_value("clean") == 42

        # Verify HTML structure - should use fallback status structure (div.information)
        info_div = self.api.soup.find("div", class_="information")
        assert info_div is not None
        span = info_div.find("span")
        assert span is not None
        assert span.get_text(strip=True) == "Available."

        # Verify ink structure - should have 5 tank elements (4 colors + 1 waste)
        tanks = self.api.soup.find_all("li", class_="tank")
        assert len(tanks) == 5

        # Verify color names in order
        color_names = [tank.find("div", class_="clrname") for tank in tanks]
        color_texts = [cn.get_text() if cn else None for cn in color_names]
        expected_colors = ["BK", "M", "Y", "C", None]  # Last one is waste tank
        assert color_texts == expected_colors

        # Verify waste tank detection
        waste_tanks = self.api.soup.find_all("div", class_="mbicn")
        assert len(waste_tanks) == 1
