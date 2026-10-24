"""Tests for unifi_eav using data captured from the real console."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

from aiohttp import CookieJar, web
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.unifi_eav.api import EavAuthError, EavClient
from custom_components.unifi_eav.const import CONF_SITE, DOMAIN

OFFICE = "8c:ed:e1:68:63:77"
GARAGE = "8c:ed:e1:68:68:be"
DEN = "8c:ed:e1:00:00:01"  # hypothetical second source

VIDEO = {
    "bridges": [OFFICE, GARAGE, DEN],
    "client_candidates": [],
    "clients": [GARAGE],
    "groups": [
        {
            "channel": 2,
            "clients": [
                {
                    "audio_enabled": True,
                    "audio_mode": "PCM",
                    "color_format": "RGB",
                    "enabled": True,
                    "mac": GARAGE,
                    "mode": "UNICAST",
                    "resolution": "AUTO",
                    "client_type": "VIDEO",
                }
            ],
            "enabled": True,
            "host": {"enabled": True, "mac": OFFICE, "refresh_rate": "AUTO", "host_type": "VIDEO"},
            "id": "6adc3fd9dfe874c1199f0f9e",
            "name": "Garage",
            "type": "VIDEO",
        }
    ],
    "host_candidates": [DEN],
    "hosts": [OFFICE],
}
AUDIO = {"bridges": [OFFICE, GARAGE], "client_candidates": [GARAGE], "clients": [GARAGE],
         "groups": [], "host_candidates": [OFFICE], "hosts": []}
NAMES = {OFFICE: "EAV Bridge - office PC", GARAGE: "EAV Bridge - garage", DEN: "EAV Bridge - den"}

DATA = {CONF_HOST: "192.168.0.1", CONF_USERNAME: "ha", CONF_PASSWORD: "pw",
        CONF_SITE: "default", CONF_VERIFY_SSL: False}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_client():
    video = copy.deepcopy(VIDEO)

    async def get_matrix(kind):
        return copy.deepcopy(video if kind == "video" else AUDIO)

    async def update_group(kind, group):
        video["groups"][0] = copy.deepcopy(group)
        return group

    with patch.multiple(
        "custom_components.unifi_eav.api.EavClient",
        login=AsyncMock(),
        get_matrix=AsyncMock(side_effect=get_matrix),
        get_bridge_names=AsyncMock(return_value=NAMES),
        get_snapshot=AsyncMock(return_value=b"\xff\xd8jpeg"),
        update_group=AsyncMock(side_effect=update_group),
    ):
        yield EavClient


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="192.168.0.1_default")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_created(hass: HomeAssistant, mock_client) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    states = {s.entity_id: s for s in hass.states.async_all()}
    selects = [s for e, s in states.items() if e.startswith("select.")]
    switches = [s for e, s in states.items() if e.startswith("switch.")]
    cams = [e for e in states if e.startswith("camera.")]
    assert len(selects) == 1 and len(switches) == 1
    assert len(cams) == 2  # office (host) + den (candidate)
    sel = selects[0]
    assert sel.state == "EAV Bridge - office PC"
    assert set(sel.attributes["options"]) == {"EAV Bridge - office PC", "EAV Bridge - den"}
    assert sel.attributes["displays"] == ["EAV Bridge - garage"]
    assert switches[0].state == "on"


async def test_select_source_sends_full_group(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass)
    sel = next(s for s in hass.states.async_all() if s.entity_id.startswith("select."))
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": sel.entity_id, "option": "EAV Bridge - den"}, blocking=True,
    )
    await hass.async_block_till_done()
    kind, sent = mock_client.update_group.call_args.args
    assert kind == "video"
    assert sent["host"]["mac"] == DEN
    # Everything else untouched.
    expected = copy.deepcopy(VIDEO["groups"][0])
    expected["host"]["mac"] = DEN
    assert sent == expected
    assert hass.states.get(sel.entity_id).state == "EAV Bridge - den"


async def test_switch_off(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass)
    sw = next(s for s in hass.states.async_all() if s.entity_id.startswith("switch."))
    await hass.services.async_call("switch", "turn_off", {"entity_id": sw.entity_id}, blocking=True)
    await hass.async_block_till_done()
    _, sent = mock_client.update_group.call_args.args
    assert sent["enabled"] is False
    assert hass.states.get(sw.entity_id).state == "off"


async def test_config_flow(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA


async def test_config_flow_bad_auth(hass: HomeAssistant, mock_client) -> None:
    mock_client.login.side_effect = EavAuthError("nope")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["errors"] == {"base": "invalid_auth"}


# ---- real HTTP against a fake console ------------------------------------

@pytest.mark.enable_socket
async def test_client_http(socket_enabled) -> None:
    """Login, CSRF header, 401 -> re-login, PUT body."""
    state = {"logins": 0, "expire_once": True, "put": None}

    async def login(req):
        state["logins"] += 1
        return web.json_response({}, headers={"x-csrf-token": f"tok{state['logins']}"})

    async def matrix(req):
        if req.headers.get("x-csrf-token") != f"tok{state['logins']}":
            return web.Response(status=403)
        if state["expire_once"]:
            state["expire_once"] = False
            return web.Response(status=401)
        return web.json_response(VIDEO)

    async def put(req):
        state["put"] = await req.json()
        return web.json_response(state["put"])

    app = web.Application()
    app.router.add_post("/api/auth/login", login)
    app.router.add_get("/proxy/network/v2/api/site/default/proav/video/matrix", matrix)
    app.router.add_put("/proxy/network/v2/api/site/default/proav/video/group/{id}", put)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    import aiohttp
    async with aiohttp.ClientSession(cookie_jar=CookieJar(unsafe=True)) as s:
        c = EavClient(s, f"127.0.0.1:{port}", "u", "p")
        c._base = f"http://127.0.0.1:{port}"  # plain HTTP for the fake
        m = await c.get_matrix("video")
        assert m["groups"][0]["name"] == "Garage"
        assert state["logins"] == 2  # initial + re-login after 401
        g = copy.deepcopy(m["groups"][0])
        g["host"]["mac"] = DEN
        out = await c.update_group("video", g)
        assert state["put"]["host"]["mac"] == DEN and out["id"] == g["id"]
    await runner.cleanup()
