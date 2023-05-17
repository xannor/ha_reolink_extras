""" Media Source Platform """

from datetime import date, datetime, time
from typing import Optional

from aiohttp import web
from aiohttp.web_request import FileField

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.loader import async_get_integration

from homeassistant.components import http

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
from homeassistant.components.reolink.entity import ReolinkHostCoordinatorEntity, ReolinkChannelCoordinatorEntity
from homeassistant.components.reolink.const import DOMAIN as REOLINK_DOMAIN

from reolink_aio.typings import VOD_file

from .helpers import async_get_reolink_data

from .const import DOMAIN, LOGGER

from .typings import SearchCache, yearmonth


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
    # if REOLINK_DOMAIN not in hass.data:
    #     LOGGER.warning("No reolink devices have been setup.")

    hass.http.register_view(ReolinkVODMediaView)
    # hass.http.register_view(ReolinkVODThumbnailMediaView)
    return ReolinkMediaSource(hass, reolink.name)


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
            device, channel, file = self.async_parse_identifier(item)
        except Unresolvable as err:
            raise BrowseError(str(err)) from err

        return await self._browse_media(device, channel, file)

    @callback
    def async_parse_identifier(self, item: MediaSourceItem):
        """Parse identifier."""
        if item.domain != DOMAIN:
            raise Unresolvable("Unknown domain.")

        ident = item.identifier
        device, _, ident = ident.partition("/")
        if ident:
            channel, _, file_name = ident.partition("/")
            if not channel.isdigit():
                raise Unresolvable("invalid channel");
            if file_name:
                year, _, ident = file_name.partition("/")
                month = None
                day = None
                if year.isdigit():
                    year = int(year)
                    if ident:
                        month, _, ident = ident.partition("/")
                        if month.isdigit():
                            month = int(month)
                            if ident:
                                day, _, ident = ident.partition("/")
                                if day.isdigit() and not ident:
                                    day = int(day)
                                else:
                                    year = None
                                    day = None
                            else:
                                day = None
                        else:
                            year = None
                            month = None

                    if year is not None:
                        file_name = (year, month, day)
        else:
            channel = None
            file_name = None

        return (device, channel, file_name)

    @callback
    def async_create_media(self, entity: ReolinkHostCoordinatorEntity, vod: VOD_file):
        """Get MediaSource for VOD """

        channel = entity._channel if isinstance(entity, ReolinkChannelCoordinatorEntity) else 0

        media, *_ = self._create_media(entity.coordinator.config_entry, channel, vod)
        return media


    def _get_cache(self, entry_id: str, channel: int, create = False):
        domain_data: dict[str, any] = self.hass.data.get(DOMAIN)
        local_data: dict[str, dict[int, SearchCache]] = domain_data.get(entry_id) if domain_data else None
        if local_data is None:
            return None

        search_data = local_data.get("VOD")
        if search_data is None and create:
            search_data = local_data.setdefault("VOD", {})
        cache = search_data.get(channel) if search_data else None
        if cache is None and create:
            cache = search_data.setdefault(channel, SearchCache())
        return cache

    def _create_media(
        self,
        device: str | ConfigEntry | None,
        channel: int | str | None,
        file: tuple[int, int|None, int|None] | VOD_file | str | None,
    ):
        title = f"{self.name} Playback"
        thumbnail = None
        path = ""
        data = None
        media_class = MediaClass.DIRECTORY
        media_type = MediaType.PLAYLIST

        if isinstance(device, str):
            device = self.hass.config_entries.async_get_entry(device)
            if not device or device.disabled_by:
                raise IncompatibleMediaSource

        if isinstance(channel, str):
            channel = int(channel)

        if device:
            data: ReolinkData = self.hass.data.get(REOLINK_DOMAIN, {}).get(
                device.entry_id
            )
            title = device.title
            path += f"/{device.entry_id}"

            if channel is not None:
                title = data.host.api.camera_name(channel) or f"Channel {channel}"
                path += f"/{channel}"

                if file is not None:
                    if isinstance(file, VOD_file):
                        path += f"/{file.file_name}"
                        title += f" {file.triggers}"
                        media_class = MediaClass.VIDEO
                        media_type = MediaType.VIDEO
                    elif isinstance(file, tuple):
                        title = "/".join(filter(lambda i: i is not None, file))
                        path += title
                    else:
                        raise IncompatibleMediaSource

        media = BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=media_class,
            media_content_type=media_type,
            title=title,
            can_play=file is not None,
            can_expand=file is None,
            thumbnail=thumbnail,
        )

        if not media.can_expand and not media.can_play:
            raise IncompatibleMediaSource

        return (media, device, channel)

    async def _browse_media(
        self,
        device: str | ConfigEntry | None,
        channel: int | str | None,
        file: tuple[int, int|None, int|None] | VOD_file | str | None,
        depth = 0,
    ):
        media, device, channel = self._create_media(device, channel, file)

        if not media.can_expand or depth < 0:
            return media

        children:list[BrowseMediaSource] = []
        media.children = children

        if not device:
            for device in self.hass.config_entries.async_entries(REOLINK_DOMAIN):
                if device.disabled_by is not None:
                    continue
                children.append(await self._browse_media(device, None, None, depth=depth-1))
        else:
            data = async_get_reolink_data(self.hass, device.entry_id)
            if channel is None:
                for channel in data.host.api.stream_channels:
                    children.append(await self._browse_media(device, channel, None, depth=depth-1))
            elif file is not None and not isinstance(file, tuple):
                raise IncompatibleMediaSource
            else:
                cache = self._get_cache(device.entry_id, channel, True)
                year, month, day = file if file is not None else (None, None, None)

                if year is None or month is None:
                    today = date.today()
                    if not cache.at_start:
                        start = cache.statuses.keys()[0] if len(cache.statuses) > 0 else yearmonth.fromdate(today) + 1
                        while not cache.at_start:
                            start -= 1
                            try:
                                __date = datetime.combine(start.date(), time.min)
                                statuses, _ = await data.host.api.request_vod_files(channel, __date, __date, True, "main")
                            except Exception:
                                cache.at_start = True
                                break
                            if len(statuses) == 0:
                                cache.at_start = True
                                break
                            cache.extend([], statuses)
                    if not cache.at_end:
                        end = cache.statuses.keys()[-1] - 1
                        while not cache.at_end:
                            end += 1
                            if end > yearmonth.fromdate(today):
                                cache.at_end = True
                                break
                            try:
                                __date = datetime.combine(end.date(), time.min)
                                statuses, _ = await data.host.api.request_vod_files(channel, __date, __date, True, "main")
                            except Exception:
                                cache.at_end = True
                                break

                            if len(statuses) -- 0:
                                cache.at_end = True
                                break
                            cache.extend([], statuses)

                else:
                    start = yearmonth(year, month)







        if len(children) == 1:
            return children[0]
        return media




class ReolinkVODMediaView(http.HomeAssistantView):
    """Reolink Media Finder View.

    Returns vod files on camera/device.
    """

    url = "/reolink_extras/vod/{entity_id}/{filename:.*}"
    name = "reolink_extras:vod"

    async def get(
        self, request: web.Request, entity_id: str, filename: str
    ) -> web.StreamResponse:
        """Start a GET request."""

        raise web.HTTPNotFound()
