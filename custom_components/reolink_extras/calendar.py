""" Reolink Calendar for VOD searches """

from dataclasses import dataclass
import datetime as dtc
from typing import Callable
from homeassistant.config_entries import (
    ConfigEntry,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.entity import EntityDescription
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from homeassistant.components.reolink import ReolinkData
from homeassistant.components.reolink.entity import ReolinkChannelCoordinatorEntity

from homeassistant.util import dt

from reolink_aio.api import DUAL_LENS_MODELS
from reolink_aio.api import Host
from reolink_aio.typings import VOD_file, VOD_search_status

from .const import DOMAIN

from .helpers.reolink import async_forward_reolink_entries, async_get_reolink_data
from .helpers.cache import async_get_cache


@dataclass
class ReolinkCalendarEntityDescriptionMixin:
    """Mixin values for Reolink calendar entities."""


@dataclass
class ReolinkCalendarEntityDescription(
    EntityDescription, ReolinkCalendarEntityDescriptionMixin
):
    """A class that describes calendar entities."""

    supported: Callable[[Host, int | None], bool] = lambda host, ch: True


CALENDARS = (ReolinkCalendarEntityDescription("vod_calendar", name="Videos"),)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the calendar platform."""

    # local_data: dict[str, any] = hass.data[DOMAIN].setdefault(entry.entry_id, {})

    async def setup_entry(entry: ConfigEntry):
        reolink_data = async_get_reolink_data(hass, entry.entry_id)

        entities: list[ReolinkVODCalendar] = []
        for channel in reolink_data.host.api.stream_channels:
            entities.extend(
                [
                    ReolinkVODCalendar(reolink_data, channel, entity_description)
                    for entity_description in CALENDARS
                    if entity_description.supported(reolink_data.host.api, channel)
                ]
            )

        async_add_entities(entities)

    await async_forward_reolink_entries(hass, setup_entry)


class ReolinkVODCalendar(ReolinkChannelCoordinatorEntity, CalendarEntity):
    """Reolink VOD Calendar"""

    entity_description: ReolinkCalendarEntityDescription

    def __init__(
        self,
        reolink_data: ReolinkData,
        channel: int,
        entity_description: ReolinkCalendarEntityDescription,
    ) -> None:
        self.entity_description = entity_description
        ReolinkChannelCoordinatorEntity.__init__(self, reolink_data, channel)
        CalendarEntity.__init__(self)
        self._last_event: CalendarEvent | None = None

        if self._host.api.model in DUAL_LENS_MODELS:
            self._attr_name = f"{self.entity_description.name} lens {self._channel}"
        self._attr_unique_id = (
            f"{self._host.unique_id}_{self._channel}_{entity_description.key}"
        )

    @property
    def event(self) -> CalendarEvent | None:
        return self._last_event

    async def _cache_events(self, start_date: dtc.datetime, end_date: dtc.datetime):
        _tz = self._host.api.timezone()
        if _tz is None:
            _tz = (await self._host.api.async_get_time()).tzinfo


        api: Host = self._host.api
        (statuses, files) = await api.request_vod_files(
            self._channel,
            start_date.astimezone(_tz),
            end_date.astimezone(_tz),
            stream="main",
        )
        cache = async_get_cache(self.hass, self.coordinator.config_entry.entry_id, self._channel, True)
        cache.extend(files, statuses)
        # if results sets are too large we will not get full ranges
        # we should, however, get what ranges can give results
        # so we will use that to do multiple queries
        start = start_date.date()
        end = end_date.date()
        possible: set[dtc.date] = set(
            (
                status_date
                for status in statuses
                for status_date in status
                if start <= status_date < end
            )
        )
        found: set[dtc.date] = set((file.start_time.date() for file in files))
        missing = list(possible - found)
        while len(missing) > 0:
            missing.sort()
            start_date = dtc.datetime.combine(missing[0], dtc.time.min)
            end_date = dtc.datetime.combine(missing[-1], dtc.time.max)
            (statuses, files) = await api.request_vod_files(
                self._channel, start_date, end_date, stream="main"
            )
            cache.extend(statuses, files)
            found.update(set((file.start_time.date() for file in files)))
            missing = list(possible - found)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dtc.datetime,
        end_date: dtc.datetime,
    ) -> list[CalendarEvent]:
        # check cache
        now = self._host.api.time()
        cache = async_get_cache(self.hass, self.coordinator.config_entry.entry_id, self._channel, True)
        if now is None:
            now = await self._host.api.async_get_time()
        if (
            cache.at_start
            and (__first := next(iter(cache), None)) and __first > start_date
        ):
            start_date = dtc.datetime.combine(
                __first.date(), dtc.time.min, tzinfo=now.tzinfo
            )
        if end_date.date() >= now.date():
            end_date = dtc.datetime.combine(now.date(), dtc.time.max, tzinfo=now.tzinfo)

        first = next(iter(cache), None)
        last = next(reversed(cache), None)
        if not first or not last or first.date() == last.date():
            await self._cache_events(start_date, end_date)
        else:
            if start_date < first:
                await self._cache_events(start_date, first)
            if end_date > last:
                await self._cache_events(last, end_date)

        return [
            _file_to_event(file) for file in cache.slice(start_date, end_date)
        ]

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await self._async_handle_event(None)
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{self._host.webhook_id}_{self._channel}",
                self._async_handle_event,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{self._host.webhook_id}_all",
                self._async_handle_event,
            )
        )

    async def _async_handle_event(self, event):  # pylint: disable=unused-argument
        """Handle incoming event for motion detection"""
        now = self._host.api.time()
        if now is None:
            now = await self._host.api.async_get_time()
        cache = async_get_cache(self.hass, self.coordinator.config_entry.entry_id, self._channel, True)
        start = cache.statuses.keys[0] if cache.at_start else None
        # if we have a hard start we also want to see if any days dropped off of it (i.e. camera cleanup)
        low = (
            dtc.datetime.combine(start.date(), dtc.time.min)
            if start is not None and start < now
            else now
        )

        (statuses, _) = await self._host.api.request_vod_files(
            self._channel, low, now, True, "main"
        )
        # todo : trim any missing results if hard start exists
        cache.extend([], statuses)
        while (_f := filter(lambda s: len(s.days) > 0, statuses)) and not any(_f):
            if now.month > 1:
                now = now.replace(month=now.month - 1)
            else:
                now = now.replace(year=now.year - 1, month=1)
            (statuses, _) = await self._host.api.request_vod_files(
                self._channel, now, now, True, "main"
            )
            cache.extend([], statuses)

        for __ym in cache.statuses:
            if (status:=cache.statuses[__ym]) and len(status) > 0:
                first = status[0]
                break
        else:
            first = None

        for __ym in reversed(cache.statuses):
            if(status:=cache.statuses[__ym]) and len(status) > 0:
                last = status[-1]
                break
        else:
            last = None

        if last is not None:
            if first is not None and first != last:
                (statuses, files) = await self._host.api.request_vod_files(
                    self._channel,
                    dtc.datetime.combine(first, dtc.time.min),
                    dtc.datetime.combine(first, dtc.time.max),
                    stream="main",
                )
                cache.trim(first)
                cache.extend(statuses, files)

            (statuses, files) = await self._host.api.request_vod_files(
                self._channel,
                dtc.datetime.combine(last, dtc.time.min),
                dtc.datetime.combine(last, dtc.time.max),
                stream="main",
            )
            cache.trim(last)
            cache.extend(statuses, files)
            if __last := next(reversed(cache), None):
                self._last_event = _file_to_event(cache[__last])

        if event is not None:
            self.async_write_ha_state()


def _file_to_event(file: VOD_file, name: str = None):
    return CalendarEvent(
        dt.as_utc(file.start_time),
        dt.as_utc(file.end_time),
        f"{name or ''} {file.triggers} event",
    )
