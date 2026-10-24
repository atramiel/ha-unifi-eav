"""Snapshot camera per source bridge."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EavConfigEntry
from .api import EavError
from .coordinator import EavCoordinator
from .entity import bridge_device


async def async_setup_entry(
    hass: HomeAssistant, entry: EavConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = []
        for mac in coordinator.data.hosts("video"):
            if mac not in known:
                known.add(mac)
                new.append(EavSnapshotCamera(coordinator, mac))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class EavSnapshotCamera(CoordinatorEntity[EavCoordinator], Camera):
    """Still image of the HDMI input on a source bridge."""

    _attr_has_entity_name = True
    _attr_name = "Input preview"

    def __init__(self, coordinator: EavCoordinator, mac: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._mac = mac
        self._attr_unique_id = f"video_{mac}_snapshot"
        self._attr_device_info = bridge_device(coordinator, mac)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self.coordinator.client.get_snapshot(self._mac)
        except EavError:
            return None
