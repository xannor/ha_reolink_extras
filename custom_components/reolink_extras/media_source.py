""" Media Source Platform """

from datetime import date, datetime
from typing import Optional

from aiohttp import web
from aiohttp.web_request import FileField

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.loader import async_get_integration

from homeassistant.util import raise_if_invalid_filename, raise_if_invalid_path

from homeassistant.components import http

from homeassistant.components.camera

from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    MediaSource,
    MediaSourceItem,
    BrowseMediaSource,
    PlayMedia,
)

from homeassistant.components.reolink import ReolinkData
from homeassistant.components.reolink.const import DOMAIN as REOLINK_DOMAIN

from reolink_aio.typings import VOD_file


from .const import DOMAIN, LOGGER

from .typings import SearchCache


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


@callback
async def async_get_media_source(hass: HomeAssistant):
    """Set up Reolink media source."""

    LOGGER.debug("Setting up Reolink Media Sources")
    try:
        reolink = await async_get_integration(hass, REOLINK_DOMAIN)
    except:  # pylint: disable=bare-except
        LOGGER.error("Reolink integration is not supported in this installation")
        return None
    if REOLINK_DOMAIN not in hass.data:
        LOGGER.warning("No reolink devices have been setup.")

    MEDIA = "MEDIA"
    domain_data: dict[MEDIA, ReolinkMediaSource] = hass.data.setdefault(DOMAIN, {})
    return domain_data.setdefault(MEDIA, ReolinkMediaSource(hass, reolink.name))


class ReolinkMediaSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.name = name
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        return await super().async_resolve_media(item)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        try:
            source, device_id, channel, filename = self.async_parse_identifier(item)
        except Unresolvable as err:
            raise BrowseError(str(err)) from err

        raise IncompatibleMediaSource

    @callback
    def async_parse_identifier(self, item: MediaSourceItem):
        """Parse identifier."""
        if item.domain != DOMAIN:
            raise Unresolvable("Unknown domain.")

        source_dir_id, _, location = item.identifier.partition("/")
        if source_dir_id not in self.hass.config.media_dirs:
            raise Unresolvable("Unknown source directory.")

        try:
            raise_if_invalid_path(location)
        except ValueError as err:
            raise Unresolvable("Invalid path.") from err

        return source_dir_id, location

    def _get_cache(self, entry_id: str, channel: int):
        domain_data: dict[str, any] = self.hass.data.get(DOMAIN)
        local_data: dict[str, any] = domain_data.get(entry_id) if domain_data else None
        search_data: dict[int, SearchCache] = (
            local_data.get("VOD") if local_data else None
        )
        return search_data.get(channel) if search_data else None

    def _create_media(
        self,
        source: str,
        device: Optional[str | ConfigEntry],
        channel: Optional[int],
        filename: Optional[str | date],
    ):
        """create BrowseMediaSource from parse"""

        title = self.name
        thumbnail = None
        path = source
        data = None
        cache = None
        file = None
        media_class = MediaClass.DIRECTORY

        if isinstance(device, str):
            device = self.hass.config_entries.async_get_entry(device)
            if not device or device.disabled_by:
                raise IncompatibleMediaSource

        if device:
            data: ReolinkData = self.hass.data.get(REOLINK_DOMAIN, {}).get(
                device.entry_id
            )
            title = device.title
            path += f"/{device.entry_id}"

        if channel is not None:
            if device:
                cache = self._get_cache(device.entry_id, channel)
            title = data.host.api.camera_name(channel) or f"Channel {channel}"
            path += f"/{channel}"

        if filename is not None:
            path += f"/{filename}"
            title = str(filename)
            if isinstance(filename, datetime) and cache:
                file = cache.get(filename)
                if not file:
                    raise IncompatibleMediaSource
                title += f" {file.triggers}"
                media_class = MediaClass.VIDEO

        media = BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=media_class,
            media_content_type=MediaType.VIDEO,
            title=title,
            can_play=file is not None,
            can_expand=file is None,
            thumbnail=thumbnail,
        )

        if not media.can_expand and not media.can_play:
            raise IncompatibleMediaSource

        return media

    def get_vod_media(self, file: VOD_file, channel: int, entry_id: str):
        """get a MediaSource from a VOD"""

        return self._create_media("devices", entry_id, channel, file.start_time)

class ReolinkVODMediaView(http.HomeAssistantView):
    """Reolink Media Finder View.

    Returns vod files on camera/device.
    """

    url = "/reolink/vod/{entity_id}/{filename:.*}"
    name = "reolink:vod"

    def __init__(self, hass: HomeAssistant, source: ReolinkMediaSource) -> None:
        """Initialize the media view."""
        self.hass = hass
        self.source = source

    async def get(
        self, request: web.Request, entity_id: str, filename: str
    ) -> web.FileResponse:
        """Start a GET request."""

        raise web.HTTPNotFound()
