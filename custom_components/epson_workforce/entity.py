"""Base entity for the Epson WorkForce integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EpsonCoordinator


class EpsonEntity(CoordinatorEntity[EpsonCoordinator]):
    """An entity belonging to one Epson printer."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EpsonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            # Keyed by entry, not host, so a new printer address keeps the device.
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.data.get("_name") or f"Epson {coordinator.host}",
            manufacturer="Epson",
            model=coordinator.data.get("_model"),
            connections=(
                {(CONNECTION_NETWORK_MAC, format_mac(coordinator.data["_mac"]))}
                if coordinator.data.get("_mac")
                else set()
            ),
        )
