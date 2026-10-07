"""Read metering and control the outlet through the existing HomeKit connection."""

import asyncio
from datetime import timedelta
import logging
import math

from aiohomekit.exceptions import HomeKitException
from aiohomekit.protocol.statuscodes import HapStatusCode

from homeassistant.components.homekit_controller.const import KNOWN_DEVICES
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .discovery import discover_meters

_LOGGER = logging.getLogger(__name__)


def existing_connection(hass, homekit_entry_id):
    """Return a loaded connection; never load or copy pairing credentials."""
    for connection in hass.data.get(KNOWN_DEVICES, {}).values():
        if (
            connection.config_entry.entry_id == homekit_entry_id
            and connection.config_entry.state is ConfigEntryState.LOADED
        ):
            return connection
    return None


class MeterCoordinator(DataUpdateCoordinator):
    """Use HKDevice.async_update so native polling retains its lock and cache."""

    def __init__(self, hass, entry):
        super().__init__(
            hass,
            _LOGGER,
            name="Incipio CommandKit Metering",
            config_entry=entry,
            update_interval=timedelta(seconds=entry.data["poll_seconds"]),
        )
        self.entry = entry
        self.connection = None
        self.meter = None
        self._owned_keys = set()
        self._meter_keys = set()
        self._control_lock = asyncio.Lock()

    def _find_meter(self, connection):
        return next(
            (
                item
                for item in discover_meters(connection)
                if item.accessory.aid == self.entry.data["aid"]
            ),
            None,
        )

    def release(self):
        """Unregister only characteristics this integration registered."""
        if self.connection is not None:
            self.connection.remove_pollable_characteristics(list(self._owned_keys))
        self._owned_keys.clear()
        self._meter_keys.clear()
        self.connection = None
        self.meter = None

    async def _async_update_data(self):
        connection = existing_connection(self.hass, self.entry.data["homekit_entry_id"])
        if connection is None:
            self.release()
            raise UpdateFailed("The existing HomeKit Device connection is not loaded")

        meter = self._find_meter(connection)
        if meter is None:
            self.release()
            raise UpdateFailed("CMNDKT-004 metering characteristics are not available")

        if (
            connection is not self.connection
            or self.meter is None
            or set(meter.keys) != self._meter_keys
        ):
            self.release()
            self.connection = connection
            self._meter_keys = set(meter.keys)
            self._owned_keys = set(meter.keys) - connection.pollable_characteristics
            connection.add_pollable_characteristics(list(self._owned_keys))
        else:
            # A native entity may have been disabled since the previous refresh.
            missing = set(meter.keys) - connection.pollable_characteristics
            self._owned_keys.update(missing)
            connection.add_pollable_characteristics(list(missing))
        self.meter = meter

        # HKDevice owns request serialization, connection recovery and cache updates.
        # This method only reads registered characteristics; poll_all stays False.
        await connection.async_update()
        if not connection.available:
            raise UpdateFailed("The existing HomeKit Device connection is unavailable")

        values = {}
        for key, char in meter.characteristics.items():
            value = char.value
            values[key] = (
                value
                if char.available
                and char.status == HapStatusCode.SUCCESS
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                else None
            )
        if (char := meter.outlet_on) is not None:
            values["on"] = (
                char.value
                if char.available
                and char.status == HapStatusCode.SUCCESS
                and isinstance(char.value, bool)
                else None
            )
        return values

    async def async_set_on(self, on: bool):
        """Write only the discovered outlet On characteristic, then confirm state."""
        if not isinstance(on, bool):
            raise HomeAssistantError("The outlet state must be a boolean")

        async with self._control_lock:
            connection = existing_connection(self.hass, self.entry.data["homekit_entry_id"])
            if connection is None or not connection.available:
                raise HomeAssistantError("The existing HomeKit Device connection is unavailable")
            meter = self._find_meter(connection)
            if meter is None or meter.outlet_on is None:
                raise HomeAssistantError("A writable outlet On characteristic is not available")

            try:
                await connection.put_characteristics(
                    [(meter.accessory.aid, meter.outlet_on.iid, on)]
                )
            except (HomeKitException, asyncio.TimeoutError) as err:
                raise HomeAssistantError("Unable to change the outlet state") from err

            await self.async_refresh()
            if not self.last_update_success or self.data.get("on") is not on:
                raise HomeAssistantError("The outlet did not confirm the requested state")
