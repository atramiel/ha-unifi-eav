"""UniFi EAV Bridge control for Home Assistant."""

from __future__ import annotations

from aiohttp import CookieJar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EavClient
from .const import CONF_SITE, DEFAULT_SITE, DEFAULT_VERIFY_SSL
from .coordinator import EavCoordinator

PLATFORMS = [Platform.SELECT, Platform.SWITCH, Platform.CAMERA]

type EavConfigEntry = ConfigEntry[EavCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EavConfigEntry) -> bool:
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    # Own session + unsafe cookie jar: UniFi OS sets its auth cookie for an IP host.
    session = async_create_clientsession(
        hass, verify_ssl=verify_ssl, cookie_jar=CookieJar(unsafe=True)
    )
    client = EavClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_SITE, DEFAULT_SITE),
        verify_ssl,
    )
    coordinator = EavCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EavConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
