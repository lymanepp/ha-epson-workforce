"""Test real fixtures with EpsonHTMLParser."""

import os
from typing import Any

import pytest

from custom_components.epson_workforce.api import EpsonHTMLParser

# ---- Discover all fixtures ----
HERE = os.path.dirname(__file__)
FIXTURES_DIR = os.path.join(HERE, "fixtures")
ALL_FIXTURES = sorted(
    f for f in os.listdir(FIXTURES_DIR) if f.lower().endswith(".html")
)

# ---- Per-file expectations (only list what you care to assert) ----
# Any keys omitted will be skipped (defaults handle the rest).
EXPECTATIONS: dict[str, dict[str, Any]] = {
    "ET-8500.html": {
        "name": "EPSON0C9E89",
        "model": "Epson ET-8500 Series",
        "printer_status": "Available",
        "mac_address": "DC:CD:2F:0C:9E:89",
        "maintenance_box": 36,
        "inks": {  # subset OK
            "BK": 26,
            "PB": 38,
            "C": 40,
            "Y": 46,
            "M": 42,
            "GY": 44,
        },
        "network": {
            "Signal Strength": "Excellent",
            "SSID": "The\xa0Bell\xa0Tower\xa0-\xa0IoT",
        },
        "wifi_direct": {
            "Connection Method": "Not Set",
        },
    },
    "L6270.html": {
        "name": "EPSON7E2246",
        "model": "Epson L6270 Series",
        "printer_status": "Available",
        "mac_address": "68:55:D4:7E:22:46",
        "maintenance_box": 90,
        "inks": {
            "BK": 68,
            "M": 80,
            "Y": 80,
            "C": 80,
        },
        "network": {
            "Signal Strength": "Excellent",
            "SSID": "eLeCtRoN-Lan-SD",
        },
        "wifi_direct": {
            "Connection Method": "Not Set",
        },
    },
    "WF-3540.html": {
        "name": "EPSON053D87",
        "model": "Epson WF-3540 Series",
        "printer_status": "Available",
        "mac_address": "B0:E8:92:05:3D:87",
        "maintenance_box": 42,
        "inks": {
            "BK": 26,
            "M": 72,
            "Y": 40,
            "C": 100,
        },
        "network": {
            "Signal Strength": "Excellent",
            "SSID": "CHAOS",
        },
        # No wifi_direct section - this model doesn't support it
    },
    "WF-7720.html": {
        "name": "EPSON06274A",
        "model": "Epson WF-7720 Series",
        "printer_status": "Available",
        "mac_address": "38:1A:52:06:27:4A",
        "maintenance_box": 88,
        "inks": {
            "BK": 96,
            "M": 88,
            "Y": 76,
            "C": 64,
        },
        "network": {
            "Signal Strength": "Excellent",
            "SSID": "knappe-home",
        },
        "wifi_direct": {
            "Connection Method": "Not Set",
        },
    },
}


def _read_fixture_text(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8", errors="ignore") as f:
        return f.read()


def _assert_subset(
    actual: dict[str, Any], expected_subset: dict[str, Any], path: str = ""
):
    """Assert that all items in expected_subset appear (recursively) in actual."""
    for k, v in expected_subset.items():
        assert k in actual, f"Missing key at {path or '.'}: {k}"
        if isinstance(v, dict):
            assert isinstance(actual[k], dict), f"Expected dict at {path}/{k}"
            _assert_subset(actual[k], v, f"{path}/{k}" if path else k)
        else:
            assert (
                actual[k] == v
            ), f"Mismatch at {path}/{k if path else k}: {actual[k]!r} != {v!r}"


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_each_fixture_parses_and_matches_expectations(fixture_name: str):
    """
    Tests that the HTML fixture for a given printer/scanner parses correctly and matches
    expected values.
    """
    html_text = _read_fixture_text(fixture_name)
    parser = EpsonHTMLParser(html_text, source=fixture_name)
    data = parser.parse()

    # Always do basic sanity checks
    assert data, "Parser returned empty result"
    assert isinstance(data, dict), "Parser did not return a dict"
    assert "model" in data
    assert "printer_status" in data or "scanner_status" in data
    assert "inks" in data
    assert isinstance(data["inks"], dict)

    # Apply per-file expectations if present
    spec = EXPECTATIONS.get(fixture_name)
    if spec:
        # Flatten top-level fields we care about (excluding nested dicts)
        flat_expect = {
            k: v for k, v in spec.items() if k not in ("inks", "network", "wifi_direct")
        }
        if flat_expect:
            _assert_subset(data, flat_expect)

        # For inks, we assert a subset (fixture may have extra colors)
        if "inks" in spec:
            _assert_subset(data.get("inks", {}), spec["inks"], path="inks")

        # For network data, we assert a subset
        if "network" in spec:
            network_data = data.get("network", {})
            network_spec = spec["network"]
            _assert_subset(network_data, network_spec, path="network")

        # For wifi_direct data, we assert a subset
        if "wifi_direct" in spec:
            _assert_subset(
                data.get("wifi_direct", {}), spec["wifi_direct"], path="wifi_direct"
            )
