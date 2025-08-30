# Tests

This directory contains automated tests for the Epson WorkForce integration.

## Running Tests

To run the tests, make sure you have installed the test dependencies:

```bash
pip install -r requirements-test.txt
```

Then run the tests:

```bash
python -m pytest tests/ -v
```

To run with coverage:

```bash
python -m pytest tests/ --cov=custom_components.epson_workforce --cov-report=term-missing
```

## Test Structure

### `test_api.py`

Comprehensive tests for the `EpsonWorkForceAPI` class using synthetic HTML examples, covering:

- **Printer Status Parsing**: Tests for both primary and fallback HTML structures
  - Primary: `<fieldset id="PRT_STATUS"><ul>...</ul></fieldset>`
  - Fallback: `<div class="information"><p class="clearfix"><span>Available.</span></p></div>`
- **Ink Level Sensors**: Tests for all color cartridge types (BK, C, M, Y, PB, LC, LM)
- **Waste Tank Sensor**: Tests for waste ink level parsing
- **Device Information**: Tests for model and MAC address extraction
- **Error Handling**: Tests for malformed HTML and network failures
- **Edge Cases**: Tests for empty content and missing elements

### `test_fixtures.py`

Real-world tests using actual HTML responses from Epson printers. Each fixture gets one comprehensive test:

- **`test_et8500()`**: Complete test of ET-8500 Series HTML
  - Printer status parsing (primary structure: fieldset)
  - Device info extraction (model, MAC address)
  - Ink levels for all colors (BK, PB, C, Y, M, GY)
  - Waste tank level
  - HTML structure validation
- **`test_wf3540()`**: Complete test of WF-3540 Series HTML
  - Printer status parsing (fallback structure: div.information)
  - Device info extraction (model, MAC address)
  - Ink levels for all colors (BK, M, Y, C)
  - Waste tank level
  - HTML structure validation

### `fixtures/`

Contains real HTML responses from actual Epson printers:

- `ET-8500.html`: HTML response from an ET-8500 Series printer
- `WF-3540.html`: HTML response from a WF-3540 Series printer

The combined tests achieve **96% code coverage** and use both synthetic and real HTML structures to ensure robust parsing.

## Test Coverage

Current coverage: **95%** (85 statements, 4 missed)

The tests cover all major functionality including:
- ✅ HTML parsing for printer status
- ✅ Ink level calculations
- ✅ Device info extraction
- ✅ Error handling
- ✅ Network update methods
- ✅ Edge cases and malformed input
