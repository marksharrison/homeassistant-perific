"""Diagnostics support for Perific Meter."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import PerificCoordinator

TO_REDACT = {"username", "password", "mac_address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[PerificCoordinator]
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "devices": async_redact_data(
            [
                {
                    "id": device.id,
                    "name": device.name,
                    "item_type": device.item_type,
                    "model": device.model,
                    "system_name": device.system_name,
                    "mac_address": device.mac_address,
                }
                for device in coordinator.devices.values()
            ],
            TO_REDACT,
        ),
        "last_update_success": coordinator.last_update_success,
        "device_packet_ids": [packet.item_id for packet in coordinator.data or []],
    }
