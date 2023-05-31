"""Cache helpers"""

from typing import Literal, overload
from homeassistant.core import HomeAssistant, callback

from ..typings import SearchCache

from ..const import DOMAIN, SOURCE_KEY, LOGGER as _LOGGER

@overload
def async_get_cache(hass: HomeAssistant, entry_id: str, channel: int)->SearchCache|None:...

@overload
def async_get_cache(hass: HomeAssistant, entry_id: str, channel: int, create:Literal[True])->SearchCache:...

@callback
def async_get_cache(hass: HomeAssistant, entry_id: str, channel: int, create = False):
    """Get ReolinkData for given reolink entry"""

    domain_data: dict[Literal["media_source"], dict[str, dict[int, SearchCache]]] = hass.data.get(DOMAIN)
    media_data = domain_data.setdefault(SOURCE_KEY, {}) if create else domain_data.get(SOURCE_KEY)

    cache_data = media_data.get(entry_id) if media_data is not None else None
    if cache_data is None:
        if not create or media_data is None:
            return None
        new_data = {}
        cache_data = media_data.setdefault(entry_id,new_data)
        if new_data is cache_data:
            def clear_on_unload():
                cache_data.pop(entry_id, None)

            hass.config_entries.async_get_entry(entry_id).async_on_unload(clear_on_unload)

    cache = cache_data.get(channel)
    if cache is None and create:
        cache = cache_data.setdefault(channel, SearchCache())

    return cache
