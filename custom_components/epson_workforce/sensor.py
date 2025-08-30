"""Support for Epson WorkForce Printer."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import DOMAIN
from .api import EpsonWorkForceAPI

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(  # type: ignore[call-arg]
        key="black",
        name="Ink level Black",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="photoblack",
        name="Ink level Photoblack",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="magenta",
        name="Ink level Magenta",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="cyan",
        name="Ink level Cyan",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="yellow",
        name="Ink level Yellow",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="lightcyan",
        name="Ink level Light Cyan",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="lightmagenta",
        name="Ink level Light Magenta",
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="clean",
        name="Cleaning level",
        icon="mdi:broom",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="printer_status",
        name="Printer Status",
        icon="mdi:printer",
    ),
)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epson WorkForce sensors from a config entry."""
    api = hass.data[DOMAIN][entry.entry_id]

    # Create update coordinator
    coordinator = EpsonWorkForceDataUpdateCoordinator(hass, api)

    # Fetch initial data so we have data when entities are added
    await coordinator.async_config_entry_first_refresh()

    # Detect which sensors are actually available on this printer
    available_sensors = await hass.async_add_executor_job(
        _detect_available_sensors, api
    )

    _LOGGER.info(
        "Detected %d available sensors for printer %s: %s",
        len(available_sensors),
        entry.data["host"],
        ", ".join(available_sensors)
    )

    # Create only sensors that are available on this printer
    sensors = [
        EpsonPrinterCartridge(coordinator, description, entry.data["host"])
        for description in SENSOR_TYPES
        if description.key in available_sensors
    ]

    _LOGGER.info(
        "Created %d sensor entities for printer %s",
        len(sensors),
        entry.data["host"],
    )
    async_add_entities(sensors, True)


def _detect_available_sensors(api: EpsonWorkForceAPI) -> list[str]:
    """Detect which sensors are available on this specific printer."""
    available_sensors = []

    for description in SENSOR_TYPES:
        sensor_key = description.key
        value = api.get_sensor_value(sensor_key)

        # Consider a sensor available if:
        # - It returns a non-None value
        # - For numeric sensors: value > 0 or value == 0 (some tanks might be empty)
        # - For string sensors (like printer_status): any string value
        if value is not None and isinstance(value, str | int | float):
            available_sensors.append(sensor_key)

    return available_sensors


def _raise_printer_unavailable() -> None:
    """Raise UpdateFailed for printer unavailable."""
    msg = "Printer is not available"
    raise UpdateFailed(msg)


class EpsonWorkForceDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, api: EpsonWorkForceAPI) -> None:
        """Initialize."""
        self.api = api
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            await self.hass.async_add_executor_job(self.api.update)
            if not self.api.available:
                _raise_printer_unavailable()
        except Exception as exception:
            raise UpdateFailed(exception) from exception
        else:
            return True


class EpsonPrinterCartridge(CoordinatorEntity, SensorEntity):
    """Representation of a cartridge sensor."""

    def __init__(
        self,
        coordinator: EpsonWorkForceDataUpdateCoordinator,
        description: SensorEntityDescription,
        host: str,
    ) -> None:
        """Initialize a cartridge sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._host = host
        self._host_clean = host.replace(".", "_").replace(":", "_")

    @property
    def device_info(self) -> DeviceInfo | None:  # type: ignore[override]
        """Return device information for this printer."""
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=f"Epson WorkForce Printer ({self._host})",
            manufacturer="Epson",
            model=self.coordinator.api.model,
        )

        # Add MAC address as a connection identifier
        if self.coordinator.api.mac_address:
            device_info["connections"] = {
                ("mac", self.coordinator.api.mac_address.lower())
            }

        return device_info

    @property
    def unique_id(self) -> str | None:  # type: ignore[override]
        """Return a unique ID for this sensor."""
        return f"epson_workforce_{self._host_clean}_{self.entity_description.key}"

    @property
    def native_value(self):
        """Return the state of the device."""
        return self.coordinator.api.get_sensor_value(self.entity_description.key)

    @property
    def available(self) -> bool:  # type: ignore[override]
        """Could the device be accessed during the last update call."""
        return self.coordinator.last_update_success and self.coordinator.api.available
