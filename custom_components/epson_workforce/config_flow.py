"""Config flow for Epson WorkForce integration."""

from __future__ import annotations

from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
import voluptuous as vol

from .const import DOMAIN
from .coordinator import async_probe_printer

_TIMEOUT = aiohttp.ClientTimeout(total=8)


def _unique_id(host: str, raw: dict[str, Any]) -> str:
    """Return the printer's MAC, or the host for models that don't show one."""
    mac = raw.get("mac_address")
    return format_mac(mac) if mac else host


def _schema(host: str | None = None) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_HOST, default=host or vol.UNDEFINED): str})


class EpsonConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Epson WorkForce."""

    VERSION = 1

    async def _async_probe(self, host: str) -> dict[str, Any] | None:
        """Return the parsed status page, or None if no printer answers."""
        session = async_get_clientsession(self.hass)
        result = await async_probe_printer(session, host, timeout=_TIMEOUT)
        return None if result is None else result[2]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            self._async_abort_entries_match({CONF_HOST: host})
            raw = await self._async_probe(host)
            if raw is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(_unique_id(host, raw))
                # Same printer at a new address: update the existing entry.
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"Epson {host}",
                    data={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="user", data_schema=_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of an existing printer."""
        entry = self._get_reconfigure_entry()
        old_host: str = entry.data[CONF_HOST]
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if host != old_host:
                self._async_abort_entries_match({CONF_HOST: host})
            raw = await self._async_probe(host)
            if raw is None:
                errors["base"] = "cannot_connect"
            else:
                unique_id = _unique_id(host, raw)
                await self.async_set_unique_id(unique_id, raise_on_progress=False)
                if entry.unique_id in (None, old_host):
                    # Host-keyed entry: adopt the new ID unless another entry
                    # already owns it.
                    other = self.hass.config_entries.async_entry_for_domain_unique_id(
                        DOMAIN, unique_id
                    )
                    if other is not None and other.entry_id != entry.entry_id:
                        return self.async_abort(reason="already_configured")
                else:
                    # MAC-keyed entry: it must still be the same printer.
                    self._abort_if_unique_id_mismatch(reason="wrong_printer")

                title = entry.title
                if title == f"Epson {old_host}":
                    title = f"Epson {host}"
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=title,
                    data_updates={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=_schema(old_host), errors=errors
        )
