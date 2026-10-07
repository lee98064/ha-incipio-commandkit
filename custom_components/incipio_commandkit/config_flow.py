"""Select an existing CMNDKT-004 HomeKit Device connection."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.homekit_controller.const import KNOWN_DEVICES
from homeassistant.config_entries import ConfigEntryState

from .discovery import DOMAIN, discover_meters


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure metering without a pairing code or network discovery."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        targets = {}
        for connection in self.hass.data.get(KNOWN_DEVICES, {}).values():
            if connection.config_entry.state is not ConfigEntryState.LOADED:
                continue
            for meter in discover_meters(connection):
                key = f"{connection.config_entry.entry_id}:{meter.accessory.aid}"
                targets[key] = (connection, meter)
        if not targets:
            return self.async_abort(reason="no_devices")

        errors = {}
        if user_input is not None:
            if user_input["device"] not in targets:
                errors["base"] = "device_unavailable"
            else:
                connection, meter = targets[user_input["device"]]
                await self.async_set_unique_id(f"{connection.unique_id}_{meter.accessory.aid}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=meter.accessory.name or "Incipio CommandKit",
                    data={
                        "homekit_entry_id": connection.config_entry.entry_id,
                        "aid": meter.accessory.aid,
                        "poll_seconds": user_input["poll_seconds"],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): vol.In(
                        {key: f"{meter.accessory.name} (CMNDKT-004, AID {meter.accessory.aid})" for key, (_, meter) in targets.items()}
                    ),
                    vol.Required("poll_seconds", default=10): vol.In([5, 10]),
                }
            ),
            errors=errors,
        )
