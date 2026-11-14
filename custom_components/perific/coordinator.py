"""Data coordinator for Perific Meter."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Client,
    Device,
    DevicePackets,
    PerificAuthenticationError,
    PerificError,
    call_with_token_refresh,
)
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class PerificCoordinator(DataUpdateCoordinator[list[DevicePackets]]):
    """Coordinate Perific API updates for one config entry."""

    def __init__(self, hass: HomeAssistant, client: Client, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        self.token: str | None = None
        self.devices: dict[int, Device] = {}

    async def async_authenticate(self, username: str, password: str) -> None:
        """Authenticate; credentials are only retained by the config entry."""
        self.token = (await self.client.authenticate(username, password)).token

    async def _async_setup(self) -> None:
        """Load devices before entities are created."""
        try:
            await self._async_refresh_devices()
        except PerificAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except PerificError as err:
            raise UpdateFailed(f"Unable to load Perific devices: {err}") from err

    async def _async_update_data(self) -> list[DevicePackets]:
        """Fetch current measurement data."""
        try:
            self.token, packets = await call_with_token_refresh(
                self.token,
                self.client.get_latest_packets,
                self._async_refresh_token,
            )
            if any(packet.item_id not in self.devices for packet in packets):
                await self._async_refresh_devices()
        except PerificAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except PerificError as err:
            raise UpdateFailed(f"Unable to update Perific data: {err}") from err
        return packets

    async def _async_refresh_token(self) -> str:
        """Authenticate again with the password stored on the config entry."""
        data = self.config_entry.data
        await self.async_authenticate(data["username"], data["password"])
        if self.token is None:
            raise PerificAuthenticationError("Perific authentication returned no token")
        return self.token

    async def _async_refresh_devices(self) -> None:
        self.token, devices = await call_with_token_refresh(
            self.token,
            self.client.get_devices,
            self._async_refresh_token,
        )
        self.devices = {device.id: device for device in devices}
