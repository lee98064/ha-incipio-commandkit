"""Outlet control using the existing HomeKit Device pairing."""

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Add a control only when the standard outlet On characteristic is writable."""
    coordinator = entry.runtime_data
    if coordinator.meter.outlet_on is not None:
        async_add_entities([OutletSwitch(coordinator)])


class OutletSwitch(CoordinatorEntity, SwitchEntity):
    """Control the outlet and expose its confirmed HomeKit state."""

    _attr_name = "Incipio Outlet"
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.connection.unique_id}_{coordinator.entry.data['aid']}_outlet"
        )
        self._attr_device_info = coordinator.connection.device_info_for_accessory(
            coordinator.meter.accessory
        )

    @property
    def available(self):
        return super().available and self.is_on is not None

    @property
    def is_on(self):
        return self.coordinator.data.get("on")

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_on(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_on(False)
