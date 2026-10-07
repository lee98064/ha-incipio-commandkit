"""Resolve the metering service from cached HomeKit metadata, without I/O."""

from dataclasses import dataclass
from typing import Any

from aiohomekit.model.characteristics import CharacteristicsTypes
from aiohomekit.model.services import ServicesTypes

DOMAIN = "incipio_commandkit"
ENERGY_SERVICE = "14FA9D31-FC94-4F98-B00D-4AE878523748"
METER_UUIDS = {
    "voltage": "032B12CF-D4E8-4277-9021-188816FD00C6",
    "current": "08874E2E-5B63-4EEC-A146-4E2D93E5642A",
    "power": "D7467855-8B65-42EC-98E1-496FF153F342",
}


@dataclass
class Meter:
    """One CMNDKT-004 accessory with all three readable meter values."""

    accessory: Any
    characteristics: dict[str, Any]
    outlet_on: Any | None = None

    @property
    def keys(self) -> list[tuple[int, int]]:
        keys = [
            (self.accessory.aid, char.iid)
            for char in self.characteristics.values()
        ]
        if self.outlet_on is not None:
            keys.append((self.accessory.aid, self.outlet_on.iid))
        return keys


def outlet_on_characteristic(accessory: Any) -> Any | None:
    """Resolve only a standard, readable and writable boolean outlet switch."""
    for service in accessory.services:
        if str(service.type).upper() != ServicesTypes.OUTLET:
            continue
        for char in service.characteristics:
            if (
                str(char.type).upper() == CharacteristicsTypes.ON
                and char.format == "bool"
                and "pr" in char.perms
                and "pw" in char.perms
            ):
                return char
    return None


def discover_meters(connection: Any) -> list[Meter]:
    """Require the model, service UUID and readable characteristic UUIDs."""
    meters = []
    for accessory in connection.entity_map.accessories:
        if str(accessory.model).strip().upper() != "CMNDKT-004":
            continue
        for service in accessory.services:
            if str(service.type).upper() != ENERGY_SERVICE:
                continue
            by_uuid = {str(char.type).upper(): char for char in service.characteristics}
            chars = {
                key: by_uuid[uuid]
                for key, uuid in METER_UUIDS.items()
                if uuid in by_uuid
            }
            if len(chars) == 3 and all("pr" in char.perms for char in chars.values()):
                meters.append(Meter(accessory, chars, outlet_on_characteristic(accessory)))
    return meters
