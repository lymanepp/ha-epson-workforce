"""Support for Epson WorkForce Printer."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_MONITORED_CONDITIONS,
    CONF_PATH,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import voluptuous as vol

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
MONITORED_CONDITIONS: list[str] = [desc.key for desc in SENSOR_TYPES]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PATH): cv.string,
        vol.Required(CONF_MONITORED_CONDITIONS): vol.All(
            cv.ensure_list, [vol.In(MONITORED_CONDITIONS)]
        ),
    }
)
SCAN_INTERVAL = timedelta(minutes=60)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the cartridge sensor."""
    host = config.get(CONF_HOST)
    path = config.get(CONF_PATH, "/PRESENTATION/HTML/TOP/PRTINFO.HTML")

    api = EpsonWorkForceAPI(host, path)
    if not api.available:
        raise PlatformNotReady

    sensors = [
        EpsonPrinterCartridge(api, description)
        for description in SENSOR_TYPES
        if description.key in config[CONF_MONITORED_CONDITIONS]
    ]

    add_devices(sensors, True)


class EpsonPrinterCartridge(SensorEntity):
    """Representation of a cartridge sensor."""

    def __init__(
        self, api: EpsonWorkForceAPI, description: SensorEntityDescription
    ) -> None:
        """Initialize a cartridge sensor."""
        self._api = api
        self.entity_description = description

    @property
    def native_value(self):
        """Return the state of the device."""
        return self._api.get_sensor_value(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Could the device be accessed during the last update call."""
        return self._api.available

    def update(self) -> None:
        """Get the latest data from the Epson printer."""
        self._api.update()
