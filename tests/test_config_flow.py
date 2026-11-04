"""Tests for the config flow, using a real Home Assistant instance."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.epson_workforce.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

MAC = "AA:BB:CC:DD:EE:01"
UID = "aa:bb:cc:dd:ee:01"


def _probe(raw: dict | None):
    """Patch the printer probe to return the given parsed page (or fail)."""
    result = None if raw is None else ("http://h", "/x", raw)
    return patch(
        "custom_components.epson_workforce.config_flow.async_probe_printer",
        AsyncMock(return_value=result),
    )


@pytest.fixture(autouse=True)
def _no_setup():
    """Don't actually set up entries created by the flow."""
    with patch(
        "custom_components.epson_workforce.async_setup_entry", return_value=True
    ):
        yield


async def _start_user(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_uses_mac_as_unique_id(hass):
    result = await _start_user(hass)
    with _probe({"mac_address": MAC}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: " 10.0.0.5 "}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "10.0.0.5"}
    assert result["result"].unique_id == UID


async def test_user_flow_falls_back_to_host_without_mac(hass):
    result = await _start_user(hass)
    with _probe({"model": "Epson WF-2510 Series"}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.0.0.5"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "10.0.0.5"


async def test_user_flow_cannot_connect(hass):
    result = await _start_user(hass)
    with _probe(None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.0.0.5"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_same_printer_new_address_updates_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UID, data={CONF_HOST: "10.0.0.5"})
    entry.add_to_hass(hass)

    result = await _start_user(hass)
    with _probe({"mac_address": MAC}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.0.0.9"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "10.0.0.9"


async def test_user_flow_same_host_aborts_without_probing(hass):
    MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.5", data={CONF_HOST: "10.0.0.5"}
    ).add_to_hass(hass)

    result = await _start_user(hass)
    with _probe(None) as probe:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.0.0.5"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    probe.assert_not_called()


async def _reconfigure(hass, entry, host, raw):
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    with _probe(raw):
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: host}
        )


async def test_reconfigure_changes_host(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UID,
        title="Epson 10.0.0.5",
        data={CONF_HOST: "10.0.0.5"},
    )
    entry.add_to_hass(hass)

    result = await _reconfigure(hass, entry, "10.0.0.9", {"mac_address": MAC})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "10.0.0.9"
    assert entry.title == "Epson 10.0.0.9"
    assert entry.unique_id == UID


async def test_reconfigure_keeps_custom_title(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=UID, title="Office", data={CONF_HOST: "10.0.0.5"}
    )
    entry.add_to_hass(hass)

    await _reconfigure(hass, entry, "10.0.0.9", {"mac_address": MAC})

    assert entry.title == "Office"


async def test_reconfigure_rejects_different_printer(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UID, data={CONF_HOST: "10.0.0.5"})
    entry.add_to_hass(hass)

    result = await _reconfigure(
        hass, entry, "10.0.0.9", {"mac_address": "AA:BB:CC:DD:EE:99"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_printer"
    assert entry.data[CONF_HOST] == "10.0.0.5"


async def test_reconfigure_migrates_host_keyed_entry_to_mac(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.5", data={CONF_HOST: "10.0.0.5"}
    )
    entry.add_to_hass(hass)

    result = await _reconfigure(hass, entry, "10.0.0.9", {"mac_address": MAC})

    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == UID
    assert entry.data[CONF_HOST] == "10.0.0.9"


async def test_reconfigure_same_host_without_mac(hass):
    """Re-entering the same address must not match the entry against itself."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.5", data={CONF_HOST: "10.0.0.5"}
    )
    entry.add_to_hass(hass)

    result = await _reconfigure(hass, entry, "10.0.0.5", {"model": "WF-2510"})

    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "10.0.0.5"


async def test_reconfigure_rejects_address_of_other_entry(hass):
    MockConfigEntry(
        domain=DOMAIN, unique_id="other", data={CONF_HOST: "10.0.0.9"}
    ).add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UID, data={CONF_HOST: "10.0.0.5"})
    entry.add_to_hass(hass)

    result = await _reconfigure(hass, entry, "10.0.0.9", {"mac_address": MAC})

    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "10.0.0.5"


async def test_reconfigure_cannot_connect(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UID, data={CONF_HOST: "10.0.0.5"})
    entry.add_to_hass(hass)

    result = await _reconfigure(hass, entry, "10.0.0.9", None)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
