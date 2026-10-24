"""Minimal client for the UniFi Network "proav" (EAV Bridge) API.

This API is undocumented. Endpoints were mapped from the UniFi Network web
app (AV Manager) and verified against a UDM Pro SE running Network with
EAV Bridge firmware 1.0.11. All paths sit under
/proxy/network/v2/api/site/{site}/proav/.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class EavError(Exception):
    """Generic API failure."""


class EavAuthError(EavError):
    """Login rejected."""


class EavClient:
    """Talks to a UniFi OS console on behalf of one site."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        site: str = "default",
        verify_ssl: bool = False,
    ) -> None:
        self._session = session
        self._base = f"https://{host}"
        self._username = username
        self._password = password
        self._site = site
        self._ssl = None if verify_ssl else False
        self._csrf: str | None = None

    # ---- auth -----------------------------------------------------------

    async def login(self) -> None:
        """Log in and store the CSRF token. Session cookie lives in the jar."""
        try:
            async with self._session.post(
                f"{self._base}/api/auth/login",
                json={
                    "username": self._username,
                    "password": self._password,
                    "rememberMe": True,
                },
                ssl=self._ssl,
            ) as resp:
                if resp.status in (400, 401, 403):
                    raise EavAuthError(f"Login rejected (HTTP {resp.status})")
                if resp.status != 200:
                    raise EavError(f"Login failed (HTTP {resp.status})")
                self._csrf = resp.headers.get("x-csrf-token")
        except aiohttp.ClientError as err:
            raise EavError(f"Cannot reach console: {err}") from err

    # ---- plumbing -------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self._base}/proxy/network/v2/api/site/{self._site}/{path}"

    async def _request(
        self, method: str, url: str, *, json: Any = None, raw: bool = False
    ) -> Any:
        """Send a request, logging in again once if the session expired."""
        for attempt in (1, 2):
            if self._csrf is None:
                await self.login()
            headers = {"x-csrf-token": self._csrf or ""}
            try:
                async with self._session.request(
                    method, url, json=json, headers=headers, ssl=self._ssl
                ) as resp:
                    updated = resp.headers.get("x-updated-csrf-token")
                    if updated:
                        self._csrf = updated
                    if resp.status == 401 and attempt == 1:
                        _LOGGER.debug("Session expired, logging in again")
                        self._csrf = None
                        continue
                    if resp.status >= 400:
                        text = await resp.text()
                        raise EavError(
                            f"{method} {url} -> HTTP {resp.status}: {text[:300]}"
                        )
                    if raw:
                        return await resp.read()
                    if resp.content_type == "application/json":
                        return await resp.json()
                    return await resp.text()
            except aiohttp.ClientError as err:
                raise EavError(f"{method} {url} failed: {err}") from err
        raise EavError(f"{method} {url} failed after re-login")

    # ---- reads ----------------------------------------------------------

    async def get_matrix(self, kind: str) -> dict[str, Any]:
        """kind is 'video' or 'audio'."""
        return await self._request("GET", self._url(f"proav/{kind}/matrix"))

    async def get_bridge_names(self) -> dict[str, str]:
        """Map EAV Bridge MAC -> name from the device list."""
        data = await self._request(
            "GET", f"{self._base}/proxy/network/api/s/{self._site}/stat/device"
        )
        names: dict[str, str] = {}
        for dev in data.get("data", []):
            if dev.get("type") == "uav":
                names[dev["mac"]] = dev.get("name") or dev["mac"]
        return names

    async def get_snapshot(self, mac: str) -> bytes:
        """JPEG of what a source bridge is currently receiving."""
        return await self._request("GET", self._url(f"proav/snapshot/{mac}"), raw=True)

    # ---- writes ---------------------------------------------------------

    async def update_group(self, kind: str, group: dict[str, Any]) -> dict[str, Any]:
        """PUT the full group object back. Returns the stored group."""
        return await self._request(
            "PUT", self._url(f"proav/{kind}/group/{group['id']}"), json=group
        )
