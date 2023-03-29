""" Media Source Platform """

from datetime import date, datetime, timedelta
from typing import NamedTuple
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.loader import async_get_integration

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

from .helpers.search import async_get_search_cache

from .const import DOMAIN, LOGGER


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


class SimpleDate(NamedTuple):
    """Simple value only date"""

    year: int
    month: int | None
    day: int | None

    def __str__(self) -> str:
        if self.month is None:
            return str(self.year)
        if self.day is None:
            return f"{self.year}/{self.month}"
        return f"{self.year}/{self.month}/{self.day}"


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

    source = ReolinkMediaSource(hass, reolink.name)
    return source


def _calc_device_utcnow(time_settings: dict):
    time = time_settings.get("Time")
    if not time:
        return datetime.utcnow()
    now = datetime(
        time["year"], time["mon"], time["day"], time["hour"], time["min"], time["sec"]
    )
    offset = timedelta(seconds=time["timeZone"])
    return now + offset


class ReolinkMediaSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.name = name
        super().__init__(DOMAIN)
        self.hass = hass
        self._range_cache: dict[str, dict[int, list[date]]] = {}

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        return await super().async_resolve_media(item)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        try:
            source, device_id, channel, filename = async_parse_identifier(item)
        except Unresolvable as err:
            raise BrowseError(str(err)) from err

        return await self._build_item_response(source, device_id, channel, filename)

    async def _build_channel_files(
        self,
        children: list[BrowseMediaSource],
        source: str,
        device: ConfigEntry,
        data: ReolinkData,
        channel: int,
        depth: int,
    ):
        cache = async_get_search_cache(self.hass, device.entry_id, channel)
        if not cache.ready:
            await cache.async_update()
        while not cache.at_start:
            await
        # since we can only search by a limited date range, and the search
        # can provide hints to which months have videos, we will search
        # as far as we can and cache that as this would only change
        # daily
        # TODO : either ditch cache daily or re-evaulate the low range daily
        vod_range = self._range_cache.setdefault(device_id, {}).get(channel)
        if vod_range is None:
            vod_range = []
            self._range_cache[device_id][channel] = vod_range
            end = datetime.utcnow()
            end = datetime(end.year, end.month + 1, 1) - timedelta(days=1)
            while True:
                start = datetime(end.year, 1, 1)
                statuses, _ = await data.host.api.request_vod_files(
                    channel,
                    start,
                    end,
                    True,
                )
                end = start - timedelta(seconds=1)
                if statuses is None:
                    break
                for status in statuses:
                    for day, flag in enumerate(status["table"], start=1):
                        if flag == "1":
                            vod_range.append(date(status["year"], status["mon"], day))
            vod_range.sort(reverse=True)
        # TODO : implement some logic to be practical with a small number of files

        # Large/default Year then Month then Day then files

    async def _build_channels(  # pylint: disable=too-many-arguments
        self,
        children: list[BrowseMediaSource],
        source: str,
        device: ConfigEntry,
        data: ReolinkData,
        depth: int,
    ):
        for channel in data.host.api.channels:
            try:
                child = await self._build_item_response(
                    source, device.entry_id, channel, None, depth=depth + 1
                )
            except IncompatibleMediaSource:
                continue
            if child:
                children.append(child)

        if len(children) == 1:
            return children[0].children

    async def _build_devices(
        self, children: list[BrowseMediaSource], source: str, depth: int
    ):
        for device in self.hass.config_entries.async_entries(REOLINK_DOMAIN):
            if device.disabled_by:
                continue
            try:
                child = await self._build_item_response(
                    source, device, None, None, depth=depth + 1
                )
            except IncompatibleMediaSource:
                continue
            if child:
                children.append(child)

        if len(children) == 1:
            return children[0].children

    async def _build_item_response(
        self,
        source: str,
        device: str | ConfigEntry | None,
        channel: int | None,
        filename: str | SimpleDate | None,
        /,
        depth=0,
    ):
        title = self.name
        thumbnail = None
        path = source
        device = None
        data = None

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
            title = data.host.api.camera_name(channel) or f"Channel {channel}"
            path += f"/{channel}"

        if filename is not None:
            path += f"/{filename}"
            title = str(filename)

        media_class = MediaClass.DIRECTORY

        media = BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=media_class,
            media_content_type=MediaType.VIDEO,
            title=title,
            can_play=False,
            can_expand=not isinstance(filename, str),
            thumbnail=thumbnail,
        )

        if not media.can_expand and not media.can_play:
            raise IncompatibleMediaSource

        if not media.can_expand or depth > 0:
            return media

        children: list[BrowseMediaSource] = []
        media.children = children

        if channel is not None:
            pass
        elif data:
            media = (
                await self._build_channels(children, source, device, data, depth)
                or media
            )
        else:
            media = await self._build_devices(children, source, depth) or media

        return media


@callback
def async_parse_identifier(
    item: MediaSourceItem,
) -> tuple[str, str, int | None, str | None]:
    """Parse Identifier."""
    if not item.identifier or "/" not in item.identifier:
        return "devices", "", -1

    source, path = item.identifier.lstrip("/").split("/", 1)
    if source != "devices":
        raise Unresolvable("Unknown source.")

    if "/" in path:
        device_id, channel = path.split("/", 1)
        filename = None
        if "/" in channel:
            channel, filename = channel.split("/", 1)

        return source, device_id, int(channel), filename

    return source, path, None, None
