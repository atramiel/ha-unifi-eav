"""Config flow for UniFi EAV."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiohttp import CookieJar
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EavAuthError, EavClient, EavError
from .const import CONF_SITE, DEFAULT_SITE, DEFAULT_VERIFY_SSL, DOMAIN


def _schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "192.168.0.1")): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_SITE, default=defaults.get(CONF_SITE, DEFAULT_SITE)): str,
            vol.Optional(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): bool,
        }
    )


class EavConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data: Mapping[str, Any]) -> str | None:
        session = async_create_clientsession(
            self.hass, verify_ssl=data[CONF_VERIFY_SSL], cookie_jar=CookieJar(unsafe=True)
        )
        client = EavClient(
            session,
            data[CONF_HOST],
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            data[CONF_SITE],
            data[CONF_VERIFY_SSL],
        )
        try:
            await client.login()
            await client.get_matrix("video")
        except EavAuthError:
            return "invalid_auth"
        except EavError:
            return "cannot_connect"
        finally:
            await session.close()
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}_{user_input[CONF_SITE]}"
            )
            self._abort_if_unique_id_configured()
            if (error := await self._validate(user_input)) is None:
                return self.async_create_entry(
                    title=f"UniFi EAV ({user_input[CONF_HOST]})", data=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if (error := await self._validate(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
