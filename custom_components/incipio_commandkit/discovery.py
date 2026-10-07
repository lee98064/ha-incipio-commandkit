"""Resolve the metering service from cached HomeKit metadata, without I/O."""

from dataclasses import dataclass
from typing import Any

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

    @property
    def keys(self) -> list[tuple[int, int]]:
        return [
            (self.accessory.aid, char.iid)
            for char in self.characteristics.values()
        ]


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
                meters.append(Meter(accessory, chars))
    return meters
