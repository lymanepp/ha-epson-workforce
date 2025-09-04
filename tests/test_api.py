"""Tests for EpsonWorkForceAPI using only the public API (no soup poking)."""

from unittest.mock import MagicMock, patch

from custom_components.epson_workforce.api import EpsonWorkForceAPI


# Helper: build an API instance whose update() reads our provided HTML
def api_from_html(html: str) -> EpsonWorkForceAPI:
    mock_resp = MagicMock()
    mock_resp.read.return_value = html.encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        api = EpsonWorkForceAPI("127.0.0.1", "/test")
        api.update()
        api._ensure_parsed()
    return api


class TestEpsonWorkForceAPI:
    def test_update_method_failure(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            api = EpsonWorkForceAPI("127.0.0.1", "/test")
            assert api.available is False

    def test_update_method_success(self):
        api = api_from_html("<html><body><title>Test</title></body></html>")
        assert api.available is True
        # soup is an implementation detail; we only check API behavior here
        assert isinstance(api.model, str)

    # -------------------------
    # Status parsing
    # -------------------------
    def test_printer_status_priority_order(self):
        html = """
        <html>
          <body>
            <fieldset id="PRT_STATUS"><ul>Primary Status</ul></fieldset>
            <div class="information"><p class="clearfix"><span>Fallback Status</span></p></div>
          </body>
        </html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Primary Status"

    def test_printer_status_missing_elements(self):
        html = """
        <html>
          <body>
            <div class="information"><p class="clearfix"><span>Available.</span></p></div>
          </body>
        </html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Available"

        html = """
        <html>
          <body>
            <fieldset id="PRT_STATUS"></fieldset>
            <div class="information"><span>Fallback Works</span></div>
          </body>
        </html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Fallback Works"

        html = "<html><body><div>Other content</div></body></html>"
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Unknown"

    def test_edge_case_empty_status(self):
        html = (
            "<html><body><fieldset id='PRT_STATUS'><ul></ul></fieldset></body></html>"
        )
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Unknown"

        html = "<html><body><fieldset id='PRT_STATUS'><ul>   </ul></fieldset></body></html>"
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Unknown"

        html = """
        <html><body><div class="information"><p class="clearfix"><span></span></p></div></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Unknown"

        html = (
            "<html><body><div class='information'><span>   </span></div></body></html>"
        )
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Unknown"

    def test_strip_trailing_period_short_status(self):
        html = """
        <html><body><div class="information"><p class="clearfix"><span>Ready.</span></p></div></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Ready"

    # -------------------------
    # Invalid/malformed inputs
    # -------------------------
    def test_invalid_sensor_types(self):
        html = "<html><body></body></html>"
        api = api_from_html(html)
        assert api.get_sensor_value("unknown_sensor") is None
        assert api.get_sensor_value(None) is None  # type: ignore[arg-type]

    def test_malformed_ink_structure(self):
        # Missing height attribute
        html = """
        <html><body><ul>
          <li class="tank"><div class="clrname">BK</div><div class="tank"><div></div></div></li>
        </ul></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("BK") is None

        # Missing inner tank
        html = """
        <html><body><ul>
          <li class="tank"><div class="clrname">BK</div></li>
        </ul></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("BK") is None

    # -------------------------
    # Device info extraction
    # -------------------------
    def test_device_info_extraction(self):
        html = """
        <html>
          <head><title>ET-8500 Series</title></head>
          <body><div><p>MAC Address: 12:34:56:78:90:AB</p></div></body>
        </html>
        """
        api = api_from_html(html)
        # model/mac exposed via public properties
        assert api.model == "Epson ET-8500 Series"
        assert api.mac_address == "12:34:56:78:90:AB"

    def test_device_info_extraction_variations(self):
        html = """
        <html>
          <head><title>WF-3720 Series</title></head>
          <body>
            Some text
            MAC Address : AA:BB:CC:DD:EE:FF
            More text
          </body>
        </html>
        """
        api = api_from_html(html)
        assert api.model == "Epson WF-3720 Series"
        assert api.mac_address == "AA:BB:CC:DD:EE:FF"

    # -------------------------
    # Exception / None soup
    # -------------------------
    def test_exception_handling(self):
        # Simulate offline by constructing, then breaking update()
        with patch("urllib.request.urlopen", side_effect=Exception("offline")):
            api = EpsonWorkForceAPI("127.0.0.1", "/test")
        assert api.get_sensor_value("printer_status") == "Unknown"
        assert api.get_sensor_value("BK") is None
        assert api.model == "WorkForce Printer"
        assert api.mac_address is None

    def test_unexpected_html_structure(self):
        # No clrname but has a height → not attributable to a color key
        html = """
        <html><body><ul>
          <li class="tank"><div class="tank"><div style="height:25px;"></div></div></li>
        </ul></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("BK") is None

        # Wrong class names
        html = """
        <html><body><ul>
          <li class="container"><div class="colorname">BK</div><div class="bar"><div style="height:30px;"></div></div></li>
        </ul></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("BK") is None

        # Non-numeric height
        html = """
        <html><body><ul>
          <li class="tank"><div class="clrname">BK</div><div class="tank"><div style="height:abc;"></div></div></li>
        </ul></body></html>
        """
        api = api_from_html(html)
        assert api.get_sensor_value("BK") is None

        # Missing everything
        html = "<html><body></body></html>"
        api = api_from_html(html)
        assert api.get_sensor_value("printer_status") == "Unknown"


class TestDiagnosticSensors:
    """Test diagnostic sensor conditional creation logic."""

    def test_diagnostic_sensors_with_network_data(self):
        """Test that network diagnostic sensors are created when data is available."""
        from custom_components.epson_workforce.sensor import _detect_available_sensors

        # Mock data with network information
        api = EpsonWorkForceAPI("192.168.1.100", "/test")
        api._data = {
            "network": {
                "Signal Strength": "Excellent",
                "SSID": "TestNetwork",
            },
            "inks": {"BK": 50, "M": 30},
            "printer_status": "Available",
        }

        available_sensors = _detect_available_sensors(api)

        # Network diagnostics should be available
        assert "signal_strength" in available_sensors
        assert "ssid" in available_sensors
        assert "ip_address" in available_sensors

        # Verify values are not "Unknown"
        assert api.get_sensor_value("signal_strength") == "Excellent"
        assert api.get_sensor_value("ssid") == "TestNetwork"

    def test_diagnostic_sensors_without_network_data(self):
        """Test that network diagnostic sensors are not created when data is missing."""
        from custom_components.epson_workforce.sensor import _detect_available_sensors

        # Mock data without network information
        api = EpsonWorkForceAPI("192.168.1.100", "/test")
        api._data = {
            "inks": {"BK": 50, "M": 30},
            "printer_status": "Available",
            "maintenance_box": 20
            # No network data
        }

        available_sensors = _detect_available_sensors(api)

        # Network diagnostics should NOT be available
        assert "signal_strength" not in available_sensors
        assert "ssid" not in available_sensors
        assert "wifi_direct_connection_method" not in available_sensors

        # IP address should still be available
        assert "ip_address" in available_sensors

        # Basic sensors should be available
        assert "BK" in available_sensors
        assert "M" in available_sensors
        assert "printer_status" in available_sensors

        # Verify that diagnostic sensors would return "Unknown"
        assert api.get_sensor_value("signal_strength") == "Unknown"
        assert api.get_sensor_value("ssid") == "Unknown"
        assert api.get_sensor_value("wifi_direct_connection_method") == "Unknown"

    def test_diagnostic_sensors_with_wifi_direct_data(self):
        """Test that WiFi Direct diagnostic sensors are created when data is available."""
        from custom_components.epson_workforce.sensor import _detect_available_sensors

        # Mock data with WiFi Direct information
        api = EpsonWorkForceAPI("192.168.1.100", "/test")
        api._data = {
            "wifi_direct": {
                "Connection Method": "Not Set",
            },
            "inks": {"BK": 50, "M": 30},
            "printer_status": "Available",
        }

        available_sensors = _detect_available_sensors(api)

        # WiFi Direct diagnostics should be available
        assert "wifi_direct_connection_method" in available_sensors
        assert "ip_address" in available_sensors

        # Verify values are not "Unknown"
        assert api.get_sensor_value("wifi_direct_connection_method") == "Not Set"

    def test_diagnostic_sensors_with_minimal_data(self):
        """Test that only basic sensors are created with minimal data."""
        from custom_components.epson_workforce.sensor import _detect_available_sensors

        # Mock data with only basic information
        api = EpsonWorkForceAPI("192.168.1.100", "/test")
        api._data = {
            "inks": {"BK": 50},
            "printer_status": "Available",
        }

        available_sensors = _detect_available_sensors(api)

        # Only basic sensors should be available
        assert "ip_address" in available_sensors
        assert "BK" in available_sensors
        assert "printer_status" in available_sensors

        # No diagnostic sensors should be available
        assert "signal_strength" not in available_sensors
        assert "ssid" not in available_sensors
        assert "wifi_direct_connection_method" not in available_sensors
