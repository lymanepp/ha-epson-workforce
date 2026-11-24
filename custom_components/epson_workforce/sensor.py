"""Sensor platform for Epson WorkForce integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EpsonConfigEntry
from .const import DOMAIN
from .coordinator import EpsonCoordinator

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    # --- Ink levels ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_bk",
        translation_key="ink_bk",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_pb",
        translation_key="ink_pb",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_gy",
        translation_key="ink_gy",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_m",
        translation_key="ink_m",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_c",
        translation_key="ink_c",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_y",
        translation_key="ink_y",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_lc",
        translation_key="ink_lc",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_lm",
        translation_key="ink_lm",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- Maintenance ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="clean",
        translation_key="clean",
        icon="mdi:broom",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- Status ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="printer_status",
        translation_key="printer_status",
        icon="mdi:printer",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="scanner_status",
        translation_key="scanner_status",
        icon="mdi:scanner",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="fax_status",
        translation_key="fax_status",
        icon="mdi:fax",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- Network (main page) — disabled by default ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ip_address",
        translation_key="ip_address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="signal_strength",
        translation_key="signal_strength",
        icon="mdi:wifi-strength-4",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ssid",
        translation_key="ssid",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_direct_connection_method",
        translation_key="wifi_direct_connection_method",
        icon="mdi:connection",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # --- Page counters ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="total_pages",
        translation_key="total_pages",
        icon="mdi:file-document-multiple",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="bw_pages",
        translation_key="bw_pages",
        icon="mdi:file-document-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="color_pages",
        translation_key="color_pages",
        icon="mdi:file-document",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="bw_copies",
        translation_key="bw_copies",
        icon="mdi:content-copy",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="color_copies",
        translation_key="color_copies",
        icon="mdi:content-copy",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="bw_scans",
        translation_key="bw_scans",
        icon="mdi:scanner",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="color_scans",
        translation_key="color_scans",
        icon="mdi:scanner",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="first_print_date",
        translation_key="first_print_date",
        icon="mdi:calendar",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # --- Extended network (supplemental) — disabled by default ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_speed",
        translation_key="wifi_speed",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_channel",
        translation_key="wifi_channel",
        icon="mdi:access-point",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_mode",
        translation_key="wifi_mode",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_security",
        translation_key="wifi_security",
        icon="mdi:shield-wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # --- Hardware status (supplemental) — disabled by default ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_hw_status",
        translation_key="wifi_hw_status",
        icon="mdi:wifi-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpsonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors from a config entry.

    A sensor is created once its value first appears. Supplemental pages can
    fail transiently, so values missing from the first refresh may arrive
    later; checking on every update makes sure those sensors still get created.
    """
    coordinator: EpsonCoordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def _async_add_new_sensors() -> None:
        data = coordinator.data or {}
        new = [
            desc for desc in SENSOR_TYPES if desc.key in data and desc.key not in added
        ]
        if not new:
            return
        added.update(desc.key for desc in new)
        async_add_entities(EpsonSensor(coordinator, entry, desc) for desc in new)

    _async_add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_sensors))


class EpsonSensor(CoordinatorEntity[EpsonCoordinator], SensorEntity):
    """A single Epson printer sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EpsonCoordinator,
        entry: EpsonConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
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

    @property
    def native_value(self):
        """Return current sensor value from coordinator data."""
        return self.coordinator.data.get(self.entity_description.key)
