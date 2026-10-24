"""Polling coordinator for UniFi EAV."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EavAuthError, EavClient, EavError
from .const import DOMAIN, KINDS, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


@dataclass
class EavData:
    """Snapshot of the AV matrix."""

    names: dict[str, str] = field(default_factory=dict)
    # kind -> raw matrix
    matrix: dict[str, dict[str, Any]] = field(default_factory=dict)

    def groups(self, kind: str) -> list[dict[str, Any]]:
        return self.matrix.get(kind, {}).get("groups", [])

    def group(self, kind: str, group_id: str) -> dict[str, Any] | None:
        return next((g for g in self.groups(kind) if g["id"] == group_id), None)

    def hosts(self, kind: str) -> list[str]:
        """All bridges that can act as a source for this kind."""
        m = self.matrix.get(kind, {})
        return list(dict.fromkeys(m.get("hosts", []) + m.get("host_candidates", [])))

    def name(self, mac: str) -> str:
        return self.names.get(mac, mac)


class EavCoordinator(DataUpdateCoordinator[EavData]):
    """Fetches both matrices plus bridge names."""

    def __init__(self, hass: HomeAssistant, client: EavClient, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> EavData:
        try:
            names = await self.client.get_bridge_names()
            matrix = {k: await self.client.get_matrix(k) for k in KINDS}
        except EavAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EavError as err:
            raise UpdateFailed(str(err)) from err
        return EavData(names=names, matrix=matrix)

    async def async_update_group(self, kind: str, group_id: str, **changes: Any) -> None:
        """Apply changes to a group and push it to the console.

        Supported changes: host_mac (new source), enabled (bool).
        """
        current = self.data.group(kind, group_id)
        if current is None:
            raise EavError(f"Group {group_id} no longer exists")
        group = copy.deepcopy(current)
        if "host_mac" in changes:
            group["host"]["mac"] = changes["host_mac"]
        if "enabled" in changes:
            group["enabled"] = bool(changes["enabled"])
        stored = await self.client.update_group(kind, group)
        # Show the change immediately, then confirm with a full refresh.
        groups = self.data.groups(kind)
        for i, g in enumerate(groups):
            if g["id"] == group_id:
                groups[i] = stored if isinstance(stored, dict) and "id" in stored else group
        self.async_update_listeners()
        await self.async_request_refresh()
