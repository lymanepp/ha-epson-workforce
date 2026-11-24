"""Button platform for Epson WorkForce integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EpsonConfigEntry
from .const import DOMAIN
from .coordinator import EpsonCoordinator
from .entity import EpsonEntity
from .maintenance import PrinterCommandError, async_print_nozzle_check


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpsonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons from a config entry.

    Like the sensors, the button is created once the printer has answered, so
    its device gets the printer's name and model.
    """
    coordinator: EpsonCoordinator = entry.runtime_data
    added = False

    @callback
    def _async_add_button() -> None:
        nonlocal added
        if added or coordinator.data is None:
            return
        added = True
        async_add_entities([EpsonNozzleCheckButton(coordinator, entry)])

    _async_add_button()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_button))


class EpsonNozzleCheckButton(EpsonEntity, ButtonEntity):
    """Print the printer's nozzle check pattern."""

    _attr_translation_key = "nozzle_check"
    _attr_icon = "mdi:printer-eye"

    def __init__(self, coordinator: EpsonCoordinator, entry: EpsonConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_nozzle_check"

    async def async_press(self) -> None:
        """Send the nozzle check job to the printer."""
        try:
            await async_print_nozzle_check(self.coordinator.host)
        except PrinterCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="nozzle_check_failed",
                translation_placeholders={
                    "host": self.coordinator.host,
                    "error": str(err),
                },
            ) from err
        # The button's own state is set before the press runs, even when it
        # fails, so successful runs are tracked separately for automations.
        self.coordinator.last_nozzle_check = dt_util.utcnow()
        self.coordinator.async_update_listeners()
