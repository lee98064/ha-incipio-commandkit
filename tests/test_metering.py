"""Offline boundary tests; no Home Assistant server or outlet is contacted."""

from enum import Enum
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

from aiohomekit.model import Accessories
from aiohomekit.exceptions import AccessoryDisconnectedError
from aiohomekit.model.characteristics import CharacteristicsTypes
from aiohomekit.model.services import ServicesTypes
from aiohomekit.protocol.statuscodes import HapStatusCode

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


class HomeAssistantError(Exception):
    pass


class CoordinatorStub:
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.data = {}
        self.last_update_success = True

    async def async_refresh(self):
        try:
            self.data = await self._async_update_data()
        except UpdateFailed:
            self.last_update_success = False
        else:
            self.last_update_success = True


class CoordinatorEntityStub:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


class SwitchDeviceClass(Enum):
    OUTLET = "outlet"


for name, attrs in {
    "homeassistant.components.homekit_controller.const": {"KNOWN_DEVICES": "homekit_controller-devices"},
    "homeassistant.config_entries": {"ConfigEntryState": EntryState},
    "homeassistant.exceptions": {"HomeAssistantError": HomeAssistantError},
    "homeassistant.helpers.update_coordinator": {"DataUpdateCoordinator": CoordinatorStub, "UpdateFailed": UpdateFailed, "CoordinatorEntity": CoordinatorEntityStub},
    "homeassistant.components.switch": {"SwitchEntity": type("SwitchEntity", (), {}), "SwitchDeviceClass": SwitchDeviceClass},
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
switch = load_module("switch")


class Connection:
    def __init__(self, offset=0, model="CMNDKT-004"):
        self.config_entry = SimpleNamespace(entry_id="existing-homekit", state=EntryState.LOADED)
        self.unique_id = "public-homekit-id"
        self.available = True
        self.pollable_characteristics = {(1, 10)}  # Native switch polling must survive.
        self.requests = []
        self.chars = [
            SimpleNamespace(type=uuid.lower(), iid=13 + index + offset, perms=["pr"], value=value, available=True, status=HapStatusCode.SUCCESS)
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
        self.conn.chars[0].status = HapStatusCode.RESOURCE_BUSY
        result = await self.reader._async_update_data()
        self.assertIsNone(result["voltage"])
        self.assertEqual(result["current"], 0.003906)

    def use_real_accessory_model(self):
        """Parse sanitized device metadata with the same library as HA 2026.9.4."""
        fixture = Path(__file__).parent / "fixtures" / "commandkit_10219.json"
        self.conn.entity_map = Accessories.from_list(json.loads(fixture.read_text()))

    async def test_real_model_success_status_keeps_diagnostic_values(self):
        self.use_real_accessory_model()
        char = self.conn.entity_map.aid(1).characteristics.iid(13)
        self.assertIs(char.status, HapStatusCode.SUCCESS)
        self.assertNotEqual(char.status, 0)
        self.assertEqual(
            await self.reader._async_update_data(),
            {"voltage": 121.421875, "current": 0.003906, "power": 0.0, "on": False},
        )

    async def test_real_model_values_update_through_native_cache(self):
        self.use_real_accessory_model()

        async def poll(*, poll_all=False):
            self.assertFalse(poll_all)
            self.conn.entity_map.process_changes({
                (1, 13): {"value": 120.5},
                (1, 14): {"value": 0.5},
                (1, 15): {"value": 60.25},
            })

        self.conn.async_update = poll
        self.assertEqual(
            await self.reader._async_update_data(),
            {"voltage": 120.5, "current": 0.5, "power": 60.25, "on": False},
        )

    async def test_real_model_error_and_recovery(self):
        self.use_real_accessory_model()
        self.conn.entity_map.process_changes({(1, 13): {"status": -70403}})
        result = await self.reader._async_update_data()
        self.assertIsNone(result["voltage"])
        self.assertEqual(result["current"], 0.003906)
        self.assertEqual(result["power"], 0.0)
        self.conn.entity_map.process_changes({(1, 13): {"value": 120.5, "status": 0}})
        self.assertEqual((await self.reader._async_update_data())["voltage"], 120.5)


class ControlConnection(Connection):
    """Simulate HKDevice's acknowledged write updating the real accessory cache."""

    def __init__(self, offset=0):
        super().__init__()
        fixture = Path(__file__).parent / "fixtures" / "commandkit_10219.json"
        accessories = json.loads(fixture.read_text())
        for accessory in accessories:
            for service in accessory["services"]:
                service["iid"] += offset
                for char in service["characteristics"]:
                    char["iid"] += offset
        self.entity_map = Accessories.from_list(accessories)
        self.writes = []
        self.ignore_writes = False
        self.write_error = None

    def device_info_for_accessory(self, accessory):
        return {"identifiers": {("homekit_controller", f"{self.unique_id}:{accessory.aid}")}}

    async def put_characteristics(self, payload):
        self.writes.append(payload)
        self.assert_outlet_only(payload)
        if self.write_error is not None:
            raise self.write_error
        if not self.ignore_writes:
            self.entity_map.process_changes({
                (aid, iid): {"value": value} for aid, iid, value in payload
            })

    def assert_outlet_only(self, payload):
        assert len(payload) == 1
        aid, iid, value = payload[0]
        char = self.entity_map.aid(aid).characteristics.iid(iid)
        assert char.type == CharacteristicsTypes.ON
        assert char.service.type == ServicesTypes.OUTLET
        assert isinstance(value, bool)


class OutletTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = ControlConnection()
        self.connections = {"public-homekit-id": self.conn}
        self.hass = SimpleNamespace(data={"homekit_controller-devices": self.connections})
        self.entry = SimpleNamespace(data={"homekit_entry_id": "existing-homekit", "aid": 1, "poll_seconds": 10})
        self.reader = coordinator.MeterCoordinator(self.hass, self.entry)

    async def test_switch_turns_on_and_off_without_touching_firmware(self):
        await self.reader.async_refresh()
        entity = switch.OutletSwitch(self.reader)
        self.assertFalse(entity.is_on)
        self.assertTrue(entity.available)
        await entity.async_turn_on()
        self.assertTrue(entity.is_on)
        await entity.async_turn_off()
        self.assertFalse(entity.is_on)
        self.assertEqual(self.conn.writes, [[(1, 9, True)], [(1, 9, False)]])
        self.assertFalse(self.conn.entity_map.aid(1).characteristics.iid(18).value)
        self.assertEqual(self.reader.data["voltage"], 121.421875)
        self.assertEqual(entity._attr_unique_id, "public-homekit-id_1_outlet")
        self.assertEqual(entity._attr_device_info, self.conn.device_info_for_accessory(self.reader.meter.accessory))

    async def test_external_switch_change_is_read_back(self):
        await self.reader.async_refresh()
        entity = switch.OutletSwitch(self.reader)
        self.conn.entity_map.process_changes({(1, 9): {"value": True}})
        await self.reader.async_refresh()
        self.assertTrue(entity.is_on)
        self.assertEqual(self.conn.writes, [])

    async def test_write_re_resolves_reloaded_connection_and_iid(self):
        await self.reader.async_refresh()
        replacement = ControlConnection(offset=100)
        self.connections["public-homekit-id"] = replacement
        await self.reader.async_set_on(True)
        self.assertEqual(replacement.writes, [[(1, 109, True)]])
        self.assertEqual(self.conn.writes, [])
        self.assertEqual(self.conn.pollable_characteristics, {(1, 10)})
        self.assertTrue(self.reader.data["on"])

    async def test_offline_or_unloaded_connection_cannot_be_written(self):
        self.conn.available = False
        with self.assertRaises(HomeAssistantError):
            await self.reader.async_set_on(True)
        self.conn.available = True
        self.conn.config_entry.state = EntryState.NOT_LOADED
        with self.assertRaises(HomeAssistantError):
            await self.reader.async_set_on(True)
        self.assertEqual(self.conn.writes, [])

    async def test_read_only_or_wrong_service_cannot_be_written(self):
        for change in ("read_only", "wrong_service", "wrong_format"):
            with self.subTest(change=change):
                self.conn = ControlConnection()
                self.connections["public-homekit-id"] = self.conn
                char = self.conn.entity_map.aid(1).characteristics.iid(9)
                if change == "read_only":
                    char.perms = ["pr"]
                elif change == "wrong_service":
                    char.service.type = "3A4B59DC-CA78-4800-A2EF-6E2E187861E2"
                else:
                    char.format = "int"
                with self.assertRaises(HomeAssistantError):
                    await self.reader.async_set_on(True)
                self.assertEqual(self.conn.writes, [])

    async def test_unconfirmed_write_does_not_report_success(self):
        await self.reader.async_refresh()
        self.conn.ignore_writes = True
        with self.assertRaisesRegex(HomeAssistantError, "did not confirm"):
            await self.reader.async_set_on(True)
        self.assertFalse(self.reader.data["on"])

    async def test_write_connection_error_is_reported(self):
        await self.reader.async_refresh()
        self.conn.write_error = AccessoryDisconnectedError("disconnected")
        with self.assertRaisesRegex(HomeAssistantError, "Unable to change"):
            await self.reader.async_set_on(True)
        self.assertFalse(self.reader.data["on"])

    async def test_unknown_switch_status_is_unavailable_without_losing_meters(self):
        self.conn.entity_map.process_changes({(1, 9): {"status": -70403}})
        await self.reader.async_refresh()
        entity = switch.OutletSwitch(self.reader)
        self.assertIsNone(entity.is_on)
        self.assertFalse(entity.available)
        self.assertEqual(self.reader.data["voltage"], 121.421875)

    async def test_switch_is_only_created_if_control_is_supported(self):
        for supported in (True, False):
            with self.subTest(supported=supported):
                self.conn = ControlConnection()
                self.connections["public-homekit-id"] = self.conn
                if not supported:
                    self.conn.entity_map.aid(1).characteristics.iid(9).perms = ["pr"]
                await self.reader.async_refresh()
                self.entry.runtime_data = self.reader
                entities = []
                await switch.async_setup_entry(self.hass, self.entry, entities.extend)
                self.assertEqual(len(entities), 1 if supported else 0)

    async def test_control_poll_registration_and_cleanup_preserve_native_keys(self):
        self.conn.pollable_characteristics.add((1, 9))
        await self.reader.async_refresh()
        self.assertEqual(self.conn.requests[-1], {(1, 9), (1, 10), (1, 13), (1, 14), (1, 15)})
        self.reader.release()
        self.assertEqual(self.conn.pollable_characteristics, {(1, 9), (1, 10)})

    async def test_polling_survives_native_switch_being_disabled(self):
        self.conn.pollable_characteristics.add((1, 9))
        await self.reader.async_refresh()
        self.conn.remove_pollable_characteristics([(1, 9)])
        await self.reader.async_refresh()
        self.assertIn((1, 9), self.conn.requests[-1])
        self.reader.release()
        self.assertEqual(self.conn.pollable_characteristics, {(1, 10)})

    async def test_controls_are_serialized_until_state_confirmation(self):
        writes_and_reads = []
        original_write = self.conn.put_characteristics
        original_read = self.conn.async_update

        async def write(payload):
            writes_and_reads.append(("write", payload[0][2]))
            await asyncio.sleep(0)
            await original_write(payload)

        async def read(*, poll_all=False):
            writes_and_reads.append(("read", self.conn.entity_map.aid(1).characteristics.iid(9).value))
            await original_read(poll_all=poll_all)

        self.conn.put_characteristics = write
        self.conn.async_update = read
        await asyncio.gather(self.reader.async_set_on(True), self.reader.async_set_on(False))
        self.assertEqual(writes_and_reads, [("write", True), ("read", True), ("write", False), ("read", False)])
        self.assertFalse(self.reader.data["on"])


if __name__ == "__main__":
    unittest.main()
