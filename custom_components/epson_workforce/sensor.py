"""Sensor platform for Epson WorkForce integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EpsonConfigEntry
from .const import DOMAIN
from .coordinator import EpsonCoordinator

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    # --- Ink levels ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_bk",
        name="Ink level Black",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_pb",
        name="Ink level Photoblack",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_gy",
        name="Ink level Gray",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_m",
        name="Ink level Magenta",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_c",
        name="Ink level Cyan",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_y",
        name="Ink level Yellow",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_lc",
        name="Ink level Light Cyan",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ink_lm",
        name="Ink level Light Magenta",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    # --- Maintenance ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="clean",
        name="Cleaning level",
        icon="mdi:broom",
        native_unit_of_measurement=PERCENTAGE,
    ),
    # --- Status ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="printer_status",
        name="Printer Status",
        icon="mdi:printer",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="scanner_status",
        name="Scanner Status",
        icon="mdi:scanner",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="fax_status",
        name="Fax Status",
        icon="mdi:fax",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- Network (main page) — disabled by default ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ip_address",
        name="IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="signal_strength",
        name="Signal Strength",
        icon="mdi:wifi-strength-4",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="ssid",
        name="WiFi Network",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_direct_connection_method",
        name="WiFi Direct Connection",
        icon="mdi:connection",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # --- Page counters ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="total_pages",
        name="Total Pages Printed",
        icon="mdi:file-document-multiple",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="bw_pages",
        name="B&W Pages Printed",
        icon="mdi:file-document-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="color_pages",
        name="Color Pages Printed",
        icon="mdi:file-document",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="bw_scans",
        name="B&W Scans",
        icon="mdi:scanner",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="color_scans",
        name="Color Scans",
        icon="mdi:scanner",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="first_print_date",
        name="First Print Date",
        icon="mdi:calendar",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # --- Extended network (supplemental) — disabled by default ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_speed",
        name="WiFi Speed",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_channel",
        name="WiFi Channel",
        icon="mdi:access-point",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_mode",
        name="WiFi Mode",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_security",
        name="WiFi Security",
        icon="mdi:shield-wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # --- Hardware status (supplemental) — disabled by default ---
    SensorEntityDescription(  # type: ignore[call-arg]
        key="wifi_hw_status",
        name="WiFi Hardware Status",
        icon="mdi:wifi-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpsonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: EpsonCoordinator = entry.runtime_data
    async_add_entities(
        EpsonSensor(coordinator, entry, desc)
        for desc in SENSOR_TYPES
        if desc.key in coordinator.data
    )


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
            identifiers={(DOMAIN, coordinator.host)},
            name=coordinator.data.get("_name") or f"Epson {coordinator.host}",
            manufacturer="Epson",
            model=coordinator.data.get("_model"),
            connections=(
                {("mac", coordinator.data["_mac"].lower())}
                if coordinator.data.get("_mac")
                else set()
            ),
        )

    @property
    def native_value(self):
        """Return current sensor value from coordinator data."""
        return self.coordinator.data.get(self.entity_description.key)
