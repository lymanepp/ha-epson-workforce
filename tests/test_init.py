"""Tests for entry setup and identity migration, using a real Home Assistant."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.epson_workforce.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

HOST = "10.0.0.5"
MAC = "AA:BB:CC:DD:EE:01"
UID = "aa:bb:cc:dd:ee:01"


def _data(mac: str | None = MAC) -> dict:
    data = {"_model": "Epson ET-4950 Series", "_name": "EPSON0C85BF", "ink_bk": 50}
    if mac:
        data["_mac"] = mac
    return data


async def _setup(hass, entry, data):
    with patch(
        "custom_components.epson_workforce.coordinator.EpsonCoordinator._async_update_data",
        return_value=data,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _entry(hass, unique_id=HOST, host=HOST) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        title=f"Epson {host}",
        data={CONF_HOST: host},
    )
    entry.add_to_hass(hass)
    return entry


async def test_new_device_is_keyed_by_entry(hass):
    entry = _entry(hass, unique_id=UID)
    await _setup(hass, entry, _data())

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {(DOMAIN, entry.entry_id)}
    assert (dr.CONNECTION_NETWORK_MAC, UID) in device.connections


async def test_host_unique_id_migrates_to_mac(hass):
    entry = _entry(hass)
    await _setup(hass, entry, _data())
    assert entry.unique_id == UID


async def test_host_unique_id_kept_without_mac(hass):
    entry = _entry(hass)
    await _setup(hass, entry, _data(mac=None))
    assert entry.unique_id == HOST


async def test_mac_unique_id_never_repointed(hass):
    entry = _entry(hass, unique_id="aa:bb:cc:dd:ee:99")
    await _setup(hass, entry, _data())
    assert entry.unique_id == "aa:bb:cc:dd:ee:99"


async def test_duplicate_entry_is_not_migrated(hass, caplog):
    _entry(hass, unique_id=UID, host="10.0.0.9")
    entry = _entry(hass)
    await _setup(hass, entry, _data())
    assert entry.unique_id == HOST
    assert "duplicate" in caplog.text


async def test_legacy_device_is_rekeyed_and_keeps_entities(hass):
    """A device keyed by host is reused, not duplicated, after upgrade."""
    entry = _entry(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, HOST)},
        connections={(dr.CONNECTION_NETWORK_MAC, "00:00:00:00:00:00")},
    )
    ent = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_ink_bk",
        config_entry=entry,
        device_id=old.id,
    )

    # No MAC on the page: nothing else could link the old device to the new one.
    await _setup(hass, entry, _data(mac=None))

    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert [d.id for d in devices] == [old.id]
    assert devices[0].identifiers == {(DOMAIN, entry.entry_id)}
    assert devices[0].connections == set()
    assert ent_reg.async_get(ent.entity_id).device_id == old.id


async def test_other_entrys_identifier_survives_migration(hass):
    """Older HA can share one device between two entries for the same printer.

    Migrating one entry must not remove the other entry's identifier, or the
    two entries keep swapping the device's identifier on every restart.
    """
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="printer.local",
        data={CONF_HOST: "printer.local"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    other.add_to_hass(hass)
    entry = _entry(hass)
    dev_reg = dr.async_get(hass)
    shared = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, HOST), (DOMAIN, other.entry_id)},
        connections={(dr.CONNECTION_NETWORK_MAC, UID)},
    )

    await _setup(hass, entry, _data())
    expected = {(DOMAIN, entry.entry_id), (DOMAIN, other.entry_id)}
    assert dev_reg.async_get(shared.id).identifiers == expected

    with patch(
        "custom_components.epson_workforce.coordinator.EpsonCoordinator._async_update_data",
        return_value=_data(),
    ):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert dev_reg.async_get(shared.id).identifiers == expected
