""" Media Source Platform """

from datetime import date, datetime, time
from typing import Optional

from aiohttp import web
from aiohttp.abc import AbstractStreamWriter
from aiohttp.typedefs import LooseHeaders
from aiohttp.web_request import BaseRequest

from homeassistant.core import HomeAssistant, callback, async_get_hass
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

from reolink_aio.typings import VOD_file, VOD_trigger, VOD_download
from reolink_aio.exceptions import InvalidContentTypeError

from .helpers.reolink import async_get_reolink_data
from .helpers.cache import async_get_cache

from .const import DOMAIN, LOGGER

from .typings import yearmonth


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

    source = ReolinkMediaSource(hass, reolink.name)
    hass.http.register_view(ReolinkVODMediaView)
    # hass.http.register_view(ReolinkVODThumbnailMediaView)

    return source


class ReolinkMediaSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.name = name
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        device, channel, file = self.async_parse_identifier(item)
        if not (isinstance(device, str) and isinstance(channel, int) and isinstance(file, str)):
            raise Unresolvable("Invalid item.")

        _device = self.hass.config_entries.async_get_entry(device)
        if not _device or _device.disabled_by:
            raise IncompatibleMediaSource
        _channel = int(channel)

        return PlayMedia(ReolinkVODMediaView.url.replace(":.*", "").format(entry_id=_device.entry_id,channel=_channel,filename=file), "video/mp4")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        try:
            device, channel, file = self.async_parse_identifier(item)
        except Unresolvable as err:
            raise BrowseError(str(err)) from err

        return await self._browse_media(device, channel, file)

    @callback
    def async_parse_identifier(self, item: MediaSourceItem)->tuple[str|None,str|None,tuple[int, int|None, int|None]|str|None]:
        """Parse identifier."""
        if item.domain != DOMAIN:
            raise Unresolvable("Unknown domain.")

        if not item.identifier:
            return (None, None, None)

        ident = item.identifier
        marker, _, ident = ident.partition("/")
        if marker != "vod":
            raise Unresolvable("Invalid identifier")

        device, _, ident = ident.partition("/")
        if ident:
            channel, _, file_name = ident.partition("/")
            if not channel.isdigit():
                raise Unresolvable("invalid channel")
            channel = int(channel)
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
                file_name = None
        else:
            channel = None
            file_name = None

        return (device, channel, file_name)

    @callback
    def async_create_media(self, entity: ReolinkHostCoordinatorEntity, vod: VOD_file):
        """Get MediaSource for VOD """
        if not isinstance(entity, ReolinkHostCoordinatorEntity):
            raise Unresolvable("Invalid entity")
        if not isinstance(vod, VOD_file):
            raise Unresolvable("Invalid vod")

        #pylint: disable=protected-access
        channel = entity._channel if isinstance(entity, ReolinkChannelCoordinatorEntity) else 0

        media, *_ = self._create_media(entity.coordinator.config_entry, channel, vod)
        return media


    def _create_media(
        self,
        device: str | ConfigEntry | None,
        channel: int | str | None,
        file: tuple[int, int|None, int|None] | VOD_file | str | None,
    ):
        title = f"{self.name} Playback"
        thumbnail = None
        path = "vod"
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
                        title = ",".join(map(lambda t: t.name.title(), (trig for trig in VOD_trigger if trig in file.triggers)))
                        title = f"{file.start_time.time()} {file.end_time - file.start_time} {title}"
                        media_class = MediaClass.VIDEO
                        media_type = MediaType.VIDEO
                    elif isinstance(file, tuple):
                        title = "/".join(map(str,filter(lambda i: i is not None, file)))
                        path += f"/{title}"
                        file = None
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
            for _device in self.hass.config_entries.async_entries(REOLINK_DOMAIN):
                if _device.disabled_by is not None:
                    continue
                children.append(await self._browse_media(_device, None, None, depth=depth-1))
        else:
            data = async_get_reolink_data(self.hass, device.entry_id)
            if channel is None:
                for _channel in data.host.api.stream_channels:
                    children.append(await self._browse_media(device, _channel, None, depth=depth-1))
            elif file is not None and not isinstance(file, tuple):
                raise IncompatibleMediaSource
            else:
                cache = async_get_cache(self.hass, device.entry_id, channel, True)
                year, month, day = file if file is not None else (None, None, None)

                if year is None or month is None:
                    today = date.today()
                    if not cache.at_start:
                        start = next(iter(cache.statuses)) if len(cache.statuses) > 0 else yearmonth.fromdate(today) + 1
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
                        end = next(reversed(cache.statuses)) - 1
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

                            if len(statuses) == 0:
                                cache.at_end = True
                                break
                            cache.extend([], statuses)
                    if year is None:
                        for start in cache.statuses:
                            if year is not None and year >= start.year:
                                continue
                            year = start.year
                            children.append(await self._browse_media(device, channel, (year, None, None), depth=depth-1))
                    else:
                        for start in cache.statuses:
                            if year > start.year:
                                continue
                            if year < start.year:
                                break
                            children.append(await self._browse_media(device, channel, (year, start.month, None), depth=depth-1))
                else:
                    status = cache.statuses.get(yearmonth(year, month))
                    if status is None:
                        raise IncompatibleMediaSource
                    if day is None:
                        for day in status.days:
                            children.append(await self._browse_media(device, channel, (year, month, day), depth=depth-1))
                    else:
                        if day not in status.days:
                            raise IncompatibleMediaSource
                        start = date(year, month, day)
                        end = datetime.combine(start, time.max)
                        start = datetime.combine(start, time.min)
                        retry = True
                        while(retry):
                            retry = False
                            for _file in cache.slice(start, end):
                                children.append(await self._browse_media(device, channel, _file, depth=depth-1))
                            if len(children) == 0:
                                statuses, files = await data.host.api.request_vod_files(channel, start, end, False, "main")
                                cache.extend(statuses, files)
                                if len(files) > 0:
                                    retry = True

        # if len(children) == 1:
        #     return children[0]
        return media


