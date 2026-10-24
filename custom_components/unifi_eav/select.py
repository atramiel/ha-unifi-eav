"""Source selector per AV group."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
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
                    new.append(EavSourceSelect(coordinator, kind, g["id"]))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class EavSourceSelect(EavGroupEntity, SelectEntity):
    """Pick which source bridge feeds this group's displays."""

    def __init__(self, coordinator: EavCoordinator, kind: str, group_id: str) -> None:
        super().__init__(coordinator, kind, group_id)
        self._attr_unique_id = f"{kind}_{group_id}_source"
        name = (self.group or {}).get("name") or group_id
        self._attr_name = f"{name} {kind} source"
        self._attr_icon = "mdi:video-input-hdmi" if kind == "video" else "mdi:speaker-wireless"

    def _label_to_mac(self) -> dict[str, str]:
        data = self.coordinator.data
        labels: dict[str, str] = {}
        for mac in data.hosts(self.kind):
            label = data.name(mac)
            if label in labels:  # duplicate names: disambiguate with MAC
                label = f"{label} ({mac})"
            labels[label] = mac
        return labels

    @property
    def options(self) -> list[str]:
        return list(self._label_to_mac())

    @property
    def current_option(self) -> str | None:
        mac = (self.group or {}).get("host", {}).get("mac")
        for label, m in self._label_to_mac().items():
            if m == mac:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        mac = self._label_to_mac().get(option)
        if mac is None:
            raise ServiceValidationError(f"Unknown source: {option}")
        if mac == (self.group or {}).get("host", {}).get("mac"):
            return
        await self._push(host_mac=mac)
