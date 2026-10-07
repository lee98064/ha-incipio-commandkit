"""Voltage, current and power from the existing HomeKit metering service."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity

DESCRIPTIONS = (
    SensorEntityDescription(
        key="voltage",
        name="Incipio Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current",
        name="Incipio Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="power",
        name="Incipio Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create three entities attached to the existing HomeKit device."""
    async_add_entities(
        MeterSensor(entry.runtime_data, description) for description in DESCRIPTIONS
    )


class MeterSensor(CoordinatorEntity, SensorEntity):
    """Read a value refreshed by the shared HomeKit connection."""

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.connection.unique_id}_{coordinator.entry.data['aid']}_{description.key}"
        )
        self._attr_device_info = coordinator.connection.device_info_for_accessory(
            coordinator.meter.accessory
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self.entity_description.key)