class VODResponse(web.StreamResponse):

    def __init__(self, vod:VOD_download, status: int = 200, reason: str | None = None, headers: LooseHeaders | None = None) -> None:
        super().__init__(status=status, reason=reason, headers=headers)
        self._vod = vod

    async def _send_vod(self, request: web.BaseRequest):
        writer = await super().prepare(request)
        assert writer is not None

        transport = request.transport
        assert transport is not None

        vod = self._vod
        async for chunk in vod.stream.iter_any():
            if transport.is_closing():
                LOGGER.debug("Client closed stream, aborting download")
                break
            await writer.write(chunk)

        LOGGER.debug("Closing VOD")
        vod.close()
        await writer.drain()
        return writer

    async def prepare(self, request: BaseRequest):
        LOGGER.debug("Preparing VOD for download (%s)", self._vod.filename)
        vod = self._vod
        if vod.etag:
            self.etag = vod.etag.replace('"', '')
        self.content_length = vod.length

        writer = await self._send_vod(request)
        await writer.write_eof()
        return writer





class ReolinkVODMediaView(http.HomeAssistantView):
    """Reolink Media Finder View.

    Returns vod files on camera/device.
    """

    url = "/reolink_extras/vod/{entry_id}/{channel}/{filename:.*}"
    name = "reolink_extras:vod"

    async def get(
        self, request: web.Request, entry_id: str, channel: str, filename: str
    ) -> web.StreamResponse:
        """Start a GET request."""

        if not channel.isdigit():
            raise web.HTTPNotAcceptable()
        channel = int(channel)

        hass = async_get_hass()
        reolink_data = async_get_reolink_data(hass, entry_id)
        if reolink_data is None:
            raise web.HTTPNotFound()

        if channel not in reolink_data.host.api.stream_channels:
            raise web.HTTPNotFound()

        try:
            vod = await reolink_data.host.api.download_vod(filename)
        except InvalidContentTypeError as exc:
            raise web.HTTPServerError(reason="Cannot download multiple files at once.") from exc

        return VODResponse(vod)
