"""Tests for the keep-print-head-fresh blueprint, using a real Home Assistant."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
import shutil
from unittest.mock import patch

from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_ON
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.epson_workforce.const import DOMAIN
from custom_components.epson_workforce.maintenance import PrinterCommandError

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

BLUEPRINT = (
    Path(__file__).parent.parent
    / "blueprints/automation/epson_workforce/keep_print_head_fresh.yaml"
)
NOW = "2026-11-22 18:00:00+00:00"  # 10:00 in the test time zone (US/Pacific)
BUTTON = "button.epson123456_nozzle_check"
SENSOR = "sensor.epson123456_last_nozzle_check"
AUTOMATION = "automation.keep_print_head_fresh"
RESULT_EVENT = "nozzle_check_result"
DATA = {"_model": "EPSON ET-8500 Series", "_name": "EPSON123456", "ink_bk": 50}
_UPDATE = (
    "custom_components.epson_workforce.coordinator.EpsonCoordinator._async_update_data"
)
_PRINT = "custom_components.epson_workforce.button.async_print_nozzle_check"


def _result_actions(result: str) -> list[dict]:
    return [{"event": RESULT_EVENT, "event_data": {"result": result}}]


@pytest.fixture
async def printer(hass, tmp_path, freezer):
    """Set up the integration and an automation from the blueprint."""
    freezer.move_to(NOW)
    hass.config.config_dir = str(tmp_path)
    target = tmp_path / "blueprints/automation/epson_workforce" / BLUEPRINT.name
    target.parent.mkdir(parents=True)
    shutil.copy(BLUEPRINT, target)

    entry = MockConfigEntry(domain=DOMAIN, title="Epson", data={CONF_HOST: "10.0.0.5"})
    entry.add_to_hass(hass)
    # Stays patched for the whole test: firing time changes also runs polling.
    update = patch(_UPDATE, return_value=DATA)
    update.start()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await async_setup_component(
        hass,
        AUTOMATION_DOMAIN,
        {
            AUTOMATION_DOMAIN: {
                "alias": "Keep print head fresh",
                "use_blueprint": {
                    "path": f"epson_workforce/{BLUEPRINT.name}",
                    "input": {
                        "nozzle_check_button": BUTTON,
                        "last_nozzle_check_sensor": SENSOR,
                        "success_actions": _result_actions("success"),
                        "failure_actions": _result_actions("failure"),
                    },
                },
            }
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get(AUTOMATION).state == STATE_ON
    yield entry

    # Detach the daily time trigger so no timer outlives the test.
    await hass.services.async_call(
        AUTOMATION_DOMAIN, "turn_off", {ATTR_ENTITY_ID: AUTOMATION}, blocking=True
    )
    await hass.config_entries.async_unload(entry.entry_id)
    update.stop()


async def _set_last_check(hass, entry, days_ago: int) -> None:
    coordinator = entry.runtime_data
    coordinator.last_nozzle_check = dt_util.utcnow() - timedelta(days=days_ago)
    coordinator.async_update_listeners()
    await hass.async_block_till_done()


async def _start(hass) -> None:
    await hass.services.async_call(
        AUTOMATION_DOMAIN,
        "trigger",
        {ATTR_ENTITY_ID: AUTOMATION, "skip_condition": False},
        blocking=False,
    )


async def _run(hass) -> None:
    await _start(hass)
    await hass.async_block_till_done()


async def test_runs_when_never_checked(hass, printer):
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_awaited_once()
    assert [e.data["result"] for e in events] == ["success"]


async def test_skips_when_checked_recently(hass, printer):
    await _set_last_check(hass, printer, days_ago=6)
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_not_awaited()
    assert events == []


async def test_runs_on_the_day_the_interval_ends(hass, printer):
    # A few minutes later than now on the calendar day seven days ago still counts.
    coordinator = printer.runtime_data
    coordinator.last_nozzle_check = (
        dt_util.utcnow() - timedelta(days=7) + timedelta(minutes=5)
    )
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_awaited_once()


async def test_failure_runs_failure_actions(hass, printer):
    await _set_last_check(hass, printer, days_ago=8)
    before = hass.states.get(SENSOR).state
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(
        _PRINT, side_effect=PrinterCommandError("connection refused")
    ) as print_check:
        await _start(hass)
        # The run now waits for the sensor until the wait times out. Time is
        # frozen, so step the loop and fire the timeout once the wait has begun.
        for _ in range(100):
            await asyncio.sleep(0)
            if print_check.await_count:
                async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
            if events:
                break
        await hass.async_block_till_done()

    assert [e.data["result"] for e in events] == ["failure"]
    assert hass.states.get(SENSOR).state == before


async def test_daily_time_trigger(hass, printer, freezer):
    with patch(_PRINT) as print_check:
        freezer.move_to("2026-11-23 18:00:00+00:00")
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    print_check.assert_awaited_once()
