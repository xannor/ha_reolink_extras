"""Reolink Component helpers"""

import asyncio
from typing import Callable, Coroutine
from homeassistant.core import HomeAssistant, callback

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigEntryChange,
    SIGNAL_CONFIG_ENTRY_CHANGED,
)

from homeassistant.helpers.dispatcher import async_dispatcher_connect


from homeassistant.components.reolink import ReolinkData
from homeassistant.components.reolink.const import DOMAIN as REOLINK_DOMAIN

from ..const import LOGGER as _LOGGER

@callback
def async_get_reolink_data(hass: HomeAssistant, entry_id: str) -> ReolinkData:
    """Get ReolinkData for given reolink entry"""
    return hass.data.get(REOLINK_DOMAIN, {}).get(entry_id)


async def _forward_reolink_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    handler: Callable[[ConfigEntry], Coroutine[any, any, None] | None],
    in_task=False,
):
    if entry.disabled_by is not None:
        return

    if entry.state != ConfigEntryState.LOADED:

        def retry(_: ConfigEntryChange, retry_entry: ConfigEntry):
            if retry_entry.entry_id != entry.entry_id:
                return
            cleanup()
            hass.create_task(
                _forward_reolink_entry(hass, retry_entry, handler, in_task=True)
            )

        cleanup = async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, retry)
        if not in_task:
            _LOGGER.info("%s is not ready will delay...", entry.title)
        return

    return await handler(entry)


async def async_forward_reolink_entries(
    hass: HomeAssistant,
    handler: Callable[[ConfigEntry], Coroutine[any, any, None] | None],
):
    """Forward callback with ready reolink entry"""

    await asyncio.gather(
        *(
            _forward_reolink_entry(hass, entry, handler)
            for entry in hass.config_entries.async_entries(REOLINK_DOMAIN)
        )
    )
