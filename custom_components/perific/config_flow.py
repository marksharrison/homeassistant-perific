"""Config flow for Perific Meter."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Client, PerificAuthenticationError, PerificConnectionError, PerificError
from .const import API_URL, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class PerificConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Perific Meter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

        errors = await self._validate(user_input)
        if errors:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        await self.async_set_unique_id(f"perific_{user_input[CONF_USERNAME].casefold()}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Perific Cloud ({user_input[CONF_USERNAME]})", data=user_input
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication for an expired token."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication credentials."""
        if user_input is not None:
            username = self._reauth_entry.data[CONF_USERNAME]
            data = {CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            errors = await self._validate(data)
            if not errors:
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        else:
            errors = {}
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    async def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        client = Client(async_get_clientsession(self.hass), API_URL)
        try:
            await client.authenticate(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
        except PerificAuthenticationError:
            return {"base": "invalid_auth"}
        except PerificConnectionError:
            return {"base": "cannot_connect"}
        except PerificError:
            return {"base": "unknown"}
        return {}
