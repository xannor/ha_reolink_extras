""" Reolink Extras """
from __future__ import annotations
import asyncio
from typing import Callable, Coroutine

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigEntryChange,
    SIGNAL_CONFIG_ENTRY_CHANGED,
)

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.dispatcher import async_dispatcher_connect

from homeassistant.components.reolink import ReolinkData
from homeassistant.components.reolink.const import DOMAIN as REOLINK_DOMAIN


from .const import DOMAIN, LOGGER as _LOGGER

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    data: dict[str, any] = {}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


@callback
def async_get_reolink_data(hass: HomeAssistant, entry: ConfigEntry) -> ReolinkData:
    return hass.data.get(REOLINK_DOMAIN, {}).get(entry.entry_id)


async def _forward_reolink_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    callback: Callable[[ConfigEntry], Coroutine[any, any, None] | None],
    in_task=False,
):
    if entry.disabled_by is not None:
        return

    if entry.state != ConfigEntryState.LOADED:

        def retry(_: ConfigEntryChange, entry: ConfigEntry):
            cleanup()
            hass.create_task(
                _forward_reolink_entry(hass, entry, callback, in_task=True)
            )

        cleanup = async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, retry)
        if not in_task:
            _LOGGER.info("%s is not ready will delay...", entry.title)
        return

    return await callback(entry)


async def async_forward_reolink_entries(
    hass: HomeAssistant,
    callback: Callable[[ConfigEntry], Coroutine[any, any, None] | None],
):
    """Forward callback with ready reolink entry"""

    await asyncio.gather(
        *(
            _forward_reolink_entry(hass, entry, callback)
            for entry in hass.config_entries.async_entries(REOLINK_DOMAIN)
        )
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
