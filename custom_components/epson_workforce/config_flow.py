"""Config flow for Epson WorkForce integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PATH
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .api import EpsonWorkForceAPI

_LOGGER = logging.getLogger(__name__)

DOMAIN = "epson_workforce"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(
            CONF_PATH, default="/PRESENTATION/HTML/TOP/PRTINFO.HTML"
        ): cv.string,
    }
)


def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    host = data[CONF_HOST]
    path = data[CONF_PATH]

    # Test the connection
    api = EpsonWorkForceAPI(host, path)

    if not api.available:
        raise CannotConnect

    # Return info that you want to store in the config entry.
    return {
        "title": f"Epson WorkForce Printer ({host})",
        "name": api.name,
        "model": api.model,
        "mac": api.mac_address,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Epson WorkForce."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._connection_info: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors: dict[str, str] = {}

        try:
            info = await self.hass.async_add_executor_job(validate_input, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            # Check if already configured
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            # Store connection info and move to device name step
            self._connection_info = user_input
            self._connection_info.update(info)

            return await self.async_step_device_name()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_device_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the device name configuration step."""
        if user_input is None:
            # Extract device name from the detected model or use a default
            suggested_name = self._connection_info.get(
                "name", "Epson WorkForce Printer"
            )

            # Create schema with the suggested device name
            device_name_schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default=suggested_name): cv.string,
                }
            )

            return self.async_show_form(
                step_id="device_name",
                data_schema=device_name_schema,
                description_placeholders={"detected_name": suggested_name},
            )

        # User has provided a device name, create the entry
        device_name = user_input[CONF_NAME]

        # Prepare final data for the config entry
        config_data = {
            CONF_HOST: self._connection_info[CONF_HOST],
            CONF_PATH: self._connection_info[CONF_PATH],
            CONF_NAME: device_name,
        }

        return self.async_create_entry(title=device_name, data=config_data)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""
