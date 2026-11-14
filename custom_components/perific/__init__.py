"""The Perific Meter integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Client
from .api import PerificAuthenticationError, PerificConnectionError, PerificError
from .const import API_URL, PLATFORMS
from .coordinator import PerificCoordinator

type PerificConfigEntry = ConfigEntry[PerificCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PerificConfigEntry) -> bool:
    """Set up Perific Meter from a config entry."""
    coordinator = PerificCoordinator(
        hass, Client(async_get_clientsession(hass), API_URL), entry
    )
    try:
        await coordinator.async_authenticate(
            entry.data["username"], entry.data["password"]
        )
    except PerificAuthenticationError as err:
        from homeassistant.config_entries import ConfigEntryAuthFailed

        raise ConfigEntryAuthFailed from err
    except (PerificConnectionError, PerificError) as err:
        from homeassistant.exceptions import ConfigEntryNotReady

        raise ConfigEntryNotReady from err
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PerificConfigEntry) -> bool:
    """Unload a Perific config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
