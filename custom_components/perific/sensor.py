"""Sensors for Perific Meter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import Packet, apparent_power_va, total_apparent_power_va
from .coordinator import PerificCoordinator
from .entity import PerificEntity


def _phase_value(values: tuple[float | None, ...], phase: int) -> float | None:
    """Return a phase measurement when it is present."""
    return values[phase] if len(values) > phase else None


@dataclass(frozen=True, kw_only=True)
class PerificSensorDescription(SensorEntityDescription):
    """Describe a Perific measurement."""

    value_fn: Callable[[Packet], float | None]
    use_minute_packet: bool = False


SENSOR_DESCRIPTIONS: tuple[PerificSensorDescription, ...] = (
    *(
        PerificSensorDescription(
            key=f"voltage_l{phase + 1}",
            translation_key=f"voltage_l{phase + 1}",
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            suggested_display_precision=0,
            value_fn=lambda packet, phase=phase: _phase_value(packet.voltage, phase),
        )
        for phase in range(3)
    ),
    *(
        PerificSensorDescription(
            key=f"current_l{phase + 1}",
            translation_key=f"current_l{phase + 1}",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            suggested_display_precision=1,
            value_fn=lambda packet, phase=phase: _phase_value(packet.current, phase),
        )
        for phase in range(3)
    ),
    *(
        PerificSensorDescription(
            key=f"power_l{phase + 1}",
            translation_key=f"power_l{phase + 1}",
            device_class=SensorDeviceClass.APPARENT_POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
            suggested_display_precision=0,
            value_fn=lambda packet, phase=phase: apparent_power_va(packet, phase),
        )
        for phase in range(3)
    ),
    PerificSensorDescription(
        key="power_total",
        translation_key="power_total",
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        suggested_display_precision=0,
        value_fn=total_apparent_power_va,
    ),
    PerificSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda packet: packet.imported_energy,
        use_minute_packet=True,
    ),
    PerificSensorDescription(
        key="energy_export",
        translation_key="energy_export",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda packet: packet.exported_energy,
        use_minute_packet=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PerificCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors for supported Perific phase devices."""
    coordinator = entry.runtime_data
    known_devices: set[int] = set()

    def _new_entities() -> list[PerificSensor]:
        entities: list[PerificSensor] = []
        for device in coordinator.devices.values():
            if device.id in known_devices or device.item_type != "Phase":
                continue
            known_devices.add(device.id)
            entities.extend(
                PerificSensor(coordinator, device, description)
                for description in SENSOR_DESCRIPTIONS
            )
        return entities

    async_add_entities(_new_entities())

    @callback
    def _add_devices_from_update() -> None:
        if entities := _new_entities():
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_devices_from_update))


class PerificSensor(PerificEntity, SensorEntity):
    """A Perific measurement sensor."""

    entity_description: PerificSensorDescription

    def __init__(
        self,
        coordinator: PerificCoordinator,
        device,
        description: PerificSensorDescription,
    ) -> None:
        super().__init__(coordinator, device)
        self.entity_description = description
        self._attr_unique_id = f"{device.id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the latest cached measurement value."""
        if self.coordinator.data is None:
            return None
        item = next(
            (packet for packet in self.coordinator.data if packet.item_id == self.device.id),
            None,
        )
        if item is None:
            return None
        packet = item.minute if self.entity_description.use_minute_packet else item.realtime
        return self.entity_description.value_fn(packet) if packet is not None else None
