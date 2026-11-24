"""Tests for sensor platform setup."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.epson_workforce.sensor import async_setup_entry


def _setup(data: dict):
    """Return (coordinator, entry, add_entities, unload_callbacks) mocks."""
    coordinator = MagicMock()
    coordinator.host = "10.0.1.116"
    coordinator.data = data
    remove_listener = MagicMock()
    coordinator.async_add_listener = MagicMock(return_value=remove_listener)

    unload_callbacks: list = []
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock(side_effect=unload_callbacks.append)

    added: list = []
    add_entities = MagicMock(side_effect=lambda ents: added.extend(ents))
    return coordinator, entry, add_entities, added, unload_callbacks


def _listener(coordinator):
    return coordinator.async_add_listener.call_args.args[0]


def _keys(entities) -> list[str]:
    return [e.entity_description.key for e in entities]


@pytest.mark.asyncio
async def test_initial_sensors_created_for_present_keys():
    coordinator, entry, add_entities, added, _ = _setup(
        {"_model": "Epson ET-4950", "ink_bk": 50, "printer_status": "Available"}
    )

    await async_setup_entry(MagicMock(), entry, add_entities)

    assert sorted(_keys(added)) == ["ink_bk", "last_nozzle_check", "printer_status"]


@pytest.mark.asyncio
async def test_sensors_missing_at_startup_are_added_later():
    """Counters from a supplemental page that failed on the first refresh."""
    coordinator, entry, add_entities, added, _ = _setup({"ink_bk": 50})

    await async_setup_entry(MagicMock(), entry, add_entities)
    assert sorted(_keys(added)) == ["ink_bk", "last_nozzle_check"]

    coordinator.data = {"ink_bk": 49, "total_pages": 1234, "bw_pages": 1000}
    _listener(coordinator)()

    assert sorted(_keys(added)) == [
        "bw_pages",
        "ink_bk",
        "last_nozzle_check",
        "total_pages",
    ]


@pytest.mark.asyncio
async def test_sensors_are_not_added_twice():
    """A key that disappears and comes back must not create a duplicate."""
    coordinator, entry, add_entities, added, _ = _setup(
        {"ink_bk": 50, "total_pages": 1}
    )

    await async_setup_entry(MagicMock(), entry, add_entities)
    listener = _listener(coordinator)

    coordinator.data = {"ink_bk": 50}
    listener()
    coordinator.data = {"ink_bk": 50, "total_pages": 2}
    listener()

    assert sorted(_keys(added)) == ["ink_bk", "last_nozzle_check", "total_pages"]
    # Once for the last-nozzle-check sensor, once for the printer's values.
    assert add_entities.call_count == 2


@pytest.mark.asyncio
async def test_listener_removed_on_unload():
    coordinator, entry, add_entities, _, unload_callbacks = _setup({"ink_bk": 50})

    await async_setup_entry(MagicMock(), entry, add_entities)

    assert unload_callbacks == [coordinator.async_add_listener.return_value]


@pytest.mark.asyncio
async def test_no_data_adds_only_last_nozzle_check():
    """The printer is off at startup: only the sensor Home Assistant records."""
    coordinator, entry, add_entities, added, _ = _setup(None)  # type: ignore[arg-type]

    await async_setup_entry(MagicMock(), entry, add_entities)
    _listener(coordinator)()

    assert _keys(added) == ["last_nozzle_check"]
    assert add_entities.call_count == 1
