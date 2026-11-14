"""Base entity for Perific Meter."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device
from .const import DOMAIN
from .coordinator import PerificCoordinator


class PerificEntity(CoordinatorEntity[PerificCoordinator]):
    """Base entity tied to a Perific device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PerificCoordinator, device: Device) -> None:
        """Initialize an entity for a device."""
        super().__init__(coordinator)
        self.device = device
        connections: set[tuple[str, str]] = set()
        if device.mac_address:
            try:
                connections.add((CONNECTION_NETWORK_MAC, format_mac(device.mac_address)))
            except ValueError:
                connections = set()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device.id))},
            connections=connections,
            manufacturer="Perific Technologies AB",
            model=device.model or device.item_type,
            name=device.name,
        )
