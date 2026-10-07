"""Incipio CommandKit metering for an already paired HomeKit device."""

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import MeterCoordinator, existing_connection
from .discovery import discover_meters

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    """Reuse a loaded HomeKit Device entry and expose read-only sensors."""
    connection = existing_connection(hass, entry.data["homekit_entry_id"])
    if connection is None:
        raise ConfigEntryNotReady("Wait for the existing HomeKit Device connection")
    if not any(meter.accessory.aid == entry.data["aid"] for meter in discover_meters(connection)):
        raise ConfigEntryNotReady("The selected CMNDKT-004 meter is not available")

    coordinator = MeterCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        coordinator.release()
        await coordinator.async_shutdown()
        raise
    return True


async def async_unload_entry(hass, entry):
    """Remove these sensors without closing or unpairing the HomeKit device."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        entry.runtime_data.release()
        return True
    return False
