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
