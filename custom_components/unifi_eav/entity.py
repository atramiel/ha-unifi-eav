"""Shared entity bits for UniFi EAV."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import EavError
from .const import DOMAIN
from .coordinator import EavCoordinator


def bridge_device(coordinator: EavCoordinator, mac: str) -> DeviceInfo:
    """Attach entities to the bridge device (merges with UniFi Network's device)."""
    return DeviceInfo(
        connections={(CONNECTION_NETWORK_MAC, mac)},
        identifiers={(DOMAIN, mac)},
        name=coordinator.data.name(mac),
        manufacturer="Ubiquiti",
        model="EAV Bridge",
    )


class EavGroupEntity(CoordinatorEntity[EavCoordinator]):
    """An entity tied to one AV group (one source feeding one or more displays)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EavCoordinator, kind: str, group_id: str) -> None:
        super().__init__(coordinator)
        self.kind = kind
        self.group_id = group_id
        group = coordinator.data.group(kind, group_id) or {}
        # Put the entity on the first display in the group, since that's
        # what "what this screen shows" is about.
        clients = group.get("clients") or []
        anchor = clients[0]["mac"] if clients else group.get("host", {}).get("mac", group_id)
        self._attr_device_info = bridge_device(coordinator, anchor)

    @property
    def group(self) -> dict[str, Any] | None:
        return self.coordinator.data.group(self.kind, self.group_id)

    @property
    def available(self) -> bool:
        return super().available and self.group is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        g = self.group or {}
        data = self.coordinator.data
        return {
            "group_name": g.get("name"),
            "group_id": self.group_id,
            "kind": self.kind,
            "source": data.name(g.get("host", {}).get("mac", "")),
            "displays": [data.name(c["mac"]) for c in g.get("clients", [])],
        }

    async def _push(self, **changes: Any) -> None:
        try:
            await self.coordinator.async_update_group(self.kind, self.group_id, **changes)
        except EavError as err:
            raise HomeAssistantError(f"UniFi EAV update failed: {err}") from err
