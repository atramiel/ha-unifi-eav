"""On/off per AV group."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EavConfigEntry
from .const import KINDS
from .coordinator import EavCoordinator
from .entity import EavGroupEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EavConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[tuple[str, str]] = set()

    @callback
    def _add_new() -> None:
        new = []
        for kind in KINDS:
            for g in coordinator.data.groups(kind):
                key = (kind, g["id"])
                if key not in known:
                    known.add(key)
                    new.append(EavGroupSwitch(coordinator, kind, g["id"]))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class EavGroupSwitch(EavGroupEntity, SwitchEntity):
    """Enable or disable a group (stops the stream to its displays)."""

    def __init__(self, coordinator: EavCoordinator, kind: str, group_id: str) -> None:
        super().__init__(coordinator, kind, group_id)
        self._attr_unique_id = f"{kind}_{group_id}_enabled"
        name = (self.group or {}).get("name") or group_id
        self._attr_name = f"{name} {kind} stream"
        self._attr_icon = "mdi:television" if kind == "video" else "mdi:speaker"

    @property
    def is_on(self) -> bool | None:
        g = self.group
        return None if g is None else bool(g.get("enabled"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._push(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._push(enabled=False)
