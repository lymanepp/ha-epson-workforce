"""The Epson WorkForce integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import EpsonCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type EpsonConfigEntry = ConfigEntry[EpsonCoordinator]

_PLACEHOLDER_MAC_CONNECTIONS = {
    (dr.CONNECTION_NETWORK_MAC, "00:00:00:00:00:00"),
    (dr.CONNECTION_NETWORK_MAC, "ff:ff:ff:ff:ff:ff"),
}


async def async_setup_entry(hass: HomeAssistant, entry: EpsonConfigEntry) -> bool:
    """Set up Epson WorkForce from a config entry."""
    _async_migrate_device(hass, entry)
    coordinator = EpsonCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    _async_migrate_unique_id(hass, entry, coordinator)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EpsonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_migrate_device(hass: HomeAssistant, entry: EpsonConfigEntry) -> None:
    """Re-key this entry's device from the printer host to the entry ID.

    Devices used to be identified by host, so changing the printer's address
    would have created a second device. Also drop placeholder MAC connections
    that some firmware reports, since they would merge unrelated printers.
    """
    dev_reg = dr.async_get(hass)
    new_identifier = (DOMAIN, entry.entry_id)
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    migrated = {d.id for d in devices if new_identifier in d.identifiers}
    for device in devices:
        old = {i for i in device.identifiers if i[0] == DOMAIN and i != new_identifier}
        bad_connections = device.connections & _PLACEHOLDER_MAC_CONNECTIONS
        if not old and not bad_connections:
            continue
        if old and migrated - {device.id}:
            _LOGGER.debug("Device for %s already migrated; skipping", entry.title)
            continue
        _LOGGER.debug("Migrating device identity for %s", entry.title)
        dev_reg.async_update_device(
            device.id,
            new_identifiers=(device.identifiers - old) | {new_identifier},
            new_connections=device.connections - bad_connections,
        )


@callback
def _async_migrate_unique_id(
    hass: HomeAssistant, entry: EpsonConfigEntry, coordinator: EpsonCoordinator
) -> None:
    """Switch a host-based entry unique ID to the printer's MAC address.

    Older entries used the host as unique ID, which breaks when the printer
    gets a new address. Only host-based IDs are migrated; an entry already
    keyed by MAC is never silently re-pointed to a different printer.
    """
    mac = coordinator.data.get("_mac")
    if not mac or entry.unique_id not in (None, entry.data[CONF_HOST]):
        return
    unique_id = dr.format_mac(mac)
    other = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
    if other is not None and other.entry_id != entry.entry_id:
        _LOGGER.warning(
            "Printer at %s (MAC %s) is also configured as '%s'; remove one of"
            " the duplicate entries",
            entry.data[CONF_HOST],
            unique_id,
            other.title,
        )
        return
    _LOGGER.debug("Changing unique ID of %s to MAC %s", entry.title, unique_id)
    hass.config_entries.async_update_entry(entry, unique_id=unique_id)
