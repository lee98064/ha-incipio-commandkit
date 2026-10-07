"""Offline boundary tests; no Home Assistant server or outlet is contacted."""

from enum import Enum
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "incipio_commandkit"

# Load only discovery/coordinator under a test package, avoiding HA startup.
package = ModuleType("commandkit_under_test")
package.__path__ = [str(COMPONENT)]
sys.modules[package.__name__] = package


class EntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


class UpdateFailed(Exception):
    pass


class CoordinatorStub:
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass


for name, attrs in {
    "homeassistant.components.homekit_controller.const": {"KNOWN_DEVICES": "homekit_controller-devices"},
    "homeassistant.config_entries": {"ConfigEntryState": EntryState},
    "homeassistant.helpers.update_coordinator": {"DataUpdateCoordinator": CoordinatorStub, "UpdateFailed": UpdateFailed},
}.items():
    module = ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"{package.__name__}.{name}", COMPONENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


discovery = load_module("discovery")
coordinator = load_module("coordinator")


class Connection:
    def __init__(self, offset=0, model="CMNDKT-004"):
        self.config_entry = SimpleNamespace(entry_id="existing-homekit", state=EntryState.LOADED)
        self.unique_id = "public-homekit-id"
        self.available = True
        self.pollable_characteristics = {(1, 10)}  # Native switch polling must survive.
        self.requests = []
        self.chars = [
            SimpleNamespace(type=uuid.lower(), iid=13 + index + offset, perms=["pr"], value=value, available=True, status=0)
            for index, (uuid, value) in enumerate(zip(discovery.METER_UUIDS.values(), [118.78125, 0.003906, 0.0]))
        ]
        energy = SimpleNamespace(type=discovery.ENERGY_SERVICE.lower(), characteristics=self.chars)
        firmware = SimpleNamespace(type="3A4B59DC-CA78-4800-A2EF-6E2E187861E2", characteristics=[SimpleNamespace(iid=18, perms=["pr", "pw"], value=False)])
        self.entity_map = SimpleNamespace(accessories=[SimpleNamespace(aid=1, model=model, services=[energy, firmware])])

    def add_pollable_characteristics(self, keys):
        self.pollable_characteristics.update(keys)

    def remove_pollable_characteristics(self, keys):
        self.pollable_characteristics.difference_update(keys)

    async def async_update(self, *, poll_all=False):
        assert poll_all is False
        self.requests.append(set(self.pollable_characteristics))

    async def put_characteristics(self, *args, **kwargs):
        raise AssertionError("Writing any characteristic is forbidden")


class MeterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = Connection()
        self.connections = {"public-homekit-id": self.conn}
        self.hass = SimpleNamespace(data={"homekit_controller-devices": self.connections})
        entry = SimpleNamespace(data={"homekit_entry_id": "existing-homekit", "aid": 1, "poll_seconds": 10})
        self.reader = coordinator.MeterCoordinator(self.hass, entry)

    async def test_read_without_firmware_or_pairing_operations(self):
        result = await self.reader._async_update_data()
        self.assertEqual(result, {"voltage": 118.78125, "current": 0.003906, "power": 0.0})
        self.assertEqual(self.conn.requests, [{(1, 10), (1, 13), (1, 14), (1, 15)}])
        self.assertFalse(self.conn.entity_map.accessories[0].services[1].characteristics[0].value)

    async def test_discovery_uses_uuid_instead_of_fixed_iids(self):
        replacement = Connection(offset=100)
        self.connections["public-homekit-id"] = replacement
        await self.reader._async_update_data()
        self.assertEqual(replacement.requests[-1], {(1, 10), (1, 113), (1, 114), (1, 115)})

    async def test_existing_native_poll_registration_survives_unload(self):
        self.conn.pollable_characteristics.add((1, 13))
        await self.reader._async_update_data()
        self.reader.release()
        self.reader.release()
        self.assertEqual(self.conn.pollable_characteristics, {(1, 10), (1, 13)})

    async def test_homekit_reload_reuses_new_connection(self):
        await self.reader._async_update_data()
        replacement = Connection(offset=100)
        self.connections["public-homekit-id"] = replacement
        await self.reader._async_update_data()
        self.assertIs(self.reader.connection, replacement)
        self.assertEqual(self.conn.pollable_characteristics, {(1, 10)})
        self.assertEqual(len(self.conn.requests), 1)
        self.assertEqual(len(replacement.requests), 1)

    async def test_iid_changes_within_same_connection(self):
        await self.reader._async_update_data()
        for char in self.conn.chars:
            char.iid += 100
        await self.reader._async_update_data()
        self.assertEqual(self.conn.requests[-1], {(1, 10), (1, 113), (1, 114), (1, 115)})

    async def test_unloaded_homekit_entry_is_not_polled(self):
        await self.reader._async_update_data()
        self.conn.config_entry.state = EntryState.NOT_LOADED
        with self.assertRaises(UpdateFailed):
            await self.reader._async_update_data()
        self.assertEqual(len(self.conn.requests), 1)
        self.assertEqual(self.conn.pollable_characteristics, {(1, 10)})

    async def test_wrong_model_is_not_polled(self):
        self.conn.entity_map.accessories[0].model = "FHH107"
        with self.assertRaises(UpdateFailed):
            await self.reader._async_update_data()
        self.assertEqual(self.conn.requests, [])

    async def test_unreadable_characteristic_is_not_polled(self):
        self.conn.chars[0].perms = ["pw"]
        with self.assertRaises(UpdateFailed):
            await self.reader._async_update_data()
        self.assertEqual(self.conn.requests, [])

    async def test_missing_characteristic_stops_extra_polling(self):
        await self.reader._async_update_data()
        self.conn.chars.pop()
        with self.assertRaises(UpdateFailed):
            await self.reader._async_update_data()
        self.assertEqual(self.conn.pollable_characteristics, {(1, 10)})

    async def test_bad_values_do_not_become_measurements(self):
        self.conn.chars[0].value = float("nan")
        self.conn.chars[1].value = True
        self.conn.chars[2].available = False
        self.assertEqual(await self.reader._async_update_data(), {"voltage": None, "current": None, "power": None})

    async def test_hap_error_does_not_republish_cached_value(self):
        self.conn.chars[0].status = -70403
        result = await self.reader._async_update_data()
        self.assertIsNone(result["voltage"])
        self.assertEqual(result["current"], 0.003906)


if __name__ == "__main__":
    unittest.main()
