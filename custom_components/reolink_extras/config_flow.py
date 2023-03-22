""" Configuration """
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN


class ReolinkExtrasFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Reolink Extras."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.FlowResult:
        """Handle a flow initialized by the user."""

        if await self.async_set_unique_id("reolink_extras") is not None:
            return self.async_abort(reason="already_configured")

        _errors = {}
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=_errors,
        )
