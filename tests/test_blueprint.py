"""Tests for the keep-print-head-fresh blueprint, using a real Home Assistant."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from unittest.mock import AsyncMock, patch

from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
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

type SetupPrinter = Callable[..., Awaitable[MockConfigEntry]]


def _result_actions(result: str) -> list[dict]:
    return [{"event": RESULT_EVENT, "event_data": {"result": result}}]


def _restore_last_check(hass, entry: MockConfigEntry, last: datetime) -> None:
    """Leave the registry and restore cache as an earlier run would have."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="EPSON123456",
    )
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_last_nozzle_check",
        suggested_object_id="epson123456_last_nozzle_check",
        config_entry=entry,
        device_id=device.id,
    )
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(SENSOR, last.isoformat()),
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


@pytest.fixture
async def setup_printer(hass, tmp_path, freezer) -> AsyncGenerator[SetupPrinter]:
    """Return a helper that sets up the integration and the blueprint automation."""
    freezer.move_to(NOW)
    hass.config.config_dir = str(tmp_path)
    target = tmp_path / "blueprints/automation/epson_workforce" / BLUEPRINT.name
    target.parent.mkdir(parents=True)
    shutil.copy(BLUEPRINT, target)
    entries: list[MockConfigEntry] = []
    # Stays patched for the whole test: firing time changes also runs polling.
    update = AsyncMock(return_value=DATA)
    patcher = patch(_UPDATE, update)
    patcher.start()

    async def _setup(
        *, online: bool = True, last_check: datetime | None = None
    ) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN, title="Epson", data={CONF_HOST: "10.0.0.5"}
        )
        entry.add_to_hass(hass)
        entries.append(entry)
        if last_check is not None:
            _restore_last_check(hass, entry, last_check)
        if not online:
            update.side_effect = UpdateFailed("offline")
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
        return entry

    yield _setup

    # Detach the daily time trigger so no timer outlives the test.
    if hass.states.get(AUTOMATION) is not None:
        await hass.services.async_call(
            AUTOMATION_DOMAIN, "turn_off", {ATTR_ENTITY_ID: AUTOMATION}, blocking=True
        )
    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)
    patcher.stop()


@pytest.fixture
async def printer(setup_printer: SetupPrinter) -> MockConfigEntry:
    """Set up an online printer and the blueprint automation."""
    return await setup_printer()


async def _set_last_check(hass, entry, last: datetime) -> None:
    coordinator = entry.runtime_data
    coordinator.last_nozzle_check = last
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


async def _run_until_wait_times_out(hass, print_check, events, during_wait=None):
    """Run the automation through a wait that is not satisfied.

    The run waits for the sensor until the wait times out. Time is frozen, so
    step the loop and fire the timeout once the press has happened.
    """
    await _start(hass)
    for _ in range(100):
        await asyncio.sleep(0)
        if print_check.await_count:
            if during_wait is not None:
                during_wait()
                during_wait = None
                continue
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
        if events:
            break
    await hass.async_block_till_done()


async def test_runs_when_never_checked(hass, printer):
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_awaited_once()
    assert [e.data["result"] for e in events] == ["success"]


async def test_skips_when_checked_recently(hass, printer):
    await _set_last_check(hass, printer, dt_util.utcnow() - timedelta(days=6))
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_not_awaited()
    assert events == []


async def test_runs_on_the_day_the_interval_ends(hass, printer):
    # A few minutes later than now on the calendar day seven days ago still counts.
    await _set_last_check(
        hass, printer, dt_util.utcnow() - timedelta(days=7) + timedelta(minutes=5)
    )
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_awaited_once()
    assert [e.data["result"] for e in events] == ["success"]


async def test_failure_runs_failure_actions(hass, printer):
    await _set_last_check(hass, printer, dt_util.utcnow() - timedelta(days=8))
    before = hass.states.get(SENSOR).state
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(
        _PRINT, side_effect=PrinterCommandError("connection refused")
    ) as print_check:
        await _run_until_wait_times_out(hass, print_check, events)

    assert [e.data["result"] for e in events] == ["failure"]
    assert hass.states.get(SENSOR).state == before


async def test_sensor_unavailable_during_wait_is_not_success(hass, printer):
    """An integration reload while waiting must not count as a sent check."""
    await _set_last_check(hass, printer, dt_util.utcnow() - timedelta(days=8))
    events = async_capture_events(hass, RESULT_EVENT)
    with patch(
        _PRINT, side_effect=PrinterCommandError("connection refused")
    ) as print_check:
        await _run_until_wait_times_out(
            hass,
            print_check,
            events,
            during_wait=lambda: hass.states.async_set(SENSOR, STATE_UNAVAILABLE),
        )

    assert [e.data["result"] for e in events] == ["failure"]


async def test_recent_check_respected_when_starting_offline(hass, setup_printer):
    """The printer is off at startup; a recent saved check is not due."""
    last = dt_util.utcnow() - timedelta(days=2)
    await setup_printer(online=False, last_check=last)
    assert hass.states.get(SENSOR).state == last.isoformat()

    events = async_capture_events(hass, RESULT_EVENT)
    with patch(_PRINT) as print_check:
        await _run(hass)

    print_check.assert_not_awaited()
    assert events == []


async def test_daily_time_trigger(hass, printer, freezer):
    with patch(_PRINT) as print_check:
        freezer.move_to("2026-11-23 18:00:00+00:00")
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    print_check.assert_awaited_once()
