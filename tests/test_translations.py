"""Tests for the translation files and translated entity names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_HOST
from homeassistant.helpers.typing import UNDEFINED
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.epson_workforce.const import DOMAIN
from custom_components.epson_workforce.sensor import SENSOR_TYPES

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN
LANGUAGES = sorted(p.stem for p in (COMPONENT / "translations").glob("*.json"))


def _load(name: str) -> dict[str, Any]:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def _keys(data: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        if isinstance(value, dict):
            keys |= _keys(value, f"{prefix}{key}.")
        else:
            keys.add(f"{prefix}{key}")
    return keys


def test_strings_match_english_translation():
    assert _load("strings.json") == _load("translations/en.json")


@pytest.mark.parametrize("language", LANGUAGES)
def test_translation_is_complete(language: str):
    assert _keys(_load(f"translations/{language}.json")) == _keys(_load("strings.json"))


def test_every_sensor_name_is_translatable():
    names = _load("strings.json")["entity"]["sensor"]
    for description in SENSOR_TYPES:
        assert description.name is UNDEFINED, description.key
        assert description.translation_key in names, description.key


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize(
    ("language", "entity_id", "friendly_name"),
    [
        ("en", "sensor.epson0c85bf_ink_level_black", "EPSON0C85BF Ink level Black"),
        (
            "de",
            "sensor.epson0c85bf_tintenstand_schwarz",
            "EPSON0C85BF Tintenstand Schwarz",
        ),
    ],
)
async def test_sensor_name_follows_language(
    hass, language: str, entity_id: str, friendly_name: str
):
    hass.config.language = language
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "10.0.0.5"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.epson_workforce.coordinator.EpsonCoordinator._async_update_data",
        return_value={"_name": "EPSON0C85BF", "ink_bk": 50},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["friendly_name"] == friendly_name
