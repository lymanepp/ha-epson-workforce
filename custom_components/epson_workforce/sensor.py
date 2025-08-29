"""Support for Epson WorkForce Printer."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
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
        icon="mdi:water",
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(  # type: ignore[call-arg]
        key="printer_status",
        name="Printer Status",
        icon="mdi:printer",
    ),
)

SCAN_INTERVAL = timedelta(minutes=60)


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

    # Create all sensor entities
    sensors = [
        EpsonPrinterCartridge(coordinator, description, entry.data["host"])
        for description in SENSOR_TYPES
    ]

    async_add_entities(sensors, True)


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
                raise UpdateFailed("Printer is not available")
            return True
        except Exception as exception:
            raise UpdateFailed(exception) from exception


class EpsonPrinterCartridge(CoordinatorEntity, SensorEntity):
    """Representation of a cartridge sensor."""

    def __init__(
        self, coordinator: EpsonWorkForceDataUpdateCoordinator, description: SensorEntityDescription, host: str
    ) -> None:
        """Initialize a cartridge sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._host = host
        self._host_clean = host.replace(".", "_").replace(":", "_")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this printer."""
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=f"Epson WorkForce Printer ({self._host})",
            manufacturer="Epson",
            model=self.coordinator.api.model,
        )

        # Add MAC address as a connection identifier
        if self.coordinator.api.mac_address:
            device_info["connections"] = {("mac", self.coordinator.api.mac_address)}

        return device_info

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this sensor."""
        return f"epson_workforce_{self._host_clean}_{self.entity_description.key}"

    @property
    def native_value(self):
        """Return the state of the device."""
        return self.coordinator.api.get_sensor_value(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Could the device be accessed during the last update call."""
        return self.coordinator.last_update_success and self.coordinator.api.available
