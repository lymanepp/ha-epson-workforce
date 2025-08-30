"""Test the Epson WorkForce API."""

import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock

from custom_components.epson_workforce.api import EpsonWorkForceAPI

class TestEpsonWorkForceAPI:
    """Test class for EpsonWorkForceAPI."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock the update method to avoid network calls
        with patch.object(EpsonWorkForceAPI, 'update'):
            self.api = EpsonWorkForceAPI("192.168.1.100", "/PRESENTATION/HTML/TOP/PRTINFO.HTML")

    def test_printer_status_primary_structure(self):
        """Test printer status parsing with primary HTML structure."""
        # Test case 1: Available status
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul>Available.</ul>
                </fieldset>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Available"

        # Test case 2: Ready status
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul>Ready</ul>
                </fieldset>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Ready"

        # Test case 3: Error status with period removal
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul>Paper jam.</ul>
                </fieldset>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Paper jam"

        # Test case 4: Long status (should not remove period)
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul>This is a very long status message that exceeds thirty characters.</ul>
                </fieldset>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "This is a very long status message that exceeds thirty characters."

    def test_printer_status_fallback_structure(self):
        """Test printer status parsing with fallback HTML structure."""
        # Test case 1: Standard fallback structure
        html = """
        <html>
            <body>
                <div class="information">
                    <p class="clearfix">
                        <span>Available.</span>
                    </p>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Available"

        # Test case 2: Fallback without clearfix class
        html = """
        <html>
            <body>
                <div class="information">
                    <span>Ready</span>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Ready"

        # Test case 3: Multiple spans - should pick first one
        html = """
        <html>
            <body>
                <div class="information">
                    <p class="clearfix">
                        <span>Printing.</span>
                        <span>Page 1 of 5</span>
                    </p>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Printing"

    def test_printer_status_priority_order(self):
        """Test that primary structure takes priority over fallback."""
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul>Primary Status</ul>
                </fieldset>
                <div class="information">
                    <p class="clearfix">
                        <span>Fallback Status</span>
                    </p>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Primary Status"

    def test_printer_status_missing_elements(self):
        """Test printer status with missing or malformed elements."""
        # Test case 1: Missing fieldset
        html = """
        <html>
            <body>
                <div class="information">
                    <p class="clearfix">
                        <span>Available.</span>
                    </p>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Available"

        # Test case 2: Empty fieldset, fallback works
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                </fieldset>
                <div class="information">
                    <span>Fallback Works</span>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Fallback Works"

        # Test case 3: Neither structure present
        html = """
        <html>
            <body>
                <div>Some other content</div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Unknown"

    def test_ink_level_sensors(self):
        """Test ink level sensor parsing."""
        # Test case: Standard ink tank structure
        html = """
        <html>
            <body>
                <ul>
                    <li class="tank">
                        <div class="clrname">BK</div>
                        <div class="tank">
                            <div height="45"></div>
                        </div>
                    </li>
                    <li class="tank">
                        <div class="clrname">C</div>
                        <div class="tank">
                            <div height="30"></div>
                        </div>
                    </li>
                    <li class="tank">
                        <div class="clrname">M</div>
                        <div class="tank">
                            <div height="25"></div>
                        </div>
                    </li>
                    <li class="tank">
                        <div class="clrname">Y</div>
                        <div class="tank">
                            <div height="40"></div>
                        </div>
                    </li>
                </ul>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")

        # Test black ink
        black_level = self.api.get_sensor_value("black")
        assert black_level == 90  # 45 * 2

        # Test cyan ink
        cyan_level = self.api.get_sensor_value("cyan")
        assert cyan_level == 60  # 30 * 2

        # Test magenta ink
        magenta_level = self.api.get_sensor_value("magenta")
        assert magenta_level == 50  # 25 * 2

        # Test yellow ink
        yellow_level = self.api.get_sensor_value("yellow")
        assert yellow_level == 80  # 40 * 2

    def test_photo_ink_sensors(self):
        """Test photo ink sensor parsing (PB, LC, LM)."""
        html = """
        <html>
            <body>
                <ul>
                    <li class="tank">
                        <div class="clrname">PB</div>
                        <div class="tank">
                            <div height="35"></div>
                        </div>
                    </li>
                    <li class="tank">
                        <div class="clrname">LC</div>
                        <div class="tank">
                            <div height="20"></div>
                        </div>
                    </li>
                    <li class="tank">
                        <div class="clrname">LM</div>
                        <div class="tank">
                            <div height="15"></div>
                        </div>
                    </li>
                </ul>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")

        # Test photo black ink
        pb_level = self.api.get_sensor_value("photoblack")
        assert pb_level == 70  # 35 * 2

        # Test light cyan ink
        lc_level = self.api.get_sensor_value("lightcyan")
        assert lc_level == 40  # 20 * 2

        # Test light magenta ink
        lm_level = self.api.get_sensor_value("lightmagenta")
        assert lm_level == 30  # 15 * 2

    def test_waste_tank_sensor(self):
        """Test waste tank sensor parsing."""
        html = """
        <html>
            <body>
                <ul>
                    <li class="tank">
                        <div class="mbicn">Waste</div>
                        <div class="tank">
                            <div height="10"></div>
                        </div>
                    </li>
                </ul>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")

        # Test waste tank level
        waste_level = self.api.get_sensor_value("clean")
        assert waste_level == 20  # 10 * 2

    def test_invalid_sensor_types(self):
        """Test handling of invalid sensor types."""
        html = """<html><body></body></html>"""
        self.api.soup = BeautifulSoup(html, "html.parser")

        # Test unknown sensor type
        result = self.api.get_sensor_value("unknown_sensor")
        assert result == 0

        # Test None sensor type
        result = self.api.get_sensor_value(None)
        assert result == 0

    def test_malformed_ink_structure(self):
        """Test handling of malformed ink level HTML."""
        # Test case 1: Missing height attribute
        html = """
        <html>
            <body>
                <ul>
                    <li class="tank">
                        <div class="clrname">BK</div>
                        <div class="tank">
                            <div></div>
                        </div>
                    </li>
                </ul>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        black_level = self.api.get_sensor_value("black")
        assert black_level == 0

        # Test case 2: Missing tank div
        html = """
        <html>
            <body>
                <ul>
                    <li class="tank">
                        <div class="clrname">BK</div>
                    </li>
                </ul>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        black_level = self.api.get_sensor_value("black")
        assert black_level == 0

    def test_device_info_extraction(self):
        """Test device information extraction."""
        html = """
        <html>
            <head>
                <title>ET-8500 Series</title>
            </head>
            <body>
                <div>
                    <p>MAC Address: 12:34:56:78:90:AB</p>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        self.api._extract_device_info()

        assert self.api.model == "Epson ET-8500 Series"
        assert self.api.mac_address == "12:34:56:78:90:AB"

    def test_device_info_extraction_variations(self):
        """Test device information extraction with various formats."""
        # Test MAC address with different formatting
        html = """
        <html>
            <head>
                <title>WF-3720 Series</title>
            </head>
            <body>
                <div>
                    Some text
                    MAC Address : AA:BB:CC:DD:EE:FF
                    More text
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        self.api._extract_device_info()

        assert self.api.model == "Epson WF-3720 Series"
        assert self.api.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_exception_handling(self):
        """Test exception handling in various scenarios."""
        # Test printer status with None soup
        self.api.soup = None
        status = self.api.get_sensor_value("printer_status")
        assert status == "Unknown"

        # Test ink level with None soup
        ink_level = self.api.get_sensor_value("black")
        assert ink_level == 0

        # Test device info extraction with None soup
        self.api.soup = None
        self.api._extract_device_info()
        assert self.api.model == "WorkForce Printer"
        assert self.api.mac_address is None

    def test_update_method_failure(self):
        """Test API update method failure handling."""
        # Test that update method sets available to False on exception
        with patch('urllib.request.urlopen', side_effect=Exception("Network error")):
            api = EpsonWorkForceAPI("192.168.1.100", "/test")
            assert api.available is False

    def test_update_method_success(self):
        """Test API update method success."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html><body><title>Test</title></body></html>"

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_response
            api = EpsonWorkForceAPI("192.168.1.100", "/test")
            assert api.available is True
            assert api.soup is not None

    def test_edge_case_empty_status(self):
        """Test edge cases with empty or whitespace status."""
        # Test empty ul content - returns "Unknown" since ul exists but has no text
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul></ul>
                </fieldset>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Unknown"

        # Test whitespace-only content - returns "Unknown" after strip()
        html = """
        <html>
            <body>
                <fieldset id="PRT_STATUS">
                    <ul>   </ul>
                </fieldset>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Unknown"

        # Test empty span in fallback structure
        html = """
        <html>
            <body>
                <div class="information">
                    <p class="clearfix">
                        <span></span>
                    </p>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Unknown"

        # Test whitespace-only span in fallback structure
        html = """
        <html>
            <body>
                <div class="information">
                    <span>   </span>
                </div>
            </body>
        </html>
        """
        self.api.soup = BeautifulSoup(html, "html.parser")
        status = self.api.get_sensor_value("printer_status")
        assert status == "Unknown"
