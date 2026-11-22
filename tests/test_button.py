"""Tests for the nozzle check button, using a real Home Assistant."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.epson_workforce.const import DOMAIN
from custom_components.epson_workforce.maintenance import PrinterCommandError

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

HOST = "10.0.0.5"
DATA = {
    "_model": "EPSON ET-8500 Series",
    "_name": "EPSON123456",
    "_mac": "AA:BB:CC:DD:EE:01",
    "ink_bk": 50,
}
_UPDATE = (
    "custom_components.epson_workforce.coordinator.EpsonCoordinator._async_update_data"
)
_PRINT = "custom_components.epson_workforce.button.async_print_nozzle_check"


async def _setup(hass, data=DATA, side_effect=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:01",
        title="Epson",
        data={CONF_HOST: HOST},
    )
    entry.add_to_hass(hass)
    with patch(_UPDATE, return_value=data, side_effect=side_effect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _button_entity_id(hass, entry) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{entry.entry_id}_nozzle_check"
    )


async def _press(hass, entity_id: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def test_button_created_on_printer_device(hass):
    entry = await _setup(hass)

    entity_id = _button_entity_id(hass, entry)
    assert entity_id == "button.epson123456_nozzle_check"
    reg_entry = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(reg_entry.device_id)
    assert device.identifiers == {(DOMAIN, entry.entry_id)}
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE


async def test_press_sends_nozzle_check(hass):
    entry = await _setup(hass)

    with patch(_PRINT) as print_check:
        await _press(hass, _button_entity_id(hass, entry))
    print_check.assert_awaited_once_with(HOST)


async def test_press_failure_raises(hass):
    entry = await _setup(hass)

    with (
        patch(_PRINT, side_effect=PrinterCommandError("connection refused")),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await _press(hass, _button_entity_id(hass, entry))
    assert exc_info.value.translation_key == "nozzle_check_failed"
    assert exc_info.value.translation_placeholders == {
        "host": HOST,
        "error": "connection refused",
    }


def _sensor_entity_id(hass, entry) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_last_nozzle_check"
    )


async def test_successful_press_updates_last_nozzle_check(hass, freezer):
    freezer.move_to("2026-11-22 10:00:00+00:00")
    entry = await _setup(hass)
    sensor_id = _sensor_entity_id(hass, entry)
    assert sensor_id == "sensor.epson123456_last_nozzle_check"
    assert hass.states.get(sensor_id).state == STATE_UNKNOWN

    with patch(_PRINT):
        await _press(hass, _button_entity_id(hass, entry))

    assert hass.states.get(sensor_id).state == "2026-11-22T10:00:00+00:00"


async def test_failed_press_keeps_last_nozzle_check(hass):
    entry = await _setup(hass)
    sensor_id = _sensor_entity_id(hass, entry)

    with (
        patch(_PRINT, side_effect=PrinterCommandError("connection refused")),
        pytest.raises(HomeAssistantError),
    ):
        await _press(hass, _button_entity_id(hass, entry))

    assert hass.states.get(sensor_id).state == STATE_UNKNOWN


async def test_last_nozzle_check_restored(hass):
    last = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.epson123456_last_nozzle_check", last.isoformat()),
                {
                    "native_value": {
                        "__type": "<class 'datetime.datetime'>",
                        "isoformat": last.isoformat(),
                    },
                    "native_unit_of_measurement": None,
                },
            )
        ],
    )
    entry = await _setup(hass)

    assert entry.runtime_data.last_nozzle_check == last
    sensor_id = _sensor_entity_id(hass, entry)
    assert hass.states.get(sensor_id).state == last.isoformat()


async def test_last_nozzle_check_available_while_printer_offline(hass, freezer):
    freezer.move_to("2026-11-22 10:00:00+00:00")
    entry = await _setup(hass)
    with patch(_PRINT):
        await _press(hass, _button_entity_id(hass, entry))

    with patch(_UPDATE, side_effect=UpdateFailed("offline")):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(_button_entity_id(hass, entry)).state == STATE_UNAVAILABLE
    sensor_id = _sensor_entity_id(hass, entry)
    assert hass.states.get(sensor_id).state == "2026-11-22T10:00:00+00:00"


async def test_button_created_once_printer_answers(hass):
    entry = await _setup(hass, side_effect=UpdateFailed("offline"))
    assert _button_entity_id(hass, entry) is None

    coordinator = entry.runtime_data
    with patch(_UPDATE, return_value=DATA):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert _button_entity_id(hass, entry) is not None

    with patch(_UPDATE, return_value=DATA):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    buttons = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == BUTTON_DOMAIN
    ]
    assert len(buttons) == 1
